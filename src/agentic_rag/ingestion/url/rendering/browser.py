"""Browser-rendering helpers for URL ingestion."""

from __future__ import annotations

import json
from collections.abc import Callable
from hashlib import sha256
from inspect import Parameter, signature
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.ingestion.url.extractor import ExtractedMarkdown, extract_markdown_with_playwright

RenderWaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]


class RenderOptions(BaseModel):
    """Browser rendering knobs derived from page-type quality strategy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout_seconds: int = Field(default=60, gt=0)
    wait_until: RenderWaitUntil = "load"
    settle_after_scroll_ms: int = Field(default=800, ge=0)
    settle_after_expand_ms: int = Field(default=400, ge=0)
    retry_on_failure: bool = True
    retry_wait_until: RenderWaitUntil = "domcontentloaded"
    retry_timeout_seconds: int | None = Field(default=None, gt=0)
    cache_dir: Path | None = None
    use_cache: bool = True


class RenderAttempt(BaseModel):
    """Result of trying a browser-backed URL extraction path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    used_browser: bool
    recovered: bool = False
    extracted: ExtractedMarkdown | None = None
    error: str | None = None
    options: RenderOptions | None = None
    attempt_count: int = 0
    from_cache: bool = False
    retry_errors: list[str] = Field(default_factory=list)


def render_url_markdown(
    url: str,
    *,
    enabled: bool = True,
    extractor: Callable[..., ExtractedMarkdown] = extract_markdown_with_playwright,
    options: RenderOptions | None = None,
) -> RenderAttempt:
    """Try browser extraction and return diagnostics instead of raising."""

    render_options = options or RenderOptions()
    if not enabled:
        return RenderAttempt(
            used_browser=False,
            error="browser extraction disabled",
            options=render_options,
        )
    attempt_options_list = _render_attempt_options(render_options)
    for cached_options in attempt_options_list:
        cached = _read_cached_extraction(url, cached_options)
        if cached is not None:
            return RenderAttempt(
                used_browser=True,
                recovered=bool(cached.markdown.strip()),
                extracted=cached,
                options=render_options,
                from_cache=True,
            )
    errors: list[str] = []
    for attempt_index, attempt_options in enumerate(attempt_options_list, start=1):
        try:
            extracted = _call_extractor(extractor, url, attempt_options)
        except Exception as exc:
            errors.append(str(exc))
            continue
        _write_cached_extraction(url, attempt_options, extracted)
        return RenderAttempt(
            used_browser=True,
            recovered=bool(extracted.markdown.strip()),
            extracted=extracted,
            options=render_options,
            attempt_count=attempt_index,
            retry_errors=errors,
        )
    error = "; ".join(errors) if errors else "browser extraction failed"
    return RenderAttempt(
        used_browser=True,
        error=error,
        options=render_options,
        attempt_count=len(attempt_options_list),
        retry_errors=errors,
    )


def _call_extractor(
    extractor: Callable[..., ExtractedMarkdown],
    url: str,
    options: RenderOptions,
) -> ExtractedMarkdown:
    if _accepts_render_options(extractor):
        return extractor(
            url,
            timeout_seconds=options.timeout_seconds,
            wait_until=options.wait_until,
            settle_after_scroll_ms=options.settle_after_scroll_ms,
            settle_after_expand_ms=options.settle_after_expand_ms,
        )
    return extractor(url)


def _accepts_render_options(extractor: Callable[..., ExtractedMarkdown]) -> bool:
    try:
        parameters = signature(extractor).parameters
    except (TypeError, ValueError):
        return True
    if any(parameter.kind == Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return True
    return "timeout_seconds" in parameters


def _render_attempt_options(options: RenderOptions) -> list[RenderOptions]:
    attempts = [options]
    if not options.retry_on_failure:
        return attempts
    retry_timeout_seconds = options.retry_timeout_seconds or options.timeout_seconds
    retry_options = options.model_copy(
        update={
            "timeout_seconds": retry_timeout_seconds,
            "wait_until": options.retry_wait_until,
            "settle_after_scroll_ms": max(options.settle_after_scroll_ms // 2, 0),
            "settle_after_expand_ms": max(options.settle_after_expand_ms // 2, 0),
        }
    )
    if retry_options != options:
        attempts.append(retry_options)
    return attempts


def _read_cached_extraction(url: str, options: RenderOptions) -> ExtractedMarkdown | None:
    if not options.cache_dir or not options.use_cache:
        return None
    cache_path = _cache_run_dir(url, options) / "extracted.json"
    if not cache_path.exists():
        return None
    try:
        return ExtractedMarkdown.model_validate_json(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cached_extraction(
    url: str,
    options: RenderOptions,
    extracted: ExtractedMarkdown,
) -> None:
    if not options.cache_dir or not options.use_cache:
        return
    run_dir = _cache_run_dir(url, options)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "extracted.json").write_text(
        json.dumps(extracted.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "parsed.md").write_text(extracted.markdown.rstrip() + "\n", encoding="utf-8")
    if extracted.rendered_html:
        (run_dir / "rendered.html").write_text(extracted.rendered_html, encoding="utf-8")
    manifest = {
        "url": url,
        "parser": extracted.parser_name,
        "final_url": extracted.final_url,
        "timeout_seconds": options.timeout_seconds,
        "wait_until": options.wait_until,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _cache_run_dir(url: str, options: RenderOptions) -> Path:
    if options.cache_dir is None:
        raise ValueError("cache_dir is required for render cache paths.")
    cache_key = sha256(f"{url}|{options.wait_until}".encode()).hexdigest()[:16]
    return options.cache_dir / cache_key


__all__ = ["RenderAttempt", "RenderOptions", "RenderWaitUntil", "render_url_markdown"]
