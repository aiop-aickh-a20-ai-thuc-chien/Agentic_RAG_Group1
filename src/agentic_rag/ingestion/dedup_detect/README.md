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

- Cosine similarity over supplied embedding vectors.

Use when:

- Two chunks/pages are semantically similar even when wording differs.
- You want stronger near-duplicate detection after exact and SimHash checks.

Strength:

- Best semantic duplicate signal.

Limit:

- Requires an embedding method.
- May call local models or external providers depending on how vectors are
  produced before they are passed into this package.

## Choosing An Embedding Similarity Method

The `dedup_detect` module does not auto-download BERT or call APIs. You choose
how to produce vectors, then pass them to `detect_duplicates()`.

### Option A: Existing Project Embedding Client

Use the configured project embedding runtime from `agentic_rag.model_runtime`.
This keeps duplicate detection aligned with retrieval embeddings.

Good for:

- Keeping dedup behavior aligned with retrieval embeddings.
- Avoiding a second embedding stack.

Tradeoff:

- Runtime may call an external service or load a local model depending on
  environment configuration.

### Option B: Local BERT / Sentence-Transformers

Use `sentence-transformers` through the project local-models extra or another
local embedding wrapper, then pass vectors into this module.

Recommended model profile:

- Multilingual/Vietnamese content:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- English-heavy content:
  `sentence-transformers/all-MiniLM-L6-v2`

Good for:

- Offline semantic duplicate detection.
- Keeping sensitive documents local.

Tradeoff:

- Requires model install/download.
- CPU inference can be slow on large batches.

Threshold test harness:

- `src/agentic_rag/ingestion/dedup_detect/test/`
- Default model:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Optional env override:
  `DEDUP_DETECT_SENTENCE_TRANSFORMER_MODEL`
- Command:

```powershell
uv sync --extra local-models
uv run python src/agentic_rag/ingestion/dedup_detect/test/threshold_sweep.py
```

The harness embeds labeled duplicate / near-duplicate / different pairs, sweeps
cosine thresholds, and recommends the best threshold by F1 score.

### Option C: Precomputed Vectors

If ingestion or retrieval already computed vectors, pass those vectors directly.

Good for:

- Avoiding duplicate embedding calls.
- Reusing vector-store payloads or batch embedding jobs.

Tradeoff:

- You must ensure all vectors use the same model and dimensions.

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

## Embedding Usage With Precomputed Vectors

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

## Embedding Usage With Project Client

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
