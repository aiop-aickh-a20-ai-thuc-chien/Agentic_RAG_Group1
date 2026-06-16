"""DOM-aware semantic block detection for URL ingestion."""

from agentic_rag.ingestion.url.dom.blocks import (
    DomBlock,
    detect_semantic_blocks,
    dom_blocks_summary,
)

__all__ = ["DomBlock", "detect_semantic_blocks", "dom_blocks_summary"]
