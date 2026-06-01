"""URL ingestion and chunking boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.artifact import DebugArtifact, persist_debug_artifacts
from agentic_rag.ingestion.url.chunking import build_chunks, normalize_space, short_hash
from agentic_rag.ingestion.url.parser import parse_html

_USER_AGENT = "AgenticRAGGroup1/0.1"


@dataclass(frozen=True)
class _FetchedPage:
    html: str
    url: str


def load_url_chunks(url: str, debug_artifact_dir: str | Path | None = None) -> list[Chunk]:
    """Fetch, clean, and chunk URL content into shared Chunk objects."""

    page = _fetch_url(url)
    return load_html_chunks(
        page.html,
        source=page.url,
        source_url=page.url,
        debug_artifact_dir=debug_artifact_dir,
    )


def load_html_chunks(
    html: str,
    source: str,
    source_url: str | None = None,
    debug_artifact_dir: str | Path | None = None,
) -> list[Chunk]:
    """Clean and chunk one HTML document into shared Chunk objects."""

    parsed = parse_html(html)
    fetched_at = _utc_now()
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
            )
        )
    return chunks


def load_text_chunks(
    text: str,
    source: str,
    debug_artifact_dir: str | Path | None = None,
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
    return build_chunks(
        text=cleaned_text,
        source=source,
        source_type="text",
        section="main",
        url=None,
        title=None,
        fetched_at=_utc_now(),
    )


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
