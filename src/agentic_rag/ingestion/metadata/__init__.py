from agentic_rag.ingestion.metadata.extract import (  # noqa: I001
    EXTRACTION_SYSTEM_MESSAGE,
    LLMExtractedMetadata,
    MetadataExtractionInput,
    apply_extracted_metadata,
    build_extraction_input,
    build_extraction_prompt,
    extract_chunk_metadata,
    parse_extraction_response,
)
from agentic_rag.ingestion.metadata.normalize import (
    KNOWN_MODELS,
    build_response_format,
    normalize_metadata,
    normalize_product_models,
)

# Imported AFTER the ``normalize`` submodule so the package-level name
# ``normalize`` resolves to this function, not the submodule object.
from agentic_rag.ingestion.metadata.entity_normalizer import (
    allowlisted_canonicals,
    build_entity_menu,
    detect_in_query,
    entity_type,
    filter_coverage,
    filterable_canonicals,
    normalize,
    normalize_all,
    normalize_filterable,
)
from agentic_rag.ingestion.metadata.schema import (
    DOCUMENT_TYPE_VALUES,
    LANGUAGE_VALUES,
    QDRANT_INDEX_FIELDS,
    REQUIRED_METADATA_FIELDS,
    SOURCE_CATEGORY_VALUES,
    SOURCE_TYPE_VALUES,
    ChunkMetadata,
    has_required_metadata,
    infer_source_type,
    missing_required_metadata,
    require_metadata,
)
from agentic_rag.ingestion.metadata.visual import (
    VISUAL_METADATA_FIELDS,
    enrich_visual_metadata,
)

__all__ = [
    "DOCUMENT_TYPE_VALUES",
    "EXTRACTION_SYSTEM_MESSAGE",
    "KNOWN_MODELS",
    "LANGUAGE_VALUES",
    "LLMExtractedMetadata",
    "MetadataExtractionInput",
    "QDRANT_INDEX_FIELDS",
    "REQUIRED_METADATA_FIELDS",
    "SOURCE_CATEGORY_VALUES",
    "SOURCE_TYPE_VALUES",
    "VISUAL_METADATA_FIELDS",
    "ChunkMetadata",
    "allowlisted_canonicals",
    "apply_extracted_metadata",
    "build_entity_menu",
    "build_extraction_input",
    "build_extraction_prompt",
    "build_response_format",
    "detect_in_query",
    "enrich_visual_metadata",
    "entity_type",
    "extract_chunk_metadata",
    "filter_coverage",
    "filterable_canonicals",
    "has_required_metadata",
    "infer_source_type",
    "missing_required_metadata",
    "normalize",
    "normalize_all",
    "normalize_filterable",
    "normalize_metadata",
    "normalize_product_models",
    "parse_extraction_response",
    "require_metadata",
]

# TODO [PixelRAG Integration — Visual Chunk Metadata]:
# When chunks are produced by the visual rendering pipeline (PixelRAG-style),
# they need additional metadata fields beyond the standard text chunk schema.
#
# Pseudocode:
#
#   VISUAL_METADATA_FIELDS = {
#       "extraction_method":  str,   # "visual_pixelrag" | "text_default"
#       "tile_index":         int,   # which tile of the full-page screenshot
#       "chunk_index":        int,   # which chunk within the tile (row-major)
#       "x_offset":           int,   # horizontal offset in pixels from tile origin
#       "y_offset":           int,   # vertical offset in pixels from tile origin
#       "chunk_width":        int,   # width of this image chunk in pixels
#       "chunk_height":       int,   # height of this image chunk in pixels
#       "viewport_width":     int,   # browser viewport width used during render (875)
#       "page_height":        int,   # total page height in pixels
#       "image_path":         str,   # path to the chunk image file
#       "tile_hash":          str,   # MD5 of source tile for change detection
#   }
#
#   FUNCTION enrich_visual_metadata(chunk: Chunk, visual_info: dict) -> Chunk:
#       """Attach visual rendering metadata to a chunk."""
#       metadata = dict(chunk.metadata)
#       metadata["extraction_method"] = "visual_pixelrag"
#       metadata["tile_index"] = visual_info["tile_index"]
#       metadata["chunk_index"] = visual_info["chunk_index"]
#       metadata["x_offset"] = visual_info.get("x_offset", 0)
#       metadata["y_offset"] = visual_info.get("y_offset", 0)
#       metadata["chunk_width"] = visual_info.get("width", 875)
#       metadata["chunk_height"] = visual_info.get("height", 1024)
#       metadata["viewport_width"] = visual_info.get("viewport_width", 875)
#       metadata["page_height"] = visual_info.get("page_height", 0)
#       metadata["image_path"] = visual_info.get("image_path", "")
#       metadata["tile_hash"] = visual_info.get("tile_hash", "")
#       RETURN chunk.model_copy(update={"metadata": metadata})
#
# Reference: guide_RAG/GUIDELINE.md §4, PixelRAG/embed/src/pixelrag_embed/chunk.py
