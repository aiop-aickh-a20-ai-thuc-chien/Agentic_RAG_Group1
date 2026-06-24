# Dedup Detect Implementation Report

Date: 2026-06-11

Code reference: `origin/develop@98e07da`

Scope: `src/agentic_rag/ingestion/dedup_detect`

## 2026-06-16 V2 Decision

This report records the earlier implementation state, where the package had
exact, SimHash, and optional embedding layers. The V2 planning decision for the
current branch is:

1. L1 confirmed: SHA-256 exact duplicate detection over normalized text or
   dedupe text.
2. L2 planned: metadata blocking plus LLM-assisted duplicate review.
3. SimHash, MinHash, and embedding similarity remain optional research helpers,
   not the active L2 default.
4. `dedup_detect` stays detection-only. It should mark duplicate evidence, not
   delete, merge, or decide factual conflicts.

Metadata blocking should use stable fields from URL/PDF ingestion such as
`source_type`, `document_type`, domain or source family, canonical URL, file
name, product model, language, heading, section, and stable entity keys when
available. The LLM review step should only compare candidates inside those
blocks and return `duplicate`, `not_duplicate`, or `needs_review` with evidence.

## Summary

`dedup_detect` is a detection-only package for finding duplicate or
near-duplicate ingestion chunks. It is designed to be shared by URL and PDF
ingestion, but it does not parse sources by itself and does not delete, merge, or
auto-resolve chunks.

The historical implementation described in this report has three detection
helpers:

1. Exact duplicate detection with SHA-256 over normalized text.
2. Near-duplicate detection with SimHash over token shingles.
3. Semantic near-duplicate detection with embeddings and cosine similarity.

For V2 planning, only the first item is confirmed as the stable L1 contract. L2
should be implemented as metadata blocking plus LLM review. SimHash and
embedding similarity can still be useful for experiments, but they should not be
treated as the default L2 path.

The output is a `DedupReport` plus optional chunk metadata. The metadata marks
which chunks have duplicate signals and which layer detected each signal.

## Main Contracts

The public contract file is:

`src/agentic_rag/ingestion/dedup_detect/models.py`

Key models:

- `DedupDocument`: text prepared for duplicate detection.
  - `document_id`
  - `text`
  - `metadata`
- `DedupConfig`: runtime switches and thresholds.
- `DuplicateMatch`: one pair detected by one layer.
- `DedupReport`: grouped result containing exact, SimHash, and embedding
  matches.

Supported duplicate layer names:

- `exact_sha256`
- `simhash`
- `embedding_similarity`

## Pipeline Order

The orchestrator is:

`src/agentic_rag/ingestion/dedup_detect/pipeline.py`

The main function is:

```python
detect_duplicates(documents, config=DedupConfig(...))
```

Pipeline order:

1. Convert input iterable into a list.
2. Run Layer 1 exact duplicate detection if `enable_exact=True`.
3. Exclude exact-match pairs from later layers.
4. Run Layer 2 SimHash detection if `enable_simhash=True`.
5. Exclude exact and SimHash pairs from Layer 3.
6. Run Layer 3 embedding similarity only if `enable_embedding=True`.
7. Return one `DedupReport`.

Important behavior:

- Layer 3 is disabled by default.
- Later layers do not repeat pairs already found by earlier layers.
- This makes the report easier to read: exact matches are exact, SimHash matches
  are lexical near-duplicates not already exact, and embedding matches are
  semantic near-duplicates not already found by Layer 1 or Layer 2.

## Chunk Integration

The helper:

```python
documents_from_chunks(chunks)
```

converts shared `Chunk` objects into `DedupDocument` objects:

- `document_id = chunk.chunk_id`
- `text = chunk.text`
- `metadata = chunk.metadata`

The helper:

```python
add_duplicate_metadata_to_chunks(chunks, report)
```

adds `metadata["deduplication"]` to chunks with duplicate signals.

Example metadata shape:

```json
{
  "has_duplicate": true,
  "match_count": 1,
  "detected_layers": ["simhash"],
  "matches": [
    {
      "other_document_id": "other_chunk_id",
      "role": "canonical",
      "detected_layer": "simhash",
      "score": 0.9375,
      "distance": 4,
      "fingerprint": "left:right",
      "reason": "SimHash Hamming distance within threshold",
      "detection_summary": "canonical side: near-duplicate detected by SimHash distance.",
      "metadata": {
        "bits": 64,
        "shingle_size": 4,
        "hamming_threshold": 6
      }
    }
  ]
}
```

This is descriptive metadata only. It is meant for review, downstream ranking,
debugging, or a future resolver. It is not an auto-delete or auto-merge action.

## Layer 1: Exact SHA-256

File:

`src/agentic_rag/ingestion/dedup_detect/exact.py`

What it does:

- Normalizes chunk text.
- Computes SHA-256 over the normalized text.
- Groups documents by fingerprint.
- Emits matches when two or more documents share the same fingerprint.

Normalization happens in:

`src/agentic_rag/ingestion/dedup_detect/normalization.py`

Normalization rules:

- Unicode NFKC normalization.
- Remove zero-width characters.
- Case-fold text.
- Collapse whitespace.
- Strip leading/trailing whitespace.

Layer 1 decision:

- If normalized text is identical, it is a duplicate.
- Score is always `1.0`.
- Distance is always `0`.

Why it exists:

- It is deterministic, fast, and safe.
- It should catch repeated boilerplate chunks, repeated parser output, and exact
  repeated source sections.

## Historical Layer 2: SimHash Near-Duplicate

V2 note: SimHash is no longer the planned L2 contract. Keep it as an optional
research helper while implementing metadata blocking plus LLM review as the
planned L2 path.

File:

`src/agentic_rag/ingestion/dedup_detect/simhash.py`

What it does:

- Normalizes text.
- Tokenizes with a Unicode word regex.
- Builds token shingles.
- Computes a SimHash fingerprint.
- Compares fingerprints by Hamming distance.
- Emits a match when distance is within threshold.

Default config from `DedupConfig`:

```python
simhash_bits = 64
simhash_shingle_size = 4
simhash_hamming_threshold = 6
```

Score:

```python
1.0 - (distance / bits)
```

Layer 2 decision:

- If Hamming distance is less than or equal to the threshold, the pair is a
  near-duplicate.
- Exact duplicate pairs are excluded before SimHash runs.

Why it exists:

- It catches chunks that are mostly the same but differ slightly.
- It is cheap and does not require API calls or local ML models.
- It is still lexical, so it can miss semantic duplicates with different words.

## Historical Layer 3: Embedding Similarity

V2 note: embedding similarity is no longer the planned semantic default for
dedup. Keep it as an optional research helper and compare it against
metadata-blocked LLM review in evaluation reports.

File:

`src/agentic_rag/ingestion/dedup_detect/embedding.py`

What it does:

- Embeds each document using either:
  - supplied `embedding_vectors`,
  - supplied `embedding_client`, or
  - the configured project embedding runtime.
- Computes cosine similarity for document pairs.
- Emits a match when cosine similarity is greater than or equal to threshold.

Default config from `DedupConfig`:

```python
enable_embedding = False
embedding_similarity_threshold = 0.92
embedding_method = None
```

Layer 3 runtime configuration:

- It uses the shared project embedding runtime.
- It does not define separate `DEDUP_*` embedding variables.
- Configure it through:
  - `EMBEDDING_PROVIDER`
  - `EMBEDDING_MODEL`
  - `EMBEDDING_API_BASE`
  - `EMBEDDING_API_KEY`
  - `EMBEDDING_DIMENSIONS`
  - `EMBEDDING_TIMEOUT_SECONDS`

Layer 3 decision:

- If cosine similarity is greater than or equal to `0.92`, the pair is a
  semantic near-duplicate.
- Exact and SimHash pairs are excluded before Layer 3 runs.

Why it exists:

- It catches semantic similarity that lexical methods miss.
- It is more expensive and more provider-dependent than Layer 1 and Layer 2.
- For this reason, it is opt-in in the default config.

## Current Threshold Decisions In Develop

These are the thresholds currently encoded in `origin/develop@98e07da`.

| Layer | Enabled By Default | Threshold / Decision |
| --- | --- | --- |
| Layer 1 exact SHA-256 | Yes | No numeric threshold. Normalized SHA-256 must match exactly. |
| Layer 2 SimHash | Yes | `simhash_hamming_threshold=6` over `64` bits with `4`-token shingles. |
| Layer 3 embedding similarity | No | `embedding_similarity_threshold=0.92` when explicitly enabled. |

Important distinction:

- The thresholds in `src/agentic_rag/ingestion/dedup_detect` are static
  conservative defaults.
- The guide demo threshold sweeps are research tools and are not the defaults
  pushed to `develop`.

## Why These Defaults Are Conservative

Layer 1 is enabled because exact duplicates are low-risk to detect.

Layer 2 is enabled with a relatively small Hamming threshold because false
positives are dangerous in RAG ingestion. A false positive can mark different
facts as duplicate-like, especially when pages have similar templates but
different product names, prices, dates, or vehicle models.

Layer 3 is disabled by default because embedding similarity can be powerful but
also riskier:

- Short chunks with similar structure can look semantically similar even when
  they refer to different products.
- API/model behavior depends on embedding provider and model.
- Embedding calls cost time and money when API-based.
- A threshold that works for URL chunks may not work for PDF chunks.

The current `0.92` Layer 3 threshold should be treated as a review threshold, not
an auto-resolution threshold.

## How The Three Layers Filter Chunks

The package does not remove chunks. It filters duplicate candidates into match
groups.

Flow:

```text
chunks
  -> documents_from_chunks()
  -> Layer 1 exact matches
  -> exclude exact pairs
  -> Layer 2 SimHash matches
  -> exclude exact + SimHash pairs
  -> optional Layer 3 embedding matches
  -> DedupReport
  -> add_duplicate_metadata_to_chunks()
```

Result:

- All original chunks remain present.
- Chunks with duplicate signals get extra metadata.
- Downstream code can inspect metadata and decide what to do later.

## What The Current Implementation Does Not Do

It does not:

- delete chunks,
- merge chunks,
- pick a final canonical chunk for storage,
- detect factual conflicts,
- decide whether same-product/different-price is an error,
- tune thresholds automatically,
- use OpenAI judgement,
- run Layer 3 unless `enable_embedding=True`.

This boundary is intentional. Detection is separate from resolution.

## Current Research Demo Decision

The guide demo under:

`guide/demo/dedup-detect-url-review`

adds research-only threshold evaluation:

- `golden_samples.json`: manually labeled duplicate/non-duplicate pairs.
- `evaluate_thresholds.py`: threshold sweep and confusion matrix.
- `judge_threshold_report.py`: optional OpenAI judgement of the confusion matrix.

These files are for research. They are not part of the `src` package behavior in
`develop`.

From the current guide demo run without Layer 3, the generated report selected:

- SimHash threshold: `34`
- Layer 3 embedding threshold: `None`
- Precision: `0.6`
- Recall: `1.0`
- F1: `0.75`

That result is useful for the sample guide dataset, but it should not replace
the `develop` default yet because:

- The golden sample is still small.
- The sample appears URL/product-page heavy.
- PDF behavior has not been validated.
- A high SimHash threshold can increase false positives on templated pages.

## Recommended Next Decision

For code defaults in `develop`, keep:

```python
simhash_hamming_threshold = 6
embedding_similarity_threshold = 0.92
enable_embedding = False
```

For research/demo tuning, keep testing:

- Layer 2 SimHash thresholds from `2` to `40`.
- Layer 3 embedding thresholds from `0.86` to `0.98`.
- Separate golden labels for URL and PDF.
- FP/FN inspection by chunk ID.

Only promote new defaults after the confusion matrix has enough manually checked
examples across both URL and PDF ingestion.

## Practical Usage

Basic detection:

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

Enable Layer 3:

```python
report = detect_duplicates(
    documents,
    config=DedupConfig(
        enable_embedding=True,
        embedding_similarity_threshold=0.92,
    ),
)
```

Use precomputed vectors:

```python
report = detect_duplicates(
    documents,
    config=DedupConfig(enable_embedding=True),
    embedding_vectors=vectors,
)
```

## Bottom Line

`dedup_detect` currently gives the project a safe detection layer, not a
resolution system.

The V2 decision for the current branch is:

- L1 exact SHA-256 is confirmed and safe to flag,
- L2 should be metadata blocking plus LLM-assisted duplicate review,
- SimHash, MinHash, and embedding similarity are optional research helpers,
- no dedup layer should delete, merge, or resolve factual conflicts without a
  separate resolver policy.
