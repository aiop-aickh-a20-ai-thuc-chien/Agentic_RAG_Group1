from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import ClassVar

import pytest

from agentic_rag.ingestion.url import crawler as crawler_module


class _FakeCacheMode:
    BYPASS = "bypass"


class _FakeBrowserConfig:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakeCrawlerRunConfig:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakeAsyncWebCrawler:
    results: ClassVar[list[object]] = []
    seen_configs: ClassVar[list[_FakeCrawlerRunConfig]] = []

    def __init__(self, *, config: object) -> None:
        self.config = config

    async def __aenter__(self) -> _FakeAsyncWebCrawler:
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None

    async def arun(self, *, url: str, config: _FakeCrawlerRunConfig) -> object:
        self.seen_configs.append(config)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _fake_crawl4ai_module() -> SimpleNamespace:
    return SimpleNamespace(
        AsyncWebCrawler=_FakeAsyncWebCrawler,
        BrowserConfig=_FakeBrowserConfig,
        CacheMode=_FakeCacheMode,
        CrawlerRunConfig=_FakeCrawlerRunConfig,
    )


def _crawl_result(
    *,
    url: str = "https://example.edu/page",
    html: str = (
        "<html><body><main><h1>Page</h1>"
        '<a href="/page-1">Page 1</a>'
        '<a href="/page-2">Page 2</a>'
        '<a href="/page-3">Page 3</a>'
        '<a href="/page-4">Page 4</a>'
        '<a href="/page-5">Page 5</a>'
        "<p>"
        + ("Useful page content for retrieval diagnostics. " * 8)
        + "</p></main></body></html>"
    ),
    markdown: str | None = "# Page\n\n" + ("Useful page content for retrieval diagnostics. " * 8),
    success: bool = True,
    error_message: str | None = None,
    links: object | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        success=success,
        error_message=error_message,
        url=url,
        cleaned_html=html,
        html=html,
        fit_html="",
        markdown=markdown,
        links=links or {},
        metadata={},
        images=[],
        tables=[],
        status_code=200 if success else 500,
        js_execution_result=None,
    )


def test_links_from_html_extracts_absolute_links() -> None:
    links = crawler_module._links_from_html(
        """
        <html>
          <body>
            <a href="/vn_vi/tin-tuc">Tin tuc</a>
            <a href="https://market.vinhomes.vn/">Market</a>
            <a href="#top">Top</a>
          </body>
        </html>
        """,
        base_url="https://vinhomes.vn/vi",
    )

    assert links == (
        "https://vinhomes.vn/vn_vi/tin-tuc",
        "https://market.vinhomes.vn/",
        "https://vinhomes.vn/vi#top",
    )


@pytest.fixture
def fake_crawl4ai(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    crawler_module.reset_crawl_shell_domain_cache()

    def fake_import_module(name: str) -> object:
        if name == "crawl4ai":
            return _fake_crawl4ai_module()
        raise ImportError(name)

    async def fake_probe_interactive_markdown(url: str) -> None:
        return None

    _FakeAsyncWebCrawler.results = []
    _FakeAsyncWebCrawler.seen_configs = []
    monkeypatch.setattr(crawler_module, "import_module", fake_import_module)
    monkeypatch.setattr(
        crawler_module,
        "probe_interactive_markdown",
        fake_probe_interactive_markdown,
    )
    yield
    crawler_module.reset_crawl_shell_domain_cache()


def test_secondary_attempt_uses_fast_shell_timeout(fake_crawl4ai: None) -> None:
    attempts = crawler_module._build_crawler_run_attempts("https://vinfastauto.com/vn_vi")
    secondary = next(attempt for attempt in attempts if attempt.name == "secondary")

    assert secondary.config.kwargs["page_timeout"] == 20000
    assert secondary.config.kwargs["delay_before_return_html"] == 2.0


@pytest.mark.asyncio
async def test_crawl4ai_retries_secondary_after_main_error(fake_crawl4ai: None) -> None:
    _FakeAsyncWebCrawler.results = [
        RuntimeError("main timeout"),
        _crawl_result(),
    ]

    page = await crawler_module._crawl_url_with_crawl4ai("https://example.edu/page")

    assert page.html.startswith("<html>")
    assert len(_FakeAsyncWebCrawler.seen_configs) == 2
    assert page.raw_result is not None
    assert page.raw_result["crawl_attempt"] == "secondary"
    assert page.raw_result["crawl_attempt_count"] == 2
    assert page.raw_result["configured_crawl_attempt_count"] == 3
    assert page.raw_result["crawl_attempt_errors"] == [
        "main: RuntimeError: main timeout",
    ]


@pytest.mark.asyncio
async def test_crawl4ai_combines_crawl4ai_and_html_links(fake_crawl4ai: None) -> None:
    _FakeAsyncWebCrawler.results = [
        _crawl_result(
            links={"internal": [{"href": "https://example.edu/from-crawler"}]},
            html=(
                "<html><body><main><h1>Page</h1></main>"
                '<a href="/from-html">HTML link</a></body></html>'
            ),
        ),
    ]

    page = await crawler_module._crawl_url_with_crawl4ai("https://example.edu/page")

    assert page.links == (
        "https://example.edu/from-crawler",
        "https://example.edu/from-html",
    )


@pytest.mark.asyncio
async def test_crawl4ai_retries_last_after_main_and_secondary_failures(
    fake_crawl4ai: None,
) -> None:
    _FakeAsyncWebCrawler.results = [
        _crawl_result(success=False, error_message="blocked by robots"),
        _crawl_result(html="", markdown=None),
        _crawl_result(),
    ]

    page = await crawler_module._crawl_url_with_crawl4ai("https://example.edu/page")

    assert len(_FakeAsyncWebCrawler.seen_configs) == 3
    assert page.raw_result is not None
    assert page.raw_result["crawl_attempt"] == "last"
    assert page.raw_result["crawl_attempt_errors"] == [
        "main: Crawl4AI failed: blocked by robots",
        "secondary: Crawl4AI returned empty HTML",
    ]


@pytest.mark.asyncio
async def test_crawl4ai_retries_last_after_large_low_content_shell(
    fake_crawl4ai: None,
) -> None:
    shell_html = (
        "<html><head><title>Shell</title></head><body><div>Promo</div>"
        + (" " * 25_000)
        + "</body></html>"
    )
    useful_html = (
        "<html><body><section><h1>VinFast</h1>"
        '<a href="/vn_vi/vf9">VF 9</a>'
        '<a href="/vn_vi/vf8">VF 8</a>'
        '<a href="/vn_vi/vf7">VF 7</a>'
        '<a href="/vn_vi/vf6">VF 6</a>'
        '<a href="/vn_vi/vf5">VF 5</a>'
        "<p>"
        + ("Useful vehicle homepage content for electric car buyers. " * 8)
        + "</p></section></body></html>"
    )
    _FakeAsyncWebCrawler.results = [
        _crawl_result(html=shell_html, markdown="Promo"),
        _crawl_result(html=shell_html, markdown="Promo"),
        _crawl_result(
            url="https://vinfastauto.com/vn_vi",
            html=useful_html,
            markdown="# VinFast\n\n"
            + ("Useful vehicle homepage content for electric car buyers. " * 8),
        ),
    ]

    page = await crawler_module._crawl_url_with_crawl4ai("https://vinfastauto.com/vn_vi")

    assert len(_FakeAsyncWebCrawler.seen_configs) == 3
    assert page.raw_result is not None
    assert page.raw_result["crawl_attempt"] == "last"
    assert page.raw_result["crawl_attempt_errors"] == [
        "main: Crawl4AI returned low-content shell HTML",
        "secondary: Crawl4AI returned low-content shell HTML",
    ]
    assert page.links == (
        "https://vinfastauto.com/vn_vi/vf9",
        "https://vinfastauto.com/vn_vi/vf8",
        "https://vinfastauto.com/vn_vi/vf7",
        "https://vinfastauto.com/vn_vi/vf6",
        "https://vinfastauto.com/vn_vi/vf5",
    )


@pytest.mark.asyncio
async def test_crawl4ai_retries_after_short_loading_shell(
    fake_crawl4ai: None,
) -> None:
    useful_html = (
        "<html><body><section><h1>VinFast</h1>"
        '<a href="/vn_vi/vf9">VF 9</a>'
        '<a href="/vn_vi/vf8">VF 8</a>'
        '<a href="/vn_vi/vf7">VF 7</a>'
        '<a href="/vn_vi/vf6">VF 6</a>'
        '<a href="/vn_vi/vf5">VF 5</a>'
        "<p>" + ("VinFast E-SUV price range battery warranty charging support. " * 8) + "</p>"
        "<p>Dòng xe E-SUV có giá bán từ 1.229.180.000 VNĐ.</p>"
        "</section></body></html>"
    )
    _FakeAsyncWebCrawler.results = [
        _crawl_result(html="<html><body>Loading...</body></html>", markdown="Loading..."),
        _crawl_result(
            url="https://vinfastauto.com/vn_vi",
            html=useful_html,
            markdown="# VinFast\n\nDòng xe E-SUV có giá bán từ 1.229.180.000 VNĐ.",
        ),
    ]

    page = await crawler_module._crawl_url_with_crawl4ai("https://vinfastauto.com/vn_vi")

    assert len(_FakeAsyncWebCrawler.seen_configs) == 2
    assert page.raw_result is not None
    assert page.raw_result["crawl_attempt"] == "secondary"
    assert page.raw_result["crawl_attempt_errors"] == [
        "main: Crawl4AI returned low-content shell HTML",
    ]
    assert page.links == (
        "https://vinfastauto.com/vn_vi/vf9",
        "https://vinfastauto.com/vn_vi/vf8",
        "https://vinfastauto.com/vn_vi/vf7",
        "https://vinfastauto.com/vn_vi/vf6",
        "https://vinfastauto.com/vn_vi/vf5",
    )


@pytest.mark.asyncio
async def test_child_url_skips_main_secondary_after_seed_shell(
    fake_crawl4ai: None,
) -> None:
    seed_url = "https://vinfastauto.com/vn_vi"
    child_url = "https://vinfastauto.com/vn_vi/ve-chung-toi"
    shell_html = "<html><body>Loading...</body></html>"
    _FakeAsyncWebCrawler.results = [
        _crawl_result(url=seed_url, html=shell_html, markdown="Loading..."),
        _crawl_result(url=seed_url, html=shell_html, markdown="Loading..."),
        _crawl_result(url=seed_url),
        _crawl_result(url=child_url),
    ]

    await crawler_module._crawl_url_with_crawl4ai(seed_url)
    child_page = await crawler_module._crawl_url_with_crawl4ai(child_url)

    assert len(_FakeAsyncWebCrawler.seen_configs) == 4
    assert child_page.raw_result is not None
    assert child_page.raw_result["crawl_attempt"] == "last"
    assert child_page.raw_result["crawl_attempt_count"] == 1
    assert child_page.raw_result["crawl_attempts_skipped"] == ["main", "secondary"]


def test_reset_crawl_shell_domain_cache_clears_domain_hint() -> None:
    crawler_module._SHELL_DOMAINS.add("vinfastauto.com")

    crawler_module.reset_crawl_shell_domain_cache()

    assert "vinfastauto.com" not in crawler_module._SHELL_DOMAINS


def test_shell_gate_rejects_promo_shell_and_accepts_good_page() -> None:
    shell = _crawl_result(
        html=("<html><body><title>VinFast</title><p>Uu dai chi toi 31/12!</p></body></html>"),
        markdown="Uu dai chi toi 31/12!",
        links={"internal": [], "external": []},
    )
    good = _crawl_result()

    assert crawler_module._crawl_result_has_useful_content(shell.html, shell) is False
    assert crawler_module._crawl_result_has_useful_content(good.html, good) is True


@pytest.mark.asyncio
async def test_vinfast_homepage_main_config_keeps_page_links(
    fake_crawl4ai: None,
) -> None:
    _FakeAsyncWebCrawler.results = [
        _crawl_result(
            url="https://vinfastauto.com/vn_vi",
            html=(
                "<html><body>"
                '<a href="/vn_vi/vf9">VF 9</a>'
                '<a href="/vn_vi/vf8">VF 8</a>'
                '<a href="/vn_vi/vf7">VF 7</a>'
                '<a href="/vn_vi/vf6">VF 6</a>'
                '<a href="/vn_vi/vf5">VF 5</a>'
                "<p>"
                + ("VinFast E-SUV price range battery warranty charging support. " * 8)
                + "</p>"
                "<p>Dòng xe E-SUV có giá bán từ 1.229.180.000 VNĐ.</p>"
                "</body></html>"
            ),
            markdown="# VinFast\n\nDòng xe E-SUV có giá bán từ 1.229.180.000 VNĐ.",
        ),
    ]

    await crawler_module._crawl_url_with_crawl4ai("https://vinfastauto.com/vn_vi")

    assert _FakeAsyncWebCrawler.seen_configs
    config = _FakeAsyncWebCrawler.seen_configs[0].kwargs
    assert config["excluded_tags"] == ["script", "style"]
    assert "excluded_selector" not in config
    assert "a[href]" in str(config["wait_for"])
