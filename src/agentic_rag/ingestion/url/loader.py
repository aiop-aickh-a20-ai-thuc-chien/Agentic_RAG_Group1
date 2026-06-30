"""URL ingestion and chunking boundary."""

from __future__ import annotations

import json
import re
from collections import defaultdict
# dataclass import removed
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.metadata import infer_source_type, normalize_metadata
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
    MarkdownChunk,
    build_chunk_id,
    build_chunks,
    chunk_markdown_by_sections,
    normalize_for_content_hash,
    normalize_for_dedupe_hash,
    normalize_space,
    short_hash,
)
from agentic_rag.ingestion.url.dom import (
    VisualEvidenceSource,
    VisualSemanticsResult,
    append_structure_aware_markdown,
    append_visual_semantics_markdown,
    detect_semantic_blocks,
    extract_visual_semantics,
)
from agentic_rag.ingestion.url.entities import (
    extract_entities,
    filter_blocks_for_primary_entity,
    infer_primary_page_entity,
)
from agentic_rag.ingestion.url.extractor import (
    ExtractedMarkdown,
    extract_markdown_from_html,
    extract_markdown_with_crawlee,
    extract_markdown_with_playwright,
    extract_markdown_with_trafilatura,
)
from agentic_rag.ingestion.url.interactions import (
    InteractionCaptureFunction,
    InteractionOptions,
    load_url_interactions_with_artifacts,
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
from agentic_rag.ingestion.url.rendering import (
    RenderAttempt,
    RenderOptions,
    render_url_markdown,
)

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


class _LoadedUrlCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

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
    visual_semantics: VisualSemanticsResult


def load_url_chunks(
    url: str,
    *,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    render_cache_dir: str | Path | None = None,
    run_id: str = "url_ingestion",
    use_browser_extractor: bool = True,
    include_interactions: bool = False,
    interaction_options: InteractionOptions | None = None,
    interaction_capture: InteractionCaptureFunction | None = None,
) -> list[Chunk]:
    """Fetch, clean, and chunk URL content into shared Chunk objects."""

    return load_url_with_artifacts(
        url,
        debug_artifact_dir=debug_artifact_dir,
        data_artifact_dir=data_artifact_dir,
        render_cache_dir=render_cache_dir,
        run_id=run_id,
        use_browser_extractor=use_browser_extractor,
        include_interactions=include_interactions,
        interaction_options=interaction_options,
        interaction_capture=interaction_capture,
    ).chunks


def load_url_with_artifacts(
    url: str,
    *,
    debug_artifact_dir: str | Path | None = None,
    data_artifact_dir: str | Path | None = None,
    render_cache_dir: str | Path | None = None,
    run_id: str = "url_ingestion",
    use_browser_extractor: bool = True,
    include_interactions: bool = False,
    interaction_options: InteractionOptions | None = None,
    interaction_capture: InteractionCaptureFunction | None = None,
) -> LoadedUrlDocument:
    """Fetch, clean, chunk, and expose URL ingestion artifacts."""

    # TODO [guide_2/TODO_Gemini.md §3b – include_interactions flag passthrough]:
    # The `include_interactions` flag is accepted here but must also be plumbed
    # through to `integrate_url()` in the integration pipeline so callers of the
    # integration boundary can toggle dynamic capture without touching the loader.
    # Reference: guide_2/TODO_Gemini.md Action Item 3
    #
    # TODO [guide_2/vinfast_pipeline_todo §3 – Scheduler ownership]:
    # A `daily_scheduler()` APScheduler job (running at 02:00 daily) should call
    # this function for each VinFast URL. The scheduler is NOT started here.
    # The deployment owner must decide: API process, separate worker, or infra cron.
    # Running multiple replicas without coordination will cause duplicate ingests.
    # Reference: guide_2/missing implementation.md §Chuưa nối vào production entry point

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
        return _with_optional_interaction_chunks(
            _finalize_candidate(
                browser_candidate,
                gate=rendered_gate,
                debug_artifact_dir=debug_artifact_dir,
                data_artifact_dir=data_artifact_dir,
                run_id=run_id,
            ),
            url=url,
            data_artifact_dir=data_artifact_dir,
            run_id=run_id,
            enabled=include_interactions,
            options=interaction_options,
            capture=interaction_capture,
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
    render_error: str | None = None
    if use_browser_extractor and should_try_rendered_parser(profile, static_gate):
        browser_candidate, render_error = _try_load_url_with_browser_extractor(
            url,
            profile=profile,
            render_cache_dir=render_cache_dir,
        )
        if browser_candidate is not None:
            rendered_gate = _quality_gate_for_candidate(
                browser_candidate,
                parser="rendered",
                profile=profile,
                browser_error=render_error,
            )
            selected_gate = better_quality_gate(rendered_gate, static_gate)
            selected_candidate = (
                browser_candidate if selected_gate.parser == "rendered" else static_candidate
            )
        else:
            selected_gate = static_gate.model_copy(
                update={
                    "browser_error": render_error,
                    "reason": _fallback_reason(static_gate, render_error),
                }
            )
    elif not use_browser_extractor and profile.requires_rendered_parser:
        selected_gate = static_gate.model_copy(
            update={"reason": f"{static_gate.reason}:browser_extractor_disabled"}
        )
    VISUAL_FALLBACK_THRESHOLD = 2.0
    if getattr(selected_gate, "quality_score", 1.0) < VISUAL_FALLBACK_THRESHOLD:
        try:
            from agentic_rag.ingestion.visual_pipeline import visual_ingest
            from agentic_rag.core.contracts import Chunk
            import tempfile
            
            # Use visual pipeline to extract structured markdown directly from screenshots
            cache_dir = render_cache_dir / "visual_tiles" if render_cache_dir else Path(tempfile.gettempdir()) / "visual_tiles"
            visual_md = visual_ingest(url, cache_dir)
            
            if visual_md.strip():
                # Append the visual markdown as a new chunk
                from agentic_rag.ingestion.url.chunking import short_hash
                visual_chunk = Chunk(
                    chunk_id=f"url_visual_{short_hash(url)}",
                    text=f"## [Visual Extraction]\n\n{visual_md}",
                    metadata=selected_candidate.chunks[0].metadata if selected_candidate.chunks else {}
                )
                selected_candidate.chunks.append(visual_chunk)
                selected_candidate.extracted_markdown += f"\n\n## [Visual Extraction]\n\n{visual_md}"
                
        except Exception as e:
            import logging
            logging.warning(f"Visual fallback failed: {e}")



    return _with_optional_interaction_chunks(
        _finalize_candidate(
            selected_candidate,
            gate=selected_gate,
            debug_artifact_dir=debug_artifact_dir,
            data_artifact_dir=data_artifact_dir,
            run_id=run_id,
        ),
        url=url,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
        enabled=include_interactions,
        options=interaction_options,
        capture=interaction_capture,
    )


def _try_load_url_with_browser_extractor(
    url: str,
    *,
    profile: UrlPageProfile,
    render_cache_dir: str | Path | None,
) -> tuple[_LoadedUrlCandidate | None, str | None]:
    attempt = _try_render_with_crawlee_first(
        url,
        profile=profile,
        render_cache_dir=render_cache_dir,
    )
    if attempt.extracted is None:
        return None, attempt.error
    extracted = attempt.extracted
    return _candidate_from_rendered_extraction(url=url, extracted=extracted), attempt.error


def _try_render_with_crawlee_first(
    url: str,
    *,
    profile: UrlPageProfile,
    render_cache_dir: str | Path | None,
) -> RenderAttempt:
    errors: list[str] = []
    if profile.requires_rendered_parser:
        crawlee_attempt = render_url_markdown(
            url,
            extractor=extract_markdown_with_crawlee,
            options=_render_options_for_profile(
                profile,
                render_cache_dir=render_cache_dir,
                unbounded=True,
            ),
        )
        if crawlee_attempt.extracted is not None:
            return crawlee_attempt
        if crawlee_attempt.error:
            errors.append(f"crawlee: {crawlee_attempt.error}")
    playwright_attempt = render_url_markdown(
        url,
        extractor=extract_markdown_with_playwright,
        options=_render_options_for_profile(profile, render_cache_dir=render_cache_dir),
    )
    if errors and playwright_attempt.error:
        # TODO [guide_2/vinfast_pipeline_todo §2 – Log failed URLs]:
        # Append `{"url": url, "error": ..., "timestamp": ...}` to
        # `failed_urls.jsonl` (in `data_artifact_dir` or a configured path)
        # so the scheduler can retry them after 24h.
        # Reference: guide_2/vinfast_pipeline_todo (1).md §2
        return playwright_attempt.model_copy(
            update={"error": "; ".join([*errors, f"playwright: {playwright_attempt.error}"])}
        )
    if errors and playwright_attempt.extracted is not None:
        return playwright_attempt.model_copy(update={"retry_errors": errors})
    return playwright_attempt


def _candidate_from_rendered_extraction(
    *,
    url: str,
    extracted: ExtractedMarkdown,
) -> _LoadedUrlCandidate:
    final_url = extracted.final_url or url
    parsed = (
        parse_html(extracted.rendered_html, base_url=final_url)
        if extracted.rendered_html
        else ParsedHtml(title=extracted.title, sections=())
    )
    return _load_extracted_markdown_candidate(
        extracted=extracted,
        source=final_url,
        source_url=final_url,
        original_url=url,
        final_url=final_url,
        parsed=parsed,
        html=extracted.rendered_html,
        source_html_stage="rendered_html",
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
    unbounded: bool = False,
) -> RenderOptions:
    return RenderOptions(
        timeout_seconds=None if unbounded else profile.latency_budget_seconds,
        wait_until="load",
        retry_on_failure=not unbounded,
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
    ingestion_at = _utc_now()
    chunks = build_chunks(
        text=cleaned_text,
        source=source,
        source_type=infer_source_type(source),
        section="main",
        url=None,
        title=None,
        ingestion_at=ingestion_at,
        chunk_id_prefix="text",
    )
    chunks = [
        chunk.model_copy(update={"metadata": normalize_metadata(dict(chunk.metadata))})
        for chunk in chunks
    ]
    persist_ingestion_artifacts(
        data_dir=data_artifact_dir,
        input_type="text",
        source=source,
        source_url=None,
        parser="plain-text",
        run_id=run_id,
        created_at=ingestion_at,
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


def _extract_next_data_layer(html: str) -> dict[str, Any] | None:
    if not html:
        return None
    # 1. Look for <script id="__NEXT_DATA__">...</script>
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass
    # 2. Look for window.__INITIAL_STATE__
    match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass
    # 3. Look for window.__NUXT__
    match = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\});', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass
    return None


def _traverse_and_extract_next_data(data: Any, results: dict[str, Any] | None = None) -> dict[str, Any]:
    if results is None:
        results = {
            "model_name": None,
            "editions": {},
            "colors": {"standard": [], "premium": []},
            "prices": {}
        }
    if isinstance(data, dict):
        model_val = data.get("modelName") or data.get("model_name") or data.get("modelCode")
        if isinstance(model_val, str) and not results["model_name"]:
            from agentic_rag.ingestion.url.entities.extractor import _MODEL_RE
            if _MODEL_RE.search(model_val):
                results["model_name"] = model_val
        
        price_val = data.get("price") or data.get("basePrice") or data.get("priceVnd") or data.get("sellingPrice")
        if price_val and model_val:
            results["prices"][str(model_val)] = str(price_val)
            
        variant_val = data.get("variant") or data.get("edition") or data.get("trim")
        if variant_val and model_val:
            results["editions"][str(model_val)] = {"price": str(price_val)} if price_val else {}

        color_list = data.get("colors") or data.get("colorList") or data.get("optionColors")
        if isinstance(color_list, list):
            for c in color_list:
                if isinstance(c, dict):
                    color_name = c.get("name") or c.get("colorName") or c.get("title")
                    if color_name:
                        surcharge = c.get("surcharge") or c.get("extraPrice") or c.get("price")
                        try:
                            surcharge_int = int(str(surcharge).replace(".", "").replace(",", "").strip() or 0)
                        except Exception:
                            surcharge_int = 0
                        bucket = "premium" if surcharge_int > 0 else "standard"
                        entry = {"name": str(color_name)}
                        if surcharge:
                            entry["surcharge"] = str(surcharge)
                        if entry not in results["colors"][bucket]:
                            results["colors"][bucket].append(entry)

        for k, v in data.items():
            _traverse_and_extract_next_data(v, results)
    elif isinstance(data, list):
        for item in data:
            _traverse_and_extract_next_data(item, results)
            
    return results


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
    ingestion_at = _utc_now()
    canonical_url = parsed.metadata.canonical_url or parsed.metadata.og_url
    source_type = infer_source_type(source_url or source)
    chunk_id_prefix = "url" if source_url else "html"
    title = extracted.title or parsed.title
    cleaned_markdown = _clean_markdown_noise(extracted.markdown)

    next_data_entities = []
    if html is not None:
        next_data = _extract_next_data_layer(html)
        next_data_extracted = _traverse_and_extract_next_data(next_data) if next_data else {}
        
        # --- LLM Enrichment Pass ---
        from agentic_rag.ingestion.url.llm_enrichment import enrich_markdown_with_llm
        cleaned_markdown = enrich_markdown_with_llm(cleaned_markdown, next_data_extracted)
        # ---------------------------
        
        if next_data_extracted.get("model_name"):
                from agentic_rag.ingestion.url.entities.extractor import _format_model_name, UrlEntity
                from agentic_rag.ingestion.url.chunking import short_hash
                model_name = _format_model_name(next_data_extracted["model_name"])
                
                structured_data = {"model_name": model_name}
                if next_data_extracted.get("prices"):
                    for m, p in next_data_extracted["prices"].items():
                        if m.casefold() == model_name.casefold():
                            structured_data["price"] = p
                            break
                if next_data_extracted.get("editions"):
                    structured_data["editions"] = next_data_extracted["editions"]
                if next_data_extracted.get("colors") and (
                    next_data_extracted["colors"]["standard"] or next_data_extracted["colors"]["premium"]
                ):
                    structured_data["colors"] = next_data_extracted["colors"]
                
                next_data_entities.append(
                    UrlEntity(
                        entity_id=f"url_entity_next_data_{short_hash(model_name)}",
                        entity_type="vehicle",
                        entity_name=model_name,
                        source_block_id="next_data",
                        dom_path="script#__NEXT_DATA__",
                        retrieval_text=f"{model_name} (vehicle)",
                        structured_data=structured_data,
                    )
                )

    dom_blocks = detect_semantic_blocks(html) if html is not None else []
    if next_data_entities:
        primary_entity = next_data_entities[0].entity_name
    else:
        primary_entity = infer_primary_page_entity(
            title=title,
            url=source_url or final_url or original_url or source,
            text=cleaned_markdown,
        )
    dom_blocks = filter_blocks_for_primary_entity(
        dom_blocks,
        primary_entity=primary_entity,
    )
    visual_semantics = (
        extract_visual_semantics(
            html,
            evidence_source=_visual_evidence_source(source_html_stage),
        )
        if html is not None
        else VisualSemanticsResult()
    )
    cleaned_markdown = append_visual_semantics_markdown(
        cleaned_markdown,
        visual_semantics,
        title=title,
    )
    cleaned_markdown = append_structure_aware_markdown(
        cleaned_markdown,
        dom_blocks,
        title=title,
    )
    chunks = _build_markdown_aware_chunks(
        markdown=cleaned_markdown,
        source=source,
        source_type=source_type,
        chunk_id_prefix=chunk_id_prefix,
        title=title,
        ingestion_at=ingestion_at,
    )
    entities = extract_entities(dom_blocks, primary_entity=primary_entity)
    if next_data_entities:
        entities = next_data_entities + [ent for ent in entities if ent.entity_type != "vehicle"]

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
    chunks = _with_visual_semantics_metadata(chunks, semantics=visual_semantics)
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
        created_at=ingestion_at,
        parsed=parsed,
        html=html,
        source_html_stage=source_html_stage,
        extracted_markdown=extracted.markdown,
        visual_semantics=visual_semantics,
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
        visual_semantics=[
            fact.model_dump(mode="json") for fact in candidate.visual_semantics.facts
        ],
    )
    return document.model_copy(update={"artifacts": artifacts})


def _with_optional_interaction_chunks(
    document: LoadedUrlDocument,
    *,
    url: str,
    data_artifact_dir: str | Path | None,
    run_id: str,
    enabled: bool,
    options: InteractionOptions | None,
    capture: InteractionCaptureFunction | None,
) -> LoadedUrlDocument:
    if not enabled:
        return document
    # TODO [guide_2/TODO.md Priority 6 – Score tracking]:
    # After merging interaction chunks, record the promotion count and any
    # evaluation score change in a local score log (e.g. guide_2/TODO.md §Score Log).
    # Format: `{date, url, static_chunk_count, promoted_count, score_before, score_after}`
    # This helps track whether interaction chunk promotion actually improves retrieval.
    # Reference: guide_2/TODO.md Priority 6, Score Log section
    try:
        interaction_document = load_url_interactions_with_artifacts(
            url,
            data_artifact_dir=data_artifact_dir,
            run_id=f"{run_id}-interactions",
            options=options,
            capture=capture,
        )
    except Exception as exc:
        return document.model_copy(
            update={
                "chunks": [
                    chunk.model_copy(
                        update={
                            "metadata": {
                                **chunk.metadata,
                                "interaction_capture_error": f"{type(exc).__name__}: {exc}",
                            }
                        }
                    )
                    for chunk in document.chunks
                ]
            }
        )
    promoted_chunks = [
        chunk
        for chunk in interaction_document.chunks
        if chunk.metadata.get("chunk_type") == "dynamic_state"
        and chunk.metadata.get("metadata_prefilter_exclude") is not True
    ]
    if not promoted_chunks:
        return document
    updated_document = document.model_copy(
        update={
            "markdown": _append_promoted_interaction_markdown(
                document.markdown,
                promoted_chunks,
            ),
            "chunks": [*document.chunks, *promoted_chunks],
        }
    )
    return _rewrite_primary_artifacts_for_interactions(updated_document, promoted_chunks)


def _append_promoted_interaction_markdown(
    markdown: str,
    promoted_chunks: list[Chunk],
) -> str:
    sections = [
        _promoted_interaction_markdown_section(chunk)
        for chunk in promoted_chunks
        if chunk.text.strip()
    ]
    if not sections:
        return markdown
    return "\n\n".join(
        part.strip()
        for part in [markdown, "## Dynamic Interaction Facts", *sections]
        if part.strip()
    )


def _promoted_interaction_markdown_section(chunk: Chunk) -> str:
    metadata = chunk.metadata
    title = (
        metadata.get("selected_product_model")
        or metadata.get("product_model")
        or metadata.get("model_name")
        or metadata.get("chunk_id")
        or "Dynamic fact"
    )
    facts = _promoted_interaction_facts(metadata)
    lines = [f"### {title}", chunk.text.strip()]
    if facts:
        lines.extend(["", "| Field | Value |", "| --- | --- |"])
        lines.extend(f"| {key} | {value} |" for key, value in facts.items())
    lines.extend(
        [
            "",
            "```json",
            json.dumps(
                {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "metadata": facts,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
        ]
    )
    return "\n".join(lines)


def _promoted_interaction_facts(metadata: dict[str, object]) -> dict[str, object]:
    fact_keys = (
        "selected_product_model",
        "selected_model_id",
        "product_model",
        "model_name",
        "option_label",
        "deposit_amount",
        "product_price",
        "currency",
        "availability",
        "section_origin",
        "evidence_source",
    )
    return {
        key: value for key in fact_keys if (value := metadata.get(key)) not in (None, "", [], {})
    }


def _rewrite_primary_artifacts_for_interactions(
    document: LoadedUrlDocument,
    promoted_chunks: list[Chunk],
) -> LoadedUrlDocument:
    artifacts = document.artifacts
    if artifacts is None:
        return document
    artifacts.markdown_path.write_text(document.markdown.rstrip() + "\n", encoding="utf-8")
    artifacts.chunks_path.write_text(_serialize_chunks_jsonl(document.chunks), encoding="utf-8")
    if artifacts.manifest_path.exists():
        manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
        manifest["chunk_count"] = len(document.chunks)
        manifest["markdown_augmented_with_interactions"] = True
        manifest["promoted_interaction_chunk_count"] = len(promoted_chunks)
        manifest["promoted_interaction_chunk_ids"] = [chunk.chunk_id for chunk in promoted_chunks]
        artifacts.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return document


def _serialize_chunks_jsonl(chunks: list[Chunk]) -> str:
    lines = [json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) for chunk in chunks]
    return "\n".join(lines) + ("\n" if lines else "")


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
    chunk_id_prefix: str,
    title: str | None,
    ingestion_at: str,
) -> list[Chunk]:
    page_hash = short_hash(normalize_for_content_hash(markdown))
    section_indexes: dict[str, int] = defaultdict(int)
    chunks: list[Chunk] = []
    for global_chunk_index, markdown_chunk in enumerate(
        chunk_markdown_by_sections(markdown, root_title=title), start=1
    ):
        section = markdown_chunk.section or "main"
        section_indexes[section] += 1
        chunk_index = section_indexes[section]
        chunk_id = build_chunk_id(chunk_id_prefix, source, section, chunk_index)
        normalized_chunk_text = normalize_for_content_hash(markdown_chunk.text)
        dedupe_text = normalize_for_dedupe_hash(markdown_chunk.text)
        chunk_metadata: dict[str, object] = {
            "chunk_id": chunk_id,
            "source": source,
            "source_type": source_type,
            "title": title,
            "section": section,
            "section_level": markdown_chunk.section_level,
            "section_path": list(markdown_chunk.section_path),
            **_structure_chunk_metadata(markdown_chunk),
            "ingestion_at": ingestion_at,
            "updated_date": ingestion_at,
            "updated_date_source": "ingestion_start",
            "chunk_index": global_chunk_index,
            "page_hash": page_hash,
            "content_hash": short_hash(normalized_chunk_text),
            "dedupe_text": dedupe_text,
            "dedupe_hash": short_hash(dedupe_text),
            "normalized_text": normalized_chunk_text,
            "chunk_token_count": markdown_chunk.chunk_token_count,
            **markdown_chunk.metadata,
        }
        if markdown_chunk.semantic_unit is not None:
            chunk_metadata["semantic_unit"] = markdown_chunk.semantic_unit
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=markdown_chunk.text,
                metadata=chunk_metadata,
            )
        )
    return chunks


def _structure_chunk_metadata(markdown_chunk: MarkdownChunk) -> dict[str, object]:
    section_path = list(markdown_chunk.section_path)
    block_types = _fields_from_structure_chunk(markdown_chunk.text, "structure_block_type")
    block_ids = _fields_from_structure_chunk(markdown_chunk.text, "structure_block_id")
    dedupe_hashes = _fields_from_structure_chunk(markdown_chunk.text, "structure_dedupe_hash")
    is_structure_section = "Structured DOM Content" in section_path or bool(block_types)
    if not is_structure_section:
        return {"section_origin": "source_markdown"}
    metadata: dict[str, object] = {
        "section_origin": "generated_structure",
        "structure_aware": True,
    }
    if block_types:
        metadata["structure_block_type"] = block_types[0]
        metadata["structure_block_types"] = block_types
    if block_ids:
        metadata["structure_block_id"] = block_ids[0]
        metadata["structure_block_ids"] = block_ids
    if dedupe_hashes:
        metadata["structure_dedupe_hash"] = dedupe_hashes[0]
        metadata["structure_dedupe_hashes"] = dedupe_hashes
    return metadata


def _fields_from_structure_chunk(text: str, field_name: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(
        rf"^\s*-\s*{re.escape(field_name)}:\s*(.+?)\s*$",
        text,
        re.MULTILINE,
    ):
        value = match.group(1).strip()
        if value and value not in values:
            values.append(value)
    return values


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
                    "requested_url": original_url or source_url,
                    "source_url": source_url,
                    "original_url": original_url,
                    "final_url": final_url,
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


def _with_visual_semantics_metadata(
    chunks: list[Chunk],
    *,
    semantics: VisualSemanticsResult,
) -> list[Chunk]:
    if not semantics.facts:
        return chunks
    facts_payload = [
        {"fact_id": fact.fact_id, "kind": fact.kind, "text": fact.text}
        for fact in semantics.facts
    ]
    old_prices = [fact.text for fact in semantics.old_prices]
    css_evidence = sorted(
        {evidence for fact in semantics.facts for evidence in fact.css_evidence if evidence}
    )
    output: list[Chunk] = []
    for chunk in chunks:
        metadata = {
            **chunk.metadata,
            "visual_semantic_count": len(semantics.facts),
        }
        if _is_visual_debug_chunk(chunk):
            metadata.update(
                {
                    "chunk_type": "visual_debug",
                    "visual_semantics": facts_payload,
                    "section_kind": "generated",
                    "section_origin": "generated_artifact",
                    "evidence_source": _primary_visual_evidence_source(semantics),
                    "css_evidence": css_evidence,
                    "retrieval_visibility": "debug_only",
                    "metadata_prefilter_exclude": True,
                    "trusted_for_retrieval": False,
                    "debug_reason": "visual_semantics_fallback_unmapped",
                }
            )
            if old_prices:
                metadata["original_price"] = old_prices[0]
            output.append(chunk.model_copy(update={"metadata": metadata}))
            continue
        if _chunk_mentions_visual_fact(chunk, semantics):
            metadata.update(
                {
                    "visual_semantics": facts_payload,
                    "section_kind": "static",
                    "section_origin": _visual_section_origin(semantics),
                    "evidence_source": _primary_visual_evidence_source(semantics),
                    "css_evidence": css_evidence,
                    "trusted_for_retrieval": True,
                }
            )
            if old_prices:
                metadata["original_price"] = old_prices[0]
        output.append(chunk.model_copy(update={"metadata": metadata}))
    return output


def _is_visual_debug_chunk(chunk: Chunk) -> bool:
    return "visual pricing evidence" in chunk.text.casefold()


def _chunk_mentions_visual_fact(chunk: Chunk, semantics: VisualSemanticsResult) -> bool:
    text = chunk.text.casefold()
    return any(fact.text.casefold() in text for fact in semantics.facts)


def _visual_section_origin(semantics: VisualSemanticsResult) -> str:
    if any(fact.evidence_source == "rendered_dom" for fact in semantics.facts):
        return "source_data_rendered"
    return "source_data_static"


def _primary_visual_evidence_source(semantics: VisualSemanticsResult) -> str:
    for fact in semantics.facts:
        if fact.evidence_source:
            return fact.evidence_source
    return "raw_html"


def _visual_evidence_source(source_html_stage: str | None) -> VisualEvidenceSource:
    return "rendered_dom" if source_html_stage == "rendered_html" else "raw_html"


def _extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(url).netloc or None


def _raise_if_pdf_url(url: str) -> None:
    reject_pdf_url(url)


def _raise_if_pdf_response(page: _FetchedPage) -> None:
    reject_pdf_content_type(page.content_type)
