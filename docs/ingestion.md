# Ingestion

The ingestion module is responsible for loading, processing, and chunking data from various sources before it is indexed by the retrieval system.

## Module Layout

The module `src/agentic_rag/ingestion` contains the following sub-components:

- **`url/`**: URL ingestion, including HTML parsing, DOM visual semantics, rendering, and interaction handling.
- **`pdf/`**: Local PDF ingestion and text extraction.
- **`chunking/`**: Shared deterministic chunking primitives and text splitting rules.
- **`dedup_detect/`**: Duplicate detection mechanisms (exact, embedding, metadata, normalization, simhash) to avoid ingesting redundant information.
- **`metadata/`**: Metadata extraction, schema validation, and normalization.
- **`knowledge_quality/`**: Heuristics and quality checks for the extracted knowledge.
- **`integration/`**: Integration layers and pipeline orchestration.

## Key Principles

- **Source Specific Loaders**: Each data source (e.g., URL, PDF) has its own dedicated loader and extraction logic.
- **Shared Chunking**: Different loaders delegate text splitting to the `chunking` module to ensure consistency across the pipeline.
- **Deduplication First**: Chunks are checked for duplicates early in the pipeline via `dedup_detect` to save processing time and storage.
- **Rich Metadata**: Every chunk is enriched with metadata (e.g., `source`, `source_type`, `url`, `title`) as defined by the `metadata` schemas.

For source-specific details, please refer to the corresponding documentation (e.g., `docs/url-ingestion.md`).
