"""Source-neutral parent/child state-scope chunk construction."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from agentic_rag.ingestion.chunking.models import ChunkCandidate, StateScope
from agentic_rag.ingestion.chunking.splitters import short_hash

_COMPARISON_ROLES = {"comparison", "comparison_table"}
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$")


def build_scope_path(parent_scope_path: str | None, scope_type: str, stable_id: str) -> str:
    """Build a stable path from source identities, never labels or DOM positions."""

    clean_type = scope_type.strip()
    clean_id = stable_id.strip()
    if not clean_type or not clean_id:
        raise ValueError("scope_type and stable_id must be non-empty.")
    if "/" in clean_type or "/" in clean_id:
        raise ValueError("scope identity components must not contain '/'.")
    segment = f"{clean_type}:{clean_id}"
    return f"{parent_scope_path}/{segment}" if parent_scope_path else segment


def chunk_state_scopes(
    scopes: Sequence[StateScope],
    *,
    max_tokens: int = 512,
    mutually_exclusive_values: Sequence[Sequence[str]] = (),
) -> list[ChunkCandidate]:
    """Create independently citable chunks without crossing state boundaries."""

    # TODO [guide_2/vinfast_pipeline_todo §6 – Category-based scope mapping]:
    # Each StateScope produced by an interaction extractor represents one UI state
    # (e.g. a selected color or trim). Map the scope's `role` or `scope_type` to
    # a semantic `attribute_group` / `category` field that matches the guide_2 §6
    # chunking table: range_charging, safety, dimensions, interior, pricing.
    # Attach `attribute_group` into the emitted ChunkCandidate.metadata so that
    # downstream dedup blocking can group by category.
    # Reference: guide_2/vinfast_pipeline_todo (1).md §6, url/TODO_dedup.md

    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero.")
    by_state = {scope.state_id: scope for scope in scopes}
    if len(by_state) != len(scopes):
        raise ValueError("state_id values must be unique.")

    paths: dict[str, str] = {}
    visiting: set[str] = set()

    def resolve_path(scope: StateScope) -> str:
        if scope.state_id in paths:
            return paths[scope.state_id]
        if scope.state_id in visiting:
            raise ValueError("state scope hierarchy contains a cycle.")
        visiting.add(scope.state_id)
        parent_path = None
        if scope.parent_state_id is not None:
            parent = by_state.get(scope.parent_state_id)
            if parent is None:
                raise ValueError(f"unknown parent_state_id: {scope.parent_state_id}")
            parent_path = resolve_path(parent)
        path = build_scope_path(parent_path, scope.scope_type, scope.stable_id)
        paths[scope.state_id] = path
        visiting.remove(scope.state_id)
        return path

    for scope in scopes:
        resolve_path(scope)

    chunk_ids = {scope.state_id: f"scope_{short_hash(paths[scope.state_id])}" for scope in scopes}
    output: list[ChunkCandidate] = []
    for scope in scopes:
        context = _context_label(scope)
        text = scope.text.strip()
        _validate_exclusive_values(
            _self_contained_text(context, text), scope.role, mutually_exclusive_values
        )
        body_budget = max(1, max_tokens - len(context.split()))
        body_parts = _split_preserving_markdown_rows(text, max_tokens=body_budget)
        parts = [_self_contained_text(context, part) for part in body_parts]
        root = scope
        while root.parent_state_id is not None:
            root = by_state[root.parent_state_id]
        for part_index, part in enumerate(parts, start=1):
            metadata = dict(scope.metadata)
            metadata.update(
                {
                    "chunk_id": chunk_ids[scope.state_id],
                    "parent_chunk_id": (
                        chunk_ids[scope.parent_state_id]
                        if scope.parent_state_id is not None
                        else None
                    ),
                    "root_chunk_id": chunk_ids[root.state_id],
                    "scope_path": paths[scope.state_id],
                    "scope_type": scope.scope_type,
                    "state_id": scope.state_id,
                    "parent_state_id": scope.parent_state_id,
                    "sibling_index": scope.sibling_index,
                    "chunk_part_index": part_index,
                    "chunk_part_total": len(parts),
                }
            )
            output.append(
                ChunkCandidate(
                    section=scope.label,
                    text=part,
                    metadata=metadata,
                    chunk_token_count=len(part.split()),
                    semantic_unit="state_scope",
                )
            )
    # TODO [GraphRAG – chunk scope tree as property graph]:
    # The `scope_path`, `parent_chunk_id`, and `root_chunk_id` fields written
    # into each ChunkCandidate already encode a rooted tree structure (one node
    # per scope, one directed edge per parent-child relationship). When the graph
    # layer is introduced, convert this tree to graph edges during chunking:
    #   (Chunk {chunk_id})-[:CHILD_OF]->(Chunk {parent_chunk_id})
    # This allows GraphRAG retrieval to walk up to the root for context without
    # re-fetching the entire document. Store `scope_type` as the edge label.
    # Reference: GraphRAG integration plan (to be created)
    return output


def promote_common_facts(
    child_facts: Sequence[Mapping[str, str]], *, traversal_complete: bool
) -> dict[str, str]:
    """Return facts safe to place at the nearest common ancestor."""

    if not traversal_complete or not child_facts:
        return {}
    common_keys = set(child_facts[0]).intersection(*(set(facts) for facts in child_facts[1:]))
    promoted: dict[str, str] = {}
    for key in sorted(common_keys):
        values = [facts[key] for facts in child_facts]
        normalized = {" ".join(value.split()).casefold() for value in values}
        if len(normalized) == 1:
            promoted[key] = values[0]
    return promoted


def compatibility_row(
    exterior_label: str, interior_label: str, *, availability: str, price: str | None = None
) -> str:
    """Represent an exterior/interior relationship as one self-contained row."""

    # TODO [guide_2/TODO.md Priority 2 – Restore Structured Tables]:
    # Color option tables (exterior and interior) must be generated as stable
    # Markdown tables preserving color name, color code, and option pricing.
    # This helper builds one row; add tests that assert the expected VF 9 table
    # headers (Exterior, Interior, Availability, Price) and required rows exist
    # in the final parsed Markdown.
    # Reference: guide_2/TODO.md Priority 2

    cells = [exterior_label.strip(), interior_label.strip(), availability.strip()]
    if price is not None:
        cells.append(price.strip())
    return "| " + " | ".join(cells) + " |"


def _context_label(scope: StateScope) -> str:
    labels = [label.strip() for label in (*scope.parent_labels, scope.label) if label.strip()]
    return " > ".join(labels)


def _self_contained_text(context: str, body: str) -> str:
    if not context or body.casefold().startswith(context.casefold()):
        return body
    return f"{context}\n\n{body}"


def _validate_exclusive_values(
    text: str, role: str | None, groups: Sequence[Sequence[str]]
) -> None:
    if role in _COMPARISON_ROLES:
        return
    folded = text.casefold()
    for group in groups:
        matches = [value for value in group if value.strip() and value.casefold() in folded]
        if len(matches) > 1:
            raise ValueError(f"state scope mixes mutually exclusive values: {matches}")


def _split_preserving_markdown_rows(text: str, *, max_tokens: int) -> list[str]:
    lines = text.splitlines()
    units: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if "|" in line and index + 1 < len(lines) and _TABLE_SEPARATOR_RE.match(lines[index + 1]):
            header = f"{line}\n{lines[index + 1]}"
            index += 2
            while index < len(lines) and "|" in lines[index]:
                units.append(f"{header}\n{lines[index]}")
                index += 1
            continue
        if line.strip():
            units.append(line.strip())
        index += 1

    parts: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        words = unit.split()
        unit_parts = (
            [unit]
            if "\n" in unit and "|" in unit
            else [
                " ".join(words[start : start + max_tokens])
                for start in range(0, len(words), max_tokens)
            ]
            or [unit]
        )
        for unit_part in unit_parts:
            token_count = len(unit_part.split())
            if current and current_tokens + token_count > max_tokens:
                parts.append("\n".join(current))
                current = []
                current_tokens = 0
            current.append(unit_part)
            current_tokens += token_count
    if current:
        parts.append("\n".join(current))
    return parts or [text.strip()]
