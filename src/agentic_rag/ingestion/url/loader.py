"""URL ingestion and chunking boundary."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.acquisition import (
    DEFAULT_REQUEST_HEADERS,
    fetch_url,
    reject_pdf_content_type,
    reject_pdf_url,
)
from agentic_rag.ingestion.url.acquisition import (
    FetchedPage as _FetchedPage,
)
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
    normalize_for_content_hash,
    normalize_for_dedupe_hash,
    normalize_space,
    short_hash,
)
from agentic_rag.ingestion.url.dom import detect_semantic_blocks
from agentic_rag.ingestion.url.entities import extract_entities
from agentic_rag.ingestion.url.extractor import (
    ExtractedMarkdown,
    extract_markdown_from_html,
    extract_markdown_with_playwright,
    extract_markdown_with_trafilatura,
)
from agentic_rag.ingestion.url.metadata import enrich_chunks_with_url_metadata
from agentic_rag.ingestion.url.parser import ParsedHtml, parse_html
from agentic_rag.ingestion.url.quality import (
    ParserKind,
    UrlPageProfile,
    UrlQualityGate,
    UrlQualityReport,
    analyze_url_quality,
    attach_quality_gate_metadata,
    attach_quality_metadata,
    better_quality_gate,
    detect_page_profile,
    evaluate_quality_gate,
    should_try_rendered_parser,
)
from agentic_rag.ingestion.url.rendering import RenderOptions, render_url_markdown

_REQUEST_HEADERS = DEFAULT_REQUEST_HEADERS
_PARSER_NAME = "builtin-html-parser"
_TRAFILATURA_PARSER_NAME = "trafilatura-markdown+builtin-html-parser"
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


class LoadedUrlDocument(BaseModel):
    """Parsed URL/text Markdown, generated chunks, and optional artifact paths."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    markdown: str
    chunks: list[Chunk]
    artifacts: IngestionArtifacts | None


@dataclass(frozen=True)
class _LoadedUrlCandidate:
    document: LoadedUrlDocument
    source: str
    source_url: str | None
    original_url: str | None
    final_url: str | None
    canonical_url: str | None
    parser_name: str
    input_type: str
    created_at: str
    parsed: ParsedHtml
    html: str | None
    source_html_stage: str | None
    extracted_markdown: str


def load_url_chunks(
    url: str,
    *,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    render_cache_dir: str | Path | None = None,
    run_id: str = "url_ingestion",
    use_browser_extractor: bool = True,
) -> list[Chunk]:
    """Fetch, clean, and chunk URL content into shared Chunk objects."""

    return load_url_with_artifacts(
        url,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        render_cache_dir=render_cache_dir,
        run_id=run_id,
        use_browser_extractor=use_browser_extractor,
    ).chunks


def load_url_with_artifacts(
    url: str,
    *,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    render_cache_dir: str | Path | None = None,
    run_id: str = "url_ingestion",
    use_browser_extractor: bool = True,
) -> LoadedUrlDocument:
    """Fetch, clean, chunk, and expose URL ingestion artifacts."""

    reject_pdf_url(url)
    try:
        page = _fetch_url(url)
        _raise_if_pdf_response(page)
    except RuntimeError as fetch_error:
        if not use_browser_extractor:
            raise
        profile = _profile_for_fetch_fallback(url)
        browser_candidate, browser_error = _try_load_url_with_browser_extractor(
            url,
            profile=profile,
            render_cache_dir=render_cache_dir,
        )
        if browser_candidate is None:
            raise RuntimeError(
                f"Static fetch failed and browser extraction failed for {url}: "
                f"{fetch_error}; {browser_error}"
            ) from fetch_error
        rendered_gate = _quality_gate_for_candidate(
            browser_candidate,
            parser="rendered",
            profile=profile,
            browser_error=_fetch_fallback_reason(fetch_error, browser_error),
        )
        return _finalize_candidate(
            browser_candidate,
            gate=rendered_gate,
            debug_artifact_dir=debug_artifact_dir,
            data_artifact_dir=data_artifact_dir,
            run_id=run_id,
        )
    profile = detect_page_profile(page.url, page.html)
    static_candidate = _load_html_candidate(
        html=page.html,
        source=page.url,
        source_url=page.url,
        original_url=url,
        final_url=page.url,
    )
    static_gate = _quality_gate_for_candidate(
        static_candidate,
        parser="static",
        profile=profile,
    )
    selected_candidate = static_candidate
    selected_gate = static_gate
    browser_error: str | None = None
    if use_browser_extractor and should_try_rendered_parser(profile, static_gate):
        browser_candidate, browser_error = _try_load_url_with_browser_extractor(
            url,
            profile=profile,
            render_cache_dir=render_cache_dir,
        )
        if browser_candidate is not None:
            rendered_gate = _quality_gate_for_candidate(
                browser_candidate,
                parser="rendered",
                profile=profile,
                browser_error=browser_error,
            )
            selected_gate = better_quality_gate(rendered_gate, static_gate)
            selected_candidate = (
                browser_candidate if selected_gate.parser == "rendered" else static_candidate
            )
        else:
            selected_gate = static_gate.model_copy(
                update={
                    "browser_error": browser_error,
                    "reason": _fallback_reason(static_gate, browser_error),
                }
            )
    elif not use_browser_extractor and profile.requires_rendered_parser:
        selected_gate = static_gate.model_copy(
            update={"reason": f"{static_gate.reason}:browser_extractor_disabled"}
        )
    return _finalize_candidate(
        selected_candidate,
        gate=selected_gate,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
    )


def _try_load_url_with_browser_extractor(
    url: str,
    *,
    profile: UrlPageProfile,
    render_cache_dir: str | Path | None,
) -> tuple[_LoadedUrlCandidate | None, str | None]:
    attempt = render_url_markdown(
        url,
        extractor=extract_markdown_with_playwright,
        options=_render_options_for_profile(profile, render_cache_dir=render_cache_dir),
    )
    if attempt.extracted is None:
        return None, attempt.error
    extracted = attempt.extracted
    final_url = extracted.final_url or url
    parsed = (
        parse_html(extracted.rendered_html, base_url=final_url)
        if extracted.rendered_html
        else ParsedHtml(title=extracted.title, sections=())
    )
    return (
        _load_extracted_markdown_candidate(
            extracted=extracted,
            source=final_url,
            source_url=final_url,
            original_url=url,
            final_url=final_url,
            parsed=parsed,
            html=extracted.rendered_html,
            source_html_stage="rendered_html",
        ),
        attempt.error,
    )


def _profile_for_fetch_fallback(url: str) -> UrlPageProfile:
    profile = detect_page_profile(url, "")
    if profile.requires_rendered_parser:
        return profile
    return profile.model_copy(
        update={
            "page_type": "dynamic_application",
            "requires_rendered_parser": True,
            "latency_budget_seconds": 35,
            "reasons": [*profile.reasons, "static_fetch_failed_requires_render"],
        }
    )


def _render_options_for_profile(
    profile: UrlPageProfile,
    *,
    render_cache_dir: str | Path | None,
) -> RenderOptions:
    return RenderOptions(
        timeout_seconds=profile.latency_budget_seconds,
        wait_until="load",
        cache_dir=Path(render_cache_dir) if render_cache_dir is not None else None,
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

    candidate = _load_html_candidate(
        html=html,
        source=source,
        source_url=source_url,
        original_url=original_url,
        final_url=final_url,
    )
    return _finalize_candidate(
        candidate,
        gate=None,
        debug_artifact_dir=debug_artifact_dir,
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
    return fetch_url(url, headers=_REQUEST_HEADERS)


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


def _augment_low_signal_markdown(markdown: str, *, parsed: ParsedHtml) -> str:
    """Add metadata/asset text when visible body extraction is title-only."""

    if not _is_low_signal_markdown(markdown):
        return markdown
    additions: list[str] = []
    descriptions = _metadata_descriptions(parsed)
    if descriptions:
        additions.extend(["## Page Summary", "", *descriptions, ""])
    asset_text = _meaningful_asset_text(parsed)
    if asset_text:
        additions.extend(["## Visual Content", "", *(f"- {text}" for text in asset_text)])
    if not additions:
        return markdown
    base = markdown.strip()
    supplement = "\n".join(additions).strip()
    return f"{base}\n\n{supplement}" if base else supplement


def _is_low_signal_markdown(markdown: str) -> bool:
    non_heading_text = "\n".join(
        line for line in markdown.splitlines() if not re.match(r"^#{1,6}\s+", line.strip())
    )
    return len(re.findall(r"\w+", non_heading_text, flags=re.UNICODE)) < 12


def _metadata_descriptions(parsed: ParsedHtml) -> list[str]:
    return _dedupe_meaningful_text(
        [parsed.metadata.description, parsed.metadata.og_description],
        min_words=6,
    )


def _meaningful_asset_text(parsed: ParsedHtml) -> list[str]:
    candidates: list[str | None] = []
    for asset in parsed.assets:
        if asset.kind != "image":
            continue
        candidates.extend([asset.alt, asset.title])
    return _dedupe_meaningful_text(candidates, min_words=4)


def _dedupe_meaningful_text(values: list[str | None], *, min_words: int) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = normalize_space(value or "")
        if len(re.findall(r"\w+", text, flags=re.UNICODE)) < min_words:
            continue
        key = normalize_for_dedupe_hash(text)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _load_html_candidate(
    *,
    html: str,
    source: str,
    source_url: str | None,
    original_url: str | None,
    final_url: str | None,
) -> _LoadedUrlCandidate:
    parsed = parse_html(html, base_url=source_url or source)
    parsed_markdown, parser_name = _extract_markdown(
        html=html,
        parsed=parsed,
        source_url=source_url or source,
    )
    parsed_markdown = _augment_low_signal_markdown(parsed_markdown, parsed=parsed)
    return _load_extracted_markdown_candidate(
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
        html=html,
        source_html_stage="static_html" if source_url else "input_html",
    )


def _load_extracted_markdown_candidate(
    *,
    extracted: ExtractedMarkdown,
    source: str,
    source_url: str | None,
    original_url: str | None,
    final_url: str | None,
    parsed: ParsedHtml,
    html: str | None,
    source_html_stage: str | None,
) -> _LoadedUrlCandidate:
    fetched_at = _utc_now()
    canonical_url = parsed.metadata.canonical_url or parsed.metadata.og_url
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
    dom_blocks = detect_semantic_blocks(html) if html is not None else []
    entities = extract_entities(dom_blocks)
    chunks = enrich_chunks_with_url_metadata(
        chunks,
        source_url=source_url,
        original_url=original_url,
        final_url=final_url,
        canonical_url=canonical_url,
        parsed=parsed,
        dom_blocks=dom_blocks,
        entities=entities,
    )
    chunks = _with_extractor_metadata(chunks, extracted=extracted)
    quality_report = analyze_url_quality(cleaned_markdown, chunks)
    chunks = attach_quality_metadata(chunks, quality_report)
    document = LoadedUrlDocument(markdown=cleaned_markdown, chunks=chunks, artifacts=None)
    return _LoadedUrlCandidate(
        document=document,
        source=source,
        source_url=source_url,
        original_url=original_url,
        final_url=final_url,
        canonical_url=canonical_url,
        parser_name=extracted.parser_name,
        input_type="url" if source_url else "html",
        created_at=fetched_at,
        parsed=parsed,
        html=html,
        source_html_stage=source_html_stage,
        extracted_markdown=extracted.markdown,
    )


def _finalize_candidate(
    candidate: _LoadedUrlCandidate,
    *,
    gate: UrlQualityGate | None,
    debug_artifact_dir: str | Path | None,
    data_artifact_dir: str | Path | None,
    run_id: str,
) -> LoadedUrlDocument:
    document = candidate.document
    if gate is not None:
        document = document.model_copy(
            update={"chunks": attach_quality_gate_metadata(document.chunks, gate)}
        )
    if candidate.html is not None:
        _persist_html_debug_artifacts(
            debug_artifact_dir=debug_artifact_dir,
            source=candidate.source,
            html=candidate.html,
            parsed_sections="\n\n".join(section.text for section in candidate.parsed.sections),
        )
    artifacts = persist_ingestion_artifacts(
        data_dir=data_artifact_dir,
        input_type=candidate.input_type,
        source=candidate.source,
        source_url=candidate.source_url,
        original_url=candidate.original_url,
        final_url=candidate.final_url,
        canonical_url=candidate.canonical_url,
        parser=candidate.parser_name,
        run_id=run_id,
        created_at=candidate.created_at,
        markdown=document.markdown,
        chunks=document.chunks,
        page_metadata=candidate.parsed.metadata,
        assets=candidate.parsed.assets,
        source_html=candidate.html,
        source_html_stage=candidate.source_html_stage,
        parsed_sections="\n\n".join(section.text for section in candidate.parsed.sections),
        extracted_markdown=candidate.extracted_markdown,
    )
    return document.model_copy(update={"artifacts": artifacts})


def _quality_gate_for_candidate(
    candidate: _LoadedUrlCandidate,
    *,
    parser: ParserKind,
    profile: UrlPageProfile,
    browser_error: str | None = None,
) -> UrlQualityGate:
    return evaluate_quality_gate(
        parser=parser,
        profile=profile,
        report=_quality_report_from_chunks(candidate.document.chunks),
        chunks=candidate.document.chunks,
        browser_error=browser_error,
    )


def _quality_report_from_chunks(chunks: list[Chunk]) -> UrlQualityReport:
    if not chunks:
        return analyze_url_quality("", [])
    report = chunks[0].metadata.get("url_quality")
    if isinstance(report, dict):
        return UrlQualityReport.model_validate(report)
    return analyze_url_quality("\n\n".join(chunk.text for chunk in chunks), chunks)


def _fallback_reason(gate: UrlQualityGate, browser_error: str | None) -> str:
    if browser_error:
        return f"{gate.reason}:render_failed:{browser_error}"
    return f"{gate.reason}:render_failed"


def _fetch_fallback_reason(fetch_error: RuntimeError, browser_error: str | None) -> str:
    reason = f"static_fetch_failed:{fetch_error}"
    if browser_error:
        return f"{reason}; render_warning:{browser_error}"
    return reason


def _build_markdown_aware_chunks(
    *,
    markdown: str,
    source: str,
    source_type: str,
    title: str | None,
    fetched_at: str,
) -> list[Chunk]:
    page_hash = short_hash(normalize_for_content_hash(markdown))
    section_indexes: dict[str, int] = defaultdict(int)
    chunks: list[Chunk] = []
    for markdown_chunk in chunk_markdown_by_sections(markdown, root_title=title):
        section = markdown_chunk.section or "main"
        section_indexes[section] += 1
        chunk_index = section_indexes[section]
        chunk_id = build_chunk_id(source_type, source, section, chunk_index)
        normalized_chunk_text = normalize_for_content_hash(markdown_chunk.text)
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
                    "updated_date": fetched_at,
                    "updated_date_source": "ingestion_start",
                    "page_hash": page_hash,
                    "content_hash": short_hash(normalized_chunk_text),
                    "dedupe_hash": short_hash(normalize_for_dedupe_hash(markdown_chunk.text)),
                    "normalized_text": normalized_chunk_text,
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
        r"^\s*Danh\s+m(?:ục|á»¥c)\s*$",
        r"^\s*(?:Đăng nhập|ÄÄƒng nháº­p)\s*$",
        r"(?:Đăng nhập|ÄÄƒng nháº­p)",
        r"Đăng ký nhận tin",
        r"Theo dõi chúng tôi",
        r"Danh\s+mục",
        r"^\s*#{1,6}\s*DANH\s+M(?:ỤC|á»¤C)\s+S(?:ẢN|áº¢N)\s+PH(?:ẨM|áº¨M)",
        r"^\s*-?\s*(?:Sản phẩm mới|Phong cách sống)\s*$",
        r"^\s*-?\s*Phụ kiện",
        r"^\s*-?\s*Sạc ô tô điện\s*$",
        r"Sản phẩm mới\s+Phong cách sống",
        r"^\s*Sắp xếp\b",
        r"^\s*Mới nhất\s*$",
        r"^\s*Hiển thị\b",
        r"^\s*Support\s*$",
        r"support\.vn@vinfastauto\.com",
        r"^\s*Hotline\b",
        r"\bhotline\b",
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
    extractor_page_type = str(extracted.normalize_stats.get("content_type", "generic"))
    return [
        chunk.model_copy(
            update={
                "metadata": {
                    **chunk.metadata,
                    "extractor_page_type": extractor_page_type,
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
    reject_pdf_url(url)


def _raise_if_pdf_response(page: _FetchedPage) -> None:
    reject_pdf_content_type(page.content_type)
