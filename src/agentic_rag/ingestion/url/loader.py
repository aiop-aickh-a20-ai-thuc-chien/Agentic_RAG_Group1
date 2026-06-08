"""URL ingestion and chunking boundary."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
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
from agentic_rag.ingestion.url.extractor import (
    ExtractedMarkdown,
    extract_markdown_from_html,
    extract_markdown_with_playwright,
    extract_markdown_with_trafilatura,
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
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class _FetchedPage:
    html: str
    url: str
    content_type: str | None = None


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
    use_browser_extractor: bool = True,
) -> list[Chunk]:
    """Fetch, clean, and chunk URL content into shared Chunk objects."""

    return load_url_with_artifacts(
        url,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
        use_browser_extractor=use_browser_extractor,
    ).chunks


def load_url_with_artifacts(
    url: str,
    *,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "url_ingestion",
    use_browser_extractor: bool = True,
) -> LoadedUrlDocument:
    """Fetch, clean, chunk, and expose URL ingestion artifacts."""

    _raise_if_pdf_url(url)
    if use_browser_extractor:
        browser_loaded = _try_load_url_with_browser_extractor(
            url,
            debug_artifact_dir=debug_artifact_dir,
            data_artifact_dir=data_artifact_dir,
            run_id=run_id,
        )
        if browser_loaded is not None:
            return browser_loaded
    page = _fetch_url(url)
    _raise_if_pdf_response(page)
    return load_html_with_artifacts(
        page.html,
        source=page.url,
        source_url=page.url,
        original_url=url,
        final_url=page.url,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
    )


def _try_load_url_with_browser_extractor(
    url: str,
    *,
    debug_artifact_dir: str | Path | None,
    data_artifact_dir: str | Path | None,
    run_id: str,
) -> LoadedUrlDocument | None:
    try:
        extracted = extract_markdown_with_playwright(url)
    except Exception:
        return None
    final_url = extracted.final_url or url
    parsed = (
        parse_html(extracted.rendered_html, base_url=final_url)
        if extracted.rendered_html
        else ParsedHtml(title=extracted.title, sections=())
    )
    return _load_extracted_markdown_with_artifacts(
        extracted=extracted,
        source=final_url,
        source_url=final_url,
        original_url=url,
        final_url=final_url,
        parsed=parsed,
        html=extracted.rendered_html,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
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
) -> LoadedUrlDocument:
    """Clean and chunk one HTML document while exposing persisted artifacts."""

    parsed = parse_html(html, base_url=source_url or source)
    parsed_markdown, parser_name = _extract_markdown(
        html=html,
        parsed=parsed,
        source_url=source_url or source,
    )
    _persist_html_debug_artifacts(
        debug_artifact_dir=debug_artifact_dir,
        source=source,
        html=html,
        parsed_sections="\n\n".join(section.text for section in parsed.sections),
    )

    return _load_extracted_markdown_with_artifacts(
        extracted=ExtractedMarkdown(
            markdown=parsed_markdown,
            parser_name=parser_name,
            title=parsed.title,
        ),
        source=source,
        source_url=source_url,
        original_url=original_url,
        final_url=final_url,
        parsed=parsed,
        html=None,
        debug_artifact_dir=None,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
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
    normalized_url = url.strip()
    parsed_url = urlparse(normalized_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("URL ingestion requires an absolute http or https URL.")

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
        html=content.decode(charset, errors="replace"),
        url=final_url,
        content_type=content_type,
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


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
) -> tuple[str, str]:
    fallback_markdown = _parsed_markdown(parsed)
    extracted = extract_markdown_from_html(html, title=parsed.title, source_url=source_url)
    if extracted is not None and _has_markdown_heading(extracted.markdown):
        return extracted.markdown, extracted.parser_name
    try:
        trafilatura_markdown = extract_markdown_with_trafilatura(
            html,
            source_url=source_url,
        )
    except (ImportError, ModuleNotFoundError, RuntimeError):
        return fallback_markdown, _PARSER_NAME
    if trafilatura_markdown is None:
        return fallback_markdown, _PARSER_NAME
    if not _has_markdown_heading(trafilatura_markdown) and _has_markdown_heading(fallback_markdown):
        return fallback_markdown, _PARSER_NAME
    return trafilatura_markdown, _TRAFILATURA_PARSER_NAME


def _has_markdown_heading(markdown: str) -> bool:
    return any(re.match(r"^#{1,6}(?!#)\s+\S", line.strip()) for line in markdown.splitlines())


def _load_extracted_markdown_with_artifacts(
    *,
    extracted: ExtractedMarkdown,
    source: str,
    source_url: str | None,
    original_url: str | None,
    final_url: str | None,
    parsed: ParsedHtml,
    html: str | None,
    debug_artifact_dir: str | Path | None,
    data_artifact_dir: str | Path | None,
    run_id: str,
) -> LoadedUrlDocument:
    fetched_at = _utc_now()
    canonical_url = parsed.metadata.canonical_url or parsed.metadata.og_url
    if html is not None:
        _persist_html_debug_artifacts(
            debug_artifact_dir=debug_artifact_dir,
            source=source,
            html=html,
            parsed_sections="\n\n".join(section.text for section in parsed.sections),
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
    chunks = _with_extractor_metadata(chunks, extracted=extracted)
    artifacts = persist_ingestion_artifacts(
        data_dir=data_artifact_dir,
        input_type="url" if source_url else "html",
        source=source,
        source_url=source_url,
        original_url=original_url,
        final_url=final_url,
        canonical_url=canonical_url,
        parser=extracted.parser_name,
        run_id=run_id,
        created_at=fetched_at,
        markdown=cleaned_markdown,
        chunks=chunks,
        page_metadata=parsed.metadata,
        assets=parsed.assets,
    )
    return LoadedUrlDocument(markdown=cleaned_markdown, chunks=chunks, artifacts=artifacts)


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
    for markdown_chunk in chunk_markdown_by_sections(markdown, root_title=title):
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
    return cleaned.strip()


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
            }
        )
        for chunk in chunks
    ]


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
        for chunk in chunks
    ]


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
