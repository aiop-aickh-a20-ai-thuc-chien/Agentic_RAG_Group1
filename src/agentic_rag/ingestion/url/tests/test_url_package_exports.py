import agentic_rag.ingestion.url as url_package
from agentic_rag.ingestion.url.crawler import Crawl4AIPage, crawl_url_with_crawl4ai
from agentic_rag.ingestion.url.loader import (
    LoadedUrlDocument,
    load_html_chunks,
    load_html_with_artifacts,
    load_text_chunks,
    load_url_chunks,
    load_url_with_artifacts,
)
from agentic_rag.ingestion.url.probe import (
    should_probe_interactive_state,
    vinfast_configurator_state_to_markdown,
)


def test_url_package_re_exports_public_ingestion_helpers() -> None:
    assert url_package.__all__ == [
        "Crawl4AIPage",
        "LoadedUrlDocument",
        "crawl_url_with_crawl4ai",
        "load_html_chunks",
        "load_html_with_artifacts",
        "load_text_chunks",
        "load_url_chunks",
        "load_url_with_artifacts",
        "should_probe_interactive_state",
        "vinfast_configurator_state_to_markdown",
    ]
    assert url_package.Crawl4AIPage is Crawl4AIPage
    assert url_package.LoadedUrlDocument is LoadedUrlDocument
    assert url_package.crawl_url_with_crawl4ai is crawl_url_with_crawl4ai
    assert url_package.load_html_chunks is load_html_chunks
    assert url_package.load_html_with_artifacts is load_html_with_artifacts
    assert url_package.load_text_chunks is load_text_chunks
    assert url_package.load_url_chunks is load_url_chunks
    assert url_package.load_url_with_artifacts is load_url_with_artifacts
    assert url_package.should_probe_interactive_state is should_probe_interactive_state
    assert (
        url_package.vinfast_configurator_state_to_markdown is vinfast_configurator_state_to_markdown
    )
