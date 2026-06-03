import pytest

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.chunking import ChunkingInput
from agentic_rag.ingestion.url.chunking import (
    TiktokenChunkingStrategy,
    build_chunk_id,
    build_chunks,
    normalize_space,
    short_hash,
    slugify,
    split_markdown,
)


class RecordingStrategy:
    provider = "test-provider"
    model = "test-model"

    def __init__(self) -> None:
        self.seen_input: ChunkingInput | None = None

    def split(self, chunking_input: ChunkingInput) -> list[str]:
        self.seen_input = chunking_input
        return ["recorded chunk"]


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
    assert chunks[0].metadata["chunk_size"] == 1200
    assert chunks[0].metadata["chunk_overlap"] == 150
    assert chunks[0].metadata["chunking_input_type"] == "parsed_section"
    assert chunks[0].metadata["chunking_library"] == "agentic_rag.ingestion.chunking"
    assert chunks[0].metadata["chunking_method"] == "deterministic-character-overlap"
    assert chunks[0].metadata["chunking_provider"] is None
    assert chunks[0].metadata["chunking_model"] is None


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


def test_build_chunks_can_use_tiktoken_strategy() -> None:
    strategy = TiktokenChunkingStrategy(max_tokens=4, overlap_tokens=1)

    chunks = build_chunks(
        text="alpha beta gamma delta epsilon zeta",
        source="https://example.edu/token",
        source_type="url",
        section="Overview",
        url="https://example.edu/token",
        title="Token Page",
        fetched_at="2026-06-01T00:00:00+00:00",
        chunking_strategy=strategy,
    )

    assert len(chunks) > 1
    assert chunks[0].metadata["chunking_method"] == "deterministic-token-overlap"
    assert chunks[0].metadata["chunking_provider"] == "tiktoken"
    assert chunks[0].metadata["chunking_model"] == "cl100k_base"


def test_build_chunks_passes_shared_chunking_input_to_injected_strategy() -> None:
    strategy = RecordingStrategy()

    chunks = build_chunks(
        text="Overview content",
        source="https://example.edu/shared",
        source_type="url",
        section="Overview",
        url="https://example.edu/shared",
        title="Shared",
        fetched_at="2026-06-01T00:00:00+00:00",
        chunking_strategy=strategy,
    )

    assert strategy.seen_input == ChunkingInput(
        markdown="Overview content",
        source_type="url",
        metadata={
            "section": "Overview",
            "source": "https://example.edu/shared",
            "title": "Shared",
            "url": "https://example.edu/shared",
        },
    )
    assert chunks[0].text == "recorded chunk"
    assert chunks[0].metadata["chunking_method"] == "llm-assisted"


def test_chunking_helpers_normalize_ids_and_text() -> None:
    assert normalize_space(" A\n\nB\tC ") == "A B C"
    assert slugify("Section: URL/Text Ingestion") == "section-url-text-ingestion"
    assert build_chunk_id("url", "https://example.edu", "Main", 2).endswith("_main_c002")
