import agentic_rag.ingestion.url as url_package
from agentic_rag.ingestion.url.chunking import TiktokenChunkingStrategy
from agentic_rag.ingestion.url.loader import load_html_chunks, load_text_chunks, load_url_chunks
from agentic_rag.ingestion.url.model_chunking import (
    GeminiChunkingClient,
    LLMChunkingConfig,
    ModelChunkingReport,
    ModelChunkingStrategy,
    OpenAIChunkingClient,
    RAGFlowChunkingStrategy,
    compare_model_chunking,
)


def test_url_package_re_exports_public_ingestion_helpers() -> None:
    assert url_package.__all__ == [
        "GeminiChunkingClient",
        "LLMChunkingConfig",
        "LoadedUrlDocument",
        "ModelChunkingReport",
        "ModelChunkingStrategy",
        "OpenAIChunkingClient",
        "RAGFlowChunkingStrategy",
        "TiktokenChunkingStrategy",
        "compare_model_chunking",
        "load_html_chunks",
        "load_html_with_artifacts",
        "load_text_chunks",
        "load_url_chunks",
        "load_url_with_artifacts",
    ]
    assert url_package.GeminiChunkingClient is GeminiChunkingClient
    assert url_package.LLMChunkingConfig is LLMChunkingConfig
    assert url_package.ModelChunkingReport is ModelChunkingReport
    assert url_package.ModelChunkingStrategy is ModelChunkingStrategy
    assert url_package.OpenAIChunkingClient is OpenAIChunkingClient
    assert url_package.RAGFlowChunkingStrategy is RAGFlowChunkingStrategy
    assert url_package.TiktokenChunkingStrategy is TiktokenChunkingStrategy
    assert url_package.compare_model_chunking is compare_model_chunking
    assert url_package.load_html_chunks is load_html_chunks
    assert url_package.load_text_chunks is load_text_chunks
    assert url_package.load_url_chunks is load_url_chunks
