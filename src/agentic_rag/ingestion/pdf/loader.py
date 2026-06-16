"""PDF ingestion and chunking boundary."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.metadata import infer_source_type, require_metadata

from .chunkers import (
    DEFAULT_MARKDOWN_CHUNKER,
    DETERMINISTIC_MARKDOWN_CHUNKER,
    DOCLING_HYBRID_CHUNKER,
    MarkdownChunker,
    resolve_markdown_chunker,
)
from .models import PdfChunkingInput, PdfParseResult
from .parser import PdfMarkdownParser
from .pipelines import (
    DEFAULT_PDF_PIPELINE,
    DEFAULT_PDF_STRATEGY,
    resolve_pdf_pipeline,
)


class LoadedPdfDocument(BaseModel):
    """Parsed PDF Markdown and the shared chunks derived from it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    markdown: str
    chunks: list[Chunk]
    parser: str = DEFAULT_PDF_STRATEGY
    pipeline: str = DEFAULT_PDF_PIPELINE
    strategy: str = DEFAULT_PDF_STRATEGY
    chunker: str = DEFAULT_MARKDOWN_CHUNKER
    requested_chunker: str | None = None
    chunking_fallback_reason: str | None = None


def load_pdf_chunks(
    path: str,
    *,
    parser_name: str | None = None,
    pipeline_name: str | None = None,
    strategy_name: str | None = None,
    chunker_name: str = DEFAULT_MARKDOWN_CHUNKER,
) -> list[Chunk]:
    """Load and chunk a PDF file into shared Chunk objects."""

    return load_pdf_with_markdown(
        path,
        parser_name=parser_name,
        pipeline_name=pipeline_name,
        strategy_name=strategy_name,
        chunker_name=chunker_name,
    ).chunks


def load_pdf_with_markdown(
    path: str,
    *,
    parser_name: str | None = None,
    pipeline_name: str | None = None,
    strategy_name: str | None = None,
    chunker_name: str = DEFAULT_MARKDOWN_CHUNKER,
) -> LoadedPdfDocument:
    """Load a PDF into Markdown and shared Chunk objects."""

    pdf_path = Path(path)
    resolved_pipeline = resolve_pdf_pipeline(
        pipeline_name,
        strategy_name if strategy_name is not None else parser_name,
    )
    return _load_pdf_with_markdown(
        pdf_path,
        resolved_pipeline.parser,
        pipeline_name=resolved_pipeline.pipeline_name,
        strategy_name=resolved_pipeline.strategy_name,
        chunker=resolve_markdown_chunker(chunker_name),
    )


def _load_pdf_chunks(
    path: Path,
    parser: PdfMarkdownParser,
    *,
    chunker: MarkdownChunker | None = None,
) -> list[Chunk]:
    return _load_pdf_with_markdown(path, parser, chunker=chunker).chunks


def _load_pdf_with_markdown(
    path: Path,
    parser: PdfMarkdownParser,
    *,
    pipeline_name: str = DEFAULT_PDF_PIPELINE,
    strategy_name: str = DEFAULT_PDF_STRATEGY,
    chunker: MarkdownChunker | None = None,
) -> LoadedPdfDocument:
    _validate_pdf_path(path)
    loaded_at = _utc_now()
    resolved_chunker = chunker if chunker is not None else resolve_markdown_chunker()
    parse_result, native_document = _parse_for_chunker(path, parser, resolved_chunker)
    chunking_input = PdfChunkingInput(
        markdown=parse_result.markdown,
        parser=parse_result.parser,
        source_path=parse_result.source_path,
        native_document=native_document,
    )
    chunker_name = resolved_chunker.chunker_name
    fallback_reason = None
    try:
        chunks = _chunks_from_chunking_input(
            path,
            chunking_input,
            chunker=resolved_chunker,
            updated_date=loaded_at,
        )
    except Exception as exc:
        if not _should_fallback_pdf_chunking(resolved_chunker, exc):
            raise
        fallback_chunker = resolve_markdown_chunker(DETERMINISTIC_MARKDOWN_CHUNKER)
        chunks = _chunks_from_chunking_input(
            path,
            chunking_input,
            chunker=fallback_chunker,
            updated_date=loaded_at,
        )
        chunker_name = fallback_chunker.chunker_name
        fallback_reason = _fallback_reason(
            requested_chunker=resolved_chunker.chunker_name,
            fallback_chunker=fallback_chunker.chunker_name,
            exc=exc,
        )
    return LoadedPdfDocument(
        markdown=parse_result.markdown,
        chunks=chunks,
        parser=parse_result.parser,
        pipeline=pipeline_name,
        strategy=strategy_name,
        chunker=chunker_name,
        requested_chunker=resolved_chunker.chunker_name,
        chunking_fallback_reason=fallback_reason,
    )


def _parse_for_chunker(
    path: Path,
    parser: PdfMarkdownParser,
    chunker: MarkdownChunker,
) -> tuple[PdfParseResult, object | None]:
    if not chunker.requires_native_document:
        return parser.parse(path), None

    parse_to_document = getattr(parser, "parse_to_document", None)
    if parse_to_document is None:
        raise RuntimeError(
            f"PDF chunker '{chunker.chunker_name}' requires parser-native document output, "
            f"but parser '{parser.parser_name}' does not provide parse_to_document()."
        )
    parsed = parse_to_document(path)
    return (
        PdfParseResult(
            parser=parser.parser_name,
            source_path=str(path),
            markdown=parsed.markdown,
        ),
        parsed.document,
    )


def _validate_pdf_path(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file path, got: {path}")


def _chunks_from_markdown(
    path: Path,
    markdown: str,
    *,
    parser_name: str = DEFAULT_PDF_STRATEGY,
    chunker: MarkdownChunker | None = None,
) -> list[Chunk]:
    resolved_chunker = (
        chunker if chunker is not None else resolve_markdown_chunker(DETERMINISTIC_MARKDOWN_CHUNKER)
    )
    chunking_input = PdfChunkingInput(
        markdown=markdown,
        parser=parser_name,
        source_path=str(path),
    )
    return _chunks_from_chunking_input(
        path,
        chunking_input,
        chunker=resolved_chunker,
        updated_date=_utc_now(),
    )


def _chunks_from_chunking_input(
    path: Path,
    chunking_input: PdfChunkingInput,
    *,
    chunker: MarkdownChunker,
    updated_date: str,
) -> list[Chunk]:
    markdown_chunks = chunker.chunk(chunking_input)
    safe_file_stem = _safe_chunk_id_part(path.stem)
    source = str(path)
    source_type = infer_source_type(source)

    chunks: list[Chunk] = []
    for index, markdown_chunk in enumerate(markdown_chunks, start=1):
        chunk_id = f"pdf_{safe_file_stem}_c{index:04d}"
        section = markdown_chunk.section
        metadata = {
            "chunk_id": chunk_id,
            "source": source,
            "source_type": source_type,
            "file_name": path.name,
            "page": None,
            "page_number": None,
            "section": section,
            "heading": section,
            "breadcrumb": _breadcrumb_for_chunk(markdown_chunk),
            "parser": chunking_input.parser,
            "chunking_method": chunker.chunker_name,
            "chunk_index": index,
            "token_count": _token_count_for_chunk(markdown_chunk),
            "updated_date": updated_date,
            "updated_date_source": "ingestion_start",
        }
        for key, value in markdown_chunk.metadata.items():
            if (key == "page" and value is not None) or key not in metadata:
                metadata[key] = value
        page = metadata.get("page")
        metadata["page_number"] = page if isinstance(page, int) else None
        if "heading" not in metadata or metadata["heading"] is None:
            metadata["heading"] = metadata.get("section")
        if "breadcrumb" not in metadata or not metadata["breadcrumb"]:
            metadata["breadcrumb"] = _breadcrumb_from_metadata(metadata)
        require_metadata(metadata)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=markdown_chunk.text,
                metadata=metadata,
            )
        )
    return chunks


def _breadcrumb_for_chunk(markdown_chunk: object) -> list[str]:
    section_path = getattr(markdown_chunk, "section_path", ())
    if section_path:
        return [str(item) for item in section_path if str(item)]
    metadata = getattr(markdown_chunk, "metadata", {})
    if isinstance(metadata, dict):
        raw_path = metadata.get("section_path")
        if isinstance(raw_path, list | tuple):
            return [str(item) for item in raw_path if str(item)]
    section = getattr(markdown_chunk, "section", None)
    return [str(section)] if section else []


def _breadcrumb_from_metadata(metadata: dict[str, object]) -> list[str]:
    raw_path = metadata.get("section_path")
    if isinstance(raw_path, list | tuple):
        return [str(item) for item in raw_path if str(item)]
    section = metadata.get("section")
    return [str(section)] if section else []


def _token_count_for_chunk(markdown_chunk: object) -> int:
    token_count = getattr(markdown_chunk, "chunk_token_count", None)
    if isinstance(token_count, int):
        return token_count
    text = getattr(markdown_chunk, "text", "")
    return len(str(text).split())


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_chunk_id_part(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "document"


def _should_fallback_pdf_chunking(chunker: MarkdownChunker, exc: Exception) -> bool:
    if chunker.chunker_name != DOCLING_HYBRID_CHUNKER:
        return False
    if not isinstance(exc, OSError | RuntimeError):
        return False
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "huggingface",
            "cached files",
            "local_files_only",
            "couldn't connect",
            "offline mode",
        )
    )


def _fallback_reason(
    *,
    requested_chunker: str,
    fallback_chunker: str,
    exc: Exception,
) -> str:
    return (
        f"{requested_chunker} unavailable ({exc.__class__.__name__}: "
        f"{_single_line(str(exc), max_chars=240)}); used {fallback_chunker}"
    )


def _single_line(value: str, *, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3]}..."
