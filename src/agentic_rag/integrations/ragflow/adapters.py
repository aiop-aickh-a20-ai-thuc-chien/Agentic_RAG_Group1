"""Adapters that normalize RAGFlow-like payloads into local contracts.

The integration layer is intentionally small: it accepts dictionaries from
RAGFlow, hand-written mocks, or export scripts and converts them into the
shared `Chunk`, `SearchResult`, `Citation`, and `Answer` models used by the
main pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha1
from typing import Any

from agentic_rag.core.contracts import Answer, Chunk, Citation, SearchResult

RAGFLOW_RETRIEVER = "ragflow"


def chunk_from_ragflow_payload(payload: Mapping[str, object]) -> Chunk:
    """Convert a RAGFlow document/chunk payload into a shared `Chunk`."""

    metadata = _metadata_from_payload(payload)
    text = _first_text(
        payload,
        ("text", "content", "content_with_weight", "chunk_text", "document_content"),
    )
    source = _first_text(
        payload,
        ("source", "document_name", "document_keyword", "docnm_kwd", "dataset_name", "url"),
    )

    if source:
        metadata.setdefault("source", source)
    else:
        metadata.setdefault("source", RAGFLOW_RETRIEVER)

    metadata.setdefault("source_type", RAGFLOW_RETRIEVER)
    metadata.setdefault("file_name", _optional_text(payload, "document_name"))
    metadata.setdefault("url", _optional_text(payload, "url"))
    metadata.setdefault("page", _optional_int(payload, "page") or _page_from_positions(payload))
    metadata.setdefault("section", _optional_text(payload, "section"))
    metadata.setdefault("document_id", _optional_text(payload, "document_id"))
    metadata.setdefault("dataset_id", _optional_text(payload, "dataset_id"))
    metadata.setdefault("similarity", _optional_float(payload, "similarity"))
    metadata.setdefault("vector_similarity", _optional_float(payload, "vector_similarity"))
    metadata.setdefault("term_similarity", _optional_float(payload, "term_similarity"))

    chunk_id = _first_text(payload, ("chunk_id", "id", "document_id"))
    if not chunk_id:
        chunk_id = _stable_chunk_id(text=text, source=str(metadata["source"]))

    return Chunk(chunk_id=chunk_id, text=text, metadata=metadata)


def search_result_from_ragflow_hit(
    payload: Mapping[str, object],
    *,
    rank: int | None = None,
    retriever: str = RAGFLOW_RETRIEVER,
) -> SearchResult:
    """Convert a RAGFlow retrieval hit into a shared `SearchResult`."""

    chunk_payload = payload.get("chunk")
    if isinstance(chunk_payload, Mapping):
        chunk = chunk_from_ragflow_payload(chunk_payload)
    else:
        chunk = chunk_from_ragflow_payload(payload)

    result_rank = rank if rank is not None else _optional_int(payload, "rank")
    if result_rank is None:
        result_rank = 1

    score = _optional_float(payload, "score") or _optional_float(payload, "similarity")
    if score is None:
        score = 1.0 / result_rank

    return SearchResult(chunk=chunk, score=score, rank=result_rank, retriever=retriever)


def citations_from_search_results(evidence_chunks: Iterable[SearchResult]) -> list[Citation]:
    """Build citations from evidence metadata without inventing new sources."""

    citations: list[Citation] = []
    seen_chunk_ids: set[str] = set()

    for result in evidence_chunks:
        chunk = result.chunk
        if chunk.chunk_id in seen_chunk_ids:
            continue

        source = _metadata_text(chunk.metadata, "source")
        if source is None:
            continue

        citations.append(
            Citation(
                source=source,
                chunk_id=chunk.chunk_id,
                page=_metadata_int(chunk.metadata, "page"),
                section=_metadata_text(chunk.metadata, "section"),
                url=_metadata_text(chunk.metadata, "url"),
            )
        )
        seen_chunk_ids.add(chunk.chunk_id)

    return citations


def answer_from_ragflow_payload(
    payload: Mapping[str, object],
    *,
    evidence_chunks: Iterable[SearchResult] = (),
    derive_citations: bool = True,
) -> Answer:
    """Convert a RAGFlow answer payload into a shared `Answer`."""

    answer_text = _first_text(payload, ("answer", "content", "text"))
    status_text = _optional_text(payload, "status")
    status = "not_found" if status_text == "not_found" or not answer_text else "answered"

    citations = _citations_from_payload(payload)
    if not citations and derive_citations and status == "answered":
        citations = citations_from_search_results(evidence_chunks)

    if status == "not_found":
        citations = []

    return Answer(answer=answer_text, status=status, citations=citations)


def _metadata_from_payload(payload: Mapping[str, object]) -> dict[str, object]:
    raw_metadata = payload.get("metadata")
    if not isinstance(raw_metadata, Mapping):
        return {}

    return {str(key): value for key, value in raw_metadata.items()}


def _citations_from_payload(payload: Mapping[str, object]) -> list[Citation]:
    raw_citations = payload.get("citations")
    if not isinstance(raw_citations, list):
        return []

    citations: list[Citation] = []
    for raw_citation in raw_citations:
        if not isinstance(raw_citation, Mapping):
            continue

        source = _first_text(raw_citation, ("source", "document_name", "url"))
        chunk_id = _first_text(raw_citation, ("chunk_id", "id", "document_id"))
        if not source or not chunk_id:
            continue

        citations.append(
            Citation(
                source=source,
                chunk_id=chunk_id,
                page=_optional_int(raw_citation, "page"),
                section=_optional_text(raw_citation, "section"),
                url=_optional_text(raw_citation, "url"),
            )
        )

    return citations


def _first_text(payload: Mapping[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _optional_text(payload, key)
        if value:
            return value
    return ""


def _optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _optional_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _optional_float(payload: Mapping[str, object], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _page_from_positions(payload: Mapping[str, object]) -> int | None:
    positions = payload.get("positions")
    if not isinstance(positions, list) or not positions:
        return None

    first_position = positions[0]
    if isinstance(first_position, list) and first_position:
        value = first_position[0]
    else:
        value = first_position

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _metadata_text(metadata: Any, key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _metadata_int(metadata: Any, key: str) -> int | None:
    value = metadata.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _stable_chunk_id(*, text: str, source: str) -> str:
    digest = sha1(f"{source}\n{text}".encode()).hexdigest()[:12]
    return f"ragflow_{digest}"
