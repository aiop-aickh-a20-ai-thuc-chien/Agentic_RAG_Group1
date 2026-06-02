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
from agentic_rag.ingestion.url.parser import ParsedHtml, parse_html

_USER_AGENT = "AgenticRAGGroup1/0.1"
_PARSER_NAME = "builtin-html-parser"
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class _FetchedPage:
    html: str
    url: str


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

    page = _fetch_url(url)
    return load_html_with_artifacts(
        page.html,
        source=page.url,
        source_url=page.url,
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
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "html_ingestion",
    chunking_strategy: TextChunkingStrategy | None = None,
) -> LoadedUrlDocument:
    """Clean and chunk one HTML document while exposing persisted artifacts."""

    parsed = parse_html(html)
    fetched_at = _utc_now()
    parsed_markdown = _parsed_markdown(parsed)
    _persist_html_debug_artifacts(
        debug_artifact_dir=debug_artifact_dir,
        source=source,
        html=html,
        parsed_sections="\n\n".join(section.text for section in parsed.sections),
    )

    chunks: list[Chunk] = []
    for section in parsed.sections:
        chunks.extend(
            build_chunks(
                text=section.text,
                source=source,
                source_type="url" if source_url else "html",
                section=section.heading,
                url=source_url,
                title=parsed.title,
                fetched_at=fetched_at,
                chunking_strategy=chunking_strategy,
            )
        )
    artifacts = persist_ingestion_artifacts(
        data_dir=data_artifact_dir,
        input_type="url" if source_url else "html",
        source=source,
        source_url=source_url,
        parser=_PARSER_NAME,
        run_id=run_id,
        created_at=fetched_at,
        markdown=parsed_markdown,
        chunks=chunks,
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
            content = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
    except HTTPError as exc:
        raise RuntimeError(f"Failed to fetch URL {normalized_url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch URL {normalized_url}: {exc.reason}") from exc

    return _FetchedPage(html=content.decode(charset, errors="replace"), url=final_url)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _parsed_markdown(parsed: ParsedHtml) -> str:
    lines: list[str] = []
    if parsed.title:
        lines.extend([f"# {parsed.title}", ""])
    for section in parsed.sections:
        if section.heading != "main":
            lines.extend([f"## {section.heading}", ""])
        lines.extend([section.text, ""])
    return "\n".join(lines)


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
