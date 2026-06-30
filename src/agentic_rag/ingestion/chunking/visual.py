"""Visual chunking models and implementations for image-based RAG."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class VisualChunk(BaseModel):
    """A visual chunk representing a rectangular region of a rendered image."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    image: Any  # PIL.Image.Image
    index: int
    x_offset: int
    y_offset: int
    width: int
    height: int


class VisualTileChunker:
    """Chunker that splits rendered page screenshots into model-sized image tiles."""

    CHUNK_HEIGHT = 1024        # max height per image chunk (pixels)
    MIN_CHUNK_HEIGHT = 28      # one Qwen3-VL patch — discard if smaller
    VIEWPORT_WIDTH = 875       # model's native input width

    def chunk(self, tile_path: Path) -> list[VisualChunk]:
        """Split a single tile image into a grid of model-sized chunks."""
        try:
            from PIL import Image
        except ImportError:
            raise RuntimeError("VisualTileChunker requires 'Pillow' (PIL) to be installed.")

        try:
            img = Image.open(tile_path)
            # Ensure it's fully loaded and in a standard format if needed
            img.load()
        except Exception as exc:
            raise ValueError(f"Failed to load image tile: {tile_path}") from exc

        w, h = img.size
        chunks: list[VisualChunk] = []
        chunk_idx = 0

        # Fast path: tile already fits in one chunk
        if w <= self.VIEWPORT_WIDTH and h <= self.CHUNK_HEIGHT:
            return [VisualChunk(
                image=img, index=0, x_offset=0, y_offset=0, width=w, height=h
            )]

        # 2D grid: CHUNK_HEIGHT rows × VIEWPORT_WIDTH columns
        y = 0
        while y < h:
            ch = min(self.CHUNK_HEIGHT, h - y)
            if ch < self.MIN_CHUNK_HEIGHT:
                break  # discard tiny tail
            x = 0
            while x < w:
                cw = min(self.VIEWPORT_WIDTH, w - x)
                if cw < self.MIN_CHUNK_HEIGHT:
                    break  # discard tiny right-edge sliver
                cropped = img.crop((x, y, x + cw, y + ch))
                chunks.append(VisualChunk(
                    image=cropped,
                    index=chunk_idx,
                    x_offset=x,
                    y_offset=y,
                    width=cw,
                    height=ch,
                ))
                chunk_idx += 1
                x += cw
            y += ch

        return chunks
