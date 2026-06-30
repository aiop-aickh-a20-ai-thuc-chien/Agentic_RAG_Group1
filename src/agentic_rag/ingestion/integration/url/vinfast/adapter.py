"""Playwright extractors that share one already-running page session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from agentic_rag.ingestion.integration.url.vinfast.structured import (
    extract_screenshot_bytes_with_instructor,
    parse_text_with_instructor,
)

StructuredExtractor = Callable[[str, str], object]
ScreenshotExtractor = Callable[[bytes, str], object]


class PlaywrightSessionAdapter:
    """Expose network, DOM, and VLM extractors over the same Playwright page."""

    def __init__(
        self,
        page: Any,
        *,
        text_extractor: StructuredExtractor = parse_text_with_instructor,
        screenshot_extractor: ScreenshotExtractor = extract_screenshot_bytes_with_instructor,
        network_settle_ms: int = 500,
    ) -> None:
        self._page = page
        self._text_extractor = text_extractor
        self._screenshot_extractor = screenshot_extractor
        self._network_settle_ms = network_settle_ms
        self._network_payloads: list[object] = []
        self._response_listener_registered = False

    def stages(self) -> tuple[Any, ...]:
        """Return stages in the pipeline's required fallback order."""

        from agentic_rag.ingestion.integration.url.vinfast.pipeline import ExtractionStage

        return (
            ExtractionStage(name="network", extract=self.extract_network),
            ExtractionStage(name="dom", extract=self.extract_dom),
            ExtractionStage(name="vlm", extract=self.extract_vlm),
        )

    async def extract_network(self, url: str) -> object | None:
        """Register interception before navigation and return JSON product candidates."""

        self._network_payloads.clear()
        if not self._response_listener_registered:
            self._page.on("response", self._capture_response)
            self._response_listener_registered = True
        response = await self._page.goto(url, wait_until="domcontentloaded")
        status = getattr(response, "status", None)
        if isinstance(status, int) and status >= 400:
            from agentic_rag.ingestion.integration.url.vinfast.pipeline import (
                TerminalExtractionError,
            )

            raise TerminalExtractionError(f"navigation returned HTTP {status}")
        if self._network_settle_ms:
            await self._page.wait_for_timeout(self._network_settle_ms)
        candidates: list[dict[str, object]] = []
        for payload in self._network_payloads:
            candidates.extend(_product_candidates(payload))
        return candidates or None

    async def extract_dom(self, url: str) -> object | None:
        """Read the current page's DOM without opening or navigating another page."""

        raw_text = await self._page.locator("body").inner_text()
        if not raw_text.strip():
            return None
        return await asyncio.to_thread(self._text_extractor, raw_text, url)

    async def extract_vlm(self, url: str) -> object:
        """Capture the current page and send its bytes to the configured VLM adapter."""

        screenshot = await self._page.screenshot(full_page=True)
        return await asyncio.to_thread(self._screenshot_extractor, screenshot, url)

    async def _capture_response(self, response: Any) -> None:
        try:
            payload = await response.json()
        except Exception:
            return
        self._network_payloads.append(payload)


def _product_candidates(value: object) -> list[dict[str, object]]:
    """Find schema-shaped records inside common nested API response envelopes."""

    if isinstance(value, dict):
        required = {"product_type", "model_name", "base_price_vnd", "battery_subscription"}
        if required <= value.keys():
            return [value]
        output: list[dict[str, object]] = []
        for nested in value.values():
            output.extend(_product_candidates(nested))
        return output
    if isinstance(value, list | tuple):
        output = []
        for nested in value:
            output.extend(_product_candidates(nested))
        return output
    return []
