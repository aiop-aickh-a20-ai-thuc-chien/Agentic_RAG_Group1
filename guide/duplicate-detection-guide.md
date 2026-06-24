# Duplicate Detection Guide

This guide explains how to learn and use duplicate detection for ingestion
chunks. The package is detection-only: it reports duplicate signals and can add
metadata, but it does not delete, merge, or resolve chunks automatically.

## What To Learn First

Duplicate detection lives under `src/agentic_rag/ingestion/dedup_detect`. The
main public functions are:

- `documents_from_chunks(chunks)`
- `detect_duplicates(documents, config=DedupConfig(...))`
- `add_duplicate_metadata_to_chunks(chunks, report)`

The typical flow is:

```python
from agentic_rag.ingestion.dedup_detect import (
    DedupConfig,
    add_duplicate_metadata_to_chunks,
    detect_duplicates,
    documents_from_chunks,
)

documents = documents_from_chunks(chunks)
report = detect_duplicates(documents, config=DedupConfig())
enriched_chunks = add_duplicate_metadata_to_chunks(chunks, report)
```

## Detection Layers

The current V2 contract is:

```text
chunks
  -> L1 SHA-256 exact duplicate detection
  -> L2 metadata blocking
  -> L2 LLM duplicate review inside candidate blocks
  -> DedupReport and descriptive chunk metadata
```

| Layer | Status | Purpose |
| --- | --- | --- |
| L1 exact SHA-256 | Confirmed | Finds identical normalized text deterministically |
| L2 metadata blocking | Planned | Narrows candidate pairs by shared source and content metadata |
| L2 LLM review | Planned | Classifies blocked candidates as duplicate, not duplicate, or needs review |
| SimHash | Optional research helper | Finds lexical near-duplicates, but is not the V2 default L2 contract |
| Embedding similarity | Optional research helper | Finds semantic similarity when vectors or an embedding client are available |

The important change is that L2 should not begin with an all-pairs lexical or
semantic comparison. It should first use metadata to form small candidate
blocks, then use an LLM only on those candidates when deterministic evidence is
not enough.

## Key Files

| File | Purpose |
| --- | --- |
| `src/agentic_rag/ingestion/dedup_detect/models.py` | `DedupDocument`, `DedupConfig`, `DuplicateMatch`, `DedupReport` |
| `src/agentic_rag/ingestion/dedup_detect/pipeline.py` | Layer orchestration and chunk conversion |
| `src/agentic_rag/ingestion/dedup_detect/exact.py` | Exact normalized SHA-256 matching |
| `src/agentic_rag/ingestion/dedup_detect/blocking/` | Planned L2 metadata block-key generation |
| `src/agentic_rag/ingestion/dedup_detect/llm_review/` | Planned L2 LLM duplicate review |
| `src/agentic_rag/ingestion/dedup_detect/simhash.py` | Optional lexical research helper |
| `src/agentic_rag/ingestion/dedup_detect/embedding.py` | Optional semantic research helper |
| `src/agentic_rag/ingestion/dedup_detect/metadata.py` | Duplicate metadata attached to chunks |

## Metadata Contract

Duplicate metadata is attached under:

```text
Chunk.metadata["deduplication"]
```

It is descriptive metadata for review, ranking, debugging, or future resolution.
Do not treat it as permission to drop content automatically.

## URL Ingestion Use Case

URL ingestion often creates duplicate-like chunks because pages share navigation,
footer text, product cards, pricing blocks, or repeated campaign copy. For URL
work:

1. Ingest URLs with `load_url_with_artifacts()` or the URL dedup demo.
2. Run L1 SHA-256 exact detection first.
3. Build L2 candidate blocks with metadata such as `source_type`,
   `document_type`, domain, canonical URL, product model, language, heading, and
   section.
4. Use LLM review only inside candidate blocks.
5. Keep SimHash or embedding experiments in guide reports until thresholds are
   validated.

## Demo Workflow

Run duplicate detection over a URL file:

```powershell
uv run python guide/demo/dedup-detect-url-review/run_url_dedup_review.py `
  --urls-file guide/demo/dedup-detect-url-review/urls.example.txt
```

Start by reading:

```text
guide/demo/dedup-detect-url-review/output/dedup_review.md
```

For threshold tuning, edit `golden_samples.json`, then run:

```powershell
uv run python guide/demo/dedup-detect-url-review/evaluate_thresholds.py
```

Read `guide/demo/dedup-detect-url-review/README.md` for embedding options and
review-output details.

## Quality Checks

For duplicate-detection changes, run focused tests for the package if present,
then the full project gate before review:

```powershell
uv run pytest -q
```

## Deeper References

- `src/agentic_rag/ingestion/dedup_detect/README.md`
- `guide/dedup-detect-implementation-report.md`
- `guide/demo/dedup-detect-url-review/README.md`
- `docs/module-contracts.md`
