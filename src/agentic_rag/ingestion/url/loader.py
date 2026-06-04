"""URL ingestion and chunking boundary."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.artifact import (
    DebugArtifact,
    IngestionArtifacts,
    persist_debug_artifacts,
    persist_ingestion_artifacts,
)
from agentic_rag.ingestion.url.chunking import (
    build_chunk_id,
    build_chunks,
    chunk_markdown_by_sections,
    normalize_space,
    short_hash,
)
from agentic_rag.ingestion.url.crawler import crawl_url_with_crawl4ai
from agentic_rag.ingestion.url.extractor import extract_markdown_with_trafilatura
from agentic_rag.ingestion.url.parser import ParsedHtml, parse_html

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36 AgenticRAGGroup1/0.1"
)
_REQUEST_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://vinfastauto.com/",
}
_PARSER_NAME = "builtin-html-parser"
_TRAFILATURA_PARSER_NAME = "trafilatura-markdown+builtin-html-parser"
_CRAWL4AI_PARSER_NAME = "crawl4ai-markdown+builtin-html-parser"
_URL_CHUNK_OVERLAP_PARAGRAPHS = 0
_BOILERPLATE_SECTION_SLUGS = {
    "page-not-found",
    "ti-n-ch",
    "th-o-lu-n",
    "ng-k-nh-n-th-ng-tin",
    "hotline-1900-23-23-89",
    "quy-n-ri-ng-t-c-a-b-n",
    "cookie-ho-n-to-n-c-n-thi-t",
    "cookie-hi-u-su-t",
    "cookie-ch-c-n-ng",
    "cookie-qu-ng-c-o",
    "gi-h-ng-kh-ng-h-p-l",
    "h-tr",
    "ki-m-tra-email",
    "i-m-t-kh-u-th-nh-c-ng",
    "qu-n-m-t-kh-u",
    "qu-kh-ch-vui-l-ng-i-m-t-kh-u-m-b-o-an-to-n-th-ng-tin",
    "ng-nh-p-ng-k",
    "ng-k-th-nh-c-ng",
    "d-ng-xe-quan-t-m",
    "mua-s-m",
    "nh-n-t-v-n",
    "filter-button",
}
_VINFAST_MODEL_RE = re.compile(r"\bVF\s*-?\s*(\d{1,2})\b", flags=re.IGNORECASE)
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class _FetchedPage:
    html: str
    url: str
    content_type: str | None = None
    markdown: str | None = None
    links: tuple[str, ...] = ()
    crawler: str = "urllib"
    crawler_error: str | None = None
    probe_markdown: str | None = None


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
    max_child_pages: int = 0,
) -> list[Chunk]:
    """Fetch, clean, and chunk URL content into shared Chunk objects."""

    return load_url_with_artifacts(
        url,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
        max_child_pages=max_child_pages,
    ).chunks


def load_url_with_artifacts(
    url: str,
    *,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "url_ingestion",
    max_child_pages: int = 0,
) -> LoadedUrlDocument:
    """Fetch, clean, chunk, and expose URL ingestion artifacts."""

    if max_child_pages < 0:
        raise ValueError("max_child_pages must be greater than or equal to zero.")
    _raise_if_pdf_url(url)
    page = _fetch_url(url)
    _raise_if_pdf_response(page)
    loaded = load_html_with_artifacts(
        page.html,
        source=page.url,
        source_url=page.url,
        original_url=url,
        final_url=page.url,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
        preferred_markdown=page.markdown,
        preferred_parser=_CRAWL4AI_PARSER_NAME if page.markdown else None,
        crawler=page.crawler,
        crawler_error=page.crawler_error,
        probe_markdown=page.probe_markdown,
    )
    if max_child_pages == 0:
        return loaded

    child_documents: list[LoadedUrlDocument] = []
    for child_url in _same_origin_child_urls(
        page.links,
        base_url=page.url,
        max_child_pages=max_child_pages,
    ):
        try:
            child_page = _fetch_url(child_url)
            _raise_if_pdf_response(child_page)
        except (RuntimeError, ValueError):
            continue
        child_documents.append(
            load_html_with_artifacts(
                child_page.html,
                source=child_page.url,
                source_url=child_page.url,
                original_url=child_url,
                final_url=child_page.url,
                debug_artifact_dir=None,
                data_artifact_dir=None,
                run_id=f"{run_id}_child",
                preferred_markdown=child_page.markdown,
                preferred_parser=_CRAWL4AI_PARSER_NAME if child_page.markdown else None,
                crawler=child_page.crawler,
                crawler_error=child_page.crawler_error,
                probe_markdown=child_page.probe_markdown,
            )
        )

    if not child_documents:
        return loaded

    all_chunks = _dedupe_chunks(
        [*loaded.chunks, *(chunk for document in child_documents for chunk in document.chunks)]
    )
    all_markdown = "\n\n".join(
        document.markdown.strip() for document in [loaded, *child_documents] if document.markdown
    )
    return LoadedUrlDocument(markdown=all_markdown, chunks=all_chunks, artifacts=loaded.artifacts)


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
    preferred_markdown: str | None = None,
    preferred_parser: str | None = None,
    crawler: str = "static-html",
    crawler_error: str | None = None,
    probe_markdown: str | None = None,
) -> LoadedUrlDocument:
    """Clean and chunk one HTML document while exposing persisted artifacts."""

    parsed = parse_html(html, base_url=source_url or source)
    fetched_at = _utc_now()
    parsed_markdown, parser_name = _extract_markdown(
        html=html,
        parsed=parsed,
        source_url=source_url or source,
        preferred_markdown=preferred_markdown,
        preferred_parser=preferred_parser,
    )
    canonical_url = parsed.metadata.canonical_url or parsed.metadata.og_url
    _persist_html_debug_artifacts(
        debug_artifact_dir=debug_artifact_dir,
        source=source,
        html=html,
        parsed_sections="\n\n".join(section.text for section in parsed.sections),
    )

    source_type = "url" if source_url else "html"
    cleaned_markdown = _clean_markdown_noise(
        _append_probe_markdown(parsed_markdown, probe_markdown)
    )
    chunks = _build_markdown_aware_chunks(
        markdown=cleaned_markdown,
        source=source,
        source_type=source_type,
        url=source_url,
        title=parsed.title,
        fetched_at=fetched_at,
    )
    chunks = _with_html_metadata(
        chunks,
        original_url=original_url,
        final_url=final_url,
        canonical_url=canonical_url,
        parsed=parsed,
        crawler=crawler,
        crawler_error=crawler_error,
        parser_name=parser_name,
    )
    chunks = _dedupe_chunks(chunks)
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
        markdown=cleaned_markdown,
        chunks=chunks,
        page_metadata=parsed.metadata,
        assets=parsed.assets,
    )
    return LoadedUrlDocument(markdown=cleaned_markdown, chunks=chunks, artifacts=artifacts)


def load_text_chunks(
    text: str,
    *,
    source: str,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "text_ingestion",
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
    _validate_http_url(url)
    try:
        crawled_page = crawl_url_with_crawl4ai(url)
    except Exception as exc:
        return _fetch_url_urllib(url, crawler_error=f"{type(exc).__name__}: {exc}")
    return _FetchedPage(
        html=crawled_page.html,
        url=crawled_page.url,
        content_type=crawled_page.content_type,
        markdown=crawled_page.markdown,
        links=crawled_page.links,
        crawler="crawl4ai",
        probe_markdown=crawled_page.probe_markdown,
    )


def _fetch_url_urllib(url: str, *, crawler_error: str | None = None) -> _FetchedPage:
    normalized_url = url.strip()
    _validate_http_url(normalized_url)

    request = Request(normalized_url, headers=_REQUEST_HEADERS)
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
        html=_decode_response_content(content, charset),
        url=final_url,
        content_type=content_type,
        crawler="urllib",
        crawler_error=crawler_error,
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _decode_response_content(content: bytes, charset: str) -> str:
    candidates: list[str] = []
    for candidate_charset in (charset, "utf-8", "utf-8-sig"):
        if candidate_charset and candidate_charset not in candidates:
            candidates.append(candidate_charset)

    decoded_candidates: list[str] = []
    for candidate_charset in candidates:
        try:
            decoded_candidates.append(content.decode(candidate_charset, errors="strict"))
        except (LookupError, UnicodeDecodeError):
            continue

    if decoded_candidates:
        return min(decoded_candidates, key=_mojibake_score)
    return content.decode(charset or "utf-8", errors="replace")


def _mojibake_score(text: str) -> int:
    suspicious_markers = ("Ã", "Â", "Ä", "Æ", "áº", "á»", "ï¿½", "\ufffd")
    return sum(text.count(marker) for marker in suspicious_markers)


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
    preferred_markdown: str | None = None,
    preferred_parser: str | None = None,
) -> tuple[str, str]:
    fallback_markdown = _parsed_markdown(parsed)
    candidates: list[tuple[str, str]] = [(fallback_markdown, _PARSER_NAME)]
    if preferred_markdown and preferred_markdown.strip():
        candidates.append((preferred_markdown.strip(), preferred_parser or _CRAWL4AI_PARSER_NAME))
    try:
        trafilatura_markdown = extract_markdown_with_trafilatura(
            html,
            source_url=source_url,
        )
    except (ImportError, ModuleNotFoundError, RuntimeError):
        trafilatura_markdown = None
    if trafilatura_markdown is not None:
        candidates.append((trafilatura_markdown, _TRAFILATURA_PARSER_NAME))
    return max(
        candidates,
        key=lambda candidate: _markdown_quality_score(candidate[0], title=parsed.title),
    )


def _append_probe_markdown(markdown: str, probe_markdown: str | None) -> str:
    if not probe_markdown or not probe_markdown.strip():
        return markdown
    if probe_markdown.strip() in markdown:
        return markdown
    return f"{markdown.strip()}\n\n{probe_markdown.strip()}"


def _has_markdown_heading(markdown: str) -> bool:
    return any(re.match(r"^#{1,6}(?!#)\s+\S", line.strip()) for line in markdown.splitlines())


def _markdown_quality_score(markdown: str, *, title: str | None) -> int:
    cleaned = _clean_markdown_noise(markdown)
    text = normalize_space(cleaned)
    token_count = len(re.findall(r"\w+", text))
    heading_count = sum(
        1 for line in cleaned.splitlines() if re.match(r"^#{1,6}(?!#)\s+\S", line.strip())
    )
    image_count = cleaned.count("![")
    price_count = len(re.findall(r"\d{1,3}(?:\.\d{3})+\s*(?:VNĐ|VND)?", cleaned, re.IGNORECASE))
    boilerplate_hits = sum(
        cleaned.lower().count(marker)
        for marker in (
            "cookie",
            "đăng nhập",
            "đăng ký",
            "quên mật khẩu",
            "giỏ hàng",
            "dòng xe quan tâm",
            "mua sắm",
        )
    )
    title_score = 0
    if title and title.strip() and normalize_space(title).lower() in text.lower():
        title_score = 400
    short_content_penalty = 300 if token_count < 20 else 0
    return (
        token_count
        + (heading_count * 80)
        + (price_count * 1000)
        + title_score
        - short_content_penalty
        - (image_count * 8)
        - (boilerplate_hits * 120)
    )


def _build_markdown_aware_chunks(
    *,
    markdown: str,
    source: str,
    source_type: str,
    url: str | None,
    title: str | None,
    fetched_at: str,
) -> list[Chunk]:
    content_hash = short_hash(markdown)
    section_indexes: dict[str, int] = defaultdict(int)
    chunks: list[Chunk] = []
    for markdown_chunk in chunk_markdown_by_sections(
        markdown,
        overlap_paragraphs=_URL_CHUNK_OVERLAP_PARAGRAPHS,
    ):
        section = markdown_chunk.section or "main"
        section_indexes[section] += 1
        chunk_index = section_indexes[section]
        chunk_text = _append_search_aliases(
            markdown_chunk.text,
            title=title,
            source=source,
        )
        chunks.append(
            Chunk(
                chunk_id=build_chunk_id(source_type, source, section, chunk_index),
                text=chunk_text,
                metadata={
                    "source": source,
                    "source_type": source_type,
                    "file_name": None,
                    "url": url,
                    "page": None,
                    "section": section,
                    "section_level": markdown_chunk.section_level,
                    "section_path": list(markdown_chunk.section_path),
                    "title": title,
                    "fetched_at": fetched_at,
                    "content_hash": content_hash,
                    "dedupe_hash": short_hash(normalize_space(chunk_text)),
                    "chunk_index": chunk_index,
                    "chunk_token_count": markdown_chunk.chunk_token_count,
                    "chunk_overlap_paragraphs": _URL_CHUNK_OVERLAP_PARAGRAPHS,
                    "chunking_method": "hybrid-markdown-aware-token-overlap",
                    "semantic_unit": markdown_chunk.semantic_unit,
                },
            )
        )
    return chunks


def _append_search_aliases(text: str, *, title: str | None, source: str) -> str:
    del source
    aliases = _vinfast_model_aliases(" ".join(part for part in (title, text) if part))
    if not aliases:
        return text
    alias_line = "Search aliases: " + ", ".join(aliases)
    if alias_line.lower() in text.lower():
        return text
    return f"{alias_line}\n\n{text}"


def _vinfast_model_aliases(text: str) -> tuple[str, ...]:
    model_numbers = sorted(
        {match.group(1).lstrip("0") for match in _VINFAST_MODEL_RE.finditer(text)}
    )
    aliases: list[str] = []
    for number in model_numbers:
        if not number:
            continue
        aliases.extend(
            [
                f"VF{number}",
                f"VF{number}",
                f"VF{number}",
                f"VF{number}",
                f"VF {number}",
                f"VinFast VF{number}",
                f"VinFast VF {number}",
                f"xe VF{number}",
                f"xe VF {number}",
            ]
        )
    return tuple(aliases)


def _clean_markdown_noise(markdown: str) -> str:
    """Strengthen noise filtering for common web UI boilerplate (config, cookies, legal)."""
    cleaned_lines: list[str] = []
    noise_line_patterns = (
        r"gtm\.js",
        r"googletagmanager",
        r"dataLayer",
        r"^\s*function\s*\(",
        r"^\s*window\.",
        r"Cookie Policy",
        r"Privacy Policy",
        r"Terms of Use",
        r"Legal Disclaimer",
    )
    noise_line_re = re.compile("|".join(noise_line_patterns), flags=re.IGNORECASE)
    for line in markdown.splitlines():
        stripped = line.strip()
        if noise_line_re.search(stripped):
            continue
        if _looks_like_json_config_line(stripped):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n\s*\n", "\n\n", cleaned)
    cleaned = _normalize_price_cards(cleaned)
    return _remove_boilerplate_sections(cleaned.strip())


def _normalize_price_cards(markdown: str) -> str:
    lines = markdown.splitlines()
    normalized_lines: list[str] = []
    index = 0
    while index < len(lines):
        price_card = _price_card_from_lines(lines, index)
        if price_card is None:
            normalized_lines.append(lines[index])
            index += 1
            continue

        normalized_lines.append(price_card[0])
        index = price_card[1]

    normalized = "\n".join(normalized_lines)
    normalized = re.sub(r"\n\s*\n", "\n\n", normalized)
    return normalized


def _price_card_from_lines(lines: list[str], index: int) -> tuple[str, int] | None:
    variant = lines[index].strip()
    if not _looks_like_vehicle_variant(variant):
        return None

    next_index = _next_nonblank_line_index(lines, index + 1)
    if next_index is None or not re.search(r"giá\s+bán\s+từ", lines[next_index], re.IGNORECASE):
        return None

    current_price_index = _next_nonblank_line_index(lines, next_index + 1)
    if current_price_index is None:
        return None
    current_price = _price_value(lines[current_price_index])
    if current_price is None:
        return None

    current_currency_index = _next_nonblank_line_index(lines, current_price_index + 1)
    if current_currency_index is None or not _is_vnd_currency_line(lines[current_currency_index]):
        return None

    old_price_index = _next_nonblank_line_index(lines, current_currency_index + 1)
    if old_price_index is None:
        return None
    old_price = _price_value(lines[old_price_index])
    if old_price is None:
        return None

    old_currency_index = _next_nonblank_line_index(lines, old_price_index + 1)
    if old_currency_index is None or not _is_vnd_currency_line(lines[old_currency_index]):
        return None

    normalized = (
        f"- {variant}: Giá bán từ {current_price} VNĐ; giá niêm yết cũ ~~{old_price} VNĐ~~."
    )
    return normalized, old_currency_index + 1


def _looks_like_vehicle_variant(value: str) -> bool:
    return bool(re.search(r"\bVF\s*-?\s*\d{1,2}\b", value, flags=re.IGNORECASE))


def _next_nonblank_line_index(lines: list[str], start_index: int) -> int | None:
    for index in range(start_index, len(lines)):
        if lines[index].strip():
            return index
    return None


def _price_value(value: str) -> str | None:
    match = re.search(r"\d{1,3}(?:\.\d{3})+", value)
    return match.group(0) if match is not None else None


def _is_vnd_currency_line(value: str) -> bool:
    return normalize_space(value).upper() in {"VND", "VNĐ"}


def _looks_like_json_config_line(line: str) -> bool:
    if not (line.startswith("{") and line.endswith("}")):
        return False
    lowered = line.lower()
    config_markers = (
        '"url"',
        '"route"',
        '"api"',
        '"config"',
        '"token"',
        '"session"',
        '"cookie"',
        '"data"',
    )
    return any(marker in lowered for marker in config_markers)


def _remove_boilerplate_sections(markdown: str) -> str:
    cleaned_lines: list[str] = []
    skip_level: int | None = None
    for line in markdown.splitlines():
        heading_match = re.match(r"^(#{1,6})(?!#)\s+(.+?)\s*$", line.strip())
        if heading_match is not None:
            heading_level = len(heading_match.group(1))
            heading_slug = _heading_slug(heading_match.group(2))
            if heading_slug in _BOILERPLATE_SECTION_SLUGS:
                skip_level = heading_level
                continue
            if skip_level is not None and heading_level <= skip_level:
                skip_level = None
        if skip_level is not None:
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n\s*\n", "\n\n", cleaned)
    return cleaned.strip()


def _heading_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


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
    crawler: str,
    crawler_error: str | None,
    parser_name: str,
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
                    "crawler": crawler,
                    "crawler_error": crawler_error,
                    "parser": parser_name,
                }
            }
        )
        for chunk in chunks
    ]


def _validate_http_url(url: str) -> None:
    parsed_url = urlparse(url.strip())
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("URL ingestion requires an absolute http or https URL.")


def _same_origin_child_urls(
    links: tuple[str, ...],
    *,
    base_url: str,
    max_child_pages: int,
) -> tuple[str, ...]:
    base = urlparse(base_url)
    base_without_fragment = urldefrag(base_url).url.rstrip("/")
    child_urls: list[str] = []
    for link in links:
        absolute_url = urldefrag(urljoin(base_url, link)).url.rstrip("/")
        parsed_link = urlparse(absolute_url)
        if parsed_link.scheme not in {"http", "https"}:
            continue
        if parsed_link.netloc != base.netloc:
            continue
        if absolute_url == base_without_fragment:
            continue
        if parsed_link.path.lower().endswith(".pdf"):
            continue
        child_urls.append(absolute_url)
        if len(dict.fromkeys(child_urls)) >= max_child_pages:
            break
    return tuple(dict.fromkeys(child_urls))


def _dedupe_chunks(chunks: list[Chunk]) -> list[Chunk]:
    seen_text_hashes: set[str] = set()
    deduped_chunks: list[Chunk] = []
    for chunk in chunks:
        text_hash = short_hash(normalize_space(chunk.text))
        if text_hash in seen_text_hashes:
            continue
        seen_text_hashes.add(text_hash)
        deduped_chunks.append(chunk)
    return deduped_chunks


def _raise_if_pdf_url(url: str) -> None:
    parsed_url = urlparse(url.strip())
    if parsed_url.path.lower().endswith(".pdf"):
        raise ValueError("URL ingestion received a PDF URL; route it to PDF ingestion.")


def _raise_if_pdf_response(page: _FetchedPage) -> None:
    if page.content_type == "application/pdf":
        raise ValueError("URL ingestion received a PDF response; route it to PDF ingestion.")
