"""URL ingestion package."""

from agentic_rag.ingestion.url.crawler import Crawl4AIPage, crawl_url_with_crawl4ai
from agentic_rag.ingestion.url.loader import (
    LoadedUrlDocument,
    load_html_chunks,
    load_html_with_artifacts,
    load_text_chunks,
    load_url_chunks,
    load_url_with_artifacts,
)

__all__ = [
    "Crawl4AIPage",
    "LoadedUrlDocument",
    "crawl_url_with_crawl4ai",
    "load_html_chunks",
    "load_html_with_artifacts",
    "load_text_chunks",
    "load_url_chunks",
    "load_url_with_artifacts",
]
