"""Shared chunking boundary for ingestion modules."""

# TODO [PixelRAG Integration — VisualTileChunker]:
# The current chunking module only handles text (markdown → text chunks).
# A future VisualTileChunker would split rendered page screenshots into
# model-sized image tiles, following PixelRAG's chunk_article algorithm.
#
# Pseudocode:
#
#   CLASS VisualTileChunker:
#       CHUNK_HEIGHT = 1024        # max height per image chunk (pixels)
#       MIN_CHUNK_HEIGHT = 28      # one Qwen3-VL patch — discard if smaller
#       VIEWPORT_WIDTH = 875       # model's native input width
#
#       FUNCTION chunk(tile_path: Path) -> list[VisualChunk]:
#           """Split a single tile image into a grid of model-sized chunks."""
#           img = Image.open(tile_path)
#           w, h = img.size
#           chunks = []
#           chunk_idx = 0
#
#           # Fast path: tile already fits in one chunk
#           IF w <= VIEWPORT_WIDTH AND h <= CHUNK_HEIGHT:
#               RETURN [VisualChunk(image=img, index=0, x=0, y=0, w=w, h=h)]
#
#           # 2D grid: CHUNK_HEIGHT rows × VIEWPORT_WIDTH columns
#           y = 0
#           WHILE y < h:
#               ch = min(CHUNK_HEIGHT, h - y)
#               IF ch < MIN_CHUNK_HEIGHT:
#                   BREAK  # discard tiny tail
#               x = 0
#               WHILE x < w:
#                   cw = min(VIEWPORT_WIDTH, w - x)
#                   IF cw < MIN_CHUNK_HEIGHT:
#                       BREAK  # discard tiny right-edge sliver
#                   cropped = img.crop((x, y, x + cw, y + ch))
#                   chunks.append(VisualChunk(
#                       image=cropped, index=chunk_idx,
#                       x_offset=x, y_offset=y, width=cw, height=ch
#                   ))
#                   chunk_idx += 1
#                   x += cw
#               y += ch
#
#           RETURN chunks
#
# Reference: guide_RAG/GUIDELINE.md §4, PixelRAG/embed/src/pixelrag_embed/chunk.py


from agentic_rag.ingestion.chunking.chunkers import (
    Chunker,
    DeterministicMarkdownChunker,
    TextChunkingStrategy,
)
from agentic_rag.ingestion.chunking.models import (
    ChunkCandidate,
    ChunkingInput,
    MarkdownChunk,
    MarkdownSection,
    StateScope,
)
from agentic_rag.ingestion.chunking.scopes import (
    build_scope_path,
    chunk_state_scopes,
    compatibility_row,
    promote_common_facts,
)
from agentic_rag.ingestion.chunking.splitters import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_PARAGRAPH_MAX_TOKENS,
    DEFAULT_PARAGRAPH_OVERLAP,
    build_chunk_id,
    chunk_markdown,
    chunk_markdown_by_sections,
    chunking_text,
    detect_lang,
    normalize_space,
    paragraph_chunk,
    short_hash,
    slugify,
    split_markdown,
    split_markdown_into_sections,
    split_markdown_paragraphs,
    split_sentences,
    split_text_with_strategy,
)
from agentic_rag.ingestion.chunking.visual import (
    VisualChunk,
    VisualTileChunker,
)

__all__ = [
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_PARAGRAPH_MAX_TOKENS",
    "DEFAULT_PARAGRAPH_OVERLAP",
    "ChunkCandidate",
    "Chunker",
    "ChunkingInput",
    "DeterministicMarkdownChunker",
    "MarkdownChunk",
    "MarkdownSection",
    "StateScope",
    "TextChunkingStrategy",
    "VisualChunk",
    "VisualTileChunker",
    "build_chunk_id",
    "build_scope_path",
    "chunk_markdown",
    "chunk_markdown_by_sections",
    "chunk_state_scopes",
    "chunking_text",
    "compatibility_row",
    "detect_lang",
    "normalize_space",
    "paragraph_chunk",
    "promote_common_facts",
    "short_hash",
    "slugify",
    "split_markdown",
    "split_markdown_into_sections",
    "split_markdown_paragraphs",
    "split_sentences",
    "split_text_with_strategy",
]
