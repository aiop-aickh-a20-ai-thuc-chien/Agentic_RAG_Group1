"""Visual chunk metadata schemas and enrichment."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agentic_rag.core.contracts import Chunk

VISUAL_METADATA_FIELDS = {
    "extraction_method":  str,   # "visual_pixelrag" | "text_default"
    "tile_index":         int,   # which tile of the full-page screenshot
    "chunk_index":        int,   # which chunk within the tile (row-major)
    "x_offset":           int,   # horizontal offset in pixels from tile origin
    "y_offset":           int,   # vertical offset in pixels from tile origin
    "chunk_width":        int,   # width of this image chunk in pixels
    "chunk_height":       int,   # height of this image chunk in pixels
    "viewport_width":     int,   # browser viewport width used during render (875)
    "page_height":        int,   # total page height in pixels
    "image_path":         str,   # path to the chunk image file
    "tile_hash":          str,   # MD5 of source tile for change detection
}


def enrich_visual_metadata(chunk: Chunk, visual_info: dict[str, Any]) -> Chunk:
    """Attach visual rendering metadata to a chunk."""
    
    metadata = dict(chunk.metadata)
    metadata["extraction_method"] = "visual_pixelrag"
    metadata["tile_index"] = visual_info.get("tile_index", 0)
    metadata["chunk_index"] = visual_info.get("chunk_index", 0)
    metadata["x_offset"] = visual_info.get("x_offset", 0)
    metadata["y_offset"] = visual_info.get("y_offset", 0)
    metadata["chunk_width"] = visual_info.get("width", 875)
    metadata["chunk_height"] = visual_info.get("height", 1024)
    metadata["viewport_width"] = visual_info.get("viewport_width", 875)
    metadata["page_height"] = visual_info.get("page_height", 0)
    metadata["image_path"] = visual_info.get("image_path", "")
    metadata["tile_hash"] = visual_info.get("tile_hash", "")
    
    return chunk.model_copy(update={"metadata": metadata})
