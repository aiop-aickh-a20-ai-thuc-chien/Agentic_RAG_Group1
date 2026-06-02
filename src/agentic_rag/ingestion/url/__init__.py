"""URL ingestion package."""

from agentic_rag.ingestion.url.chunking import TiktokenChunkingStrategy
from agentic_rag.ingestion.url.loader import (
    LoadedUrlDocument,
    load_html_chunks,
    load_html_with_artifacts,
    load_text_chunks,
    load_url_chunks,
    load_url_with_artifacts,
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
    "LoadedUrlDocument",
    "ModelChunkingReport",
    "ModelChunkingStrategy",
    "OpenAIChunkingClient",
    "TiktokenChunkingStrategy",
    "compare_model_chunking",
    "load_html_chunks",
    "load_html_with_artifacts",
    "load_text_chunks",
    "load_url_chunks",
    "load_url_with_artifacts",
]
