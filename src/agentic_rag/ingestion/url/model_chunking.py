"""Optional OpenAI and Gemini assisted chunking for URL/HTML ingestion."""

from __future__ import annotations

import importlib
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from agentic_rag.ingestion.url.chunking import normalize_space

LLMChunkingProvider = Literal["openai", "gemini"]


class TextGenerationClient(Protocol):
    """Minimal text generation boundary for model-assisted chunking."""

    @property
    def provider(self) -> LLMChunkingProvider:
        """Model provider name."""

    @property
    def model(self) -> str:
        """Model version/name."""

    def generate_text(self, prompt: str) -> str:
        """Return model text for one prompt."""


@dataclass(frozen=True)
class LLMChunkingConfig:
    """One model configuration used for optional LLM-assisted chunking."""

    provider: LLMChunkingProvider
    model: str
    max_chunk_chars: int = 1_200
    overlap_hint_chars: int = 150


@dataclass(frozen=True)
class ModelChunkingReport:
    """Comparable output for one model-assisted chunking run."""

    provider: LLMChunkingProvider
    model: str
    chunk_count: int
    average_chunk_chars: float
    chunks: tuple[str, ...]


class ModelChunkingStrategy:
    """Chunk text by asking an injected OpenAI/Gemini-compatible client."""

    def __init__(
        self,
        client: TextGenerationClient,
        *,
        max_chunk_chars: int = 1_200,
        overlap_hint_chars: int = 150,
    ) -> None:
        self._client = client
        self._max_chunk_chars = max_chunk_chars
        self._overlap_hint_chars = overlap_hint_chars

    @property
    def provider(self) -> str:
        return self._client.provider

    @property
    def model(self) -> str:
        return self._client.model

    def split(self, text: str) -> list[str]:
        """Split text with the configured model and validate JSON output."""

        cleaned_text = normalize_space(text)
        if not cleaned_text:
            return []
        prompt = _chunking_prompt(
            cleaned_text,
            max_chunk_chars=self._max_chunk_chars,
            overlap_hint_chars=self._overlap_hint_chars,
        )
        return parse_model_chunks(self._client.generate_text(prompt))


class OpenAIChunkingClient:
    """OpenAI Responses API adapter for optional chunking."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: object | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client

    @property
    def provider(self) -> LLMChunkingProvider:
        return "openai"

    def generate_text(self, prompt: str) -> str:
        client = self._client or _openai_client(self._api_key)
        response = client.responses.create(  # type: ignore[attr-defined]
            model=self.model,
            input=prompt,
        )
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            return output_text
        raise RuntimeError("OpenAI response did not include output_text.")


class GeminiChunkingClient:
    """Google Gemini API adapter for optional chunking."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: object | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client

    @property
    def provider(self) -> LLMChunkingProvider:
        return "gemini"

    def generate_text(self, prompt: str) -> str:
        client = self._client or _gemini_client(self._api_key)
        response = client.models.generate_content(  # type: ignore[attr-defined]
            model=self.model,
            contents=prompt,
        )
        output_text = getattr(response, "text", None)
        if isinstance(output_text, str):
            return output_text
        raise RuntimeError("Gemini response did not include text.")


def compare_model_chunking(
    text: str,
    configs: Sequence[LLMChunkingConfig],
    *,
    client_factory: Callable[[LLMChunkingConfig], TextGenerationClient] | None = None,
) -> list[ModelChunkingReport]:
    """Run comparable model-assisted chunking for OpenAI/Gemini configs."""

    reports: list[ModelChunkingReport] = []
    for config in configs:
        client = client_factory(config) if client_factory else client_from_config(config)
        strategy = ModelChunkingStrategy(
            client,
            max_chunk_chars=config.max_chunk_chars,
            overlap_hint_chars=config.overlap_hint_chars,
        )
        chunks = tuple(strategy.split(text))
        reports.append(
            ModelChunkingReport(
                provider=config.provider,
                model=config.model,
                chunk_count=len(chunks),
                average_chunk_chars=_average_chunk_chars(chunks),
                chunks=chunks,
            )
        )
    return reports


def client_from_config(config: LLMChunkingConfig) -> TextGenerationClient:
    """Build a real API client from one chunking config."""

    if config.provider == "openai":
        return OpenAIChunkingClient(model=config.model)
    return GeminiChunkingClient(model=config.model)


def parse_model_chunks(value: str) -> list[str]:
    """Parse and validate a model-returned JSON string of chunk texts."""

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Model chunking output must be valid JSON.") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("Model chunking output must be a JSON array of strings.")
    chunks = [normalize_space(item) for item in parsed if normalize_space(item)]
    if not chunks:
        raise ValueError("Model chunking output must include at least one non-empty chunk.")
    return chunks


def _chunking_prompt(text: str, *, max_chunk_chars: int, overlap_hint_chars: int) -> str:
    return "\n".join(
        [
            "<task>",
            "Split URL/HTML-derived Markdown or text into retrieval chunks.",
            "</task>",
            "",
            "<rules>",
            f"- Target maximum chunk length: {max_chunk_chars} characters.",
            f"- Use about {overlap_hint_chars} characters of overlap when useful.",
            "- Keep headings with the content they describe.",
            "- Do not add facts that are not in the input.",
            "</rules>",
            "",
            "<input>",
            text,
            "</input>",
            "",
            "<output>",
            "Return only valid JSON: an array of strings.",
            "</output>",
        ]
    )


def _openai_client(api_key: str | None) -> object:
    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI-assisted chunking.")
    openai_module = importlib.import_module("openai")
    return openai_module.OpenAI(api_key=resolved_api_key)


def _gemini_client(api_key: str | None) -> object:
    resolved_api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not resolved_api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required for Gemini chunking.")
    try:
        genai_module = importlib.import_module("google.genai")
    except ImportError as exc:
        raise RuntimeError("Install google-genai to use Gemini-assisted chunking.") from exc
    return genai_module.Client(api_key=resolved_api_key)


def _average_chunk_chars(chunks: Sequence[str]) -> float:
    if not chunks:
        return 0.0
    return round(sum(len(chunk) for chunk in chunks) / len(chunks), 2)
