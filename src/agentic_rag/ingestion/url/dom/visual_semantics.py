"""Visual HTML/CSS semantics for URL ingestion."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.ingestion.url.chunking import normalize_space, short_hash

VisualSemanticKind = Literal["old_price", "hidden_text", "generated_label"]
VisualEvidenceSource = Literal["raw_html", "rendered_dom", "computed_style"]

_PRICE_RE = re.compile(
    r"\b\d[\d.,]*(?:\s*(?:VND|VN\u0110|\u0111|dong|USD|US\$|\$)|\s*\u20ab)\b",
    re.IGNORECASE,
)
_LINE_THROUGH_RE = re.compile(r"text-decoration(?:-line)?\s*:[^;]*line-through", re.I)
_HIDDEN_STYLE_RE = re.compile(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", re.I)
_PSEUDO_CONTENT_RE = re.compile(
    r"(?P<selector>[#.][\w-]+)::(?P<pseudo>before|after)\s*\{[^{}]*?"
    r"content\s*:\s*(?P<quote>['\"])(?P<content>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)


class VisualSemanticFact(BaseModel):
    """One source-backed visual meaning fact from HTML/CSS.

    # TODO [GraphRAG – VisualSemanticFact as graph evidence node]:
    # Each VisualSemanticFact (especially `old_price` and `generated_label`) is
    # a verifiable claim that can be stored as a VisualEvidence node in the graph:
    #   (VisualEvidence {kind, text, fact_id})-[:OBSERVED_IN]->(DomBlock)
    # The `dom_path` field is the natural join key to the DomBlock node whose
    # `dom_path` matches. When the graph layer is introduced, link these nodes
    # during the same ingestion pass as DomBlock node creation to avoid a
    # second DOM parse.
    # Reference: GraphRAG integration plan (to be created)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    kind: VisualSemanticKind
    text: str
    tag: str | None = None
    dom_path: str | None = None
    selector: str | None = None
    evidence_source: VisualEvidenceSource
    css_evidence: list[str] = Field(default_factory=list)
    trusted_for_retrieval: bool = True


class VisualSemanticsResult(BaseModel):
    """Visual semantic facts extracted from one HTML snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    facts: list[VisualSemanticFact] = Field(default_factory=list)

    @property
    def old_prices(self) -> list[VisualSemanticFact]:
        """Return old-price facts in source order."""

        return [fact for fact in self.facts if fact.kind == "old_price"]


class _Node:
    def __init__(
        self,
        *,
        tag: str,
        attrs: dict[str, str],
        path: str,
        hidden: bool,
        strike: bool,
    ) -> None:
        self.tag = tag
        self.attrs = attrs
        self.path = path
        self.hidden = hidden
        self.strike = strike
        self.text_parts: list[str] = []

    @property
    def text(self) -> str:
        return normalize_space(" ".join(self.text_parts))


class _VisualSemanticsParser(HTMLParser):
    def __init__(self, *, evidence_source: VisualEvidenceSource) -> None:
        super().__init__(convert_charrefs=True)
        self.evidence_source = evidence_source
        self._stack: list[_Node] = []
        self._tag_counts: dict[str, int] = {}
        self._capture_style = False
        self._style_parts: list[str] = []
        self.facts: list[VisualSemanticFact] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "style":
            self._capture_style = True
            self._style_parts = []
            return

        attr_map = {name.lower(): value or "" for name, value in attrs}
        self._tag_counts[normalized_tag] = self._tag_counts.get(normalized_tag, 0) + 1
        parent_path = self._stack[-1].path if self._stack else ""
        path = f"{parent_path}/{normalized_tag}[{self._tag_counts[normalized_tag]}]"
        parent_hidden = self._stack[-1].hidden if self._stack else False
        parent_strike = self._stack[-1].strike if self._stack else False
        node = _Node(
            tag=normalized_tag,
            attrs=attr_map,
            path=path,
            hidden=parent_hidden or _is_hidden(attr_map),
            strike=parent_strike or _is_strike_tag(normalized_tag) or _has_line_through(attr_map),
        )
        self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "style":
            self._capture_style = False
            self._add_generated_label_facts("".join(self._style_parts))
            self._style_parts = []
            return
        if not self._stack:
            return
        node = self._stack.pop()
        if node.tag != normalized_tag:
            self._stack.append(node)
            return
        text = node.text
        if self._stack and text:
            self._stack[-1].text_parts.append(text)
        self._add_node_facts(node, text)

    def handle_data(self, data: str) -> None:
        if self._capture_style:
            self._style_parts.append(data)
            return
        text = normalize_space(data)
        if text and self._stack:
            self._stack[-1].text_parts.append(text)

    def close(self) -> None:
        super().close()
        if self._capture_style and self._style_parts:
            self._add_generated_label_facts("".join(self._style_parts))
        while self._stack:
            node = self._stack.pop()
            self._add_node_facts(node, node.text)

    def _add_node_facts(self, node: _Node, text: str) -> None:
        if not text:
            return
        if node.strike and _PRICE_RE.search(text):
            self._append_fact(
                kind="old_price",
                text=_first_price(text) or text,
                tag=node.tag,
                dom_path=node.path,
                css_evidence=_strike_evidence(node),
            )
        elif node.hidden and _interesting_hidden_text(text):
            self._append_fact(
                kind="hidden_text",
                text=text,
                tag=node.tag,
                dom_path=node.path,
                css_evidence=_hidden_evidence(node.attrs),
                trusted_for_retrieval=False,
            )

    def _add_generated_label_facts(self, css_text: str) -> None:
        for match in _PSEUDO_CONTENT_RE.finditer(css_text):
            content = normalize_space(match.group("content"))
            if not content:
                continue
            selector = f"{match.group('selector')}::{match.group('pseudo').lower()}"
            self._append_fact(
                kind="generated_label",
                text=content,
                selector=selector,
                evidence_source="computed_style",
                css_evidence=[f"content:{content}"],
            )

    def _append_fact(
        self,
        *,
        kind: VisualSemanticKind,
        text: str,
        tag: str | None = None,
        dom_path: str | None = None,
        selector: str | None = None,
        evidence_source: VisualEvidenceSource | None = None,
        css_evidence: list[str] | None = None,
        trusted_for_retrieval: bool = True,
    ) -> None:
        cleaned_text = normalize_space(text)
        if not cleaned_text:
            return
        key = "|".join((kind, cleaned_text.casefold(), dom_path or "", selector or ""))
        fact = VisualSemanticFact(
            fact_id=f"visual_{short_hash(key)}",
            kind=kind,
            text=cleaned_text,
            tag=tag,
            dom_path=dom_path,
            selector=selector,
            evidence_source=evidence_source or self.evidence_source,
            css_evidence=css_evidence or [],
            trusted_for_retrieval=trusted_for_retrieval,
        )
        if fact not in self.facts:
            self.facts.append(fact)


def extract_visual_semantics(
    html: str,
    *,
    evidence_source: VisualEvidenceSource = "raw_html",
) -> VisualSemanticsResult:
    """Extract visual semantics that plain text extraction can lose."""

    parser = _VisualSemanticsParser(evidence_source=evidence_source)
    parser.feed(html)
    parser.close()
    return VisualSemanticsResult(facts=_dedupe_facts(parser.facts))


def append_visual_semantics_markdown(
    markdown: str,
    semantics: VisualSemanticsResult,
    *,
    title: str | None = None,
) -> str:
    """Append source-backed visual facts that are missing from Markdown."""

    updated_markdown = markdown
    missing_old_prices: list[VisualSemanticFact] = []
    for fact in semantics.old_prices:
        if f"~~{fact.text}~~" in updated_markdown:
            continue
        if fact.text in updated_markdown:
            updated_markdown = updated_markdown.replace(fact.text, f"~~{fact.text}~~", 1)
            continue
        missing_old_prices.append(fact)
    if not missing_old_prices:
        return updated_markdown
    subject = normalize_space(title or "Page")
    lines = ["## Visual Pricing Evidence", ""]
    for fact in missing_old_prices:
        lines.append(f"- {subject} original price from strike-through text: ~~{fact.text}~~.")
    supplement = "\n".join(lines)
    base = updated_markdown.strip()
    return f"{base}\n\n{supplement}" if base else supplement


def _dedupe_facts(facts: list[VisualSemanticFact]) -> list[VisualSemanticFact]:
    seen: set[tuple[str, str, str | None, str | None]] = set()
    output: list[VisualSemanticFact] = []
    for fact in facts:
        key = (fact.kind, fact.text.casefold(), fact.dom_path, fact.selector)
        if key in seen:
            continue
        seen.add(key)
        output.append(fact)
    return output


def _is_hidden(attrs: dict[str, str]) -> bool:
    style = attrs.get("style", "")
    aria_hidden = attrs.get("aria-hidden", "").lower()
    return "hidden" in attrs or aria_hidden == "true" or bool(_HIDDEN_STYLE_RE.search(style))


def _is_strike_tag(tag: str) -> bool:
    return tag in {"s", "del", "strike"}


def _has_line_through(attrs: dict[str, str]) -> bool:
    return bool(_LINE_THROUGH_RE.search(attrs.get("style", "")))


def _strike_evidence(node: _Node) -> list[str]:
    evidence: list[str] = []
    if _is_strike_tag(node.tag):
        evidence.append(f"tag:{node.tag}")
    if _has_line_through(node.attrs):
        evidence.append("text-decoration:line-through")
    return evidence


def _hidden_evidence(attrs: dict[str, str]) -> list[str]:
    evidence: list[str] = []
    if "hidden" in attrs:
        evidence.append("hidden")
    if attrs.get("aria-hidden", "").lower() == "true":
        evidence.append("aria-hidden:true")
    style = attrs.get("style", "")
    if "display" in style.lower() or "visibility" in style.lower():
        evidence.append(style)
    return evidence


def _first_price(text: str) -> str | None:
    match = _PRICE_RE.search(text)
    return normalize_space(match.group(0)) if match else None


def _interesting_hidden_text(text: str) -> bool:
    return bool(_PRICE_RE.search(text)) or len(text.split()) >= 4


__all__ = [
    "VisualSemanticFact",
    "VisualSemanticKind",
    "VisualSemanticsResult",
    "append_visual_semantics_markdown",
    "extract_visual_semantics",
]
