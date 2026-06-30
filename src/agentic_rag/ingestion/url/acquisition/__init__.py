"""URL acquisition helpers for HTML ingestion."""

from agentic_rag.ingestion.url.acquisition.fetcher import (
    DEFAULT_REQUEST_HEADERS,
    AcquisitionRecord,
    FetchedPage,
    acquisition_record_from_fetched_page,
    fetch_url,
    reject_pdf_content_type,
    reject_pdf_url,
    validate_http_url,
)

__all__ = [
    "DEFAULT_REQUEST_HEADERS",
    "AcquisitionRecord",
    "FetchedPage",
    "acquisition_record_from_fetched_page",
    "fetch_url",
    "reject_pdf_content_type",
    "reject_pdf_url",
    "validate_http_url",
]
