"""PDF ingestion and chunking boundary."""

from __future__ import annotations

import hashlib
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
    # TODO [PixelRAG Integration — PDF Visual Chunking]:
    # For PDFs with heavy visual content (brochures, catalogs, spec sheets with
    # diagrams), consider rendering pages as screenshot tiles alongside the
    # existing text-based markdown chunking.
    #
    # Pseudocode:
    #
    #   IF config.VISUAL_PDF_ENABLED:
    #       # Stage 1: Render each PDF page to an image (poppler / pdf2image)
    #       page_images = render_pdf(path, visual_output_dir / "tiles", dpi=200)
    #       # Each page produces ~1650×2200 pixels for A4 at DPI=200
    #
    #       # Stage 2: Chunk page images into 1024px-tall strips
    #       FOR EACH page_tile_dir IN page_images:
    #           chunk_article(page_tile_dir)
    #           # Produces chunk_XXXX_YY.png files (1024px height, viewport_width)
    #           # Discards strips < 28px (one Qwen3-VL patch)
    #
    #       # Stage 3: Embed image chunks with VLM
    #       image_items = scan_chunks(visual_output_dir / "tiles")
    #       visual_embeddings = embed_items(image_items,
    #                                       model="Qwen/Qwen3-VL-Embedding-2B",
    #                                       device="auto")
    #
    #       # Stage 4: Create visual Chunk objects with page-level metadata
    #       FOR i, item IN enumerate(image_items):
    #           visual_chunk = Chunk(
    #               chunk_id=f"pdf_visual_{safe_file_stem}_p{item.tile_index}_c{item.chunk_index}",
    #               text="[visual chunk — see image tile]",
    #               metadata={
    #                   "source": str(path),
    #                   "source_type": "pdf",
    #                   "extraction_method": "visual_pixelrag",
    #                   "page": item.tile_index + 1,
    #                   "tile_index": item.tile_index,
    #                   "chunk_index": item.chunk_index,
    #                   "y_offset": item.y_offset,
    #                   "image_path": item.path,
    #                   "viewport_width": 875,
    #               }
    #           )
    #           chunks.append(visual_chunk)
    #
    #       # Optionally build a separate FAISS index for visual PDF retrieval
    #       build_faiss_index(visual_output_dir / "embeddings",
    #                         visual_output_dir / "index")
    #
    # Reference: guide_RAG/GUIDELINE.md §4, PixelRAG/render/src/pixelrag_render/render.py

    VISUAL_PDF_ENABLED = False  # Set to True when PixelRAG backend is installed
    if VISUAL_PDF_ENABLED:
        try:
            from agentic_rag.ingestion.visual_pipeline import render_pdf, embed_visual_chunks, build_faiss_index
            from agentic_rag.ingestion.chunking.visual import VisualTileChunker
            from agentic_rag.ingestion.metadata.visual import enrich_visual_metadata
            
            # Using the same safe stem logic as text chunks
            safe_file_stem = _safe_chunk_id_part(path.stem)
            visual_output_dir = path.parent / f"{path.name}_visual"
            
            # Stage 1
            page_images = render_pdf(path, visual_output_dir / "tiles", dpi=200)
            
            # Stage 2
            chunker = VisualTileChunker()
            all_image_chunks = []
            for page_tile_dir in page_images:
                page_img_path = page_tile_dir / "page.png"
                if page_img_path.exists():
                    all_image_chunks.extend(chunker.chunk(page_img_path))
                    
            # Stage 3
            if all_image_chunks:
                try:
                    visual_embeddings = embed_visual_chunks(all_image_chunks)
                    build_faiss_index(visual_output_dir / "embeddings", visual_output_dir / "index")
                except NotImplementedError:
                    pass  # Embedding unsupported but we still keep chunks
                    
            # Stage 4
            for i, item in enumerate(all_image_chunks):
                visual_chunk = Chunk(
                    chunk_id=f"pdf_visual_{safe_file_stem}_p{item.index}_c{i}",
                    text="[visual chunk — see image tile]",
                    metadata={}
                )
                enriched_chunk = enrich_visual_metadata(visual_chunk, {
                    "source": str(path),
                    "source_type": "pdf",
                    "extraction_method": "visual_pixelrag",
                    "page": item.index + 1,
                    "tile_index": item.index,
                    "chunk_index": i,
                    "y_offset": item.y_offset,
                    "image_path": str(visual_output_dir),  # Path placeholder
                    "viewport_width": chunker.VIEWPORT_WIDTH,
                })
                chunks.append(enriched_chunk)

        except NotImplementedError:
            pass  # Visual PDF rendering gracefully degrades if backend absent


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
    title = _extract_title(chunking_input.markdown)
    ingestion_at = datetime.now(UTC).isoformat()

    chunks: list[Chunk] = []
    for index, markdown_chunk in enumerate(markdown_chunks, start=1):
        chunk_id = f"pdf_{safe_file_stem}_c{index:04d}"
        section = markdown_chunk.section
        metadata = {
            "chunk_id": chunk_id,
            "source": source,
            "source_type": source_type,
            "document_type": "manual",
            "title": title,
            "file_name": path.name,
            "page": None,
            "page_number": None,
            "section": section,
            "section_level": markdown_chunk.section_level or None,
            "section_path": list(markdown_chunk.section_path),
            "heading": section,
            "breadcrumb": _breadcrumb_for_chunk(markdown_chunk),
            "parser": chunking_input.parser,
            "chunking_method": chunker.chunker_name,
            "chunk_index": index,
            "token_count": _token_count_for_chunk(markdown_chunk),
            "updated_date": updated_date,
            "updated_date_source": "ingestion_start",
            "ingestion_at": ingestion_at,
            "content_hash": _short_hash(markdown_chunk.text),
        }
        for key, value in markdown_chunk.metadata.items():
            is_page_override = key == "page" and value is not None
            is_override_field = (
                key in ("section_path", "section_level", "title") and value is not None
            )
            if is_page_override or is_override_field or key not in metadata:
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


def _extract_title(markdown: str) -> str | None:
    """Extract document title from the first H1 heading in markdown."""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip() or None
    return None


def _short_hash(value: str) -> str:
    """Return a stable short SHA-256 digest."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
