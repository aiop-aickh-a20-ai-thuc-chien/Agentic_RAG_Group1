import pytest

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.chunking import (
    build_chunk_id,
    build_chunks,
    chunk_evidence_diagnostics,
    chunk_structural_clarity,
    chunk_text_quality,
    detect_lang,
    is_usable_chunk_text,
    normalize_space,
    paragraph_chunk,
    short_hash,
    slugify,
    split_markdown,
    split_markdown_paragraphs,
    split_sentences,
)


def test_split_markdown_is_deterministic_and_uses_overlap() -> None:
    text = "alpha beta gamma delta epsilon"

    chunks = split_markdown(text, chunk_size=16, chunk_overlap=5)

    assert chunks == ["alpha beta", "beta gamma", "gamma delta", "delta epsilon"]


def test_split_markdown_always_advances_when_split_is_near_start() -> None:
    text = "a " + ("b" * 40)

    chunks = split_markdown(text, chunk_size=10, chunk_overlap=8)

    assert chunks[0] == "a"
    assert chunks[-1]
    assert all(chunks)
    assert len(chunks) < len(text)


def test_split_markdown_paragraphs_uses_markdown_boundaries_and_overlap() -> None:
    text = "\n\n".join(
        [
            "Alpha one two three.",
            "Beta one two three.",
            "Gamma one two three.",
        ]
    )

    chunks = split_markdown_paragraphs(text, max_tokens=7, overlap_paragraphs=1)

    assert chunks == [
        "Alpha one two three.",
        "Alpha one two three.\n\nBeta one two three.",
        "Beta one two three.\n\nGamma one two three.",
    ]


def test_paragraph_chunk_returns_token_counts() -> None:
    chunks = paragraph_chunk(
        "First paragraph.\n\nSecond paragraph.",
        max_tokens=512,
        overlap_paragraphs=1,
    )

    assert chunks
    assert chunks[0]["text"] == "First paragraph.\n\nSecond paragraph."
    assert isinstance(chunks[0]["token_count"], int)
    assert chunks[0]["token_count"] > 0


def test_split_sentences_detects_english_and_vietnamese() -> None:
    english_sentences = split_sentences("Open the page. Extract clean Markdown.")
    vietnamese_sentences = split_sentences("Mở trang URL. Trích xuất Markdown sạch.")

    assert detect_lang("Open the page.") == "en"
    assert detect_lang("Trích xuất nội dung tiếng Việt.") == "vi"
    assert english_sentences == ["Open the page.", "Extract clean Markdown."]
    assert vietnamese_sentences == ["Mở trang URL.", "Trích xuất Markdown sạch."]


def test_paragraph_chunk_splits_oversized_paragraph_on_sentence_boundaries() -> None:
    chunks = paragraph_chunk(
        "Alpha beta gamma. Delta epsilon zeta. Eta theta iota.",
        max_tokens=5,
        overlap_paragraphs=0,
    )

    chunk_texts = [str(chunk["text"]) for chunk in chunks]

    assert len(chunk_texts) == 3
    assert chunk_texts == [
        "Alpha beta gamma.",
        "Delta epsilon zeta.",
        "Eta theta iota.",
    ]


def test_build_chunks_returns_contract_objects_with_metadata() -> None:
    chunks = build_chunks(
        text="Overview content",
        source="https://example.edu",
        source_type="url",
        section="Overview",
        url="https://example.edu",
        title="Example",
        fetched_at="2026-06-01T00:00:00+00:00",
    )

    assert len(chunks) == 1
    assert isinstance(chunks[0], Chunk)
    assert chunks[0].chunk_id == build_chunk_id("url", "https://example.edu", "Overview", 1)
    assert chunks[0].metadata["chunk_id"] == chunks[0].chunk_id
    assert chunks[0].metadata["content_hash"] == short_hash("Overview content")
    assert chunks[0].metadata["fetched_at"] == "2026-06-01T00:00:00+00:00"
    assert chunks[0].metadata["is_usable_for_retrieval"] is False
    assert chunks[0].metadata["chunk_quality"] == chunk_text_quality("Overview content")
    assert chunks[0].metadata["structural_clarity"] == chunk_structural_clarity("Overview content")
    assert chunks[0].metadata["has_structural_confusion"] is False
    assert chunks[0].metadata["needs_table_reconstruction"] is False
    assert chunks[0].metadata["evidence_diagnostics"]["has_duplicate_evidence"] is False
    assert chunks[0].metadata["has_possible_conflict"] is False


def test_chunk_quality_marks_useful_url_evidence() -> None:
    useful_text = (
        "Dòng xe E-SUV có 6-7 chỗ ngồi, quãng đường lên tới 626 km và giá bán từ 1.229.180.000 VNĐ."
    )

    assert is_usable_chunk_text("Ưu đãi chỉ tới 31/12!") is False
    assert is_usable_chunk_text(useful_text) is True


def test_chunk_evidence_diagnostics_flags_duplicates_and_conflicts() -> None:
    text = "\n".join(
        [
            "VF 9 Eco: giÃ¡ bÃ¡n 1.229.180.000 VNÄ",
            "VF 9 Eco: giÃ¡ bÃ¡n 1.499.000.000 VNÄ",
            "VinFast electric vehicle battery warranty policy lasts 10 years",
            "VinFast electric vehicle battery warranty policy lasts 10 years",
        ]
    )

    diagnostics = chunk_evidence_diagnostics(text)

    assert diagnostics["has_duplicate_evidence"] is True
    assert diagnostics["has_possible_conflict"] is True
    assert diagnostics["numeric_value_count"] >= 2
    assert diagnostics["possible_conflict_examples"][0]["label"] == "vf 9 eco"


def test_build_chunks_marks_flattened_table_as_structural_confusion() -> None:
    text = (
        "D-SUV 5 seats 480 km 819.180.000 VND 999.000.000 VND "
        "MPV 7 seats 450 km 704.340.000 VND 819.000.000 VND "
        "A-SUV 326 km 411.940.000 VND 479.000.000 VND "
        "B-SUV 318 km 644.140.000 VND 749.000.000 VND "
        "C-SUV 496 km 678.540.000 VND 789.000.000 VND "
        "E-SUV 626 km 1.229.180.000 VND 1.499.000.000 VND "
        "MiniCar 170 km 231.340.000 VND 269.000.000 VND "
        "Scooter 70 km/h 156 km 39.900.000 VND 3000 W"
    )

    chunks = build_chunks(
        text=text,
        source="https://example.edu",
        source_type="url",
        section="Products",
        url="https://example.edu",
        title="Products",
        fetched_at="2026-06-01T00:00:00+00:00",
    )

    assert chunks[0].metadata["is_usable_for_retrieval"] is False
    assert chunks[0].metadata["has_structural_confusion"] is True
    assert chunks[0].metadata["needs_table_reconstruction"] is True


def test_build_chunks_validates_chunk_settings() -> None:
    with pytest.raises(ValueError, match="chunk_size"):
        build_chunks(
            text="bad",
            source="source",
            source_type="text",
            section="main",
            url=None,
            title=None,
            fetched_at="now",
            chunk_size=0,
        )

    with pytest.raises(ValueError, match="chunk_overlap"):
        build_chunks(
            text="bad",
            source="source",
            source_type="text",
            section="main",
            url=None,
            title=None,
            fetched_at="now",
            chunk_size=10,
            chunk_overlap=10,
        )


def test_chunking_helpers_normalize_ids_and_text() -> None:
    assert normalize_space(" A\n\nB\tC ") == "A B C"
    assert slugify("Section: URL/Text Ingestion") == "section-url-text-ingestion"
    assert build_chunk_id("url", "https://example.edu", "Main", 2).endswith("_main_c002")
