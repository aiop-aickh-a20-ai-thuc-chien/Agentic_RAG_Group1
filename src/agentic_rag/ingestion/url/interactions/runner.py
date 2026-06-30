"""High-level helpers for rule-based interaction ingestion."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.interactions.artifacts import persist_interaction_artifacts
from agentic_rag.ingestion.url.interactions.extractor import (
    build_interaction_chunks,
    build_promoted_interaction_chunks,
)
from agentic_rag.ingestion.url.interactions.models import (
    InteractionArtifacts,
    InteractionCaptureResult,
    InteractionOptions,
)
from agentic_rag.ingestion.url.interactions.playwright import (
    capture_interaction_states_with_playwright,
)
from agentic_rag.ingestion.url.interactions.traversal import (
    assess_configurator_readiness,
    finalize_traversal,
)

InteractionCaptureFunction = Callable[[str, InteractionOptions], InteractionCaptureResult]


class LoadedInteractionDocument(BaseModel):
    """Interaction capture result, generated chunks, and optional artifacts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result: InteractionCaptureResult
    chunks: list[Chunk]
    artifacts: InteractionArtifacts | None = None


def load_url_interaction_chunks(
    url: str,
    *,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "url_interactions",
    options: InteractionOptions | None = None,
    capture: InteractionCaptureFunction | None = None,
) -> list[Chunk]:
    """Capture safe UI states for one URL and return shared chunks."""

    return load_url_interactions_with_artifacts(
        url,
        data_artifact_dir=data_artifact_dir,
        run_id=run_id,
        options=options,
        capture=capture,
    ).chunks


def load_url_interactions_with_artifacts(
    url: str,
    *,
    data_artifact_dir: str | Path | None = None,
    run_id: str = "url_interactions",
    options: InteractionOptions | None = None,
    capture: InteractionCaptureFunction | None = None,
) -> LoadedInteractionDocument:
    """Capture safe UI states, convert them to chunks, and persist artifacts."""

    # TODO [guide_2/TODO_Gemini.md §3c – Per-model vehicle selector click]:
    # For booking/configurator URLs with a `modelId` query param, simulate
    # clicking each vehicle model selector button before option enumeration.
    # This ensures each model's configurator state is captured independently
    # (e.g. VF 9, VF 8, VF 7 each get their own interaction record).
    # Reference: guide_2/TODO_Gemini.md §3 Action Item 3c
    #
    # TODO [url/TODO_LLM.md §1 – LLM review stage after rule-based capture]:
    # After `capture_result` is built and artifacts are written, optionally run
    # an LLM review step that:
    #   1. Bundles selected control text, state diffs, and screenshot filenames.
    #   2. Sends the bundle to the LLM for classification/validation.
    #   3. Stores LLM output under `interaction_review.llm_notes` artifact key.
    #   4. Does NOT overwrite deterministic product facts from DOM/network.
    # This stage is optional; gate it behind `options.enable_llm_review: bool`.
    # Reference: url/TODO_LLM.md §1, Evidence-First Flow

    capture_options = options or InteractionOptions()
    capture_result = (
        capture(url, capture_options)
        if capture is not None
        else capture_interaction_states_with_playwright(url, options=capture_options)
    )
    if capture_result.profile.interaction_required and capture_result.profile.model_id:
        readiness = capture_result.readiness or assess_configurator_readiness(
            target_model_id=capture_result.profile.model_id,
            selected_model_id=capture_result.profile.model_id,
            visible_text=capture_result.source_html or "",
            controls=capture_result.controls,
            configuration_panel_present=bool(
                capture_result.panel_snapshots or capture_result.controls
            ),
        )
        capture_result = finalize_traversal(
            capture_result.model_copy(update={"readiness": readiness}),
            expected_model=capture_result.profile.model_id,
        )
    debug_chunks = build_interaction_chunks(capture_result)
    promoted_chunks = build_promoted_interaction_chunks(capture_result)
    chunks = [*debug_chunks, *promoted_chunks]
    artifacts = persist_interaction_artifacts(
        data_dir=data_artifact_dir,
        source=url,
        run_id=run_id,
        result=capture_result,
        chunks=chunks,
    )
    return LoadedInteractionDocument(
        result=capture_result,
        chunks=chunks,
        artifacts=artifacts,
    )


__all__ = [
    "InteractionCaptureFunction",
    "LoadedInteractionDocument",
    "load_url_interaction_chunks",
    "load_url_interactions_with_artifacts",
]
