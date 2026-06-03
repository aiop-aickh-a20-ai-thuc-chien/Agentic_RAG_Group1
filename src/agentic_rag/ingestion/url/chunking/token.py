"""Token-aware chunking strategy for URL ingestion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol, cast

from agentic_rag.ingestion.chunking import ChunkingInput, chunking_text
from agentic_rag.ingestion.url.chunking.core import normalize_space


class _TiktokenEncoding(Protocol):
    def encode(self, text: str) -> list[int]:
        """Encode text into token IDs."""

    def decode(self, tokens: list[int]) -> str:
        """Decode token IDs into text."""


@dataclass(frozen=True)
class TiktokenChunkingStrategy:
    """Split text into deterministic token windows using tiktoken."""

    encoding_name: str = "cl100k_base"
    max_tokens: int = 800
    overlap_tokens: int = 80

    @property
    def provider(self) -> str:
        return "tiktoken"

    @property
    def model(self) -> str:
        return self.encoding_name

    def split(self, chunking_input: str | ChunkingInput) -> list[str]:
        """Return normalized chunks bounded by token count."""

        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0.")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than max_tokens.")

        cleaned_text = normalize_space(chunking_text(chunking_input))
        if not cleaned_text:
            return []

        encoding = _get_encoding(self.encoding_name)
        token_ids = encoding.encode(cleaned_text)
        if len(token_ids) <= self.max_tokens:
            return [cleaned_text]

        chunks: list[str] = []
        start = 0
        while start < len(token_ids):
            end = min(start + self.max_tokens, len(token_ids))
            chunk = normalize_space(encoding.decode(token_ids[start:end]))
            if chunk:
                chunks.append(chunk)
            if end >= len(token_ids):
                break
            next_start = end - self.overlap_tokens
            start = end if next_start <= start else next_start
        return chunks


def _get_encoding(encoding_name: str) -> _TiktokenEncoding:
    tiktoken = cast(Any, import_module("tiktoken"))
    get_encoding = cast(Callable[[str], _TiktokenEncoding], tiktoken.get_encoding)
    return get_encoding(encoding_name)
