"""URL ingestion and chunking boundary."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
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
    MarkdownChunk,
    build_chunk_id,
    build_chunks,
    normalize_space,
    short_hash,
    split_markdown_into_sections,
    split_markdown_paragraphs,
)
from agentic_rag.ingestion.url.crawler import crawl_url_with_crawl4ai
from agentic_rag.ingestion.url.extractor import (
    extract_markdown_with_trafilatura,
    fetch_html_with_trafilatura,
)
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
_CRAWL4AI_BM25_PARSER_NAME = "crawl4ai-bm25-markdown+builtin-html-parser"
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
    bm25_markdown: str | None = None
    structured_markdown: str | None = None
    links: tuple[str, ...] = ()
    crawler: str = "urllib"
    crawler_error: str | None = None
    probe_markdown: str | None = None
    raw_crawler_result: dict[str, Any] | None = None


@dataclass(frozen=True)
class MarkdownCandidate:
    markdown: str
    parser: str
    role: str
    score: int
    token_count: int
    heading_count: int
    price_count: int
    boilerplate_hits: int
    image_count: int
    link_count: int


@dataclass(frozen=True)
class MarkdownSelection:
    markdown: str
    parser: str
    selected_role: str
    fallback_reason: str | None
    candidates: tuple[MarkdownCandidate, ...]


@dataclass(frozen=True)
class LoadedUrlDocument:
    """Parsed URL/text Markdown, generated chunks, and optional artifact paths."""

    markdown: str
    chunks: list[Chunk]
    artifacts: IngestionArtifacts | None
    selection: MarkdownSelection | None = None
    primary_chunks: list[Chunk] | None = None
    raw_crawler_result: dict[str, Any] | None = None


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
        bm25_markdown=page.bm25_markdown,
        structured_markdown=page.structured_markdown,
        crawler=page.crawler,
        crawler_error=page.crawler_error,
        probe_markdown=page.probe_markdown,
        raw_crawler_result=page.raw_crawler_result,
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
                bm25_markdown=child_page.bm25_markdown,
                structured_markdown=child_page.structured_markdown,
                crawler=child_page.crawler,
                crawler_error=child_page.crawler_error,
                probe_markdown=child_page.probe_markdown,
                raw_crawler_result=child_page.raw_crawler_result,
            )
        )

    if not child_documents:
        return loaded

    # Merge chunks
    all_chunks = _with_chunk_adjacency(
        _dedupe_chunks(
            [*loaded.chunks, *(chunk for document in child_documents for chunk in document.chunks)]
        )
    )

    # Aggregate primary chunks for demo comparison across children
    all_primary: list[Chunk] | None = None
    if loaded.primary_chunks is not None or any(d.primary_chunks for d in child_documents):
        primary_list = list(loaded.primary_chunks or [])
        for doc in child_documents:
            primary_list.extend(doc.primary_chunks or [])
        all_primary = _dedupe_chunks(primary_list)

    all_markdown = "\n\n".join(
        document.markdown.strip() for document in [loaded, *child_documents] if document.markdown
    )
    return LoadedUrlDocument(
        markdown=all_markdown,
        chunks=all_chunks,
        artifacts=loaded.artifacts,
        selection=loaded.selection,
        primary_chunks=all_primary,
        raw_crawler_result=loaded.raw_crawler_result,
    )


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
    bm25_markdown: str | None = None,
    structured_markdown: str | None = None,
    crawler: str = "static-html",
    crawler_error: str | None = None,
    probe_markdown: str | None = None,
    raw_crawler_result: dict[str, Any] | None = None,
) -> LoadedUrlDocument:
    """Clean and chunk one HTML document while exposing persisted artifacts."""

    parsed = parse_html(html, base_url=source_url or source)
    fetched_at = _utc_now()
    selection = _extract_markdown(
        html=html,
        parsed=parsed,
        source_url=source_url or source,
        preferred_markdown=preferred_markdown,
        preferred_parser=preferred_parser,
        bm25_markdown=bm25_markdown,
    )
    parsed_markdown = selection.markdown
    parser_name = selection.parser
    parser_name = _combined_parser_name(
        parser_name,
        crawler=crawler,
        structured_markdown=structured_markdown,
        probe_markdown=probe_markdown,
    )

    primary_candidate = next(
        (c for c in selection.candidates if c.role == "crawl4ai_primary"), None
    )
    primary_chunks: list[Chunk] | None = None

    canonical_url = parsed.metadata.canonical_url or parsed.metadata.og_url
    _persist_html_debug_artifacts(
        debug_artifact_dir=debug_artifact_dir,
        source=source,
        html=html,
        parsed_sections="\n\n".join(section.text for section in parsed.sections),
    )

    source_type = "url" if source_url else "html"
    cleaned_markdown = _clean_markdown_noise(
        _append_supplemental_markdown(
            parsed_markdown,
            structured_markdown,
            probe_markdown,
        )
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
        selection=selection,
    )
    chunks = _with_chunk_adjacency(_dedupe_chunks(chunks))

    # If a fallback was used, generate chunks for the primary to allow comparison in demo
    if primary_candidate and selection.selected_role != "crawl4ai_primary":
        primary_chunks = _build_markdown_aware_chunks(
            markdown=_clean_markdown_noise(primary_candidate.markdown),
            source=source,
            source_type=source_type,
            url=source_url,
            title=parsed.title,
            fetched_at=fetched_at,
        )
        primary_chunks = _with_html_metadata(
            primary_chunks,
            original_url=original_url,
            final_url=final_url,
            canonical_url=canonical_url,
            parsed=parsed,
            crawler=crawler,
            crawler_error=crawler_error,
            parser_name=primary_candidate.parser,
            selection=selection,
        )

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
    return LoadedUrlDocument(
        markdown=cleaned_markdown,
        chunks=chunks,
        artifacts=artifacts,
        selection=selection,
        primary_chunks=primary_chunks,
        raw_crawler_result=raw_crawler_result,
    )


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
        crawl4ai_error = f"{type(exc).__name__}: {exc}"
        try:
            return _fetch_url_trafilatura(url, crawler_error=crawl4ai_error)
        except Exception as trafilatura_exc:
            crawler_error = (
                f"{crawl4ai_error}; trafilatura fetch failed: "
                f"{type(trafilatura_exc).__name__}: {trafilatura_exc}"
            )
            return _fetch_url_urllib(url, crawler_error=crawler_error)
    if _crawl4ai_page_is_title_only(crawled_page):
        title_only_error = "Crawl4AI returned title-only content"
        try:
            return _fetch_url_trafilatura(url, crawler_error=title_only_error)
        except Exception as trafilatura_exc:
            crawler_error = (
                f"{title_only_error}; trafilatura fetch failed: "
                f"{type(trafilatura_exc).__name__}: {trafilatura_exc}"
            )
            return _fetch_url_urllib(url, crawler_error=crawler_error)
    return _FetchedPage(
        html=crawled_page.html,
        url=crawled_page.url,
        content_type=crawled_page.content_type,
        markdown=crawled_page.markdown,
        bm25_markdown=crawled_page.bm25_markdown,
        structured_markdown=crawled_page.structured_markdown,
        links=crawled_page.links,
        crawler="crawl4ai",
        probe_markdown=crawled_page.probe_markdown,
        raw_crawler_result=crawled_page.raw_result,
    )


def _crawl4ai_page_is_title_only(page: object) -> bool:
    markdown = normalize_space(str(getattr(page, "markdown", "") or ""))
    bm25_markdown = normalize_space(str(getattr(page, "bm25_markdown", "") or ""))
    structured_markdown = normalize_space(str(getattr(page, "structured_markdown", "") or ""))
    probe_markdown = normalize_space(str(getattr(page, "probe_markdown", "") or ""))
    if markdown or bm25_markdown or structured_markdown or probe_markdown:
        return False
    html = str(getattr(page, "html", "") or "")
    try:
        parsed = parse_html(html, base_url=str(getattr(page, "url", "") or ""))
    except Exception:
        return False
    text = normalize_space("\n".join(section.text for section in parsed.sections))
    if not text:
        return True
    title = normalize_space(parsed.title or "")
    return text == title or (len(text) < 120 and bool(title) and text in title)


def _fetch_url_trafilatura(url: str, *, crawler_error: str | None = None) -> _FetchedPage:
    normalized_url = url.strip()
    _validate_http_url(normalized_url)
    html = fetch_html_with_trafilatura(normalized_url)
    if not html:
        raise RuntimeError("trafilatura returned empty HTML")
    return _FetchedPage(
        html=html,
        url=normalized_url,
        content_type="text/html",
        crawler="trafilatura",
        crawler_error=crawler_error,
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
    bm25_markdown: str | None = None,
) -> MarkdownSelection:
    return _select_markdown(
        html=html,
        parsed=parsed,
        source_url=source_url,
        preferred_markdown=preferred_markdown,
        preferred_parser=preferred_parser,
        bm25_markdown=bm25_markdown,
    )


def _select_markdown(
    *,
    html: str,
    parsed: ParsedHtml,
    source_url: str | None,
    preferred_markdown: str | None,
    preferred_parser: str | None,
    bm25_markdown: str | None,
) -> MarkdownSelection:
    fallback_markdown = _parsed_markdown(parsed)
    candidates = [
        _build_markdown_candidate(
            fallback_markdown,
            parser=_PARSER_NAME,
            role="builtin_fallback",
            title=parsed.title,
        )
    ]
    if preferred_markdown and preferred_markdown.strip():
        candidates.append(
            _build_markdown_candidate(
                preferred_markdown.strip(),
                parser=preferred_parser or _CRAWL4AI_PARSER_NAME,
                role="crawl4ai_primary",
                title=parsed.title,
            )
        )
    if bm25_markdown and bm25_markdown.strip():
        candidates.append(
            _build_markdown_candidate(
                bm25_markdown.strip(),
                parser=_CRAWL4AI_BM25_PARSER_NAME,
                role="crawl4ai_bm25_filter",
                title=parsed.title,
            )
        )
    try:
        trafilatura_markdown = _extract_trafilatura_markdown(
            html,
            source_url=source_url,
        )
    except (ImportError, ModuleNotFoundError, RuntimeError):
        trafilatura_markdown = None
    if trafilatura_markdown is not None:
        candidates.append(
            _build_markdown_candidate(
                trafilatura_markdown,
                parser=_TRAFILATURA_PARSER_NAME,
                role="trafilatura_quality_check",
                title=parsed.title,
            )
        )

    selected, fallback_reason = _select_primary_or_fallback(candidates)
    return MarkdownSelection(
        markdown=selected.markdown,
        parser=selected.parser,
        selected_role=selected.role,
        fallback_reason=fallback_reason,
        candidates=tuple(candidates),
    )


def _extract_trafilatura_markdown(html: str, *, source_url: str | None) -> str | None:
    extracted = extract_markdown_with_trafilatura(html, source_url=source_url)
    if extracted is None:
        return None
    if isinstance(extracted, str):
        return extracted
    markdown = getattr(extracted, "markdown", None)
    return markdown if isinstance(markdown, str) else None


def _combined_parser_name(
    parser_name: str,
    *,
    crawler: str,
    structured_markdown: str | None,
    probe_markdown: str | None,
) -> str:
    parts = [parser_name]
    if crawler == "crawl4ai" and not parser_name.startswith("crawl4ai"):
        parts.append("crawl4ai-rendered-html")
    if structured_markdown and structured_markdown.strip():
        parts.append("structured-data")
    if probe_markdown and probe_markdown.strip():
        parts.append("interactive-probe")
    return "+".join(dict.fromkeys(parts))


def _build_markdown_candidate(
    markdown: str,
    *,
    parser: str,
    role: str,
    title: str | None,
) -> MarkdownCandidate:
    quality = _markdown_quality(markdown, title=title)
    return MarkdownCandidate(
        markdown=markdown,
        parser=parser,
        role=role,
        score=quality["score"],
        token_count=quality["token_count"],
        heading_count=quality["heading_count"],
        price_count=quality["price_count"],
        boilerplate_hits=quality["boilerplate_hits"],
        image_count=quality["image_count"],
        link_count=quality["link_count"],
    )


def _select_primary_or_fallback(
    candidates: list[MarkdownCandidate],
) -> tuple[MarkdownCandidate, str | None]:
    primary = next(
        (candidate for candidate in candidates if candidate.role == "crawl4ai_primary"), None
    )
    best = max(candidates, key=lambda candidate: candidate.score)
    if primary is None:
        return best, None

    cleaner = _cleaner_quality_fallback(primary, candidates)
    if cleaner is not None:
        reason = "content_quality_selected_for_lower_noise"
        if cleaner.role == "trafilatura_quality_check":
            reason = "trafilatura_quality_check_selected_for_lower_noise"
        elif cleaner.role == "crawl4ai_bm25_filter":
            reason = "crawl4ai_bm25_filter_selected_for_lower_noise"
        return cleaner, reason

    if _crawl4ai_primary_is_usable(primary, best):
        return primary, None

    reason = "crawl4ai_primary_quality_check_failed"
    if best.role == "trafilatura_quality_check":
        reason = "trafilatura_quality_check_selected_as_fallback"
    elif best.role == "crawl4ai_bm25_filter":
        reason = "crawl4ai_bm25_filter_selected_as_fallback"
    return best, reason


def _crawl4ai_primary_is_usable(
    primary: MarkdownCandidate,
    best: MarkdownCandidate,
) -> bool:
    if best is primary:
        return True
    if _is_image_heavy_candidate(primary):
        return False
    if primary.token_count >= 80 and primary.boilerplate_hits <= 5:
        return best.score < primary.score + 900
    if primary.token_count >= 20 and primary.price_count > 0:
        return best.score < primary.score + 1200
    return False


def _cleaner_quality_fallback(
    primary: MarkdownCandidate,
    candidates: list[MarkdownCandidate],
) -> MarkdownCandidate | None:
    cleaner_candidates = [
        candidate
        for candidate in candidates
        if candidate is not primary
        and candidate.role
        in {"trafilatura_quality_check", "builtin_fallback", "crawl4ai_bm25_filter"}
        and _candidate_has_enough_signal(candidate, primary)
        and _candidate_is_materially_cleaner(candidate, primary)
    ]
    if not cleaner_candidates:
        return None
    return max(cleaner_candidates, key=lambda candidate: candidate.score)


def _candidate_has_enough_signal(
    candidate: MarkdownCandidate,
    primary: MarkdownCandidate,
) -> bool:
    if candidate.token_count < 80 and candidate.price_count == 0:
        return False
    minimum_tokens = 30 if candidate.price_count > 0 else 80
    if candidate.token_count < max(minimum_tokens, int(primary.token_count * 0.10)):
        return False
    if primary.price_count > 0 and candidate.price_count < max(1, int(primary.price_count * 0.4)):
        return False
    return candidate.score >= primary.score - 20000


def _candidate_is_materially_cleaner(
    candidate: MarkdownCandidate,
    primary: MarkdownCandidate,
) -> bool:
    if primary.boilerplate_hits - candidate.boilerplate_hits >= 2:
        return True
    return (
        _is_image_heavy_candidate(primary) and candidate.image_count * 3 + 10 <= primary.image_count
    )


def _is_image_heavy_candidate(candidate: MarkdownCandidate) -> bool:
    if candidate.image_count < 20:
        return False
    return candidate.image_count > candidate.heading_count + 12


def _append_supplemental_markdown(markdown: str, *supplements: str | None) -> str:
    combined = markdown.strip()
    for supplement in supplements:
        if not supplement or not supplement.strip():
            continue
        cleaned_supplement = supplement.strip()
        if cleaned_supplement in combined:
            continue
        combined = f"{combined}\n\n{cleaned_supplement}" if combined else cleaned_supplement
    return combined


def _has_markdown_heading(markdown: str) -> bool:
    return any(re.match(r"^#{1,6}(?!#)\s+\S", line.strip()) for line in markdown.splitlines())


def _markdown_quality_score(markdown: str, *, title: str | None) -> int:
    return _markdown_quality(markdown, title=title)["score"]


def _markdown_quality(markdown: str, *, title: str | None) -> dict[str, int]:
    cleaned = _clean_markdown_noise(markdown)
    text = normalize_space(cleaned)
    token_count = len(re.findall(r"\w+", text))
    heading_count = sum(
        1 for line in cleaned.splitlines() if re.match(r"^#{1,6}(?!#)\s+\S", line.strip())
    )
    image_count = cleaned.count("![")
    link_count = len(re.findall(r"\[[^\]]+\]\([^)]+\)", cleaned))
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
    source_type = "url" if source_url else "html"
    title = extracted.title or parsed.title
    cleaned_markdown = _clean_markdown_noise(extracted.markdown)
    chunks = _build_markdown_aware_chunks(
        markdown=cleaned_markdown,
        source=source,
        source_type=source_type,
        title=title,
        fetched_at=fetched_at,
    )
    chunks = _with_html_metadata(
        chunks,
        source_url=source_url,
        original_url=original_url,
        final_url=final_url,
        canonical_url=canonical_url,
        parsed=parsed,
    )
    return {
        "score": score,
        "token_count": token_count,
        "heading_count": heading_count,
        "price_count": price_count,
        "boilerplate_hits": boilerplate_hits,
        "image_count": image_count,
        "link_count": link_count,
    }


def _build_markdown_aware_chunks(
    *,
    markdown: str,
    source: str,
    source_type: str,
    title: str | None,
    fetched_at: str,
) -> list[Chunk]:
    content_hash = short_hash(markdown)
    section_indexes: dict[str, int] = defaultdict(int)
    chunks: list[Chunk] = []
    for markdown_chunk in _chunk_markdown_for_url(markdown):
        section = markdown_chunk.section or "main"
        section_indexes[section] += 1
        chunk_index = section_indexes[section]
        chunk_id = build_chunk_id(source_type, source, section, chunk_index)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=markdown_chunk.text,
                metadata={
                    "chunk_id": chunk_id,
                    "source": source,
                    "source_type": source_type,
                    "title": title,
                    "section": section,
                    "section_level": markdown_chunk.section_level,
                    "section_path": list(markdown_chunk.section_path),
                    "fetched_at": fetched_at,
                    "content_hash": content_hash,
                    "chunk_token_count": markdown_chunk.chunk_token_count,
                    **markdown_chunk.metadata,
                },
            )
        )
    return chunks


def _chunk_markdown_for_url(markdown: str) -> list[MarkdownChunk]:
    markdown_chunks: list[MarkdownChunk] = []
    for section in split_markdown_into_sections(markdown):
        section_text = section.text.strip()
        if not section_text:
            continue
        section_path = tuple(section.path)
        section_title = section.title or (section_path[-1] if section_path else "main")
        section_level = section.level or 1
        parts = split_markdown_paragraphs(
            section_text,
            overlap_paragraphs=_URL_CHUNK_OVERLAP_PARAGRAPHS,
        )
        for part_index, part in enumerate(parts or [section_text], start=1):
            chunk_text = _section_chunk_text(
                title=section_title,
                level=section_level,
                text=part,
            )
            markdown_chunks.append(
                MarkdownChunk(
                    section=section_title,
                    text=chunk_text,
                    metadata={
                        "full_path": list(section_path),
                        "depth": len(section_path),
                        "part_index": part_index,
                        "part_total": len(parts) if parts else 1,
                        "n_chars": len(part),
                    },
                    section_level=section_level,
                    section_path=section_path,
                    chunk_token_count=len(re.findall(r"\w+", part)),
                    semantic_unit="url_markdown_section_paragraph",
                )
            )
    if markdown_chunks:
        return markdown_chunks
    stripped_markdown = markdown.strip()
    if not stripped_markdown:
        return []
    return [
        MarkdownChunk(
            section="main",
            text=stripped_markdown,
            metadata={
                "full_path": ["main"],
                "depth": 1,
                "part_index": 1,
                "part_total": 1,
                "n_chars": len(stripped_markdown),
            },
            section_level=0,
            section_path=("main",),
            chunk_token_count=len(re.findall(r"\w+", stripped_markdown)),
            semantic_unit="url_markdown_document_fallback",
        )
    ]


def _section_chunk_text(*, title: str | None, level: int, text: str) -> str:
    stripped_text = text.strip()
    if not title:
        return stripped_text
    heading = f"{'#' * max(1, min(level, 6))} {title}"
    if stripped_text.startswith(heading):
        return stripped_text
    return f"{heading}\n\n{stripped_text}".strip()


def _chunk_content_origin(section_path: list[str]) -> str:
    if section_path and section_path[0] == "Probed Interactive State":
        return "interactive_probe"
    if section_path and section_path[0] == "Structured Page Data":
        return "structured_parse"
    return "document"


def _probe_parent_section(section_path: list[str], content_origin: str) -> str | None:
    if content_origin != "interactive_probe":
        return None
    return section_path[1] if len(section_path) > 1 else None


def _probe_state_label(section: str, content_origin: str) -> str | None:
    if content_origin != "interactive_probe":
        return None
    return section


def _with_chunk_adjacency(chunks: list[Chunk]) -> list[Chunk]:
    grouped_indexes: dict[str, list[int]] = defaultdict(list)
    for index, chunk in enumerate(chunks):
        grouped_indexes[str(chunk.metadata.get("chunk_group_id", ""))].append(index)

    updated_chunks = list(chunks)
    for indexes in grouped_indexes.values():
        group_size = len(indexes)
        for position, chunk_index in enumerate(indexes):
            chunk = updated_chunks[chunk_index]
            previous_chunk_id = (
                updated_chunks[indexes[position - 1]].chunk_id if position > 0 else None
            )
            next_chunk_id = (
                updated_chunks[indexes[position + 1]].chunk_id
                if position < group_size - 1
                else None
            )
            updated_chunks[chunk_index] = chunk.model_copy(
                update={
                    "metadata": {
                        **chunk.metadata,
                        "chunk_group_index": position + 1,
                        "chunk_group_size": group_size,
                        "previous_chunk_id": previous_chunk_id,
                        "next_chunk_id": next_chunk_id,
                        "is_continuation": position > 0,
                        "continues_to_next": next_chunk_id is not None,
                    }
                }
            )
    return updated_chunks


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
                f"VF {number}",
                f"VinFast VF{number}",
                f"VinFast VF {number}",
                f"xe VF{number}",
                f"xe VF {number}",
            ]
        )
    return tuple(dict.fromkeys(aliases))


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
    cleaned = _normalize_product_price_links(cleaned)
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


def _normalize_product_price_links(markdown: str) -> str:
    normalized_lines = [_product_price_link_line(line) or line for line in markdown.splitlines()]
    normalized = "\n".join(normalized_lines)
    return re.sub(r"\n\s*\n", "\n\n", normalized)


def _product_price_link_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.count("[") != 1:
        return None
    match = re.fullmatch(
        r"\[\s*(?P<label>.+?)\s+(?P<price>\d{1,3}(?:\.\d{3})+)\s*(?P<currency>VNĐ|VND)\s*\]"
        r"\((?P<url>[^\s)]+)(?:\s+\"[^\"]*\")?\)",
        stripped,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None

    label = normalize_space(match.group("label"))
    if not label or len(label) > 120 or label.startswith("!"):
        return None
    price = match.group("price")
    currency = _normalize_currency(match.group("currency"))
    url = match.group("url")
    return f"- {label}: giá bán hiện tại / current price {price} {currency}. Link: {url}"


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


def _normalize_currency(value: str) -> str:
    normalized = normalize_space(value).upper()
    return "VND" if normalized == "VND" else "VNĐ"


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
    source_url: str | None,
    original_url: str | None,
    final_url: str | None,
    canonical_url: str | None,
    parsed: ParsedHtml,
    crawler: str,
    crawler_error: str | None,
    parser_name: str,
    selection: MarkdownSelection,
) -> list[Chunk]:
    best_url = canonical_url or final_url or source_url or original_url
    return [
        chunk.model_copy(
            update={
                "metadata": {
                    **chunk.metadata,
                    "url": best_url,
                    "domain": _extract_domain(best_url),
                    "original_url": original_url,
                    "canonical_url": canonical_url,
                    "language": parsed.metadata.language,
                    "author": parsed.metadata.author,
                    "published_at": parsed.metadata.published_at,
                }
            )
        )
    return updated_chunks


def _with_extractor_metadata(
    chunks: list[Chunk],
    *,
    extracted: ExtractedMarkdown,
) -> list[Chunk]:
    page_type = str(extracted.normalize_stats.get("content_type", "generic"))
    return [
        chunk.model_copy(
            update={
                "metadata": {
                    **chunk.metadata,
                    "page_type": page_type,
                    "is_product": bool(extracted.product),
                }
            }
        )
        if len(references) >= 5:
            break
    return references


def _reference_words(text: str) -> set[str]:
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "cua",
        "cho",
        "mau",
        "hinh",
        "anh",
        "xe",
        "vinfast",
    }
    return {word for word in re.findall(r"[a-zA-Z0-9]{3,}", text.lower()) if word not in stop_words}


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


def _extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(url).netloc or None


def _raise_if_pdf_url(url: str) -> None:
    parsed_url = urlparse(url.strip())
    if parsed_url.path.lower().endswith(".pdf"):
        raise ValueError("URL ingestion received a PDF URL; route it to PDF ingestion.")


def _raise_if_pdf_response(page: _FetchedPage) -> None:
    if page.content_type == "application/pdf":
        raise ValueError("URL ingestion received a PDF response; route it to PDF ingestion.")
