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
        "# Section\nDoan mot ngan du dai de giu lai trong pipeline.\n\n"
        "Doan hai ngan nhung van vuot nguong toi thieu.",
        max_chars=100,
        overlap_chars=10,
    )

    assert [chunk.section for chunk in chunks] == ["Section"]
    assert chunks[0].section_level == 1
    assert chunks[0].section_path == ("Section",)
    assert chunks[0].text == (
        "# Section\n\nDoan mot ngan du dai de giu lai trong pipeline.\n\n"
        "Doan hai ngan nhung van vuot nguong toi thieu."
    )
    assert chunks[0].chunk_token_count is not None
    assert chunks[0].chunk_token_count > 0
    assert chunks[0].semantic_unit == "hierarchical_markdown_subsection"
    assert chunks[0].section_path == ("Section",)
    assert chunks[0].metadata["chunk_part_index"] == 1
    assert chunks[0].metadata["chunk_part_total"] == 1


def test_oversized_section_splits_deterministically_by_token_budget() -> None:
    markdown = "# Long\nAlpha beta gamma.\n\nDelta epsilon zeta.\n\nEta theta iota."

    chunks = chunk_markdown_by_sections(markdown, max_tokens=5, overlap_paragraphs=0)

    assert len(chunks) > 1
    assert all(chunk.section == "Long" for chunk in chunks)
    assert all(chunk.section_path == ("Long",) for chunk in chunks)
    assert all(chunk.text for chunk in chunks)
    assert chunks == chunk_markdown_by_sections(markdown, max_tokens=5, overlap_paragraphs=0)


def test_chunk_markdown_by_sections_splits_numbered_subsections() -> None:
    chunks = chunk_markdown_by_sections(
        "# VF 8\n1. Battery warranty\n"
        "Warranty covers the battery pack for long ownership periods.\n\n"
        "2. Charging speed\nCharging information is available at showrooms with support.",
        max_chars=80,
    )

    assert [chunk.section for chunk in chunks] == ["1 Battery warranty", "2 Charging speed"]
    assert chunks[0].section_path == ("VF 8", "1 Battery warranty")
    assert chunks[1].section_path == ("VF 8", "2 Charging speed")
    # Title line must be present in chunk body (not just in the synthesized heading prefix)
    assert "1. Battery warranty" in chunks[0].text
    assert "2. Charging speed" in chunks[1].text
    assert "Warranty covers the battery pack for long ownership periods." in chunks[0].text


def test_chunk_input_range_maps_to_body_not_heading_prefix() -> None:
    # Each section body must be > DEFAULT_HIERARCHICAL_TARGET_MIN (512 chars) to avoid coalescing
    body_1 = "Xe điện VinFast với công nghệ tiên tiến mang lại trải nghiệm lái xe tuyệt vời. " * 8
    body_2 = "Pin 75 kWh sạc nhanh DC 150 kW phạm vi hoạt động 400 km mỗi lần sạc đầy. " * 8
    markdown = f"# VinFast VF 7\n\n{body_1}\n\n## Thông số kỹ thuật\n\n{body_2}"

    chunks = chunk_markdown_by_sections(markdown)

    assert len(chunks) >= 2
    for chunk in chunks:
        start, end = chunk.metadata["chunk_input_range"]
        body_from_range = markdown[start:end].strip()
        assert body_from_range, f"chunk_input_range [{start}:{end}] maps to empty string"
        assert 0 <= start < end <= len(markdown)
        # chunk.text = "<heading prefix>\n\n<body>" — body must match the range
        assert chunk.text.endswith(body_from_range), (
            f"chunk.text does not end with body from range:\n"
            f"  range body: {body_from_range!r}\n"
            f"  chunk.text: {chunk.text!r}"
        )
        # Heading prefix (## ...) must NOT be part of chunk_input_range
        assert not body_from_range.startswith("#"), (
            "chunk_input_range should point to body text, not heading markup"
        )
