# src/agentic_rag/ingestion/url/__init__.py

from .chunking import (
    TextChunkingStrategy,
    build_chunks,
    split_markdown,
    build_chunk_id,
)
# Assuming you have a loader.py file next to this chunking file:
from .loader import load_url_chunks 

# If your tests are explicitly looking for old functions, 
# point them to the new unified function as an alias to prevent breaking changes:
load_html_chunks = load_url_chunks
load_text_chunks = load_url_chunks

__all__ = [
    "TextChunkingStrategy",
    "build_chunks",
    "split_markdown",
    "build_chunk_id",
    "load_url_chunks",
    "load_html_chunks",
    "load_text_chunks",
]