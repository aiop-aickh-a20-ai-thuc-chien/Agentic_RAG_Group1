"""PDF ingestion and chunking boundary."""

from __future__ import annotations

from agentic_rag.core.contracts import Chunk


def load_pdf_chunks(path: str) -> list[Chunk]:
    """Load and chunk a PDF file into shared Chunk objects."""

    raise NotImplementedError("load_pdf_chunks is scaffolded for PDF ingestion and chunking.")
