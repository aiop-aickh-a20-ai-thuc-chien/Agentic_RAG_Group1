from agentic_rag.ingestion.url.extractor import normalize_extracted_markdown


def test_normalize_extracted_markdown_adds_space_after_link() -> None:
    markdown = "[World Wide Web](https://en.wikipedia.org/wiki/World_Wide_Web)using"

    assert normalize_extracted_markdown(markdown) == (
        "[World Wide Web](https://en.wikipedia.org/wiki/World_Wide_Web) using"
    )


def test_normalize_extracted_markdown_joins_inline_link_continuation() -> None:
    markdown = (
        "using the\n\n"
        "[Hypertext Transfer Protocol](https://en.wikipedia.org/wiki/"
        "Hypertext_Transfer_Protocol)or a web browser."
    )

    assert normalize_extracted_markdown(markdown) == (
        "using the [Hypertext Transfer Protocol](https://en.wikipedia.org/wiki/"
        "Hypertext_Transfer_Protocol) or a web browser."
    )


def test_normalize_extracted_markdown_preserves_heading_breaks() -> None:
    markdown = "# Heading\n\n[Link](https://example.edu)text"

    assert normalize_extracted_markdown(markdown) == (
        "# Heading\n\n[Link](https://example.edu) text"
    )


def test_normalize_extracted_markdown_handles_link_urls_with_parentheses() -> None:
    markdown = (
        "[honeypot](https://en.wikipedia.org/wiki/Honeypot_(computing))or "
        "[Python](https://en.wikipedia.org/wiki/Python_(programming_language))script"
    )

    assert normalize_extracted_markdown(markdown) == (
        "[honeypot](https://en.wikipedia.org/wiki/Honeypot_(computing)) or "
        "[Python](https://en.wikipedia.org/wiki/Python_(programming_language)) script"
    )
