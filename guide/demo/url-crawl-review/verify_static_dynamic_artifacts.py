"""Compare static/dynamic URL artifacts against parsed Markdown.

This offline verifier reads saved HTML and Markdown artifacts. It is meant for
reviewing whether Markdown chunks are backed by raw/static HTML, rendered HTML,
or JavaScript-updated DOM sections.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

VALUE_PATTERN = re.compile(
    r"(?i)(?:\d[\d.,]*\s*(?:vnđ|vnd|km|kwh|kw|hp|nm|năm|tháng|%))|(?:vf\s*\d+|evo|feliz|klara|vento|theon)"
)
WORD_PATTERN = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)
BLOCK_TAGS = {"article", "section", "main", "div", "li", "tr", "table"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"script", "style", "noscript", "svg"}


@dataclass
class HtmlSection:
    stage: str
    section_id: str
    tag: str
    selector: str
    dom_path: str
    heading: str | None
    text: str
    values: list[str]
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class MarkdownSection:
    section_id: str
    heading: str
    text: str
    values: list[str]


@dataclass
class SectionMatch:
    markdown_section_id: str
    markdown_heading: str
    html_stage: str
    html_section_id: str
    html_selector: str
    html_heading: str | None
    overlap_score: float
    shared_values: list[str]
    markdown_only_values: list[str]
    html_only_values: list[str]


class _Node:
    def __init__(self, tag: str, attrs: dict[str, str], path: str, skip: bool) -> None:
        self.tag = tag
        self.attrs = attrs
        self.path = path
        self.skip = skip
        self.text_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.child_blocks = 0

    @property
    def text(self) -> str:
        return _clean_text(" ".join(self.text_parts))

    @property
    def heading(self) -> str | None:
        heading = _clean_text(" ".join(self.heading_parts))
        return heading or None


class _SectionParser(HTMLParser):
    def __init__(self, stage: str) -> None:
        super().__init__(convert_charrefs=True)
        self.stage = stage
        self.stack: list[_Node] = []
        self.tag_counts: dict[str, int] = {}
        self.heading_depth = 0
        self.sections: list[HtmlSection] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        attr_map = {key.lower(): value or "" for key, value in attrs}
        self.tag_counts[normalized] = self.tag_counts.get(normalized, 0) + 1
        parent_path = self.stack[-1].path if self.stack else ""
        path = f"{parent_path}/{normalized}[{self.tag_counts[normalized]}]"
        parent_skip = self.stack[-1].skip if self.stack else False
        self.stack.append(_Node(normalized, attr_map, path, normalized in SKIP_TAGS or parent_skip))
        if normalized in HEADING_TAGS:
            self.heading_depth += 1

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in HEADING_TAGS and self.heading_depth > 0:
            self.heading_depth -= 1
        if not self.stack:
            return
        node = self.stack.pop()
        if node.tag != normalized:
            self.stack.append(node)
            return
        text = node.text
        if self.stack and text:
            self.stack[-1].text_parts.append(text)
            if node.heading and not self.stack[-1].heading:
                self.stack[-1].heading_parts.append(node.heading)
            self.stack[-1].child_blocks += node.child_blocks
        if node.skip or node.tag not in BLOCK_TAGS or len(text) < 40:
            return
        if node.child_blocks >= 5 and node.tag not in {"table", "tr"}:
            return
        self.sections.append(
            HtmlSection(
                stage=self.stage,
                section_id=f"{self.stage}_{len(self.sections) + 1}",
                tag=node.tag,
                selector=_selector(node),
                dom_path=node.path,
                heading=node.heading,
                text=text[:4000],
                values=_extract_values(text),
                attributes=_selected_attrs(node.attrs),
            )
        )
        if self.stack:
            self.stack[-1].child_blocks += 1

    def handle_data(self, data: str) -> None:
        if not self.stack:
            return
        text = _clean_text(data)
        if not text:
            return
        self.stack[-1].text_parts.append(text)
        if self.heading_depth > 0:
            self.stack[-1].heading_parts.append(text)


def main() -> None:
    args = _parse_args()
    payload = build_review_payload(
        markdown_path=Path(args.markdown),
        html_paths=[_stage_path(value) for value in args.html],
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".json":
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    else:
        output_path.write_text(render_markdown_report(payload), encoding="utf-8")
    print(output_path)


def build_review_payload(
    *,
    markdown_path: Path,
    html_paths: list[tuple[str, Path]],
) -> dict[str, Any]:
    markdown = markdown_path.read_text(encoding="utf-8", errors="replace")
    markdown_sections = parse_markdown_sections(markdown)
    html_sections_by_stage: dict[str, list[HtmlSection]] = {}
    for stage, html_path in html_paths:
        if not html_path.exists():
            html_sections_by_stage[stage] = []
            continue
        html = html_path.read_text(encoding="utf-8", errors="replace")
        html_sections_by_stage[stage] = parse_html_sections(stage, html)
    changes = dynamic_value_changes(html_sections_by_stage)
    matches = [
        match
        for md_section in markdown_sections
        for match in best_matches(md_section, html_sections_by_stage)
    ]
    return {
        "schema_version": 1,
        "markdown_path": str(markdown_path),
        "html_paths": {stage: str(path) for stage, path in html_paths},
        "summary": _summary(markdown_sections, html_sections_by_stage, matches, changes),
        "markdown_sections": [asdict(section) for section in markdown_sections],
        "html_sections": {
            stage: [asdict(section) for section in sections]
            for stage, sections in html_sections_by_stage.items()
        },
        "matches": [asdict(match) for match in matches],
        "dynamic_value_changes": changes,
    }


def parse_html_sections(stage: str, html: str) -> list[HtmlSection]:
    parser = _SectionParser(stage)
    parser.feed(html)
    parser.close()
    return _dedupe_html_sections(parser.sections)


def parse_markdown_sections(markdown: str) -> list[MarkdownSection]:
    sections: list[MarkdownSection] = []
    heading = "Document"
    buffer: list[str] = []

    def flush() -> None:
        text = _clean_text(" ".join(buffer))
        if text:
            sections.append(
                MarkdownSection(
                    section_id=f"md_{len(sections) + 1}",
                    heading=heading,
                    text=text[:4000],
                    values=_extract_values(text),
                )
            )
        buffer.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            heading = stripped.lstrip("#").strip() or "Untitled"
            continue
        if stripped:
            buffer.append(stripped)
    flush()
    return sections


def best_matches(
    md_section: MarkdownSection,
    html_sections_by_stage: dict[str, list[HtmlSection]],
    *,
    per_stage: int = 2,
) -> list[SectionMatch]:
    output: list[SectionMatch] = []
    for stage, html_sections in html_sections_by_stage.items():
        scored = [
            (_overlap_score(md_section.text, html_section.text), html_section)
            for html_section in html_sections
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        for score, html_section in scored[:per_stage]:
            if score <= 0:
                continue
            md_values = set(md_section.values)
            html_values = set(html_section.values)
            output.append(
                SectionMatch(
                    markdown_section_id=md_section.section_id,
                    markdown_heading=md_section.heading,
                    html_stage=stage,
                    html_section_id=html_section.section_id,
                    html_selector=html_section.selector,
                    html_heading=html_section.heading,
                    overlap_score=round(score, 3),
                    shared_values=sorted(md_values & html_values),
                    markdown_only_values=sorted(md_values - html_values),
                    html_only_values=sorted(html_values - md_values),
                )
            )
    return output


def dynamic_value_changes(
    html_sections_by_stage: dict[str, list[HtmlSection]],
) -> list[dict[str, Any]]:
    stages = list(html_sections_by_stage)
    if len(stages) < 2:
        return []
    baseline_stage = stages[0]
    baseline_sections = html_sections_by_stage[baseline_stage]
    output: list[dict[str, Any]] = []
    for stage in stages[1:]:
        for section in html_sections_by_stage[stage]:
            baseline = _best_html_section(section, baseline_sections)
            if baseline is None:
                continue
            before = set(baseline.values)
            after = set(section.values)
            added = sorted(after - before)
            removed = sorted(before - after)
            if not added and not removed:
                continue
            output.append(
                {
                    "baseline_stage": baseline_stage,
                    "dynamic_stage": stage,
                    "baseline_selector": baseline.selector,
                    "dynamic_selector": section.selector,
                    "overlap_score": round(_overlap_score(baseline.text, section.text), 3),
                    "added_values": added,
                    "removed_values": removed,
                    "possible_replaced_section": section.heading or section.selector,
                }
            )
    return output


def render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# Static Dynamic Artifact Verification",
        "",
        f"- Markdown: `{payload.get('markdown_path')}`",
        f"- HTML stages: `{', '.join((payload.get('html_paths') or {}).keys())}`",
        f"- Markdown sections: `{summary.get('markdown_section_count')}`",
        f"- HTML sections: `{summary.get('html_section_count')}`",
        f"- Matched sections: `{summary.get('matched_section_count')}`",
        f"- Dynamic value changes: `{summary.get('dynamic_value_change_count')}`",
        "",
        "## Dynamic Value Changes",
        "",
    ]
    changes = payload.get("dynamic_value_changes") or []
    if not changes:
        lines.append("(none detected)")
    for change in changes[:40]:
        lines.extend(
            [
                f"- Section: `{change.get('possible_replaced_section')}`",
                f"  - static selector: `{change.get('baseline_selector')}`",
                f"  - dynamic selector: `{change.get('dynamic_selector')}`",
                f"  - added values: `{', '.join(change.get('added_values') or [])}`",
                f"  - removed values: `{', '.join(change.get('removed_values') or [])}`",
            ]
        )
    lines.extend(["", "## Markdown To HTML Evidence", ""])
    for match in (payload.get("matches") or [])[:80]:
        lines.append(
            f"- `{match.get('markdown_heading')}` -> `{match.get('html_stage')}` "
            f"`{match.get('html_selector')}` score `{match.get('overlap_score')}`"
        )
        if match.get("shared_values"):
            lines.append(f"  - shared values: `{', '.join(match['shared_values'])}`")
        if match.get("markdown_only_values"):
            lines.append(f"  - markdown only: `{', '.join(match['markdown_only_values'][:8])}`")
        if match.get("html_only_values"):
            lines.append(f"  - html only: `{', '.join(match['html_only_values'][:8])}`")
    return "\n".join(lines).rstrip() + "\n"


def _summary(
    markdown_sections: list[MarkdownSection],
    html_sections_by_stage: dict[str, list[HtmlSection]],
    matches: list[SectionMatch],
    changes: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "markdown_section_count": len(markdown_sections),
        "html_section_count": sum(len(sections) for sections in html_sections_by_stage.values()),
        "matched_section_count": len({match.markdown_section_id for match in matches}),
        "dynamic_value_change_count": len(changes),
    }


def _stage_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        path = Path(value)
        return path.stem, path
    stage, path = value.split("=", 1)
    return stage.strip() or Path(path).stem, Path(path.strip())


def _selector(node: _Node) -> str:
    node_id = node.attrs.get("id")
    classes = [value for value in node.attrs.get("class", "").split() if value]
    if node_id:
        return f"{node.tag}#{node_id}"
    if classes:
        return node.tag + "." + ".".join(classes[:4])
    data_keys = [key for key in node.attrs if key.startswith("data-")]
    if data_keys:
        return f"{node.tag}[{data_keys[0]}]"
    return node.path


def _selected_attrs(attrs: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in attrs.items()
        if key in {"id", "class", "role", "aria-label", "style"} or key.startswith("data-")
    }


def _extract_values(text: str) -> list[str]:
    values: list[str] = []
    for match in VALUE_PATTERN.findall(text):
        value = _clean_text(match)
        if value and value not in values:
            values.append(value)
    return values[:80]


def _overlap_score(left: str, right: str) -> float:
    left_words = set(_tokens(left))
    right_words = set(_tokens(right))
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / max(1, min(len(left_words), len(right_words)))


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in WORD_PATTERN.findall(text) if len(token) > 2]


def _best_html_section(section: HtmlSection, candidates: list[HtmlSection]) -> HtmlSection | None:
    if not candidates:
        return None
    scored = [(_overlap_score(section.text, candidate.text), candidate) for candidate in candidates]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored[0][0] >= 0.2 else None


def _dedupe_html_sections(sections: list[HtmlSection]) -> list[HtmlSection]:
    seen: set[str] = set()
    output: list[HtmlSection] = []
    for section in sections:
        key = section.text.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(section)
    return output


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Markdown sections against static and dynamic HTML artifacts.",
    )
    parser.add_argument(
        "--markdown",
        required=True,
        help="Path to parsed.md or another Markdown artifact.",
    )
    parser.add_argument(
        "--html",
        action="append",
        required=True,
        help=(
            "HTML artifact as stage=path, for example static=source.html or dynamic=rendered.html."
        ),
    )
    parser.add_argument(
        "--output",
        default="guide/demo/url-crawl-review/output/static_dynamic_verification.md",
        help="Output .md or .json report path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
