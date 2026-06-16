"""Page profiling helpers for URL interaction capture."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlparse

from agentic_rag.ingestion.url.interactions.models import InteractionProfile
from agentic_rag.ingestion.url.quality import detect_page_profile

_INTERACTION_PATH_MARKERS = (
    "dat-coc",
    "booking",
    "configurator",
    "cau-hinh",
)
_INTERACTION_QUERY_KEYS = ("modelId", "model_id", "sku", "variantId")


def detect_interaction_profile(
    requested_url: str,
    *,
    final_url: str | None = None,
    html: str = "",
) -> InteractionProfile:
    """Detect whether a URL needs deterministic JS interaction capture."""

    inspected_url = final_url or requested_url
    page_profile = detect_page_profile(inspected_url, html)
    parsed = urlparse(requested_url)
    path = parsed.path.lower()
    query_params = {key: value for key, value in parse_qsl(parsed.query, keep_blank_values=True)}
    reasons: list[str] = []
    if page_profile.page_type in {"booking_flow", "vehicle_configurator"}:
        reasons.append(f"page_type:{page_profile.page_type}")
    for marker in _INTERACTION_PATH_MARKERS:
        if marker in path:
            reasons.append(f"path_marker:{marker}")
            break
    for key in _INTERACTION_QUERY_KEYS:
        if key in query_params:
            reasons.append(f"query_param:{key}")
            break
    if _has_option_signal(html):
        reasons.append("html_option_signals")

    model_id = _first_query_value(query_params, _INTERACTION_QUERY_KEYS)
    return InteractionProfile(
        requested_url=requested_url,
        final_url=final_url,
        page_type=page_profile.page_type,
        interaction_required=bool(reasons),
        reasons=reasons,
        url_query_params=query_params,
        model_id=model_id,
    )


def _first_query_value(query_params: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = query_params.get(key)
        if value:
            return value
    return None


def _has_option_signal(html: str) -> bool:
    lowered = html.lower()
    return any(
        marker in lowered
        for marker in (
            "data-option-group",
            "data-option-label",
            "data-price",
            "data-image",
            "color-swatch",
            "variant-card",
            "aria-pressed",
        )
    )
