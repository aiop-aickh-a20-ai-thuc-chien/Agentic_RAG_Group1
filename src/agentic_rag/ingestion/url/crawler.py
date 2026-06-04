"""Crawl4AI-backed URL crawling adapter."""

from __future__ import annotations

import asyncio
import io
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast


@dataclass(frozen=True)
class Crawl4AIPage:
    """Rendered page content returned by Crawl4AI."""

    html: str
    markdown: str | None
    url: str
    links: tuple[str, ...] = ()
    content_type: str | None = "text/html"


def crawl_url_with_crawl4ai(url: str) -> Crawl4AIPage:
    """Render and crawl one URL with Crawl4AI.

    The public ingestion API is synchronous, while Crawl4AI is async. This helper
    owns the event-loop boundary and lets the loader fall back to the simple HTTP
    fetcher when Crawl4AI or its browser runtime is unavailable.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_crawl_url_with_crawl4ai(url))

    raise RuntimeError("Crawl4AI cannot run inside an active event loop from this sync API.")


async def _crawl_url_with_crawl4ai(url: str) -> Crawl4AIPage:
    try:
        crawl4ai = import_module("crawl4ai")
    except ImportError as exc:
        raise ImportError("Crawl4AI is not installed.") from exc

    async_web_crawler = crawl4ai.AsyncWebCrawler
    browser_config = crawl4ai.BrowserConfig(headless=True)
    run_config = _build_crawler_run_config()

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        async with async_web_crawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)

    if not bool(getattr(result, "success", True)):
        error_message = str(getattr(result, "error_message", "unknown Crawl4AI error"))
        raise RuntimeError(f"Crawl4AI failed to crawl {url}: {error_message}")

    html = _first_text_attr(result, ("cleaned_html", "html"))
    if not html:
        raise RuntimeError(f"Crawl4AI returned empty HTML for {url}.")

    return Crawl4AIPage(
        html=html,
        markdown=_markdown_text(getattr(result, "markdown", None)),
        url=_first_text_attr(result, ("url",)) or url,
        links=_links_from_result(getattr(result, "links", None)),
    )


def _build_crawler_run_config() -> object:
    try:
        crawl4ai = import_module("crawl4ai")
    except ImportError as exc:
        raise ImportError("Crawl4AI is not installed.") from exc

    cache_mode = crawl4ai.CacheMode
    crawler_run_config = crawl4ai.CrawlerRunConfig
    candidate_configs: tuple[dict[str, object], ...] = (
        {
            "cache_mode": cache_mode.BYPASS,
            "check_robots_txt": True,
            "magic": True,
            "simulate_user": True,
            "word_count_threshold": 5,
        },
        {
            "cache_mode": cache_mode.BYPASS,
            "magic": True,
            "simulate_user": True,
            "word_count_threshold": 5,
        },
        {
            "cache_mode": cache_mode.BYPASS,
            "word_count_threshold": 5,
        },
        {},
    )
    for config_kwargs in candidate_configs:
        try:
            return crawler_run_config(**config_kwargs)
        except TypeError:
            continue
    return crawler_run_config()


def _markdown_text(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if value is None:
        return None
    for attr_name in (
        "raw_markdown",
        "fit_markdown",
        "markdown_with_citations",
        "markdown",
    ):
        attr_value = getattr(value, attr_name, None)
        if isinstance(attr_value, str) and attr_value.strip():
            return attr_value.strip()
    text = str(value).strip()
    return text or None


def _links_from_result(value: object) -> tuple[str, ...]:
    links: list[str] = []
    if isinstance(value, dict):
        for group in value.values():
            links.extend(_links_from_iterable(group))
    else:
        links.extend(_links_from_iterable(value))
    return tuple(dict.fromkeys(link for link in links if link))


def _links_from_iterable(value: object) -> list[str]:
    if value is None or isinstance(value, str | bytes):
        return []
    if not isinstance(value, list | tuple):
        return []

    links: list[str] = []
    for item in value:
        if isinstance(item, str):
            links.append(item)
            continue
        if isinstance(item, dict):
            raw_link = item.get("href") or item.get("url")
            if raw_link is not None:
                links.append(str(raw_link))
            continue
        raw_link = getattr(item, "href", None) or getattr(item, "url", None)
        if raw_link is not None:
            links.append(str(raw_link))
    return links


def _first_text_attr(value: object, attr_names: tuple[str, ...]) -> str:
    for attr_name in attr_names:
        attr_value = getattr(value, attr_name, None)
        if isinstance(attr_value, str) and attr_value.strip():
            return attr_value.strip()
    return cast(str, "")
