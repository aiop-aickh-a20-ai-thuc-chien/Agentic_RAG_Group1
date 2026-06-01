"""URL and text ingestion implementation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from agentic_rag.core.contracts import Chunk

DEFAULT_CHUNK_SIZE = 1_200
DEFAULT_CHUNK_OVERLAP = 150
_NOISE_TAGS = {"script", "style", "nav", "footer", "header", "aside"}
_HEADING_TAGS = {"h1", "h2", "h3"}
_USER_AGENT = "AgenticRAGGroup1/0.1"


@dataclass(frozen=True)
class _FetchedPage:
    html: str
    url: str


@dataclass(frozen=True)
class _Section:
    heading: str
    text: str


@dataclass(frozen=True)
class _ParsedHtml:
    title: str | None
    sections: tuple[_Section, ...]


def load_url_chunks(url: str) -> list[Chunk]:
    """Fetch, clean, and chunk URL content into shared Chunk objects."""

    page = _fetch_url(url)
    return load_html_chunks(page.html, source=page.url, source_url=page.url)


def load_html_chunks(html: str, source: str, source_url: str | None = None) -> list[Chunk]:
    """Clean and chunk one HTML document into shared Chunk objects."""

    parsed = _parse_html(html)
    chunks: list[Chunk] = []
    for section in parsed.sections:
        chunks.extend(
            _build_chunks(
                text=section.text,
                source=source,
                source_type="url" if source_url else "html",
                section=section.heading,
                url=source_url,
                title=parsed.title,
                chunk_size=DEFAULT_CHUNK_SIZE,
                chunk_overlap=DEFAULT_CHUNK_OVERLAP,
            )
        )
    return chunks


def load_text_chunks(text: str, source: str) -> list[Chunk]:
    """Clean and chunk plain text into shared Chunk objects."""

    cleaned_text = _normalize_space(text)
    if not cleaned_text:
        return []
    return _build_chunks(
        text=cleaned_text,
        source=source,
        source_type="text",
        section="main",
        url=None,
        title=None,
        chunk_size=DEFAULT_CHUNK_SIZE,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    )


class _MainContentParser(HTMLParser):
    """Extract readable content while ignoring common boilerplate tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._capture_title = False
        self._current_heading_tag: str | None = None
        self._current_section = "main"
        self._title_parts: list[str] = []
        self._heading_parts: list[str] = []
        self._section_parts: list[str] = []
        self._sections: list[_Section] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized_tag = tag.lower()
        if normalized_tag in _NOISE_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if normalized_tag == "title":
            self._capture_title = True
            self._title_parts = []
            return
        if normalized_tag in _HEADING_TAGS:
            self._current_heading_tag = normalized_tag
            self._heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _NOISE_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return
        if normalized_tag == "title":
            self._capture_title = False
            return
        if normalized_tag == self._current_heading_tag:
            heading = _normalize_space(" ".join(self._heading_parts))
            if heading:
                self._flush_section()
                self._current_section = heading
                self._section_parts = [heading]
            self._current_heading_tag = None
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = _normalize_space(data)
        if not text:
            return
        if self._capture_title:
            self._title_parts.append(text)
            return
        if self._current_heading_tag is not None:
            self._heading_parts.append(text)
            return
        self._section_parts.append(text)

    def close(self) -> None:
        super().close()
        self._flush_section()

    @property
    def title(self) -> str | None:
        title = _normalize_space(" ".join(self._title_parts))
        return title or None

    @property
    def sections(self) -> tuple[_Section, ...]:
        return tuple(self._sections)

    def _flush_section(self) -> None:
        text = _normalize_space(" ".join(self._section_parts))
        if text:
            self._sections.append(_Section(heading=self._current_section, text=text))
        self._section_parts = []


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


def _parse_html(html: str) -> _ParsedHtml:
    parser = _MainContentParser()
    parser.feed(html)
    parser.close()
    return _ParsedHtml(title=parser.title, sections=parser.sections)


def _build_chunks(
    *,
    text: str,
    source: str,
    source_type: str,
    section: str,
    url: str | None,
    title: str | None,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")

    chunks: list[Chunk] = []
    content_hash = _short_hash(text)
    text_chunks = _split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    for index, chunk_text in enumerate(text_chunks, start=1):
        chunk_id = _build_chunk_id(source_type, source, section, index)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=chunk_text,
                metadata={
                    "source": source,
                    "source_type": source_type,
                    "file_name": None,
                    "url": url,
                    "page": None,
                    "section": section,
                    "title": title,
                    "fetched_at": _utc_now(),
                    "content_hash": content_hash,
                    "chunk_index": index,
                },
            )
        )
    return chunks


def _split_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    cleaned_text = _normalize_space(text)
    if not cleaned_text:
        return []
    if len(cleaned_text) <= chunk_size:
        return [cleaned_text]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned_text):
        end = min(start + chunk_size, len(cleaned_text))
        if end < len(cleaned_text):
            split_at = cleaned_text.rfind(" ", start, end)
            if split_at > start:
                end = split_at
        chunk = cleaned_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned_text):
            break
        start = max(end - chunk_overlap, 0)
    return chunks


def _build_chunk_id(source_type: str, source: str, section: str, index: int) -> str:
    return f"{source_type}_{_short_hash(source)}_{_slugify(section)}_c{index:03d}"


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "main"


def _normalize_space(value: str) -> str:
    return " ".join(value.split())


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
