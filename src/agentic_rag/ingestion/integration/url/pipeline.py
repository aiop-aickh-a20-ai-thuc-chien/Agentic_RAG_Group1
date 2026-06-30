"""Quality-routed URL integration pipeline."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pydantic import BaseModel, ConfigDict

from agentic_rag.ingestion.chunking import ChunkingInput
from agentic_rag.ingestion.integration.url.adapters import (
    AcquisitionAdapter,
    ExtractionAdapter,
    acquire_supplied_html,
    acquire_with_crawlee,
    extract_dom,
    extract_interactions,
)
from agentic_rag.ingestion.integration.url.config import UrlIntegrationConfig
from agentic_rag.ingestion.integration.url.models import (
    UrlAcquisitionResult,
    UrlIntegrationInput,
    UrlIntegrationResult,
    UrlStage,
    UrlStrategyOutput,
    UrlStrategyTrace,
    UrlStructuredSection,
    UrlValidatedPayload,
)
from agentic_rag.ingestion.integration.url.quality import (
    needs_interaction,
    needs_layout_parser,
    needs_vision,
)
from agentic_rag.ingestion.integration.url.reconciliation import reconcile_strategy_outputs
from agentic_rag.ingestion.integration.url.validation import validate_evidence_links


class UrlIntegrationAdapters:
    def __init__(
        self,
        acquisition: AcquisitionAdapter | None = None,
        dom: ExtractionAdapter = extract_dom,
        layout: ExtractionAdapter | None = None,
        interaction: ExtractionAdapter | None = None,
        vision: ExtractionAdapter | None = None,
    ) -> None:
        self.acquisition = acquisition
        self.dom = dom
        self.layout = layout
        self.interaction = interaction
        self.vision = vision


def integrate_url(
    request: UrlIntegrationInput,
    *,
    config: UrlIntegrationConfig | None = None,
    adapters: UrlIntegrationAdapters | None = None,
) -> UrlIntegrationResult:
    # TODO [guide_2/vinfast_pipeline_todo §1a – Stealth browser setup]:
    # When `resolved.acquisition_strategy == "crawlee"` or "playwright",
    # the underlying browser should be launched with:
    #   - channel="chrome" (real Chrome, not Chromium)
    #   - --disable-blink-features=AutomationControlled
    #   - user_agent from a real desktop browser
    #   - random viewport (1280–1920 x 800–1080)
    #   - locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh"
    # This is required for VinFast pages that block headless/automation UA.
    # Reference: guide_2/vinfast_pipeline_todo (1).md §1a
    #
    # TODO [guide_2/missing implementation.md – Single-session production adapter]:
    # The production entry point should create network interceptors, DOM extractor,
    # and VLM screenshot from a **single Playwright page session** to avoid
    # launching multiple browser instances for one URL.
    # Currently the acquisition and interaction adapters open separate sessions.
    # Reference: guide_2/missing implementation.md §Điều kiện để đóng file này #1
    #
    # TODO [guide_2/TODO_Gemini.md §3b – include_interactions flag]:
    # Accept an `include_interactions: bool` parameter and pass it to the
    # interaction adapter so the demo review script can toggle it via CLI flag.
    # Reference: guide_2/TODO_Gemini.md §3, Action Item 3
    resolved = config or UrlIntegrationConfig.from_env()
    injected = adapters or UrlIntegrationAdapters()
    if request.requested_url.lower().split("?", 1)[0].endswith(".pdf"):
        payload = UrlValidatedPayload(
            requested_url=request.requested_url,
            final_url=request.requested_url,
            unresolved_gaps=("pdf_routing_required",),
        )
        return UrlIntegrationResult(
            status="routed_to_pdf", payload=payload, pdf_handoff_url=request.requested_url
        )

    traces: list[UrlStrategyTrace] = []
    acquire = injected.acquisition
    if acquire is None:
        acquire = acquire_supplied_html if request.html is not None else acquire_with_crawlee
    acquisition, trace = _run_acquisition(acquire, request, resolved.acquisition_strategy)
    traces.append(trace)

    outputs: list[UrlStrategyOutput] = []
    dom_output, trace = _run_extraction(injected.dom, request, acquisition, resolved.dom_strategy)
    outputs.append(dom_output)
    traces.append(trace)
    html = acquisition.rendered_html or acquisition.raw_html or ""

    if _allowed(request, resolved.layout_strategy) and needs_layout_parser(html, dom_output):
        if injected.layout is None:
            traces.append(
                _skipped(
                    "layout",
                    resolved.layout_strategy,
                    "Layout gap detected, but no opt-in Docling adapter was supplied.",
                )
            )
        else:
            output, trace = _try_extraction(
                injected.layout,
                request,
                acquisition,
                resolved.layout_strategy,
                stage="layout",
            )
            traces.append(trace)
            if output is not None:
                outputs.append(output)
    else:
        traces.append(_skipped("layout", resolved.layout_strategy, "No measured layout gap."))

    interaction_needed = request.include_interactions or resolved.interaction_policy == "always" or (
        resolved.interaction_policy == "auto" and needs_interaction(request.page_profile, html)
    )
    if interaction_needed and _allowed(request, "playwright"):
        interaction = injected.interaction or extract_interactions
        output, trace = _try_extraction(
            interaction, request, acquisition, "playwright", stage="interaction"
        )
        traces.append(trace)
        if output is not None:
            outputs.append(output)
    else:
        traces.append(_skipped("interaction", "playwright", "Interaction not required."))

    visual_gap = any(needs_vision(output) for output in outputs)
    vision_needed = resolved.vlm_policy == "always" or (
        resolved.vlm_policy == "auto" and visual_gap
    )
    if vision_needed and injected.vision is not None and _allowed(request, "vlm-region"):
        output, trace = _try_extraction(
            injected.vision, request, acquisition, "vlm-region", stage="vision"
        )
        traces.append(trace)
        if output is not None:
            outputs.append(output)
    else:
        reason = "VLM disabled or no visual gap." if not vision_needed else "No VLM adapter."
        traces.append(_skipped("vision", "vlm-region", reason))

    acquisition_output = UrlStrategyOutput(strategy="acquisition", evidence=acquisition.evidence)
    sections, facts, evidence, conflicts = reconcile_strategy_outputs(
        [acquisition_output, *outputs]
    )
    # TODO [GraphRAG – emit graph import batch from reconciled facts]:
    # After reconciliation, the (sections, facts, evidence) triple is the richest
    # structured representation of one URL's content. This is the ideal hook to
    # build a graph import batch:
    #   - Each `UrlEvidenceFact` becomes a (:Fact {subject, attribute, value}) node
    #     with a [:SOURCED_FROM]->(:EvidenceRef) edge.
    #   - Each `UrlStructuredSection` becomes a (:Section {section_id}) node
    #     with [:PART_OF]->(:Document {url}) edges.
    #   - Conflicts become (:Conflict)-[:BETWEEN]->(fact, fact) for human review.
    # Write the batch to a `.graphml` or Cypher import file per URL; the graph DB
    # import job can pick them up asynchronously without blocking ingestion.
    # Reference: GraphRAG integration plan (to be created)
    accepted, rejected = validate_evidence_links(sections, facts, evidence)
    gaps = tuple(dict.fromkeys(gap for output in outputs for gap in output.unresolved_gaps))
    warnings = tuple(dict.fromkeys(warning for output in outputs for warning in output.warnings))
    canonical = next(
        (
            str(output.metadata["canonical_url"])
            for output in outputs
            if output.metadata.get("canonical_url")
        ),
        None,
    )
    payload = UrlValidatedPayload(
        requested_url=request.requested_url,
        final_url=acquisition.final_url,
        canonical_url=canonical,
        sections=sections,
        facts=accepted,
        evidence=evidence,
        conflicts=conflicts,
        unresolved_gaps=gaps,
        rejected_claims=rejected,
        strategy_trace=tuple(traces),
        warnings=warnings,
    )
    markdown = _merged_markdown(outputs, sections)
    chunking_input = ChunkingInput(
        markdown=markdown,
        source_type="url",
        parser="url-integration",
        source_path=acquisition.final_url,
        metadata={
            "requested_url": request.requested_url,
            "final_url": acquisition.final_url,
            "canonical_url": canonical,
            "evidence_refs": [item.evidence_id for item in evidence],
            "strategies": [trace.strategy for trace in traces if trace.status == "selected"],
        },
    )
    status = "complete" if markdown and not gaps and not rejected else "partial"
    return UrlIntegrationResult(status=status, payload=payload, chunking_input=chunking_input)


def _run_acquisition(
    adapter: AcquisitionAdapter, request: UrlIntegrationInput, name: str
) -> tuple[UrlAcquisitionResult, UrlStrategyTrace]:
    start = time.perf_counter()
    
    import random
    import datetime
    import json
    import os
    
    retries = 3
    base_delay = 2.0
    result = None
    last_err = None
    
    for attempt in range(retries):
        try:
            result = adapter(request)
            last_err = None
            break
        except Exception as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(base_delay * (2 ** attempt) + random.uniform(0.1, 0.5))
                
    if last_err is not None:
        try:
            failed_log = "failed_urls.jsonl"
            if os.path.exists("storage"):
                failed_log = os.path.join("storage", "failed_urls.jsonl")
            with open(failed_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "url": request.requested_url,
                    "error": str(last_err),
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass
        raise last_err

    trace = UrlStrategyTrace(
        stage="acquisition",
        strategy="supplied-html" if request.html is not None else name,
        status="selected",
        reason="Acquisition completed.",
        duration_ms=int((time.perf_counter() - start) * 1000),
        output_evidence_ids=tuple(item.evidence_id for item in result.evidence),
    )
    return result, trace


def _run_extraction(
    adapter: ExtractionAdapter,
    request: UrlIntegrationInput,
    acquisition: UrlAcquisitionResult,
    name: str,
) -> tuple[UrlStrategyOutput, UrlStrategyTrace]:
    output, trace = _try_extraction(adapter, request, acquisition, name, stage="dom")
    if output is None:
        raise RuntimeError(trace.error or f"{name} extraction failed.")
    return output, trace


def _try_extraction(
    adapter: ExtractionAdapter,
    request: UrlIntegrationInput,
    acquisition: UrlAcquisitionResult,
    name: str,
    *,
    stage: UrlStage,
) -> tuple[UrlStrategyOutput | None, UrlStrategyTrace]:
    start = time.perf_counter()
    try:
        output = adapter(request, acquisition)
    except Exception as exc:
        return None, UrlStrategyTrace(
            stage=stage,
            strategy=name,
            status="failed",
            reason="Optional strategy failed; evidence was preserved.",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=str(exc),
        )
    return output, UrlStrategyTrace(
        stage=stage,
        strategy=name,
        status="selected",
        reason="Strategy completed.",
        duration_ms=int((time.perf_counter() - start) * 1000),
        input_evidence_ids=tuple(item.evidence_id for item in acquisition.evidence),
        output_evidence_ids=tuple(item.evidence_id for item in output.evidence),
    )


def _skipped(stage: UrlStage, strategy: str, reason: str) -> UrlStrategyTrace:
    return UrlStrategyTrace(stage=stage, strategy=strategy, status="skipped", reason=reason)


def _allowed(request: UrlIntegrationInput, strategy: str) -> bool:
    return not request.allowed_strategies or strategy in request.allowed_strategies


def _merged_markdown(
    outputs: Sequence[UrlStrategyOutput], sections: Sequence[UrlStructuredSection]
) -> str:
    if sections:
        return "\n\n".join(
            section.markdown for section in sections if section.markdown.strip()
        )
    return "\n\n".join(output.markdown for output in outputs if output.markdown.strip())
