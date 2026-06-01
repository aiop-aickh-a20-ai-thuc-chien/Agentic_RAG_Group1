"""URL ingestion package."""

from .loader import load_url_chunks
# Assuming chunking classes live in a chunking module:
from .chunking import (
    GeminiChunkingClient,
    LLMChunkingConfig,
    ModelChunkingReport,
    ModelChunkingStrategy,
    OpenAIChunkingClient,
    compare_model_chunking
)

__all__ = [
    "load_url_chunks",
    "GeminiChunkingClient",
    "LLMChunkingConfig",
    "ModelChunkingReport",
    "ModelChunkingStrategy",
    "OpenAIChunkingClient",
    "compare_model_chunking",
]
