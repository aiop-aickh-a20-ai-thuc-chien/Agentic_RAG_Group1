from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from agentic_rag.ingestion.url import load_html_chunks
from agentic_rag.ingestion.url.model_chunking import (
    LLMChunkingConfig,
    LLMChunkingProvider,
    ModelChunkingStrategy,
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


def test_parse_model_chunks_requires_json_array_of_strings() -> None:
    assert parse_model_chunks('[" One  chunk. ", "Second\\nchunk."]') == [
        "One chunk.",
        "Second chunk.",
    ]

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
