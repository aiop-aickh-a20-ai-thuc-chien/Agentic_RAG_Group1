"""URL ingestion and chunking boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.artifact import (
    DebugArtifact,
    IngestionArtifacts,
    persist_debug_artifacts,
    persist_ingestion_artifacts,
)
from agentic_rag.ingestion.url.chunking import (
    TextChunkingStrategy,
    build_chunks,
    normalize_space,
    short_hash,
)
from agentic_rag.ingestion.url.extractor import extract_markdown_with_trafilatura
from agentic_rag.ingestion.url.parser import ParsedHtml, parse_html

_USER_AGENT = "AgenticRAGGroup1/0.1"
_PARSER_NAME = "builtin-html-parser"
_TRAFILATURA_PARSER_NAME = "trafilatura-markdown+builtin-html-parser"
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class _FetchedPage:
    html: str
    url: str
    content_type: str | None = None


@dataclass(frozen=True)
class LoadedUrlDocument:
    """Parsed URL/text Markdown, generated chunks, and optional artifact paths."""

    markdown: str
    chunks: list[Chunk]
    artifacts: IngestionArtifacts | None


def load_url_chunks(
    url: str,
    *,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "url_ingestion",
    chunking_strategy: TextChunkingStrategy | None = None,
) -> list[Chunk]:
    """Fetch, clean, and chunk URL content into shared Chunk objects."""

    return load_url_with_artifacts(
        url,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
        chunking_strategy=chunking_strategy,
    ).chunks


def load_url_with_artifacts(
    url: str,
    *,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "url_ingestion",
    chunking_strategy: TextChunkingStrategy | None = None,
) -> LoadedUrlDocument:
    """Fetch, clean, chunk, and expose URL ingestion artifacts."""

    _raise_if_pdf_url(url)
    page = _fetch_url(url)
    _raise_if_pdf_response(page)
    return load_html_with_artifacts(
        page.html,
        source=page.url,
        source_url=page.url,
        original_url=url,
        final_url=page.url,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
        chunking_strategy=chunking_strategy,
    )


def load_html_chunks(
    html: str,
    *,
    source: str,
    source_url: str | None = None,
    original_url: str | None = None,
    final_url: str | None = None,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "html_ingestion",
    chunking_strategy: TextChunkingStrategy | None = None,
) -> list[Chunk]:
    """Clean and chunk one HTML document into shared Chunk objects."""

    return load_html_with_artifacts(
        html,
        source=source,
        source_url=source_url,
        original_url=original_url,
        final_url=final_url,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
        chunking_strategy=chunking_strategy,
    ).chunks


def load_html_with_artifacts(
    html: str,
    *,
    source: str,
    source_url: str | None = None,
    original_url: str | None = None,
    final_url: str | None = None,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "html_ingestion",
    chunking_strategy: TextChunkingStrategy | None = None,
) -> LoadedUrlDocument:
    """Clean and chunk one HTML document while exposing persisted artifacts."""

    parsed = parse_html(html, base_url=source_url or source)
    fetched_at = _utc_now()
    parsed_markdown, parser_name = _extract_markdown(
        html=html,
        parsed=parsed,
        source_url=source_url or source,
    )
    canonical_url = parsed.metadata.canonical_url or parsed.metadata.og_url
    _persist_html_debug_artifacts(
        debug_artifact_dir=debug_artifact_dir,
        source=source,
        html=html,
        parsed_sections="\n\n".join(section.text for section in parsed.sections),
    )

    source_type = "url" if source_url else "html"
    chunks: list[Chunk] = []
    for section in parsed.sections:
        chunks.extend(
            build_chunks(
                text=section.markdown or section.text,
                source=source,
                source_type=source_type,
                section=section.heading,
                url=source_url,
                title=parsed.title,
                fetched_at=fetched_at,
                chunking_strategy=chunking_strategy,
            )
        )
    chunks = _with_html_metadata(
        chunks,
        original_url=original_url,
        final_url=final_url,
        canonical_url=canonical_url,
        parsed=parsed,
    )
    artifacts = persist_ingestion_artifacts(
        data_dir=data_artifact_dir,
        input_type="url" if source_url else "html",
        source=source,
        source_url=source_url,
        original_url=original_url,
        final_url=final_url,
        canonical_url=canonical_url,
        parser=parser_name,
        run_id=run_id,
        created_at=fetched_at,
        markdown=parsed_markdown,
        chunks=chunks,
        page_metadata=parsed.metadata,
        assets=parsed.assets,
    )
    return LoadedUrlDocument(markdown=parsed_markdown, chunks=chunks, artifacts=artifacts)


def load_text_chunks(
    text: str,
    *,
    source: str,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "text_ingestion",
    chunking_strategy: TextChunkingStrategy | None = None,
) -> list[Chunk]:
    """Clean and chunk plain text into shared Chunk objects."""

    cleaned_text = normalize_space(text)
    if not cleaned_text:
        return []
    _persist_text_debug_artifacts(
        debug_artifact_dir=debug_artifact_dir,
        source=source,
        text=cleaned_text,
    )
    fetched_at = _utc_now()
    chunks = build_chunks(
        text=cleaned_text,
        source=source,
        source_type="text",
        section="main",
        url=None,
        title=None,
        fetched_at=fetched_at,
        chunking_strategy=chunking_strategy,
    )
    persist_ingestion_artifacts(
        data_dir=data_artifact_dir,
        input_type="text",
        source=source,
        source_url=None,
        parser="plain-text",
        run_id=run_id,
        created_at=fetched_at,
        markdown=cleaned_text,
        chunks=chunks,
    )
    return chunks


def _fetch_url(url: str) -> _FetchedPage:
    normalized_url = url.strip()
    parsed_url = urlparse(normalized_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("URL ingestion requires an absolute http or https URL.")

    request = Request(normalized_url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            content = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
    except HTTPError as exc:
        raise RuntimeError(f"Failed to fetch URL {normalized_url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch URL {normalized_url}: {exc.reason}") from exc

    return _FetchedPage(
        html=content.decode(charset, errors="replace"),
        url=final_url,
        content_type=content_type,
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _parsed_markdown(parsed: ParsedHtml) -> str:
    lines: list[str] = []
    if parsed.title:
        lines.extend([f"# {parsed.title}", ""])
    for section in parsed.sections:
        if section.markdown:
            lines.extend([section.markdown, ""])
            continue
        if section.heading != "main":
            heading_level = section.heading_level or 2
            lines.extend([f"{'#' * heading_level} {section.heading}", ""])
        lines.extend([section.text, ""])
    return "\n".join(lines)


def _extract_markdown(
    *,
    html: str,
    parsed: ParsedHtml,
    source_url: str | None,
) -> tuple[str, str]:
    fallback_markdown = _parsed_markdown(parsed)
    try:
        trafilatura_markdown = extract_markdown_with_trafilatura(
            html,
            source_url=source_url,
        )
    except (ImportError, ModuleNotFoundError, RuntimeError):
        return fallback_markdown, _PARSER_NAME
    if trafilatura_markdown is None:
        return fallback_markdown, _PARSER_NAME
    return trafilatura_markdown, _TRAFILATURA_PARSER_NAME


def _persist_html_debug_artifacts(
    *,
    debug_artifact_dir: str | Path | None,
    source: str,
    html: str,
    parsed_sections: str,
) -> None:
    source_hash = short_hash(source)
    persist_debug_artifacts(
        debug_artifact_dir,
        (
            DebugArtifact(name=f"{source_hash}_raw.html", content=html),
            DebugArtifact(name=f"{source_hash}_parsed.txt", content=parsed_sections),
        ),
    )


def _persist_text_debug_artifacts(
    *,
    debug_artifact_dir: str | Path | None,
    source: str,
    text: str,
) -> None:
    persist_debug_artifacts(
        debug_artifact_dir,
        (DebugArtifact(name=f"{short_hash(source)}_text.txt", content=text),),
    )


def _with_html_metadata(
    chunks: list[Chunk],
    *,
    original_url: str | None,
    final_url: str | None,
    canonical_url: str | None,
    parsed: ParsedHtml,
) -> list[Chunk]:
    return [
        chunk.model_copy(
            update={
                "metadata": {
                    **chunk.metadata,
                    "original_url": original_url,
                    "final_url": final_url,
                    "canonical_url": canonical_url,
                    "language": parsed.metadata.language,
                    "author": parsed.metadata.author,
                    "published_at": parsed.metadata.published_at,
                    "description": parsed.metadata.description or parsed.metadata.og_description,
                    "asset_count": len(parsed.assets),
                }
            }
        )
        for chunk in chunks
    ]


def _raise_if_pdf_url(url: str) -> None:
    parsed_url = urlparse(url.strip())
    if parsed_url.path.lower().endswith(".pdf"):
        raise ValueError("URL ingestion received a PDF URL; route it to PDF ingestion.")


def _raise_if_pdf_response(page: _FetchedPage) -> None:
    if page.content_type == "application/pdf":
        raise ValueError("URL ingestion received a PDF response; route it to PDF ingestion.")
