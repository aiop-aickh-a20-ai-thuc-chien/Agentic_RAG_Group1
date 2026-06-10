"""URL ingestion package."""

from agentic_rag.ingestion.url.loader import (
    LoadedUrlDocument,
    load_html_chunks,
    load_html_with_artifacts,
    load_text_chunks,
    load_url_chunks,
    load_url_with_artifacts,
)

__all__ = [
    "LoadedUrlDocument",
    "load_html_chunks",
    "load_html_with_artifacts",
    "load_text_chunks",
    "load_url_chunks",
    "load_url_with_artifacts",
]
