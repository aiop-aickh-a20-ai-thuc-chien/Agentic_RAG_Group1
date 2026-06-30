from __future__ import annotations

from http.client import IncompleteRead

import pytest

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.acquisition import (
    fetch_url,
    reject_pdf_content_type,
    reject_pdf_url,
    validate_http_url,
)
from agentic_rag.ingestion.url.acquisition import fetcher as fetcher_module
from agentic_rag.ingestion.url.extractor import ExtractedMarkdown
from agentic_rag.ingestion.url.quality import (
    analyze_url_quality,
    attach_quality_metadata,
    detect_page_profile,
    evaluate_quality_gate,
    should_try_rendered_parser,
)
from agentic_rag.ingestion.url.rendering import RenderOptions, render_url_markdown


def test_validate_http_url_rejects_non_http() -> None:
    with pytest.raises(ValueError, match="absolute http or https URL"):
        validate_http_url("file:///tmp/page.html")


def test_acquisition_rejects_pdf_inputs() -> None:
    with pytest.raises(ValueError, match="PDF URL"):
        reject_pdf_url("https://example.com/file.pdf")
    with pytest.raises(ValueError, match="PDF response"):
        reject_pdf_content_type("application/pdf")


def test_fetch_url_wraps_incomplete_reads_for_rendered_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*_args: object, **_kwargs: object) -> object:
        raise IncompleteRead(b"")

    monkeypatch.setattr(fetcher_module, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="IncompleteRead"):
        fetch_url("https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html")


def test_render_url_markdown_returns_diagnostics_from_injected_extractor() -> None:
    def fake_extractor(url: str) -> ExtractedMarkdown:
        assert url == "https://example.com"
        return ExtractedMarkdown(markdown="# Title", parser_name="fake-renderer")

    attempt = render_url_markdown("https://example.com", extractor=fake_extractor)

    assert attempt.used_browser is True
    assert attempt.recovered is True
    assert attempt.extracted is not None
    assert attempt.extracted.parser_name == "fake-renderer"


def test_render_url_markdown_captures_extractor_errors() -> None:
    def fake_extractor(_url: str) -> ExtractedMarkdown:
        raise RuntimeError("browser unavailable")

    attempt = render_url_markdown("https://example.com", extractor=fake_extractor)

    assert attempt.used_browser is True
    assert attempt.recovered is False
    assert attempt.extracted is None
    assert attempt.error is not None
    assert "browser unavailable" in attempt.error
    assert attempt.attempt_count == 2
    assert attempt.retry_errors == ["browser unavailable", "browser unavailable"]


def test_render_url_markdown_passes_render_options_to_extractor() -> None:
    captured_options: dict[str, object] = {}

    def fake_extractor(url: str, **kwargs: object) -> ExtractedMarkdown:
        assert url == "https://example.com"
        captured_options.update(kwargs)
        return ExtractedMarkdown(markdown="# Title", parser_name="fake-renderer")

    attempt = render_url_markdown(
        "https://example.com",
        extractor=fake_extractor,
        options=RenderOptions(timeout_seconds=12, wait_until="domcontentloaded"),
    )

    assert attempt.recovered is True
    assert attempt.options is not None
    assert attempt.options.timeout_seconds == 12
    assert captured_options["timeout_seconds"] == 12
    assert captured_options["wait_until"] == "domcontentloaded"
    assert captured_options["settle_after_scroll_ms"] == 800
    assert captured_options["settle_after_expand_ms"] == 400


def test_render_url_markdown_allows_unbounded_timeout_for_crawlee_mode() -> None:
    captured_options: dict[str, object] = {}

    def fake_extractor(url: str, **kwargs: object) -> ExtractedMarkdown:
        assert url == "https://example.com"
        captured_options.update(kwargs)
        return ExtractedMarkdown(markdown="# Title", parser_name="fake-crawlee")

    attempt = render_url_markdown(
        "https://example.com",
        extractor=fake_extractor,
        options=RenderOptions(timeout_seconds=None, retry_on_failure=False),
    )

    assert attempt.recovered is True
    assert captured_options["timeout_seconds"] is None
    assert attempt.attempt_count == 1


def test_render_url_markdown_retries_with_lightweight_wait_strategy() -> None:
    wait_strategies: list[object] = []

    def fake_extractor(url: str, **kwargs: object) -> ExtractedMarkdown:
        assert url == "https://example.com"
        wait_strategies.append(kwargs["wait_until"])
        if kwargs["wait_until"] == "load":
            raise RuntimeError("load timeout")
        return ExtractedMarkdown(markdown="# Recovered", parser_name="fake-renderer")

    attempt = render_url_markdown("https://example.com", extractor=fake_extractor)

    assert attempt.recovered is True
    assert attempt.attempt_count == 2
    assert attempt.retry_errors == ["load timeout"]
    assert wait_strategies == ["load", "domcontentloaded"]


def test_render_url_markdown_reuses_cached_extraction(tmp_path) -> None:
    calls = 0

    def first_extractor(url: str, **_kwargs: object) -> ExtractedMarkdown:
        nonlocal calls
        calls += 1
        assert url == "https://example.com"
        return ExtractedMarkdown(
            markdown="# Cached",
            parser_name="fake-renderer",
            final_url=url,
            rendered_html="<html><body><h1>Cached</h1></body></html>",
        )

    options = RenderOptions(cache_dir=tmp_path)
    first_attempt = render_url_markdown(
        "https://example.com",
        extractor=first_extractor,
        options=options,
    )

    def failing_extractor(_url: str, **_kwargs: object) -> ExtractedMarkdown:
        raise RuntimeError("cache was not used")

    cached_attempt = render_url_markdown(
        "https://example.com",
        extractor=failing_extractor,
        options=options,
    )

    assert first_attempt.recovered is True
    assert calls == 1
    assert cached_attempt.from_cache is True
    assert cached_attempt.extracted is not None
    assert cached_attempt.extracted.markdown == "# Cached"


def test_quality_report_and_metadata_attachment() -> None:
    chunk = Chunk(
        chunk_id="url_example_c0001",
        text="# Title\n\nUseful content with enough words for a meaningful URL chunk.",
        metadata={"source": "https://example.com", "source_type": "unknown"},
    )

    report = analyze_url_quality(
        "# Title\n\nUseful content with enough words for a meaningful URL chunk. "
        "This fixture has enough body text to pass the local quality threshold.",
        [chunk],
    )
    enriched = attach_quality_metadata([chunk], report)

    assert report.verdict == "useful"
    assert report.chunk_count == 1
    assert enriched[0].metadata["url_quality"]["verdict"] == "useful"


def test_page_profile_requires_render_for_react_product_pages() -> None:
    profile = detect_page_profile(
        "https://shop.vinfastauto.com/vn_vi/VF8.html",
        '<html><script id="__NEXT_DATA__"></script><body><div id="__next"></div></body></html>',
    )

    assert profile.page_type == "product_detail"
    assert profile.requires_rendered_parser is True
    assert "next_data" in profile.dynamic_signals
    assert profile.latency_budget_seconds == 20


def test_page_profile_classifies_vinfast_model_slugs_as_product_pages() -> None:
    profile = detect_page_profile(
        "https://vinfastauto.com/vn_vi/limo-green",
        "<html><body><main><h1>Limo Green</h1></main></body></html>",
    )

    assert profile.page_type == "product_detail"
    assert profile.requires_rendered_parser is True
    assert profile.latency_budget_seconds == 20


def test_quality_gate_requests_render_for_low_signal_dynamic_shell() -> None:
    chunk = Chunk(
        chunk_id="url_shell_c001",
        text="# VF 8",
        metadata={"source": "https://shop.vinfastauto.com/vn_vi/VF8.html", "title": "VF 8"},
    )
    profile = detect_page_profile(
        "https://shop.vinfastauto.com/vn_vi/VF8.html",
        '<html><script id="__NEXT_DATA__"></script><div id="__next"></div></html>',
    )
    report = analyze_url_quality("# VF 8", [chunk])
    gate = evaluate_quality_gate(
        parser="static",
        profile=profile,
        report=report,
        chunks=[chunk],
    )

    assert gate.status == "rejected"
    assert gate.accepted is False
    assert should_try_rendered_parser(profile, gate) is True
