# Integration

Target home for ingestion-facing helpers.

Responsibilities:

- Convert shared `Chunk` objects into `DedupDocument` objects.
- Attach duplicate metadata under `Chunk.metadata["deduplication"]`.
- Add future document-level raw-source fingerprint helpers only when ingestion
  needs them.

Current code:

- `src/agentic_rag/ingestion/dedup_detect/pipeline.py`
- `src/agentic_rag/ingestion/dedup_detect/metadata.py`
