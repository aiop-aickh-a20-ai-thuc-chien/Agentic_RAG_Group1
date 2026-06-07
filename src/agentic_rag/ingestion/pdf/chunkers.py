"""Markdown chunker strategies for PDF ingestion."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from agentic_rag.ingestion.chunking import (
    ChunkingInput,
    MarkdownChunk,
    chunk_markdown,
)
from agentic_rag.ingestion.chunking import (
    DeterministicMarkdownChunker as SharedDeterministicMarkdownChunker,
)

DETERMINISTIC_MARKDOWN_CHUNKER = "deterministic"
DOCLING_PAGE_AWARE_CHUNKER = "docling-page-aware"
DOCLING_HYBRID_CHUNKER = "docling-hybrid"
DEFAULT_MARKDOWN_CHUNKER = DETERMINISTIC_MARKDOWN_CHUNKER


class MarkdownChunker(Protocol):
    """Strategy interface for converting parser Markdown into chunk candidates."""

    chunker_name: str
    requires_native_document: bool

    def chunk(self, chunking_input: ChunkingInput) -> list[MarkdownChunk]:
        """Split Markdown into chunk candidates."""


class DeterministicMarkdownChunker(SharedDeterministicMarkdownChunker):
    """Default deterministic section-aware character chunker."""


class DoclingPageAwareChunker:
    """Docling-native chunker that preserves page provenance when available."""

    chunker_name = DOCLING_PAGE_AWARE_CHUNKER
    requires_native_document = True

    def chunk(self, chunking_input: ChunkingInput) -> list[MarkdownChunk]:
        """Split Docling document text by page, then reuse deterministic Markdown chunking."""

        if chunking_input.native_document is None:
            raise ValueError("Docling page-aware chunking requires parser-native document output.")

        page_texts = _page_texts_from_docling_document(chunking_input.native_document)
        if not page_texts:
            return _chunks_with_page_metadata(
                chunk_markdown(chunking_input.markdown),
                page=None,
            )

        chunks: list[MarkdownChunk] = []
        for page_text in page_texts:
            chunks.extend(
                _chunks_with_page_metadata(
                    chunk_markdown(page_text.text),
                    page=page_text.page,
                    pages=page_text.pages,
                )
            )
        return chunks


class DoclingHybridChunker:
    """Docling-native HybridChunker adapter for parser-native PDF documents."""

    chunker_name = DOCLING_HYBRID_CHUNKER
    requires_native_document = True

    def __init__(self, hybrid_chunker_factory: Callable[[], Any] | None = None) -> None:
        self._hybrid_chunker_factory = hybrid_chunker_factory or _default_hybrid_chunker_factory

    def chunk(self, chunking_input: ChunkingInput) -> list[MarkdownChunk]:
        """Split a Docling document with Docling HybridChunker."""

        if chunking_input.native_document is None:
            raise ValueError("Docling hybrid chunking requires parser-native document output.")

        hybrid_chunker = self._hybrid_chunker_factory()
        chunks: list[MarkdownChunk] = []
        for docling_chunk in hybrid_chunker.chunk(chunking_input.native_document):
            raw_text = str(getattr(docling_chunk, "text", "")).strip()
            section_path = _section_path_from_docling_chunk(docling_chunk)
            text = str(hybrid_chunker.contextualize(docling_chunk)).strip()
            if not text:
                text = raw_text
            if text:
                chunks.append(
                    MarkdownChunk(
                        section=_section_from_section_path(section_path),
                        text=text,
                        metadata={
                            "section_path": section_path,
                            "raw_text": raw_text,
                        },
                    )
                )
        return chunks


class MarkdownChunkerDefinition(BaseModel):
    """Registered Markdown chunker factory."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    name: str
    factory: Callable[[], MarkdownChunker]


_MARKDOWN_CHUNKER_REGISTRY: dict[str, MarkdownChunkerDefinition] = {
    DETERMINISTIC_MARKDOWN_CHUNKER: MarkdownChunkerDefinition(
        name=DETERMINISTIC_MARKDOWN_CHUNKER,
        factory=DeterministicMarkdownChunker,
    ),
    DOCLING_PAGE_AWARE_CHUNKER: MarkdownChunkerDefinition(
        name=DOCLING_PAGE_AWARE_CHUNKER,
        factory=DoclingPageAwareChunker,
    ),
    DOCLING_HYBRID_CHUNKER: MarkdownChunkerDefinition(
        name=DOCLING_HYBRID_CHUNKER,
        factory=DoclingHybridChunker,
    ),
}


def resolve_markdown_chunker(chunker_name: str | None = None) -> MarkdownChunker:
    """Resolve a supported Markdown chunker name to a fresh chunker instance."""

    normalized_name = _normalize_chunker_name(chunker_name)
    definition = _MARKDOWN_CHUNKER_REGISTRY.get(normalized_name)
    if definition is None:
        raise ValueError(
            "Unsupported Markdown chunker: "
            f"{chunker_name}. Supported chunkers: {', '.join(supported_markdown_chunkers())}."
        )
    return definition.factory()


def supported_markdown_chunkers() -> tuple[str, ...]:
    """Return registered Markdown chunker names in stable order."""

    return tuple(sorted(_MARKDOWN_CHUNKER_REGISTRY))


def _normalize_chunker_name(chunker_name: str | None) -> str:
    if chunker_name is None:
        return DEFAULT_MARKDOWN_CHUNKER
    return chunker_name.strip().lower().replace("_", "-")


def _default_hybrid_chunker_factory() -> Any:
    from docling_core.transforms.chunker.hybrid_chunker import HybridChunker

    return HybridChunker()


class _PageText(BaseModel):
    model_config = ConfigDict(frozen=True)

    pages: list[int]
    text: str

    @property
    def page(self) -> int | None:
        return self.pages[0] if self.pages else None


def _page_texts_from_docling_document(doc: Any) -> list[_PageText]:
    page_buffers: dict[tuple[int, ...], list[str]] = {}
    for item in _iter_docling_items(doc):
        text = _chunkable_item_text(item, doc)
        if not text:
            continue
        pages = tuple(_item_pages(item))
        page_buffers.setdefault(pages, []).append(text)
    return [
        _PageText(pages=list(pages), text="\n\n".join(parts))
        for pages, parts in page_buffers.items()
        if "\n\n".join(parts).strip()
    ]


def _chunks_with_page_metadata(
    chunks: list[MarkdownChunk],
    *,
    page: int | None,
    pages: list[int] | None = None,
) -> list[MarkdownChunk]:
    page_metadata: dict[str, Any] = {"page": page}
    if pages:
        page_metadata["pages"] = pages
        page_metadata["page_range"] = [pages[0], pages[-1]]
    elif page is not None:
        page_metadata["pages"] = [page]
        page_metadata["page_range"] = [page, page]
    return [
        chunk.model_copy(update={"metadata": {**chunk.metadata, **page_metadata}})
        for chunk in chunks
    ]


def _iter_docling_items(doc: Any) -> list[Any]:
    iterate_items = getattr(doc, "iterate_items", None)
    if not callable(iterate_items):
        return []

    try:
        raw_items = iterate_items(traverse_pictures=True)
    except TypeError:
        raw_items = iterate_items()

    items: list[Any] = []
    for entry in raw_items:
        if isinstance(entry, tuple):
            items.append(entry[0])
        else:
            items.append(entry)
    return items


def _chunkable_item_text(item: Any, doc: Any) -> str | None:
    if _element_kind(item) in {"image", "chart"}:
        return None

    markdown = _call_item_method(item, "export_to_markdown", doc)
    if isinstance(markdown, str) and markdown.strip():
        return markdown.strip()

    raw_text = getattr(item, "text", None)
    if isinstance(raw_text, str) and raw_text.strip():
        normalized_label = _normalized_label(item)
        stripped = raw_text.strip()
        if normalized_label.endswith("title"):
            return f"# {stripped}"
        if normalized_label.endswith("section_header") or normalized_label.endswith(
            "section-header"
        ):
            return f"## {stripped}"
        return stripped

    text = _call_item_method(item, "export_to_text", doc)
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def _element_kind(item: Any) -> str | None:
    normalized_label = _normalized_label(item)
    if normalized_label.endswith("picture"):
        return "image"
    if normalized_label.endswith("chart"):
        return "chart"
    if normalized_label.endswith("table"):
        return "table"
    return None


def _item_pages(item: Any) -> list[int]:
    provenance = getattr(item, "prov", None)
    if not provenance:
        return []
    pages: list[int] = []
    for item_provenance in provenance:
        page_no = getattr(item_provenance, "page_no", None)
        if isinstance(page_no, int) and page_no not in pages:
            pages.append(page_no)
    return sorted(pages)


def _normalized_label(item: Any) -> str:
    label = getattr(item, "label", "")
    label_value = getattr(label, "value", label)
    return str(label_value).lower()


def _call_item_method(item: Any, method_name: str, doc: Any) -> Any:
    method = getattr(item, method_name, None)
    if not callable(method):
        return None

    try:
        return method(doc)
    except TypeError:
        return method()


def _section_path_from_docling_chunk(docling_chunk: Any) -> list[str]:
    meta = getattr(docling_chunk, "meta", None)
    headings = getattr(meta, "headings", None)
    if not headings:
        return []
    return [str(heading).strip() for heading in headings if str(heading).strip()]


def _section_from_section_path(section_path: list[str]) -> str | None:
    return " > ".join(section_path) or None


def _pages_from_docling_chunk(docling_chunk: Any) -> list[int]:
    meta = getattr(docling_chunk, "meta", None)
    if meta is None:
        return []
    pages: set[int] = set()
    for item in getattr(meta, "doc_items", []):
        for prov in getattr(item, "prov", []):
            page_no = getattr(prov, "page_no", None)
            if isinstance(page_no, int):
                pages.add(page_no)
    return sorted(pages)
