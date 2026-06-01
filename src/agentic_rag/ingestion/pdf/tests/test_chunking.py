from agentic_rag.ingestion.pdf.chunking import chunk_markdown, split_markdown_into_sections


def test_empty_markdown_returns_no_sections_or_chunks() -> None:
    assert split_markdown_into_sections(" \n\n\t") == []
    assert chunk_markdown(" \n\n\t") == []


def test_markdown_headings_define_sections() -> None:
    sections = split_markdown_into_sections(
        "# Warranty\nPin duoc bao hanh 8 nam.\n\n## Dieu kien\nBao hanh ap dung cho xe hop le."
    )

    assert [section.title for section in sections] == ["Warranty", "Dieu kien"]
    assert sections[0].text == "Pin duoc bao hanh 8 nam."
    assert sections[1].text == "Bao hanh ap dung cho xe hop le."


def test_seven_hashes_are_not_treated_as_markdown_heading() -> None:
    sections = split_markdown_into_sections("####### Not a heading\nText below.")

    assert sections[0].title is None
    assert sections[0].text == "####### Not a heading\nText below."


def test_chunk_markdown_prefers_paragraph_boundaries() -> None:
    chunks = chunk_markdown(
        "# Section\nDoan mot ngan.\n\nDoan hai ngan.",
        max_chars=100,
        overlap_chars=10,
    )

    assert [chunk.section for chunk in chunks] == ["Section"]
    assert chunks[0].text == "Doan mot ngan.\n\nDoan hai ngan."


def test_oversized_section_splits_deterministically_with_overlap() -> None:
    markdown = "# Long\n" + ("abcdef " * 30)

    chunks = chunk_markdown(markdown, max_chars=60, overlap_chars=10)

    assert len(chunks) > 1
    assert all(chunk.section == "Long" for chunk in chunks)
    assert all(chunk.text for chunk in chunks)
    assert chunks == chunk_markdown(markdown, max_chars=60, overlap_chars=10)
