from agentic_rag.ingestion.url.chunking import (
    chunk_markdown_by_sections,
    split_markdown_into_sections,
)


def test_empty_markdown_returns_no_sections_or_chunks() -> None:
    assert split_markdown_into_sections(" \n\n\t") == []
    assert chunk_markdown_by_sections(" \n\n\t") == []


def test_markdown_headings_preserve_parent_child_path() -> None:
    sections = split_markdown_into_sections(
        "# Product Page\nOverview text.\n\n## Specs\nBattery and warranty details."
    )

    assert [section.title for section in sections] == ["Product Page", "Specs"]
    assert [section.level for section in sections] == [1, 2]
    assert sections[0].path == ("Product Page",)
    assert sections[1].path == ("Product Page", "Specs")
    assert sections[0].text == "Overview text."
    assert sections[1].text == "Battery and warranty details."


def test_seven_hashes_are_not_treated_as_markdown_heading() -> None:
    sections = split_markdown_into_sections("####### Not a heading\nText below.")

    assert sections[0].title is None
    assert sections[0].level == 0
    assert sections[0].path == ()
    assert sections[0].text == "####### Not a heading\nText below."


def test_chunk_markdown_by_sections_prefers_paragraph_boundaries() -> None:
    chunks = chunk_markdown_by_sections(
        "# Section\nDoan mot ngan.\n\nDoan hai ngan.",
        max_chars=100,
        overlap_chars=10,
    )

    assert [chunk.section for chunk in chunks] == ["Section"]
    assert chunks[0].section_level == 1
    assert chunks[0].section_path == ("Section",)
    assert chunks[0].text == "# Section\n\nDoan mot ngan.\n\nDoan hai ngan."
    assert chunks[0].chunk_token_count is not None
    assert chunks[0].chunk_token_count > 0
    assert chunks[0].semantic_unit == "markdown_section_paragraph_sentence"


def test_oversized_section_splits_deterministically_by_token_budget() -> None:
    markdown = "# Long\nAlpha beta gamma.\n\nDelta epsilon zeta.\n\nEta theta iota."

    chunks = chunk_markdown_by_sections(markdown, max_tokens=5, overlap_paragraphs=0)

    assert len(chunks) > 1
    assert all(chunk.section == "Long" for chunk in chunks)
    assert all(chunk.section_path == ("Long",) for chunk in chunks)
    assert all(chunk.text for chunk in chunks)
    assert chunks == chunk_markdown_by_sections(markdown, max_tokens=5, overlap_paragraphs=0)
