import pytest

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.chunking import (
    build_chunk_id,
    build_chunks,
    normalize_space,
    short_hash,
    slugify,
    split_markdown,
)


def test_split_markdown_is_deterministic_and_uses_overlap() -> None:
    text = "alpha beta gamma delta epsilon"

    chunks = split_markdown(text, chunk_size=16, chunk_overlap=5)

    assert chunks == ["alpha beta", "beta gamma", "gamma delta", "delta epsilon"]


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
    assert chunks[0].metadata["content_hash"] == short_hash("Overview content")
    assert chunks[0].metadata["fetched_at"] == "2026-06-01T00:00:00+00:00"


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
