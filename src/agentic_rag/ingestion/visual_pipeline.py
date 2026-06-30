"""Visual ingestion pipeline integrating chunking and embedding."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_rag.ingestion.chunking.visual import VisualChunk, VisualTileChunker


try:
    from pixelrag_render.render import render_file, render_pdf, render_url
except ImportError:
    def render_url(url: str, output_dir: Path, **kwargs: Any) -> list[Path]:
        """Render a URL to full-page screenshot tiles. (Stub for PixelRAG backend)"""
        raise NotImplementedError(
            "URL rendering requires the PixelRAG backend (pixelshot). "
            "Install missing dependencies to enable."
        )

    def render_pdf(path: str | Path, output_dir: Path, **kwargs: Any) -> list[Path]:
        """Render PDF pages to screenshot tiles. (Stub for PixelRAG backend)"""
        raise NotImplementedError(
            "PDF rendering requires the PixelRAG backend (poppler/pdf2image). "
            "Install missing dependencies to enable."
        )

    def render_file(path: str | Path, output_dir: Path, **kwargs: Any) -> list[Path]:
        """Render a local HTML/Markdown file to tiles. (Stub for PixelRAG backend)"""
        raise NotImplementedError(
            "File rendering requires the PixelRAG backend (pixelshot). "
            "Install missing dependencies to enable."
        )


def extract_text_from_visual_chunks(visual_chunks: list[VisualChunk]) -> str:
    """Pass visual chunks to the VLM to extract text and structured tables."""
    from agentic_rag.model_runtime.errors import ModelRuntimeConfigurationError
    from agentic_rag.model_runtime.factory import get_llm_client
    from agentic_rag.core.contracts import LLMCompletionInput
    from agentic_rag.runtime_env import load_local_env

    try:
        load_local_env()
        vlm_client = get_llm_client("ingestion")
    except ModelRuntimeConfigurationError as exc:
        import logging
        logging.warning(f"Vision model not configured. Falling back to empty text. {exc}")
        return ""

    extracted_texts = []
    
    # We pass all image tile paths to the VLM at once for it to summarize the page
    image_paths = [str(chunk.source_path) for chunk in visual_chunks if chunk.source_path]

    if not image_paths:
        return ""

    try:
        completion = vlm_client.complete(
            LLMCompletionInput(
                system_message="You are an expert Vision-Language Model data extractor. Your job is to read screenshots of a webpage and transcribe all visible text, tables, forms, and product configurations into highly accurate, structured Markdown. Ensure prices and color names are perfectly mapped.",
                prompt="Please extract all structured text and tables from these webpage screenshots.",
                images=image_paths,
                temperature=0.1
            )
        )
        if completion.text.strip():
            extracted_texts.append(completion.text.strip())
    except Exception as e:
        import logging
        logging.warning(f"VLM visual extraction failed: {e}")

    return "\n\n".join(extracted_texts)


def visual_ingest(source: str | Path, output_dir: Path, **kwargs: Any) -> str:
    """Render a document to screenshot tiles and transcribe them to Markdown using VLM."""
    output_dir = Path(output_dir)
    tiles_dir = output_dir / "tiles"
    
    # Stage 1: Render source to tiled JPEG images
    if isinstance(source, str) and (source.startswith("http://") or source.startswith("https://")):
        tiles = render_url(source, tiles_dir, backend="cdp", tile_height=2048, viewport_width=1200)
    elif str(source).lower().endswith(".pdf"):
        tiles = render_pdf(source, tiles_dir, dpi=150)
    else:
        tiles = render_file(source, tiles_dir)

    # Stage 2: Chunk tiles into model-sized strips
    chunker = VisualTileChunker()
    all_chunks: list[VisualChunk] = []
    for tile_dir in tiles:
        tile_path = tile_dir / "tile.png"
        if tile_path.exists():
            all_chunks.extend(chunker.chunk(tile_path))

    # Stage 3: Extract structured text using VLM
    extracted_markdown = extract_text_from_visual_chunks(all_chunks)

    return extracted_markdown
