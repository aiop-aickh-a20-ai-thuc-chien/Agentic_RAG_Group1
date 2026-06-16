# Ingestion Dedup Detection

This package provides duplicate detection that can be shared by PDF and URL
ingestion. It is intentionally separate from parser-specific modules and only
reports duplicate signals. It does not merge, delete, or judge documents.

## Three Layers

### Layer 1: Exact Duplicate Detection

Technology:

- SHA-256 over normalized text.

Use when:

- Two chunks/pages have the same content after Unicode, case, zero-width, and
  whitespace normalization.

Strength:

- Deterministic and fast.
- Safe for ingestion-time use.

Limit:

- Does not catch paraphrases or small edits.

### Layer 2: Near-Duplicate Detection

Technology:

- SimHash over normalized token shingles.
- Hamming distance threshold.

Use when:

- Two chunks/pages are mostly the same but have small edits, reordered spacing,
  repeated headers, or minor number/text changes.

Strength:

- Fast enough for local pairwise checks on modest document sets.
- Does not require model calls.

Limit:

- Still lexical. It does not understand semantic equivalence.

### Layer 3: Embedding Similarity

Technology:

- The shared project embedding runtime configured through `.env`.
- Cosine similarity over the selected embedding vectors.

Use when:

- Two chunks/pages are semantically similar even when wording differs.
- You want stronger near-duplicate detection after exact and SimHash checks.

Strength:

- Best semantic duplicate signal.

Limit:

- Runtime requirements depend on the configured embedding provider.
- Local sentence-transformers models require the `local-models` extra and a
  cached/downloadable model.

## Layer 3 Runtime Configuration

When `DedupConfig(enable_embedding=True)` is used without precomputed vectors or
an explicit embedding client, `dedup_detect` uses the same embedding client as
the rest of the project.

Do not configure dedup-specific embedding variables. Use the existing
`.env.example` contract:

```env
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_API_BASE=
EMBEDDING_API_KEY=
EMBEDDING_DIMENSIONS=
EMBEDDING_TIMEOUT_SECONDS=60
```

If you want OpenAI or another API-based embedding provider, set the shared
`EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, and `EMBEDDING_API_KEY` values for the
project. Dedup detection will use that same client.

### Runtime Usage

```python
from agentic_rag.ingestion.dedup_detect import DedupConfig, detect_duplicates

report = detect_duplicates(
    documents,
    config=DedupConfig(
        enable_embedding=True,
        embedding_similarity_threshold=0.92,
    ),
)
```

### Option A: Existing Project Embedding Client

You can bypass the OpenAI-first fallback and provide the configured project
embedding runtime directly.

```python
from agentic_rag.ingestion.dedup_detect import DedupConfig, detect_duplicates
from agentic_rag.model_runtime.factory import get_embedding_client

report = detect_duplicates(
    documents,
    config=DedupConfig(
        enable_embedding=True,
        embedding_similarity_threshold=0.92,
        embedding_method="project-embedding-client",
    ),
    embedding_client=get_embedding_client(),
)
```

### Option B: Precomputed Vectors

If ingestion or retrieval already computed vectors, pass those vectors directly.
This avoids extra provider calls.

```python
from agentic_rag.ingestion.dedup_detect import DedupConfig, detect_duplicates

vectors = {
    "a": [0.1, 0.2, 0.3],
    "b": [0.1, 0.2, 0.3],
    "c": [0.2, 0.1, 0.3],
}

report = detect_duplicates(
    documents,
    config=DedupConfig(
        enable_embedding=True,
        embedding_similarity_threshold=0.92,
        embedding_method="precomputed-cosine",
    ),
    embedding_vectors=vectors,
)
```

## Basic Usage

```python
from agentic_rag.ingestion.dedup_detect import DedupConfig, DedupDocument, detect_duplicates

documents = [
    DedupDocument(document_id="a", text="VinFast VF 9 price from 1.2B VND"),
    DedupDocument(document_id="b", text="VinFast VF 9 price from 1.2B VND"),
    DedupDocument(document_id="c", text="VinFast VF9 starts around 1.2 billion VND"),
]

report = detect_duplicates(documents)

print(report.exact_matches)
print(report.simhash_matches)
```

## Detection Metadata

Duplicate detection can attach metadata to chunks without merging or deleting
anything:

```python
from agentic_rag.ingestion.dedup_detect import (
    add_duplicate_metadata_to_chunks,
    detect_duplicates,
    documents_from_chunks,
)

documents = documents_from_chunks(chunks)
report = detect_duplicates(documents)
enriched_chunks = add_duplicate_metadata_to_chunks(chunks, report)
```

Only duplicate candidates get `Chunk.metadata["deduplication"]`. The canonical
chunk stays clean and is referenced from the candidate metadata:

```json
{
  "status": "duplicate_candidate",
  "review_status": "pending",
  "has_duplicate": true,
  "match_count": 1,
  "detected_layers": ["exact_sha256"],
  "canonical_chunk_id": "chunk-a",
  "canonical_document_id": "doc-a",
  "group_id": "chunk-a::chunk-b",
  "matches": [
    {
      "canonical_chunk_id": "chunk-a",
      "canonical_document_id": "doc-a",
      "duplicate_chunk_id": "chunk-b",
      "duplicate_document_id": "doc-b",
      "role": "duplicate_candidate",
      "detected_layer": "exact_sha256",
      "score": 1.0,
      "distance": 0,
      "fingerprint": "sha256...",
      "reason": "same normalized text SHA-256",
      "detection_summary": "candidate side: exact normalized text duplicate detected.",
      "metadata": {}
    }
  ]
}
```

This metadata is descriptive only. It records which layer detected the duplicate
signal and enough match details for a later human review or a separate resolver.

## Shared Metadata Contract Check

Dedup expects ingestion chunks to follow the shared metadata contract. The
minimum required fields are:

- `source_type`: required for every chunk. It is the shared source category:
  `official`, `internal`, `partner`, `news`, `community`, or `unknown`.
- `source`: concrete source URL/path/source name, used for citations and
  grouping.
- `updated_date`: required for every chunk. In this project it means the time
  ingestion started for that source, not the source's own modified time.

`created_date`, `language`, and `document_type` are optional. `created_date`
should only be present when URL/PDF ingestion can extract trusted source modified
metadata from the source data. URL ingestion may add `document_type` when it can
infer page type. PDF ingestion should leave `document_type` absent unless a
parser or enrichment step can prove it.

Before reviewing duplicate candidates, you can summarize metadata readiness:

```python
from agentic_rag.ingestion.dedup_detect import chunk_metadata_contract_summary

summary = chunk_metadata_contract_summary(chunks)
print(summary["missing_required_count"])
print(summary["source_type_counts"])
print(summary["document_type_counts"])
```

The helper reports missing required fields but does not repair chunks or change
dedup decisions.

## Integration And Backfill

`LocalPdfEvidenceProvider` runs dedup during PDF, URL, and text upload after
source-specific chunks have local metadata and before chunks are written to the
source store/vector index. Upload-time dedup compares new chunks with existing
stored chunks. Exact, SimHash, and embedding layers are enabled by default.
Only duplicate candidates get dedup metadata; canonical chunks stay unmarked.

Canonical selection is order-based across all three layers. Upload-time dedup
puts existing chunks before new chunks, so already-stored chunks stay canonical.
Backfill sorts legacy chunks by this policy before detection:

1. chunks/documents referenced by eval questions
2. older `created_at`/ingestion timestamps when available
3. stable fallback: `document_id`, chunk index, then `chunk_id`

Embedding dedup is best-effort during upload. If the configured embedding runtime
fails, ingestion keeps exact and SimHash results and records
`embedding_status="fallback_without_embedding"` in the upload trace.
Layer 3 embedding requests are batched with `DEDUP_EMBEDDING_BATCH_SIZE` to keep
large backfills within provider request limits.

To backfill metadata for sources that were uploaded before dedup existed:

```bash
uv run python scripts/backfill_dedup.py --dry-run
uv run python scripts/backfill_dedup.py
```

Use `--strict-embedding` when Layer 3 failure should stop the job instead of
falling back to exact/SimHash. Backfill rewrites stored chunk metadata and
re-upserts dense payloads so Qdrant/pgvector retrieval sees the updated metadata.

The internal review page is available at `/internal/dedup-review`; it reads
duplicate candidates from `GET /internal/dedup`.

## Suggested Thresholds

| Layer | Default | Suggested Range |
| --- | ---: | ---: |
| SimHash Hamming distance | `6` over 64 bits | `3-10` |
| Embedding cosine similarity | `0.92` | `0.88-0.97` |

Use higher embedding thresholds when false positives are costly. Use lower
thresholds when you want review candidates rather than automatic removal.

## Policy For Ingestion

Recommended behavior:

- Exact duplicates can be marked as duplicate metadata.
- SimHash matches should usually be marked as near-duplicate metadata first.
- Embedding matches should be review signals unless the threshold and provider
  are validated for the document type.

This keeps ingestion conservative and avoids silently deleting useful evidence.
