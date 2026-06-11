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

- OpenAI-compatible embeddings first when API credentials are configured.
- Local `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` fallback.
- Cosine similarity over the selected embedding vectors.

Use when:

- Two chunks/pages are semantically similar even when wording differs.
- You want stronger near-duplicate detection after exact and SimHash checks.

Strength:

- Best semantic duplicate signal.

Limit:

- OpenAI requires an API key or compatible API base.
- Local fallback requires the `local-models` extra and a cached/downloadable
  sentence-transformers model.

## Layer 3 Runtime Order

When `DedupConfig(enable_embedding=True)` is used without precomputed vectors or
an explicit embedding client, `dedup_detect` builds Layer 3 candidates in this
order:

1. OpenAI-compatible embedding client through LiteLLM.
2. Local sentence-transformers embedding client.

OpenAI is attempted only when `DEDUP_DETECT_OPENAI_API_KEY`, `OPENAI_API_KEY`,
`DEDUP_DETECT_OPENAI_API_BASE`, or a compatible embedding API base is configured.
If OpenAI fails or is unavailable, the local sentence-transformers model is used.
Matches still use cosine similarity, and match metadata records the provider,
model, and failed fallback attempts.

Useful variables:

- `DEDUP_DETECT_OPENAI_EMBEDDING_MODEL`
- `DEDUP_DETECT_OPENAI_API_KEY`
- `DEDUP_DETECT_OPENAI_API_BASE`
- `DEDUP_DETECT_SENTENCE_TRANSFORMER_MODEL`
- `DEDUP_DETECT_SENTENCE_TRANSFORMER_DEVICE`

Defaults:

- OpenAI model: `text-embedding-3-small`
- Local fallback model:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

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

Each duplicate chunk gets `Chunk.metadata["deduplication"]`:

```json
{
  "has_duplicate": true,
  "match_count": 1,
  "detected_layers": ["exact_sha256"],
  "matches": [
    {
      "other_document_id": "chunk-a",
      "role": "duplicate_candidate",
      "detected_layer": "exact_sha256",
      "score": 1.0,
      "distance": 0,
      "fingerprint": "sha256...",
      "reason": "same normalized text SHA-256",
      "detection_summary": "duplicate-candidate side: exact normalized text duplicate detected.",
      "metadata": {}
    }
  ]
}
```

This metadata is descriptive only. It records which layer detected the duplicate
signal and enough match details for a later human review or a separate resolver.

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
