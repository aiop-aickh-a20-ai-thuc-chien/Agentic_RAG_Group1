"""Cheap routing signals for multi-strategy URL extraction."""

from __future__ import annotations

from agentic_rag.ingestion.integration.url.models import UrlStrategyOutput


def needs_layout_parser(html: str, output: UrlStrategyOutput) -> bool:
    lowered = html.casefold()
    
    # Check for cross-model contamination
    from agentic_rag.ingestion.url.entities.extractor import _MODEL_RE, _format_model_name
    found_models = set()
    for match in _MODEL_RE.finditer(output.markdown):
        found_models.add(_format_model_name(match.group(0)))
        
    return bool(
        "table_structure_missing" in output.unresolved_gaps
        or len(found_models) > 1
        or "column-count" in lowered
        or "display:grid" in lowered
        or "display: grid" in lowered
    )


def needs_interaction(page_profile: str | None, html: str) -> bool:
    profile = (page_profile or "").casefold()
    lowered = html.casefold()
    return any(
        marker in profile
        for marker in ("configurator", "booking_flow", "interactive_application")
    ) or any(
        marker in lowered
        for marker in ("data-option-group", "__next_data__", "aria-selected")
    )


def needs_vision(output: UrlStrategyOutput) -> bool:
    return any(
        gap in {
            "visual_chart_or_canvas",
            "image_only_content",
            "visual_state_unknown",
            "dom_obfuscated",
            "react_hydration_empty",
        }
        for gap in output.unresolved_gaps
    )
