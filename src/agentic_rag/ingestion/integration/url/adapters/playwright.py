"""Adapter over the existing Playwright state-graph capture."""

from __future__ import annotations

from agentic_rag.ingestion.integration.url.models import (
    UrlAcquisitionResult,
    UrlEvidenceRef,
    UrlIntegrationInput,
    UrlStrategyOutput,
    UrlStructuredSection,
)
from agentic_rag.ingestion.url.interactions import (
    InteractionOptions,
    capture_interaction_states_with_playwright,
)


def extract_interactions(
    request: UrlIntegrationInput, acquisition: UrlAcquisitionResult
) -> UrlStrategyOutput:
    # TODO [guide_2/vinfast_pipeline_todo §1b – Human-like interaction behavior]:
    # Before each click, add:
    #   - `asyncio.sleep(random.uniform(1.5, 4.0))` between actions
    #   - `page.mouse.move()` to simulate cursor movement
    #   - slow scroll: `page.evaluate("window.scrollBy(0, 300)")`
    #   - 0.5–1.5s wait after element is ready before clicking
    # This reduces anti-bot detection on VinFast configurator pages.
    # Reference: guide_2/vinfast_pipeline_todo (1).md §1b
    #
    # TODO [guide_2/vinfast_pipeline_todo §2 – Timeout → VLM fallback]:
    # If `capture_interaction_states_with_playwright` raises a timeout or
    # `wait_for_selector` error, do NOT crash. Instead:
    #   1. Capture a full-page screenshot.
    #   2. Forward it to the VLM adapter.
    #   3. Record the fallback in the strategy trace.
    # Reference: guide_2/vinfast_pipeline_todo (1).md §2
    #
    # TODO [guide_2/TODO.md Priority 4 – Keep debug artifacts out of retrieval]:
    # Interaction/debug artifacts (interaction_states.json, network_payloads.jsonl,
    # raw snapshots) must NOT be promoted into retrieval chunks unless they have
    # been converted into clean product fact chunks with `chunk_type="dynamic_state"`.
    # Reference: guide_2/TODO.md Priority 4, last item (unchecked)
    result = capture_interaction_states_with_playwright(
        acquisition.final_url,
        options=InteractionOptions(
            max_states=request.max_states,
            timeout_seconds=request.timeout_seconds,
        ),
    )
    evidence: list[UrlEvidenceRef] = []
    sections: list[UrlStructuredSection] = []
    for index, state in enumerate(result.states):
        refs = [
            value
            for value in (
                state.before_snapshot_ref,
                state.after_snapshot_ref,
                state.state_diff_ref,
            )
            if value
        ]
        for ref in refs:
            if not any(item.evidence_id == ref for item in evidence):
                evidence.append(
                    UrlEvidenceRef(
                        evidence_id=ref,
                        kind="screenshot" if "snapshot" in ref else "dom_region",
                        artifact_ref=ref,
                        strategy="playwright",
                        state_id=state.state_id,
                    )
                )
        sections.append(
            UrlStructuredSection(
                section_id=state.section_id or f"dynamic-{index:04d}",
                heading=state.option_label,
                markdown=state.to_chunk_text(),
                reading_order=index,
                evidence_refs=tuple(refs),
                state_id=state.state_id,
            )
        )
    return UrlStrategyOutput(
        strategy="playwright",
        markdown="\n\n".join(section.markdown for section in sections),
        sections=tuple(sections),
        evidence=tuple(evidence),
        unresolved_gaps=tuple(issue.code for issue in result.traversal_issues),
        metadata={
            "traversal_complete": result.traversal_complete,
            "transition_count": len(result.transitions),
        },
    )

