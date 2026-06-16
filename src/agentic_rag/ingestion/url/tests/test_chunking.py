import pytest

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.chunking import (
    build_chunk_id,
    build_chunks,
    detect_lang,
    normalize_for_content_hash,
    normalize_for_dedupe_hash,
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
        source_type="unknown",
        section="Overview",
        url="https://example.edu",
        title="Example",
        fetched_at="2026-06-01T00:00:00+00:00",
        chunk_id_prefix="url",
    )

    assert len(chunks) == 1
    assert isinstance(chunks[0], Chunk)
    assert chunks[0].chunk_id == build_chunk_id("url", "https://example.edu", "Overview", 1)
    assert chunks[0].metadata["chunk_id"] == chunks[0].chunk_id
    assert chunks[0].metadata["page_hash"] == short_hash(
        normalize_for_content_hash("Overview content")
    )
    assert chunks[0].metadata["content_hash"] == short_hash(
        normalize_for_content_hash("Overview content")
    )
    assert chunks[0].metadata["dedupe_hash"] == short_hash(
        normalize_for_dedupe_hash("Overview content")
    )
    assert chunks[0].metadata["normalized_text"] == "overview content"
    assert chunks[0].metadata["fetched_at"] == "2026-06-01T00:00:00+00:00"


def test_build_chunks_validates_chunk_settings() -> None:
    with pytest.raises(ValueError, match="chunk_size"):
        build_chunks(
            text="bad",
            source="source",
            source_type="internal",
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
            source_type="internal",
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
