"""Rule-based interaction capture for dynamic URL product/configurator pages."""

from agentic_rag.ingestion.url.interactions.artifacts import persist_interaction_artifacts
from agentic_rag.ingestion.url.interactions.extractor import (
    build_interaction_chunks,
    extract_interaction_states_from_html,
)
from agentic_rag.ingestion.url.interactions.models import (
    InteractionArtifacts,
    InteractionCaptureResult,
    InteractionControl,
    InteractionOptions,
    InteractionProfile,
    InteractionStateRecord,
)
from agentic_rag.ingestion.url.interactions.playwright import (
    capture_interaction_states_with_playwright,
)
from agentic_rag.ingestion.url.interactions.profile import detect_interaction_profile
from agentic_rag.ingestion.url.interactions.runner import (
    InteractionCaptureFunction,
    LoadedInteractionDocument,
    load_url_interaction_chunks,
    load_url_interactions_with_artifacts,
)

__all__ = [
    "InteractionArtifacts",
    "InteractionCaptureFunction",
    "InteractionCaptureResult",
    "InteractionControl",
    "InteractionOptions",
    "InteractionProfile",
    "InteractionStateRecord",
    "LoadedInteractionDocument",
    "build_interaction_chunks",
    "capture_interaction_states_with_playwright",
    "detect_interaction_profile",
    "extract_interaction_states_from_html",
    "load_url_interaction_chunks",
    "load_url_interactions_with_artifacts",
    "persist_interaction_artifacts",
]
