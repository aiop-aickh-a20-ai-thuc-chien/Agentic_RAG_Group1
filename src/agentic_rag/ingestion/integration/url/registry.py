"""Capability registry for URL integration strategies."""

from __future__ import annotations

from agentic_rag.ingestion.integration.url.models import UrlStrategyCapabilities

_REGISTRY = {
    "crawlee": UrlStrategyCapabilities(
        stage="acquisition",
        strategy="crawlee",
        supports_rendered_html=True,
        supports_network_payloads=True,
        requires_browser=True,
        requires_network=True,
        estimated_cost_class="medium",
        latency_class="medium",
    ),
    "beautifulsoup": UrlStrategyCapabilities(
        stage="dom",
        strategy="beautifulsoup",
        supports_static_html=True,
        supports_tables=True,
        supports_images=True,
        supports_structured_output=True,
    ),
    "trafilatura": UrlStrategyCapabilities(
        stage="dom",
        strategy="trafilatura",
        supports_static_html=True,
        supports_reading_order=True,
    ),
    "docling-html": UrlStrategyCapabilities(
        stage="layout",
        strategy="docling-html",
        supports_static_html=True,
        supports_rendered_html=True,
        supports_tables=True,
        supports_images=True,
        supports_charts=True,
        supports_reading_order=True,
        supports_structured_output=True,
        estimated_cost_class="medium",
        latency_class="medium",
    ),
    "playwright": UrlStrategyCapabilities(
        stage="interaction",
        strategy="playwright",
        supports_rendered_html=True,
        supports_network_payloads=True,
        supports_interactions=True,
        supports_images=True,
        supports_state_provenance=True,
        requires_browser=True,
        requires_network=True,
        estimated_cost_class="medium",
        latency_class="high",
    ),
    "vlm-region": UrlStrategyCapabilities(
        stage="vision",
        strategy="vlm-region",
        supports_tables=True,
        supports_images=True,
        supports_charts=True,
        supports_structured_output=True,
        requires_credentials=True,
        estimated_cost_class="high",
        latency_class="high",
    ),
    "pydantic": UrlStrategyCapabilities(
        stage="structuring",
        strategy="pydantic",
        supports_structured_output=True,
    ),
    # TODO [guide_2/vinfast_pipeline_todo §1a – Stealth Chrome strategy]:
    # Register a `"stealth-chrome"` acquisition strategy that wraps `"crawlee"`
    # but launches with:
    #   - channel="chrome" (real installed Chrome binary)
    #   - --disable-blink-features=AutomationControlled
    #   - navigator.webdriver overridden to `undefined`
    #   - real desktop user_agent, random viewport (1280–1920 x 800–1080)
    #   - locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh"
    # Use `estimated_cost_class="medium"` and `latency_class="high"`.
    # Add the corresponding adapter in `adapters/` and a capability entry here.
    # Reference: guide_2/vinfast_pipeline_todo (1).md §1a
}


def supported_url_integration_strategies() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def url_strategy_capabilities(name: str) -> UrlStrategyCapabilities:
    normalized = name.strip().lower().replace("_", "-")
    try:
        return _REGISTRY[normalized]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported URL integration strategy: {name}. Supported strategies: "
            f"{', '.join(supported_url_integration_strategies())}."
        ) from exc

