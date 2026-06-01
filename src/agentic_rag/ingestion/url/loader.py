"""URL ingestion boundary."""

from __future__ import annotations

from dataclasses import dataclass

from agentic_rag.core.contracts import Chunk


@dataclass(frozen=True)
class _FetchedPage:
    """Internal container for fetched URL content."""

    url: str
    content: str
    content_type: str


def load_url_chunks(url: str) -> list[Chunk]:
    """Fetch, clean, and chunk URL content into shared Chunk objects."""

    raise NotImplementedError("load_url_chunks is scaffolded for URL ingestion.")


def load_html_chunks(
    html: str,
    *,
    source: str,
    source_url: str | None = None,
    chunking_strategy: TextChunkingStrategy | None = None,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    run_id: str | None = None,
) -> list[Chunk]:
    """Parse and chunk raw HTML string."""

    raise NotImplementedError("load_html_chunks is scaffolded for URL ingestion.")


def load_text_chunks(
    text: str,
    *,
    source: str,
) -> list[Chunk]:
    """Chunk raw text or Markdown string."""

    raise NotImplementedError("load_text_chunks is scaffolded for URL ingestion.")
