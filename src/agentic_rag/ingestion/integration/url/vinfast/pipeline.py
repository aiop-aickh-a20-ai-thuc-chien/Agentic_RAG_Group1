"""Network -> DOM -> screenshot/VLM extraction fallback chain."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from agentic_rag.ingestion.integration.url.vinfast.models import VinFastProduct
from agentic_rag.ingestion.integration.url.vinfast.storage import FailedUrlLog

StageName = Literal["network", "dom", "vlm"]
Extractor = Callable[[str], Awaitable[object | None]]


class TerminalExtractionError(RuntimeError):
    """Stop fallback processing when the source itself is not extractable."""


async def retry_async[T](
    operation: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay: float = 2.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run an async operation with bounded exponential backoff."""

    if retries < 1:
        raise ValueError("retries must be at least 1")
    for attempt in range(retries):
        try:
            return await operation()
        except Exception:
            if attempt == retries - 1:
                raise
            await sleep(base_delay * (2**attempt))
    raise RuntimeError("unreachable retry state")


class ExtractionStage(BaseModel):
    """Immutable extractor stage compatible with the repository's model policy."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: StageName
    extract: Extractor


class VinFastExtractionPipeline:
    """Try independent extraction stages and accept only schema-valid output."""

    def __init__(
        self,
        stages: Sequence[ExtractionStage] | None = None,
        *,
        page: Any | None = None,
        failed_urls: FailedUrlLog | None = None,
        retries: int = 3,
        base_delay: float = 2.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if stages is None:
            if page is None:
                raise ValueError("stages or a Playwright page must be provided")
            from agentic_rag.ingestion.integration.url.vinfast.adapter import (
                PlaywrightSessionAdapter,
            )

            stages = PlaywrightSessionAdapter(page).stages()
        elif page is not None:
            raise ValueError("provide stages or page, not both")
        ordered = [stage.name for stage in stages]
        if ordered != sorted(ordered, key=("network", "dom", "vlm").index):
            raise ValueError("stages must follow network, DOM, then VLM priority")
        self._stages = tuple(stages)
        self._failed_urls = failed_urls
        self._retries = retries
        self._base_delay = base_delay
        self._sleep = sleep

    async def extract(self, url: str) -> list[VinFastProduct]:
        failures: list[str] = []
        for stage in self._stages:
            try:
                operation = stage.extract

                async def invoke(extractor: Extractor = operation) -> object | None:
                    return await extractor(url)

                raw = await retry_async(
                    invoke,
                    retries=self._retries,
                    base_delay=self._base_delay,
                    sleep=self._sleep,
                )
                products = _validate_products(raw)
                if products:
                    return products
                failures.append(f"{stage.name}: no schema-valid products")
            except TerminalExtractionError as exc:
                failures.append(f"{stage.name}: {exc}")
                break
            except Exception as exc:
                failures.append(f"{stage.name}: {exc}")
        reason = "; ".join(failures) or "no extraction stages configured"
        if self._failed_urls is not None:
            self._failed_urls.append(url, reason)
        raise RuntimeError(f"VinFast extraction failed for {url}: {reason}")


def _validate_products(raw: object | None) -> list[VinFastProduct]:
    if raw is None:
        return []
    values = raw if isinstance(raw, list | tuple) else [raw]
    products: list[VinFastProduct] = []
    for value in values:
        try:
            if isinstance(value, VinFastProduct):
                products.append(value)
            elif isinstance(value, dict):
                products.append(VinFastProduct.model_validate(value))
        except ValidationError:
            continue
    return products
