"""DOM-aware parsing and extraction helpers for URL ingestion.

# TODO [GraphRAG – DOM module as graph extraction boundary]:
# This module is the natural boundary for graph extraction in the URL ingestion
# pipeline. The three sub-modules expose complementary graph primitives:
#   - `blocks.py`          → DomBlock nodes + containment edges (CONTAINS)
#   - `entities.py`        → SemanticBlock/LabelValuePair → entity nodes + HAS_ATTRIBUTE edges
#   - `visual_semantics.py`→ VisualSemanticFact nodes + OBSERVED_IN edges to DomBlock
# When the graph layer is introduced, add a `dom_to_graph_batch(html, url)` public
# function here that runs all three extractors and returns a unified GraphImportBatch
# (nodes + edges) without coupling to any specific graph DB driver.
# Reference: GraphRAG integration plan (to be created)
"""

from agentic_rag.ingestion.url.dom.blocks import (
    DomBlock,
    append_structure_aware_markdown,
    detect_semantic_blocks,
    dom_blocks_summary,
)
from agentic_rag.ingestion.url.dom.visual_semantics import (
    VisualEvidenceSource,
    VisualSemanticFact,
    VisualSemanticKind,
    VisualSemanticsResult,
    append_visual_semantics_markdown,
    extract_visual_semantics,
)

__all__ = [
    "DomBlock",
    "VisualEvidenceSource",
    "VisualSemanticFact",
    "VisualSemanticKind",
    "VisualSemanticsResult",
    "append_structure_aware_markdown",
    "append_visual_semantics_markdown",
    "detect_semantic_blocks",
    "dom_blocks_summary",
    "extract_visual_semantics",
]
