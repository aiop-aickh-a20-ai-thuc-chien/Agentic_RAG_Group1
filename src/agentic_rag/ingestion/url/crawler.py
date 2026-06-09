"""Crawl4AI-backed URL crawling adapter."""

from __future__ import annotations

import asyncio
import io
import re
import time
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from html.parser import HTMLParser
from importlib import import_module
from typing import Any, Protocol, cast
from urllib.parse import urljoin, urlparse

from agentic_rag.ingestion.url.probe import (
    probe_interactive_markdown,
    should_probe_interactive_state,
)

_VINFAST_EXCLUDED_SELECTOR = ", ".join(
    [
        "#onetrust-consent-sdk",
        ".onetrust-pc-dark-filter",
        "header",
        "nav",
        ".navigation",
        ".breadcrumb",
        "footer",
        ".footer",
        ".chat-widget",
        "#freshdesk-widget",
    ]
)
_BM25_MULTILINGUAL_QUERY = (
    "VinFast xe dien phien ban gia ban thong so ky thuat bao hanh pin "
    "charging range vehicle model edition price specs warranty battery"
)
_SHELL_DOMAINS: set[str] = set()


class _MarkdownGenerator(Protocol):
    def generate_markdown(self, input_html: str, **kwargs: object) -> object: ...


@dataclass(frozen=True)
class Crawl4AIPage:
    """Rendered page content returned by Crawl4AI."""

    html: str
    markdown: str | None
    url: str
    links: tuple[str, ...] = ()
    content_type: str | None = "text/html"
    bm25_markdown: str | None = None
    structured_markdown: str | None = None
    probe_markdown: str | None = None
    raw_result: dict[str, Any] | None = None


@dataclass(frozen=True)
class _CrawlAttempt:
    name: str
    config: Any
    wait_until_target: str


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
    browser_config = _build_browser_config()
    run_attempts = _build_crawler_run_attempts(url)
    attempt_plan = _attempts_for_url(url, run_attempts)
    skipped_attempts = tuple(
        attempt.name for attempt in run_attempts if attempt not in attempt_plan
    )

    start_time = time.perf_counter()
    result: object | None = None
    html = ""
    selected_attempt: _CrawlAttempt | None = None
    selected_attempt_index = 0
    selected_attempt_duration = 0.0
    attempt_errors: list[str] = []
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        async with async_web_crawler(config=browser_config) as crawler:
            for attempt_index, attempt in enumerate(attempt_plan, start=1):
                attempt_start = time.perf_counter()
                try:
                    candidate_result = await crawler.arun(url=url, config=attempt.config)
                except Exception as exc:
                    attempt_errors.append(_crawl_attempt_error(attempt, exc))
                    continue

                if not bool(getattr(candidate_result, "success", True)):
                    error_message = str(
                        getattr(candidate_result, "error_message", "unknown Crawl4AI error")
                    )
                    attempt_errors.append(f"{attempt.name}: Crawl4AI failed: {error_message}")
                    continue

                candidate_html = _best_html_attr(candidate_result)
                if not candidate_html:
                    attempt_errors.append(f"{attempt.name}: Crawl4AI returned empty HTML")
                    continue
                if not _crawl_result_has_useful_content(candidate_html, candidate_result):
                    attempt_errors.append(
                        f"{attempt.name}: Crawl4AI returned low-content shell HTML"
                    )
                    _record_shell_domain(url, attempt.name)
                    continue

                result = candidate_result
                html = candidate_html
                selected_attempt = attempt
                selected_attempt_index = attempt_index
                selected_attempt_duration = time.perf_counter() - attempt_start
                break
    end_time = time.perf_counter()
    duration = end_time - start_time

    if result is None or selected_attempt is None:
        error_summary = "; ".join(attempt_errors) or "no Crawl4AI attempt produced content"
        raise RuntimeError(
            f"Crawl4AI failed to crawl {url} after {len(attempt_plan)} attempts: {error_summary}"
        )

    # Extract JS-probed diagnostics and merge into metadata for UI visibility
    metadata = getattr(result, "metadata", {}) or {}
    js_res = _merged_js_execution_result(getattr(result, "js_execution_result", None))
    if isinstance(js_res, dict):
        # Handle script errors
        script_errors = js_res.get("resource_errors")
        if isinstance(script_errors, list) and script_errors:
            res_errors = list(metadata.get("resource_errors", []))
            res_errors.extend(
                [item for item in script_errors if isinstance(item, dict) and "url" in item]
            )
            metadata["resource_errors"] = res_errors
        # Handle initialization status
        init_status = js_res.get("initialization")
        if isinstance(init_status, dict):
            metadata["initialization_status"] = init_status
    elif isinstance(js_res, list):
        # Fallback for old list-based results
        script_errors = [item for item in js_res if isinstance(item, dict) and "url" in item]
        if script_errors:
            res_errors = list(metadata.get("resource_errors", []))
            res_errors.extend(script_errors)
            metadata["resource_errors"] = res_errors

    # Capture relevant metadata from CrawlResult for diagnostics
    raw_data: dict[str, Any] = {
        "crawl_duration_seconds": duration,
        "crawl_attempt_duration_seconds": selected_attempt_duration,
        "crawl_attempt": selected_attempt.name,
        "crawl_attempt_index": selected_attempt_index,
        "crawl_attempt_count": selected_attempt_index,
        "configured_crawl_attempt_count": len(run_attempts),
        "crawl_attempts_skipped": list(skipped_attempts),
        "crawl_attempt_errors": attempt_errors,
        "wait_until_target": selected_attempt.wait_until_target,
        "success": getattr(result, "success", True),
        "status_code": getattr(result, "status_code", None),
        "error_message": getattr(result, "error_message", None),
        "links": getattr(result, "links", {}),
        "metadata": metadata,
        "images": getattr(result, "images", []),
    }

    final_url = _first_text_attr(result, ("url",)) or url
    links = tuple(
        dict.fromkeys(
            [
                *_links_from_result(getattr(result, "links", None)),
                *_links_from_html(html, base_url=final_url),
            ]
        )
    )
    return Crawl4AIPage(
        html=html,
        markdown=_markdown_text(getattr(result, "markdown", None)),
        url=final_url,
        links=links,
        bm25_markdown=_build_bm25_markdown(html, base_url=final_url),
        structured_markdown=_structured_markdown_from_result(result),
        probe_markdown=await _safe_probe_interactive_markdown(url),
        raw_result=raw_data,
    )


def reset_crawl_shell_domain_cache() -> None:
    """Clear per-session shell-domain hints used to skip wasted retry attempts."""

    _SHELL_DOMAINS.clear()


async def _safe_probe_interactive_markdown(url: str) -> str | None:
    try:
        return await probe_interactive_markdown(url)
    except Exception:
        return None


def _build_crawler_run_config(url: str) -> object:
    """Build the primary Crawl4AI run config.

    Kept for compatibility with existing tests and callers. Runtime crawling
    uses `_build_crawler_run_attempts()` so it can retry with secondary and last
    fallback configs when the main crawl fails.
    """

    return _build_crawler_run_attempts(url)[0].config


def _build_crawler_run_attempts(url: str) -> tuple[_CrawlAttempt, ...]:
    try:
        crawl4ai = import_module("crawl4ai")
    except ImportError as exc:
        raise ImportError("Crawl4AI is not installed.") from exc

    cache_mode = crawl4ai.CacheMode
    crawler_run_config = crawl4ai.CrawlerRunConfig
    markdown_generator = _build_default_markdown_generator(_build_pruning_filter())
    strict_wait_selector = _crawl4ai_wait_for_selector(url)
    main_config: dict[str, object] = {
        "cache_mode": cache_mode.BYPASS,
        "check_robots_txt": True,
        "magic": True,
        "simulate_user": True,
        "override_navigator": True,
        "excluded_tags": ["nav", "footer", "header", "script", "style"],
        "excluded_selector": _VINFAST_EXCLUDED_SELECTOR,
        "remove_overlay_elements": True,
        "remove_consent_popups": True,
        "remove_forms": False,
        "keep_data_attributes": True,
        "keep_attrs": ["data-edition", "data-price", "aria-selected", "aria-pressed"],
        "markdown_generator": markdown_generator,
        "wait_until": "load",
        "delay_before_return_html": 10.0,
        "page_timeout": 90000,
        "locale": "vi-VN",
        "user_agent": _user_agent(),
        "word_count_threshold": 5,
        "js_code": _react_spa_js_code(),
    }
    if strict_wait_selector is not None:
        main_config["wait_for"] = strict_wait_selector
    if _is_vinfast_homepage(url):
        main_config = {
            **_without_keys(main_config, "excluded_selector"),
            "excluded_tags": ["script", "style"],
        }

    secondary_config: dict[str, object] = {
        "cache_mode": cache_mode.BYPASS,
        "check_robots_txt": True,
        "magic": True,
        "simulate_user": True,
        "excluded_tags": ["nav", "footer", "header", "script", "style"],
        "excluded_selector": _VINFAST_EXCLUDED_SELECTOR,
        "remove_overlay_elements": True,
        "markdown_generator": markdown_generator,
        "wait_until": "networkidle",
        "delay_before_return_html": 2.0,
        "page_timeout": 20000,
        "locale": "vi-VN",
        "word_count_threshold": 5,
        "js_code": _react_spa_js_code(),
    }
    last_config: dict[str, object] = {
        "cache_mode": cache_mode.BYPASS,
        "check_robots_txt": True,
        "markdown_generator": markdown_generator,
        "word_count_threshold": 5,
    }
    return tuple(
        attempt
        for attempt in (
            _compatible_crawl_attempt(
                "main",
                "load",
                crawler_run_config,
                (
                    main_config,
                    _without_keys(main_config, "check_robots_txt", "override_navigator"),
                    _without_keys(main_config, "wait_for", "js_code", "keep_attrs"),
                    {},
                ),
            ),
            _compatible_crawl_attempt(
                "secondary",
                "networkidle",
                crawler_run_config,
                (
                    secondary_config,
                    _without_keys(secondary_config, "check_robots_txt", "js_code"),
                    _without_keys(secondary_config, "excluded_selector", "locale"),
                    {},
                ),
            ),
            _compatible_crawl_attempt(
                "last",
                "default",
                crawler_run_config,
                (
                    last_config,
                    _without_keys(last_config, "check_robots_txt"),
                    _without_keys(last_config, "markdown_generator"),
                    {},
                ),
            ),
        )
        if attempt is not None
    )


def _compatible_crawl_attempt(
    name: str,
    wait_until_target: str,
    crawler_run_config: Callable[..., object],
    candidate_configs: tuple[dict[str, object], ...],
) -> _CrawlAttempt | None:
    for config_kwargs in candidate_configs:
        try:
            return _CrawlAttempt(
                name=name,
                config=crawler_run_config(**config_kwargs),
                wait_until_target=wait_until_target,
            )
        except TypeError:
            continue
    return None


def _without_keys(config: dict[str, object], *keys: str) -> dict[str, object]:
    excluded = set(keys)
    return {key: value for key, value in config.items() if key not in excluded}


def _crawl_attempt_error(attempt: _CrawlAttempt, exc: Exception) -> str:
    return f"{attempt.name}: {type(exc).__name__}: {exc}"


def _attempts_for_url(url: str, attempts: tuple[_CrawlAttempt, ...]) -> tuple[_CrawlAttempt, ...]:
    domain = _crawl_domain(url)
    if not domain or domain not in _SHELL_DOMAINS:
        return attempts
    last_attempt = tuple(attempt for attempt in attempts if attempt.name == "last")
    return last_attempt or attempts


def _record_shell_domain(url: str, attempt_name: str) -> None:
    if attempt_name != "main":
        return
    domain = _crawl_domain(url)
    if domain:
        _SHELL_DOMAINS.add(domain)


def _crawl_domain(url: str) -> str:
    return urlparse(url.strip()).netloc.lower().split("@")[-1].split(":")[0]


def _crawl4ai_wait_for_selector(url: str) -> str | None:
    if _is_vinfast_homepage(url):
        return (
            "js:() => document.querySelectorAll('a[href]').length >= 20 "
            "&& (document.body?.innerText || '').length > 500"
        )
    if should_probe_interactive_state(url):
        return (
            "js:() => Boolean(window.carDeposit?.products) "
            "|| (document.body && document.body.innerText.length > 1000)"
        )
    return (
        "js:() => Boolean(document.querySelector('main, [data-loaded], .main-content, "
        "#root, #app')) || (document.body && document.body.innerText.length > 500)"
    )


def _react_spa_js_code() -> list[str]:
    return [
        "window.scrollTo(0, document.body.scrollHeight);",
        "await new Promise(r => setTimeout(r, 800));",
        "window.scrollTo(0, 0);",
        (
            "for (const el of document.querySelectorAll('[aria-expanded=false], "
            ".accordion button, [role=tab]')) { "
            "try { el.click(); await new Promise(r => setTimeout(r, 350)); } catch (e) {} "
            "}"
        ),
        "await new Promise(r => setTimeout(r, 800));",
        _diagnostic_js_code(),
    ]


def _diagnostic_js_code() -> str:
    return (
        "(() => ({ "
        "resource_errors: Array.from(window.performance.getEntriesByType('resource'))"
        ".filter(r => r.initiatorType === 'script' && r.duration === 0)"
        ".map(r => ({url: r.name, status: 0, error: 'Script failed to load or blocked'})), "
        "initialization: { react: !!window.React, "
        "react_dom: !!window.ReactDOM, car_deposit: !!window.carDeposit } "
        "}))()"
    )


def _merged_js_execution_result(value: object) -> dict[str, object] | list[object] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return None

    merged: dict[str, object] = {}
    passthrough: list[object] = []
    for item in value:
        if not isinstance(item, dict):
            passthrough.append(item)
            continue
        resource_errors = item.get("resource_errors")
        if isinstance(resource_errors, list):
            existing_errors = merged.setdefault("resource_errors", [])
            if isinstance(existing_errors, list):
                existing_errors.extend(resource_errors)
        initialization = item.get("initialization")
        if isinstance(initialization, dict):
            merged["initialization"] = initialization
    return merged if merged else passthrough


def _build_browser_config() -> object:
    try:
        crawl4ai = import_module("crawl4ai")
    except ImportError as exc:
        raise ImportError("Crawl4AI is not installed.") from exc

    browser_config = crawl4ai.BrowserConfig
    candidate_configs: tuple[dict[str, object], ...] = (
        {
            "browser_type": "chromium",
            "headless": True,
            "viewport_width": 1440,
            "viewport_height": 1200,
            "java_script_enabled": True,
            "headers": {"Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"},
            "user_agent": _user_agent(),
        },
        {
            "headless": True,
            "viewport_width": 1440,
            "viewport_height": 1200,
            "java_script_enabled": True,
        },
        {"headless": True},
    )
    for config_kwargs in candidate_configs:
        try:
            return browser_config(**config_kwargs)
        except TypeError:
            continue
    return browser_config()


def _build_pruning_filter() -> object | None:
    try:
        content_filter_strategy = import_module("crawl4ai.content_filter_strategy")
    except ImportError:
        return None

    pruning_filter = cast(Callable[..., object], content_filter_strategy.PruningContentFilter)
    for kwargs in (
        {"threshold": 0.48, "threshold_type": "fixed"},
        {"threshold": 0.48},
        {},
    ):
        try:
            return pruning_filter(**kwargs)
        except TypeError:
            continue
    return None


def _build_bm25_filter() -> object | None:
    try:
        content_filter_strategy = import_module("crawl4ai.content_filter_strategy")
    except ImportError:
        return None

    bm25_filter = cast(Callable[..., object], content_filter_strategy.BM25ContentFilter)
    for kwargs in (
        {
            "user_query": _BM25_MULTILINGUAL_QUERY,
            "bm25_threshold": 1.0,
            "language": "english",
            "use_stemming": False,
        },
        {
            "user_query": _BM25_MULTILINGUAL_QUERY,
            "bm25_threshold": 1.0,
            "language": "english",
        },
        {"user_query": _BM25_MULTILINGUAL_QUERY},
    ):
        try:
            return bm25_filter(**kwargs)
        except TypeError:
            continue
    return None


def _build_default_markdown_generator(content_filter: object | None) -> _MarkdownGenerator | None:
    try:
        markdown_generation_strategy = import_module("crawl4ai.markdown_generation_strategy")
    except ImportError:
        return None

    default_markdown_generator = cast(
        Callable[..., _MarkdownGenerator],
        markdown_generation_strategy.DefaultMarkdownGenerator,
    )
    for kwargs in (
        {
            "content_filter": content_filter,
            "options": {"ignore_links": False},
            "content_source": "cleaned_html",
        },
        {"content_filter": content_filter, "content_source": "cleaned_html"},
        {"content_filter": content_filter},
        {},
    ):
        try:
            return default_markdown_generator(**kwargs)
        except TypeError:
            continue
    return None


def _build_bm25_markdown(html: str, *, base_url: str) -> str | None:
    bm25_filter = _build_bm25_filter()
    if bm25_filter is None:
        return None
    markdown_generator = _build_default_markdown_generator(bm25_filter)
    if markdown_generator is None:
        return None

    try:
        markdown_result = markdown_generator.generate_markdown(
            html,
            base_url=base_url,
            content_filter=bm25_filter,
            citations=False,
        )
    except Exception:
        return None
    return _markdown_text(markdown_result)


def _markdown_text(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if value is None:
        return None
    for attr_name in (
        "fit_markdown",
        "raw_markdown",
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


def _links_from_html(html: str, *, base_url: str) -> tuple[str, ...]:
    parser = _HtmlLinkParser(base_url=base_url)
    try:
        parser.feed(html)
    except Exception:
        return ()
    return tuple(dict.fromkeys(parser.links))


def _crawl_result_has_useful_content(html: str, result: object) -> bool:
    links = (
        *_links_from_result(getattr(result, "links", None)),
        *_links_from_html(html, base_url=_first_text_attr(result, ("url",)) or ""),
    )
    link_count = len(tuple(dict.fromkeys(links)))
    markdown = _markdown_text(getattr(result, "markdown", None)) or ""
    if _word_count(markdown) >= 30:
        return True
    visible_text = _html_visible_text(html)
    visible_words = _word_count(visible_text)
    if visible_words >= 30:
        return True
    if _looks_like_loading_or_promo_shell(markdown) or _looks_like_loading_or_promo_shell(html):
        return False
    if link_count >= 5:
        return True
    return len(visible_text.strip()) >= 200 and link_count >= 5


def _looks_like_loading_or_promo_shell(value: str) -> bool:
    cleaned = re.sub(r"<[^>]+>", " ", value)
    cleaned = " ".join(cleaned.split()).lower()
    if not cleaned:
        return True
    shell_markers = (
        "loading",
        "please wait",
        "\u0111ang t\u1ea3i",
        "dang tai",
        "\u01b0u \u0111\u00e3i ch\u1ec9 t\u1edbi",
        "uu dai chi toi",
    )
    return any(marker in cleaned for marker in shell_markers) and _word_count(cleaned) < 30


def _is_vinfast_homepage(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().split(":")[0]
    path = parsed.path.rstrip("/")
    return host == "vinfastauto.com" and path in {"", "/vn_vi"}


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def _html_visible_word_count(html: str) -> int:
    return _word_count(_html_visible_text(html))


def _html_visible_text(html: str) -> str:
    parser = _HtmlTextStatsParser()
    try:
        parser.feed(html)
    except Exception:
        return ""
    return " ".join(parser.text_parts)


class _HtmlLinkParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {key.lower(): value for key, value in attrs if value}
        href = attr_map.get("href")
        if not href:
            return
        self.links.append(urljoin(self._base_url, href))


class _HtmlTextStatsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "head", "noscript", "svg"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "head", "noscript", "svg"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = data.strip()
        if text:
            self.text_parts.append(text)


def _structured_markdown_from_result(result: object) -> str | None:
    tables = getattr(result, "tables", None)
    if not isinstance(tables, list) or not tables:
        return None

    lines: list[str] = ["# Structured Page Data", ""]
    for index, table in enumerate(tables, start=1):
        table_markdown = _table_to_markdown(table)
        if not table_markdown:
            continue
        lines.extend([f"## Table {index}", "", table_markdown, ""])

    markdown = "\n".join(lines).strip()
    return markdown if markdown != "# Structured Page Data" else None


def _table_to_markdown(table: object) -> str:
    if isinstance(table, str):
        return table.strip()
    if not isinstance(table, dict):
        return ""

    for key in ("markdown", "text", "content"):
        value = table.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    rows = _table_rows(table)
    if not rows:
        return ""

    width = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (width - len(row)) for row in rows]
    header = normalized_rows[0]
    lines = [
        "| " + " | ".join(_clean_table_cell(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in normalized_rows[1:]:
        lines.append("| " + " | ".join(_clean_table_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _table_rows(table: dict[str, object]) -> list[list[str]]:
    raw_rows = table.get("rows") or table.get("data")
    if not isinstance(raw_rows, list):
        return []

    rows: list[list[str]] = []
    headers = table.get("headers")
    if isinstance(headers, list) and headers:
        rows.append([str(header) for header in headers])
    for raw_row in raw_rows:
        if isinstance(raw_row, list):
            rows.append([str(cell) for cell in raw_row])
        elif isinstance(raw_row, dict):
            if not rows:
                rows.append([str(key) for key in raw_row])
            rows.append([str(value) for value in raw_row.values()])
    return rows


def _clean_table_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("|", "\\|").strip()


def _first_text_attr(value: object, attr_names: tuple[str, ...]) -> str:
    for attr_name in attr_names:
        attr_value = getattr(value, attr_name, None)
        if isinstance(attr_value, str) and attr_value.strip():
            return attr_value.strip()
    return ""


def _best_html_attr(value: object) -> str:
    cleaned_html = _first_text_attr(value, ("cleaned_html",))
    raw_html = _first_text_attr(value, ("html",))
    fit_html = _first_text_attr(value, ("fit_html",))
    candidates = [candidate for candidate in (cleaned_html, fit_html, raw_html) if candidate]
    if not candidates:
        return ""
    if _looks_like_title_only_html(cleaned_html) and raw_html:
        return raw_html
    return max(candidates, key=_html_content_score)


def _looks_like_title_only_html(html: str) -> bool:
    if not html:
        return False
    lowered = html.lower()
    return len(html) < 500 and "<title" in lowered and "<body" not in lowered


def _html_content_score(html: str) -> int:
    lowered = html.lower()
    body_bonus = 2_000 if "<body" in lowered else 0
    content_markers = sum(
        lowered.count(marker)
        for marker in (
            "<main",
            "<article",
            "<section",
            "<h1",
            "<h2",
            "<p",
            "<li",
            "vf 9",
            "vinfast",
        )
    )
    return len(html) + body_bonus + (content_markers * 200)


def _user_agent() -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36 AgenticRAGGroup1/0.1"
    )
