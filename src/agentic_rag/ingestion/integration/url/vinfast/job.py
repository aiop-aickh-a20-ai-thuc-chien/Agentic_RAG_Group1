"""Concrete browser-to-vector-store job used by the dedicated worker."""

from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path
from typing import Any

from agentic_rag.ingestion.integration.url.vinfast.browser import (
    BrowserProfile,
    launch_async_chrome,
)
from agentic_rag.ingestion.integration.url.vinfast.chunking import product_chunks
from agentic_rag.ingestion.integration.url.vinfast.pipeline import VinFastExtractionPipeline
from agentic_rag.ingestion.integration.url.vinfast.storage import (
    ChangeStore,
    FailedUrlLog,
    upsert_changed_chunks,
)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)


async def run_configured_pipeline() -> None:
    """Crawl configured VinFast URLs and persist only changed semantic chunks."""

    urls = [value.strip() for value in os.environ.get("VINFAST_URLS", "").split(",")]
    urls = [url for url in urls if url]
    if not urls:
        raise RuntimeError("VINFAST_URLS must contain at least one URL")

    state_root = Path(os.environ.get("VINFAST_STATE_DIR", "artifacts/vinfast"))
    profile = BrowserProfile(
        headless=_boolean_env("VINFAST_BROWSER_HEADLESS", default=True),
        user_agent=os.environ.get("VINFAST_BROWSER_USER_AGENT", _DEFAULT_USER_AGENT),
    )
    async_playwright: Any = import_module("playwright.async_api").async_playwright
    async with async_playwright() as playwright:
        browser, context = await launch_async_chrome(playwright, profile)
        try:
            page = await context.new_page()
            pipeline = VinFastExtractionPipeline(
                page=page,
                failed_urls=FailedUrlLog(state_root / "failed_urls.jsonl"),
            )
            chunks = []
            for url in urls:
                products = await pipeline.extract(url)
                for product in products:
                    chunks.extend(product_chunks(product))
            upsert_changed_chunks(chunks, ChangeStore(state_root / "changes"))
        finally:
            await context.close()
            await browser.close()


def _boolean_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
