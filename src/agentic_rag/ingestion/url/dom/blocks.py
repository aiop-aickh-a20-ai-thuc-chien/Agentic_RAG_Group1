"""DOM-aware semantic block detection for URL ingestion."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.ingestion.url.chunking import normalize_space, short_hash

_SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside"}
_BLOCK_TAGS = {"article", "section", "div", "li", "details", "table", "tr"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("vehicle", "vehicle_card"),
    ("car", "vehicle_card"),
    ("product", "product_card"),
    ("card", "product_card"),
    ("faq", "faq_item"),
    ("question", "faq_item"),
    ("policy", "policy_section"),
    ("table", "comparison_table"),
    ("course", "course_card"),
    ("job", "job_card"),
)


class DomBlock(BaseModel):
    """A semantic DOM block candidate before URL chunking."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    block_id: str
    block_type: str
    tag: str
    text: str
    dom_path: str
    heading: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class _Node:
    def __init__(
        self,
        *,
        tag: str,
        attrs: dict[str, str],
        path: str,
        skip: bool,
    ) -> None:
        self.tag = tag
        self.attrs = attrs
        self.path = path
        self.skip = skip
        self.text_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.child_blocks: int = 0

    @property
    def text(self) -> str:
        return normalize_space(" ".join(self.text_parts))

    @property
    def heading(self) -> str | None:
        heading = normalize_space(" ".join(self.heading_parts))
        return heading or None


class _SemanticBlockParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[_Node] = []
        self._tag_counts: dict[str, int] = {}
        self._heading_depth = 0
        self.blocks: list[DomBlock] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attr_map = {name.lower(): value or "" for name, value in attrs}
        self._tag_counts[normalized_tag] = self._tag_counts.get(normalized_tag, 0) + 1
        parent_path = self._stack[-1].path if self._stack else ""
        path = f"{parent_path}/{normalized_tag}[{self._tag_counts[normalized_tag]}]"
        skip = normalized_tag in _SKIP_TAGS or (self._stack[-1].skip if self._stack else False)
        self._stack.append(_Node(tag=normalized_tag, attrs=attr_map, path=path, skip=skip))
        if normalized_tag in _HEADING_TAGS:
            self._heading_depth += 1

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _HEADING_TAGS and self._heading_depth > 0:
            self._heading_depth -= 1
        if not self._stack:
            return
        node = self._stack.pop()
        if node.tag != normalized_tag:
            self._stack.append(node)
            return
        text = node.text
        if self._stack and text:
            self._stack[-1].text_parts.append(text)
            if node.heading and not self._stack[-1].heading:
                self._stack[-1].heading_parts.append(node.heading)
            self._stack[-1].child_blocks += node.child_blocks
        if node.skip or not text:
            return
        block_type = _infer_block_type(node)
        if block_type is None:
            return
        if node.child_blocks >= 4 and block_type not in {"comparison_table", "faq_item"}:
            return
        self.blocks.append(
            DomBlock(
                block_id=f"dom_{short_hash(node.path + '|' + text)}",
                block_type=block_type,
                tag=node.tag,
                text=text,
                dom_path=node.path,
                heading=node.heading,
                attributes=_selected_attributes(node.attrs),
            )
        )
        if self._stack:
            self._stack[-1].child_blocks += 1

    def handle_data(self, data: str) -> None:
        if not self._stack:
            return
        text = normalize_space(data)
        if not text:
            return
        self._stack[-1].text_parts.append(text)
        if self._heading_depth > 0:
            self._stack[-1].heading_parts.append(text)


def detect_semantic_blocks(html: str) -> list[DomBlock]:
    """Return semantic DOM block candidates from HTML."""

    parser = _SemanticBlockParser()
    parser.feed(html)
    parser.close()
    return _deduplicate_blocks(parser.blocks)


def _infer_block_type(node: _Node) -> str | None:
    if node.tag == "table":
        return "comparison_table"
    if node.tag == "tr":
        return "comparison_row"
    if node.tag not in _BLOCK_TAGS:
        return None
    hint_text = " ".join(
        value
        for key, value in node.attrs.items()
        if key in {"class", "id", "role", "aria-label", "itemtype"}
    ).lower()
    for marker, block_type in _TYPE_HINTS:
        if marker in hint_text:
            return block_type
    text = node.text.lower()
    if "?" in text and len(text) < 1200:
        return "faq_item"
    if any(marker in text for marker in ("vnd", "vnđ", "₫", "price", "gia", "giá")):
        return "product_card"
    return None


def _selected_attributes(attrs: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in attrs.items()
        if key in {"class", "id", "role", "aria-label", "itemtype"} and value
    }


def _deduplicate_blocks(blocks: list[DomBlock]) -> list[DomBlock]:
    seen: set[tuple[str, str]] = set()
    output: list[DomBlock] = []
    for block in blocks:
        key = (block.block_type, block.text.casefold())
        if key in seen:
            continue
        seen.add(key)
        output.append(block)
    return output


def dom_blocks_summary(blocks: list[DomBlock]) -> dict[str, Any]:
    """Return compact block diagnostics for chunk metadata."""

    counts: dict[str, int] = {}
    for block in blocks:
        counts[block.block_type] = counts.get(block.block_type, 0) + 1
    return {
        "semantic_block_count": len(blocks),
        "semantic_block_types": counts,
    }


__all__ = ["DomBlock", "detect_semantic_blocks", "dom_blocks_summary"]
