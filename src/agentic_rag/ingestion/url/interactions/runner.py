"""High-level helpers for rule-based interaction ingestion."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.interactions.artifacts import persist_interaction_artifacts
from agentic_rag.ingestion.url.interactions.extractor import build_interaction_chunks
from agentic_rag.ingestion.url.interactions.models import (
    InteractionArtifacts,
    InteractionCaptureResult,
    InteractionOptions,
)
from agentic_rag.ingestion.url.interactions.playwright import (
    capture_interaction_states_with_playwright,
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

    capture_options = options or InteractionOptions()
    capture_result = (
        capture(url, capture_options)
        if capture is not None
        else capture_interaction_states_with_playwright(url, options=capture_options)
    )
    chunks = build_interaction_chunks(capture_result)
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
