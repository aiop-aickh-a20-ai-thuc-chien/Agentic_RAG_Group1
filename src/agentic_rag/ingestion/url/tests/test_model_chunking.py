from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from agentic_rag.ingestion.url import load_html_chunks
from agentic_rag.ingestion.url.model_chunking import (
    LLMChunkingConfig,
    LLMChunkingProvider,
    ModelChunkingStrategy,
    RAGFlowChunkingStrategy,
    TextGenerationClient,
    compare_model_chunking,
    parse_model_chunks,
)


@dataclass(frozen=True)
class FakeGenerationClient:
    provider: LLMChunkingProvider
    model: str
    chunks: tuple[str, ...]

    def generate_text(self, prompt: str) -> str:
        assert "Return only valid JSON" in prompt
        return json.dumps(list(self.chunks))


@dataclass
class FakeRAGFlowChunkingClient:
    chunks: tuple[str, ...]
    uploaded_content: bytes | None = None
    parsed_document_ids: list[str] | None = None

    def upload_document(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        dataset_id: str | None = None,
    ) -> dict[str, object]:
        assert filename == "sample-url.md"
        assert content_type == "text/markdown; charset=utf-8"
        assert dataset_id == "dataset-1"
        self.uploaded_content = content
        return {"id": "doc-1"}

    def parse_documents(
        self,
        *,
        document_ids: list[str],
        dataset_id: str | None = None,
    ) -> dict[str, object]:
        assert dataset_id == "dataset-1"
        self.parsed_document_ids = document_ids
        return {"code": 0}

    def list_chunks(
        self,
        *,
        document_id: str,
        dataset_id: str | None = None,
        keywords: str | None = None,
        page: int = 1,
        page_size: int | None = None,
        chunk_id: str | None = None,
    ) -> dict[str, object]:
        assert document_id == "doc-1"
        assert dataset_id == "dataset-1"
        assert page == 1
        assert page_size == 10
        del keywords, chunk_id
        return {
            "data": {
                "chunks": [{"content": chunk} for chunk in self.chunks],
            }
        }


def test_parse_model_chunks_requires_json_array_of_strings() -> None:
    assert parse_model_chunks('[" One  chunk. ", "Second\\nchunk."]') == [
        "One chunk.",
        "Second chunk.",
    ]
    assert parse_model_chunks('```json\n["Fenced chunk."]\n```') == ["Fenced chunk."]

    with pytest.raises(ValueError, match="valid JSON"):
        parse_model_chunks("not json")

    with pytest.raises(ValueError, match="array of strings"):
        parse_model_chunks('{"chunk": "bad"}')


def test_compare_model_chunking_compares_openai_and_gemini_model_versions() -> None:
    configs = [
        LLMChunkingConfig(provider="openai", model="gpt-4.1-mini"),
        LLMChunkingConfig(provider="openai", model="gpt-4o-mini"),
        LLMChunkingConfig(provider="gemini", model="gemini-2.5-flash"),
        LLMChunkingConfig(provider="gemini", model="gemini-2.5-pro"),
    ]

    def client_factory(config: LLMChunkingConfig) -> TextGenerationClient:
        return FakeGenerationClient(
            provider=config.provider,
            model=config.model,
            chunks=(f"{config.provider}:{config.model}:chunk-1", "chunk-2"),
        )

    reports = compare_model_chunking(
        "Heading. Body text for model comparison.",
        configs,
        client_factory=client_factory,
    )

    assert [(report.provider, report.model) for report in reports] == [
        ("openai", "gpt-4.1-mini"),
        ("openai", "gpt-4o-mini"),
        ("gemini", "gemini-2.5-flash"),
        ("gemini", "gemini-2.5-pro"),
    ]
    assert all(report.chunk_count == 2 for report in reports)
    assert reports[0].chunks[0] == "openai:gpt-4.1-mini:chunk-1"
    assert reports[3].chunks[0] == "gemini:gemini-2.5-pro:chunk-1"


def test_load_html_chunks_can_use_optional_model_chunking_strategy() -> None:
    strategy = ModelChunkingStrategy(
        FakeGenerationClient(
            provider="openai",
            model="gpt-4.1-mini",
            chunks=("Overview model chunk A.", "Overview model chunk B."),
        )
    )

    chunks = load_html_chunks(
        "<html><body><h1>Overview</h1><p>Long section for model chunking.</p></body></html>",
        source="https://example.edu/model",
        source_url="https://example.edu/model",
        chunking_strategy=strategy,
    )

    assert [chunk.text for chunk in chunks] == [
        "Overview model chunk A.",
        "Overview model chunk B.",
    ]
    assert chunks[0].metadata["chunking_method"] == "llm-assisted"
    assert chunks[0].metadata["chunking_provider"] == "openai"
    assert chunks[0].metadata["chunking_model"] == "gpt-4.1-mini"


def test_ragflow_chunking_strategy_delegates_markdown_chunking_to_ragflow() -> None:
    client = FakeRAGFlowChunkingClient(
        chunks=("RAGFlow chunk A.", "RAGFlow chunk B."),
    )
    strategy = RAGFlowChunkingStrategy(
        client,
        dataset_id="dataset-1",
        filename="sample-url.md",
        model="gpt-4o-mini",
        page_size=10,
        poll_interval_seconds=0,
    )

    assert strategy.split("# Overview\n\nBody text.") == [
        "RAGFlow chunk A.",
        "RAGFlow chunk B.",
    ]
    assert client.uploaded_content == b"# Overview\n\nBody text."
    assert client.parsed_document_ids == ["doc-1"]


def test_load_html_chunks_can_use_optional_ragflow_chunking_strategy() -> None:
    strategy = RAGFlowChunkingStrategy(
        FakeRAGFlowChunkingClient(chunks=("RAGFlow overview chunk.",)),
        dataset_id="dataset-1",
        filename="sample-url.md",
        model="gpt-4o-mini",
        page_size=10,
        poll_interval_seconds=0,
    )

    chunks = load_html_chunks(
        "<html><body><h1>Overview</h1><p>Long section for RAGFlow chunking.</p></body></html>",
        source="https://example.edu/ragflow",
        source_url="https://example.edu/ragflow",
        chunking_strategy=strategy,
    )

    assert [chunk.text for chunk in chunks] == ["RAGFlow overview chunk."]
    assert chunks[0].metadata["chunking_method"] == "ragflow-assisted"
    assert chunks[0].metadata["chunking_provider"] == "ragflow"
    assert chunks[0].metadata["chunking_model"] == "gpt-4o-mini"
