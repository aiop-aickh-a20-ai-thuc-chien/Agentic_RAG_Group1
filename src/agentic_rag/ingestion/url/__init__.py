"""URL ingestion package."""

from agentic_rag.ingestion.url.loader import (
    load_html_chunks,
    load_text_chunks,
    load_url_chunks,
)
from agentic_rag.ingestion.url.model_chunking import (
    GeminiChunkingClient,
    LLMChunkingConfig,
    ModelChunkingReport,
    ModelChunkingStrategy,
    OpenAIChunkingClient,
    compare_model_chunking,
)

__all__ = [
    "load_url_chunks",
    "load_html_chunks",
    "load_text_chunks",
    "LLMChunkingConfig",
    "ModelChunkingReport",
    "ModelChunkingStrategy",
    "OpenAIChunkingClient",
    "GeminiChunkingClient",
    "compare_model_chunking",
]
