"""DOM-aware semantic block detection for URL ingestion."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.ingestion.url.chunking import (
    normalize_for_dedupe_hash,
    normalize_space,
    short_hash,
)

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
# TODO [GraphRAG – DOM block type → graph node label vocabulary]:
# Each value in _TYPE_HINTS is a candidate graph node label in a knowledge graph
# (e.g. VehicleCard, FaqItem, ComparisonTable). Before introducing the graph
# layer, lock this vocabulary here so node labels are stable across ingestion runs.
# Add an `is_graphrag_node: bool` flag to DomBlock if only certain types should
# be promoted to graph nodes (e.g. vehicle_card, comparison_table), keeping
# finer-grained types as properties rather than independent nodes.
# Reference: GraphRAG integration plan (to be created)


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


_VOID_TAGS = {"img", "br", "hr", "input", "meta", "link", "area", "base", "col", "embed", "param", "source", "track", "wbr"}


class _Node:
    def __init__(
        self,
        *,
        tag: str,
        attrs: dict[str, str],
        path: str,
        skip: bool,
        is_color_context: bool = False,
    ) -> None:
        self.tag = tag
        self.attrs = attrs
        self.path = path
        self.skip = skip
        self.is_color_context = is_color_context
        self.text_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.child_blocks: int = 0
        # TODO [GraphRAG – DOM parent-child edge capture]:
        # Track the `block_id` of the nearest ancestor block node so that
        # `_SemanticBlockParser` can emit (parent_block_id, child_block_id) edges
        # alongside the DomBlock list. These edges form the structural backbone
        # of the DOM sub-graph and allow GraphRAG traversal to respect containment
        # (e.g. a VehicleCard is CONTAINS a ComparisonTable row).
        # Add `parent_block_id: str | None = None` to DomBlock when the graph
        # layer is introduced, populated from the nearest ancestor in the stack.

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
        if normalized_tag in _VOID_TAGS:
            if self._stack:
                if normalized_tag == "img":
                    alt = attr_map.get("alt")
                    if alt:
                        self._stack[-1].text_parts.append(normalize_space(alt))
                    src = attr_map.get("src")
                    if src and not self._stack[-1].attrs.get("_img_src"):
                        self._stack[-1].attrs["_img_src"] = src
                else:
                    title = attr_map.get("title")
                    if title:
                        self._stack[-1].text_parts.append(normalize_space(title))
            return

        self._tag_counts[normalized_tag] = self._tag_counts.get(normalized_tag, 0) + 1
        parent_node = self._stack[-1] if self._stack else None
        parent_path = parent_node.path if parent_node else ""
        path = f"{parent_path}/{normalized_tag}[{self._tag_counts[normalized_tag]}]"
        skip = normalized_tag in _SKIP_TAGS or (parent_node.skip if parent_node else False)

        parent_is_color = parent_node.is_color_context if parent_node else False
        hint_text = " ".join(
            value
            for key, value in attr_map.items()
            if key in {"class", "id", "role", "aria-label", "itemtype"}
        ).lower()
        current_is_color = parent_is_color or any(marker in hint_text for marker in ("color", "colour", "mau"))
        if attr_map.get("data-name") or attr_map.get("data-color") or attr_map.get("data-item") or attr_map.get("data-pid"):
            current_is_color = True

        self._stack.append(_Node(tag=normalized_tag, attrs=attr_map, path=path, skip=skip, is_color_context=current_is_color))
        if normalized_tag in _HEADING_TAGS:
            self._heading_depth += 1

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _VOID_TAGS:
            return
        if normalized_tag in _HEADING_TAGS and self._heading_depth > 0:
            self._heading_depth -= 1
        if not self._stack:
            return
        node = self._stack.pop()
        if node.tag != normalized_tag:
            self._stack.append(node)
            return

        # Determine custom color text if this node represents a color option/item
        color_name = node.attrs.get("data-name") or node.attrs.get("data-color")
        color_code = node.attrs.get("data-item")
        if not color_code:
            pid = node.attrs.get("data-pid")
            if pid:
                parts = pid.split("-")
                if len(parts) > 1 and len(parts[-1]) <= 6:
                    color_code = parts[-1]

        if node.is_color_context and (color_name or color_code):
            if color_name:
                if color_code:
                    text = f"Màu ngoại thất: {color_name} ({color_code})"
                else:
                    text = f"Màu ngoại thất: {color_name}"
            elif color_code:
                img_src = node.attrs.get("_img_src")
                if img_src:
                    text = f"Màu ngoại thất: {color_code} ({img_src})"
                else:
                    text = f"Màu ngoại thất: {color_code}"
            else:
                base_text = node.text
                if base_text and not any(base_text.casefold().startswith(p) for p in ("màu", "color", "colour")):
                    text = f"Màu ngoại thất: {base_text}"
                else:
                    text = base_text
        else:
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
        if node.child_blocks >= 4 and block_type not in {"comparison_table", "faq_item", "product_card", "vehicle_card"}:
            return

        # Tag product cards or vehicle cards with model name if heading is missing
        heading = node.heading
        if block_type in {"product_card", "vehicle_card"} and not heading:
            from agentic_rag.ingestion.url.entities.extractor import _MODEL_RE
            model_match = _MODEL_RE.search(text)
            if model_match:
                heading = model_match.group(0)

        self.blocks.append(
            DomBlock(
                block_id=f"dom_{short_hash(node.path + '|' + text)}",
                block_type=block_type,
                tag=node.tag,
                text=text,
                dom_path=node.path,
                heading=heading,
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

    # Check for color-related context and attributes
    color_name = node.attrs.get("data-name") or node.attrs.get("data-color")
    color_code = node.attrs.get("data-item")
    if not color_code:
        pid = node.attrs.get("data-pid")
        if pid:
            parts = pid.split("-")
            if len(parts) > 1 and len(parts[-1]) <= 6:
                color_code = parts[-1]

    hint_text = " ".join(
        value
        for key, value in node.attrs.items()
        if key in {"class", "id", "role", "aria-label", "itemtype"}
    ).lower()

    if (node.is_color_context and (color_name or color_code)) or any(marker in hint_text for marker in ("color", "colour", "mau")):
        return "color_option"

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
        if (key in {"class", "id", "role", "aria-label", "itemtype"} or key.startswith("data-"))
        and value
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
    # TODO [GraphRAG – block summary as graph subgraph descriptor]:
    # Extend this function to also return an adjacency list or edge list
    # (block_id → [child_block_ids]) once parent_block_id is tracked on DomBlock.
    # This adjacency list is the minimal representation needed to build the DOM
    # sub-graph for a single URL ingestion without requiring a full graph DB at
    # ingestion time; the graph DB import can happen as a separate offline step.


def append_structure_aware_markdown(
    markdown: str,
    blocks: list[DomBlock],
    *,
    title: str | None = None,
    max_blocks: int = 20,
) -> str:
    """Append generated Markdown sections for useful DOM semantic blocks.

    Text extractors often flatten product cards and tables into anonymous prose.
    This keeps the original Markdown as the source of truth while adding a
    small, deduped, clearly generated section that gives the chunker stable
    headings for product cards, FAQs, and table-like blocks.
    """

    usable_blocks = [
        block
        for block in blocks
        if block.block_type
        in {
            "comparison_table",
            "comparison_row",
            "faq_item",
            "product_card",
            "vehicle_card",
            "color_option",
        }
        and _is_structural_block_useful(block)
    ]
    if not usable_blocks:
        return markdown

    existing = normalize_for_dedupe_hash(markdown)
    emitted: set[str] = set()
    additions: list[str] = []
    for block in usable_blocks:
        text = normalize_space(block.text)
        dedupe_key = normalize_for_dedupe_hash(text)
        if not dedupe_key or dedupe_key in emitted:
            continue
        if _is_block_already_structured(existing, dedupe_key, block):
            continue
        emitted.add(dedupe_key)
        additions.extend(_format_structure_block(block, title=title))
        if len(emitted) >= max_blocks:
            break

    if not additions:
        return markdown
    base = markdown.strip()
    supplement = "\n".join(["## Structured DOM Content", "", *additions]).strip()
    return f"{base}\n\n{supplement}" if base else supplement


def _is_structural_block_useful(block: DomBlock) -> bool:
    text = normalize_space(block.text)
    if block.block_type == "color_option":
        return len(text) >= 10
    if len(text) < 20:
        return False
    if block.block_type in {"comparison_table", "comparison_row"}:
        return True
    if block.heading:
        return True
    return any(char.isdigit() for char in text)


def _is_block_already_structured(
    existing_dedupe_text: str,
    block_dedupe_text: str,
    block: DomBlock,
) -> bool:
    if block.block_type in {"comparison_table", "comparison_row"}:
        return False
    return block_dedupe_text in existing_dedupe_text


def _format_structure_block(block: DomBlock, *, title: str | None) -> list[str]:
    heading = _structure_heading(block, title=title)
    text = normalize_space(block.text)
    lines = [
        f"### {heading}",
        "",
        f"- structure_block_type: {block.block_type}",
        f"- structure_block_id: {block.block_id}",
        f"- structure_dedupe_hash: {short_hash(normalize_for_dedupe_hash(text))}",
        f"- content: {text}",
        "",
    ]
    if block.attributes:
        attributes = " ".join(f"{key}={value!r}" for key, value in sorted(block.attributes.items()))
        lines.insert(5, f"- structure_attributes: {attributes}")
    return lines


def _structure_heading(block: DomBlock, *, title: str | None) -> str:
    heading = normalize_space(block.heading or "")
    if heading:
        return heading
    if block.block_type in {"comparison_table", "comparison_row"}:
        return "Structured Table"
    if title:
        return f"{title} {block.block_type.replace('_', ' ')}"
    return block.block_type.replace("_", " ").title()


__all__ = [
    "DomBlock",
    "append_structure_aware_markdown",
    "detect_semantic_blocks",
    "dom_blocks_summary",
]
