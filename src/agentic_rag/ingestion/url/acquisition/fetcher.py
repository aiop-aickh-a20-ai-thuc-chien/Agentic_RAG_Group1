"""URL acquisition helpers for HTML ingestion."""

from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36 AgenticRAGGroup1/0.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://vinfastauto.com/",
}


class FetchedPage(BaseModel):
    """Fetched URL response payload before parsing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    html: str
    url: str
    content_type: str | None = None
    charset: str = "utf-8"
    original_url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


def fetch_url(
    url: str,
    *,
    timeout_seconds: int = 20,
    headers: dict[str, str] | None = None,
) -> FetchedPage:
    """Fetch an absolute HTTP(S) URL and return decoded HTML-like content."""

    normalized_url = validate_http_url(url)
    reject_pdf_url(normalized_url)
    request = Request(normalized_url, headers=headers or DEFAULT_REQUEST_HEADERS)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_type()
            reject_pdf_content_type(content_type)
            content = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
            response_headers = dict(response.headers.items())
    except HTTPError as exc:
        raise RuntimeError(f"Failed to fetch URL {normalized_url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch URL {normalized_url}: {exc.reason}") from exc

    return FetchedPage(
        html=content.decode(charset, errors="replace"),
        url=final_url,
        content_type=content_type,
        charset=charset,
        original_url=normalized_url,
        headers=response_headers,
    )


def validate_http_url(url: str) -> str:
    """Return a stripped absolute HTTP(S) URL or raise a clear error."""

    normalized_url = url.strip()
    parsed_url = urlparse(normalized_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("URL ingestion requires an absolute http or https URL.")
    return normalized_url


def reject_pdf_url(url: str) -> None:
    """Reject direct PDF URLs before HTML parsing."""

    parsed_url = urlparse(url.strip())
    if parsed_url.path.lower().endswith(".pdf"):
        raise ValueError("URL ingestion received a PDF URL; route it to PDF ingestion.")


def reject_pdf_content_type(content_type: str | None) -> None:
    """Reject PDF responses before HTML parsing."""

    if (content_type or "").lower().split(";", 1)[0] == "application/pdf":
        raise ValueError("URL ingestion received a PDF response; route it to PDF ingestion.")


__all__ = [
    "DEFAULT_REQUEST_HEADERS",
    "FetchedPage",
    "fetch_url",
    "reject_pdf_content_type",
    "reject_pdf_url",
    "validate_http_url",
]
