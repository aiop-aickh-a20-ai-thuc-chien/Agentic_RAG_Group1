"""Document ingestion module boundaries."""

# TODO [PixelRAG Integration — Visual Ingestion Pipeline]:
# The current ingestion pipeline is text-only: HTML/PDF → parse → markdown → text chunks.
# PixelRAG introduces a visual alternative: render → screenshot tiles → image chunks → VLM embed.
#
# Pseudocode for a future `visual_ingest(source)` entry point:
#
#   FUNCTION visual_ingest(source: str | Path, output_dir: Path, config: VisualConfig):
#       """Render a document to screenshot tiles and produce visual chunks."""
#
#       # Stage 1: Render source to tiled JPEG images
#       IF source is URL:
#           tiles = render_url(source, output_dir / "tiles",
#                              backend="cdp", tile_height=8192, viewport_width=875)
#       ELIF source is PDF:
#           tiles = render_pdf(source, output_dir / "tiles", dpi=200)
#       ELIF source is HTML file:
#           tiles = render_file(source, output_dir / "tiles")
#
#       # Stage 2: Chunk tiles into model-sized strips (1024px height)
#       FOR EACH tile_dir IN tiles:
#           chunk_article(tile_dir)  # produces chunks.json + chunk_XXXX_YY.png
#
#       # Stage 3: Embed image chunks with vision-language model
#       items = scan_chunks(output_dir / "tiles")
#       embeddings = embed_items(items,
#                                model="Qwen/Qwen3-VL-Embedding-2B",
#                                device="auto")  # cuda > mps > cpu
#       save_embeddings(output_dir / "embeddings", embeddings, items)
#
#       # Stage 4: Build FAISS index for visual retrieval
#       build_faiss_index(output_dir / "embeddings", output_dir / "index",
#                         nlist=min(4096, len(embeddings) // 40))
#
#       RETURN VisualIndex(path=output_dir / "index")
#
# Reference: guide_RAG/GUIDELINE.md §4, PixelRAG/index/src/pixelrag_index/pipelines.py

from agentic_rag.ingestion.visual_pipeline import visual_ingest

__all__ = ["visual_ingest"]
