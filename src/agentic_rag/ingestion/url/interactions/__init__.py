"""Rule-based interaction capture for dynamic URL product/configurator pages."""

from agentic_rag.ingestion.url.interactions.artifacts import persist_interaction_artifacts
from agentic_rag.ingestion.url.interactions.extractor import (
    build_interaction_chunks,
    build_promoted_interaction_chunks,
    extract_interaction_states_from_html,
    extract_specifications_from_text,
)
from agentic_rag.ingestion.url.interactions.models import (
    InteractionArtifacts,
    InteractionCaptureResult,
    InteractionControl,
    InteractionOptions,
    InteractionPanelDiff,
    InteractionPanelSnapshot,
    InteractionProfile,
    InteractionStateRecord,
    PanelRole,
    ReadinessReport,
    SectionVisit,
    StateTransition,
    TraversalIssue,
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
from agentic_rag.ingestion.url.interactions.traversal import (
    DEFAULT_CONFIGURATOR_SECTIONS,
    assess_configurator_readiness,
    finalize_traversal,
    stable_control_identity,
    transition_manifest,
    traversal_issues,
)

__all__ = [
    "DEFAULT_CONFIGURATOR_SECTIONS",
    "InteractionArtifacts",
    "InteractionCaptureFunction",
    "InteractionCaptureResult",
    "InteractionControl",
    "InteractionOptions",
    "InteractionPanelDiff",
    "InteractionPanelSnapshot",
    "InteractionProfile",
    "InteractionStateRecord",
    "LoadedInteractionDocument",
    "PanelRole",
    "ReadinessReport",
    "SectionVisit",
    "StateTransition",
    "TraversalIssue",
    "assess_configurator_readiness",
    "build_interaction_chunks",
    "build_promoted_interaction_chunks",
    "capture_interaction_states_with_playwright",
    "detect_interaction_profile",
    "extract_interaction_states_from_html",
    "extract_specifications_from_text",
    "finalize_traversal",
    "load_url_interaction_chunks",
    "load_url_interactions_with_artifacts",
    "persist_interaction_artifacts",
    "stable_control_identity",
    "transition_manifest",
    "traversal_issues",
]
