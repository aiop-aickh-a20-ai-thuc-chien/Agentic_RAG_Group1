"""URL ingestion boundary."""

from __future__ import annotations

from agentic_rag.core.contracts import Chunk


def load_url_chunks(url: str) -> list[Chunk]:
    """Fetch, clean, and chunk URL content into shared Chunk objects."""

    raise NotImplementedError("load_url_chunks is scaffolded for URL ingestion.")
