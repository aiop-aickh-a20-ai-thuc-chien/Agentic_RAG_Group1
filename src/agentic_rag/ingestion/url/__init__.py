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
    "GeminiChunkingClient",
    "LLMChunkingConfig",
    "ModelChunkingReport",
    "ModelChunkingStrategy",
    "OpenAIChunkingClient",
    "compare_model_chunking",
    "load_html_chunks",
    "load_text_chunks",
    "load_url_chunks",
]
