# Duplicate Detection Strategy for RAG Ingestion: Latency and Relevance Improvements

## Purpose

This document explains how to apply duplicate detection in a RAG ingestion pipeline, especially for URL-crawled pages such as VinFast pages. The goal is not only to remove repeated text, but also to improve retrieval speed, reduce noisy context, avoid repeated citations, and improve answer quality.

The recommended approach is layered:

```text
Normalize text
↓
Exact duplicate detection with chunk-level hash
↓
Metadata blocking
↓
Embedding similarity inside each block
↓
Decision: delete, merge, keep, or flag conflict
```

---

## Current Observation From the VinFast Crawl Artifact

The uploaded crawl artifact has these useful signals:

- `manifest.json` reports `chunk_count = 30`.
- The page source is `https://vinfastauto.com/vn_vi`.
- The parser used a combined strategy: `trafilatura-markdown+builtin-html-parser+crawl4ai-rendered-html`.
- The parsed content contains many repeated product-listing sections such as:
  - `Dòng xe D-SUV`
  - `Dòng xe MPV`
  - `Dòng xe MiniCar`
  - `Dòng xe A-SUV`
  - `Dòng xe B-SUV`
  - `Xe máy điện`
- The parsed content also includes low-value navigation, footer, country selector, and cookie text.

Important implementation issue found:

```text
metadata.content_hash is identical across all 30 chunks.
metadata.dedupe_hash is unique across all 30 chunks.
```

This suggests `content_hash` may currently be generated from the full page or shared artifact instead of the individual normalized chunk. For duplicate detection, you should separate:

```json
{
  "page_hash": "hash of the full parsed page",
  "content_hash": "hash of this normalized chunk",
  "dedupe_hash": "hash used for duplicate matching after normalization"
}
```

Recommended fix:

```python
page_hash = sha256(normalized_full_page)
content_hash = sha256(normalized_chunk_text)
dedupe_hash = sha256(aggressively_normalized_chunk_text)
```

Implementation note:

URL ingestion now emits separate `page_hash`, chunk-level `content_hash`, and
`dedupe_hash` values in `Chunk.metadata`. Duplicate detection should consume
those URL-provided hashes for exact duplicate checks and blocking, while keeping
merge/delete/conflict decisions inside `dedup_detect` and `knowledge_quality`.

---

## Why Duplicate Detection Improves Latency

Duplicate detection reduces latency in four places:

1. **Ingestion time**
   - Exact duplicates can be skipped before embedding generation.
   - This avoids unnecessary calls to embedding APIs or local embedding models.

2. **Vector index size**
   - Fewer duplicate chunks means fewer vectors stored.
   - Smaller vector indexes usually search faster and use less memory.

3. **Retrieval time**
   - Dense retrieval and BM25 search return fewer repeated results.
   - Reranking has fewer redundant candidates to evaluate.

4. **Generation time**
   - The LLM receives fewer duplicate context chunks.
   - Context is shorter, cleaner, and cheaper.

Example:

```text
Without dedupe:
Query → retrieve 20 chunks → 8 chunks are repeated product cards → rerank/generate with noise

With dedupe:
Query → retrieve 20 chunks → mostly unique facts → rerank/generate with better evidence
```

---

## Why Duplicate Detection Improves Relevance

Duplicate chunks can hurt relevance because they dominate retrieval results.

Example problem:

```text
Top 5 retrieved chunks:
1. VF8 price page copy A
2. VF8 price page copy B
3. VF8 price page copy C
4. VF8 price page copy D
5. VF8 price page copy E
```

The answer may miss useful supporting evidence such as warranty, promotion terms, official policy, or updated source.

Better result after dedupe:

```text
Top 5 retrieved chunks:
1. VF8 price/spec chunk
2. VF8 promotion condition chunk
3. VF8 official booking page chunk
4. Battery policy chunk
5. Warranty/service chunk
```

This improves:

- diversity of evidence
- citation quality
- answer grounding
- conflict detection
- user trust

---

## Layer 1: Exact Duplicate Detection

Use this for chunks that are textually identical after normalization.

### Normalization

Recommended normalization:

```python
def normalize_for_exact_dedupe(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text
```

Optional aggressive normalization:

```python
def normalize_for_dedupe(text: str) -> str:
    text = normalize_for_exact_dedupe(text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[\u200b\u200c\u200d]", "", text)
    return text.strip()
```

### Hashing

```python
import hashlib

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```

Store:

```json
{
  "content_hash": "sha256(normalized_chunk_text)",
  "dedupe_hash": "sha256(aggressively_normalized_chunk_text)"
}
```

### Decision

```text
same dedupe_hash
→ exact duplicate
→ keep one canonical chunk
→ merge metadata/source references
```

Do not delete all source references. Keep provenance:

```json
{
  "canonical_chunk_id": "chunk_001",
  "duplicate_sources": [
    {
      "source": "https://...",
      "section_path": ["..."],
      "fetched_at": "2026-06-10T07:08:00Z"
    }
  ]
}
```

---

## Layer 2: Metadata Blocking

Metadata blocking prevents expensive all-to-all comparison.

Bad approach:

```python
for chunk_a in chunks:
    for chunk_b in chunks:
        compare(chunk_a, chunk_b)
```

This is `O(n²)` and becomes expensive quickly.

Better approach:

```python
blocks = group_by_metadata(chunks)
for block in blocks:
    compare_only_inside(block)
```

### Recommended Blocking Keys

For VinFast-style URLs, use:

```python
block_key = (
    canonical_domain,
    source_page_type,
    entity_type,
    entity_name,
    attribute_group,
    language,
)
```

Example blocks:

```text
vinfastauto.com | product_listing | car | VF 8 | pricing_specs | vi
vinfastauto.com | product_listing | car | VF 9 | pricing_specs | vi
vinfastauto.com | faq | car | VF 8 | battery_policy | vi
vinfastauto.com | article | charging | wall_charger | guide | vi
vinfastauto.com | policy | warranty | general | terms | vi
```

### Do Not Rely Only on Section Names

The current crawl contains repeated generic sections:

```text
Dòng xe D-SUV
Dòng xe MPV
Xe máy điện
```

These are not enough. For example, many scooters may be under the same section name `Xe máy điện`. If you block only by `section`, unrelated scooter products may be compared or merged incorrectly.

Instead, enrich metadata with entity extraction:

```json
{
  "entity_name": "VF 8",
  "entity_type": "car",
  "vehicle_segment": "D-SUV",
  "attribute_group": "pricing_specs",
  "section": "Dòng xe D-SUV"
}
```

---

## Layer 3: Embedding Similarity Inside Each Block

After exact dedupe and blocking, run embedding similarity only inside relevant blocks.

```python
for block_key, block_chunks in blocks.items():
    vectors = embed(block_chunks)
    pairs = find_similar_pairs(vectors, threshold=0.90)
```

### Threshold Guide

Use different thresholds for different decisions:

```text
0.98 - 1.00
→ near-exact duplicate
→ safe to merge after fact check

0.94 - 0.98
→ likely duplicate or paraphrase
→ merge if entity and facts match

0.88 - 0.94
→ same topic
→ check for conflict, do not auto-merge

< 0.88
→ probably unrelated
→ keep separate
```

For price/specification chunks, be conservative:

```text
embedding similarity high + values identical
→ merge

embedding similarity high + values different
→ conflict candidate
```

Example:

```text
Chunk A: VF8 price is 819.180.000 VNĐ.
Chunk B: VF8 price is 835.580.000 VNĐ.
```

These may have high embedding similarity, but they should not be merged automatically because the numeric values differ.

---

## Duplicate Decision Matrix

| Condition | Action | Reason |
|---|---|---|
| Same `dedupe_hash` | Delete duplicate / merge provenance | Exact duplicate |
| Same block + embedding > 0.98 + same extracted facts | Merge | Near-identical content |
| Same block + embedding 0.94–0.98 + same facts | Merge with review flag | Likely paraphrase duplicate |
| Same block + embedding > 0.90 + different price/date/range | Flag conflict | Similar topic, different facts |
| Different entity_name | Keep separate | Avoid false merge |
| Different attribute_group | Usually keep separate | Different retrieval use case |
| Navigation/footer/cookie section | Exclude or downrank | Low retrieval value |

---

## How to Improve Latency

### 1. Skip embeddings for exact duplicates

```text
if dedupe_hash already exists:
    do not embed again
    only append provenance
```

Expected impact:

```text
Lower embedding cost
Lower ingestion latency
Smaller vector DB
```

### 2. Use metadata blocking before pairwise comparison

Instead of comparing all chunks globally:

```text
Compare only chunks with same entity/type/attribute block.
```

Expected impact:

```text
From O(n²) global comparison
To many small O(k²) block comparisons
```

### 3. Use approximate nearest neighbor search

For large corpora:

```text
FAISS / HNSW / Chroma / Qdrant / Milvus
```

Do not compute all embedding pair similarities manually once data grows.

### 4. Cache embeddings by `dedupe_hash`

```python
embedding_cache[dedupe_hash] = vector
```

If the same normalized chunk appears again, reuse the vector.

---

## How to Improve Relevance

### 1. Remove repeated chunks before retrieval

This avoids repeated evidence occupying all top-k results.

### 2. Merge provenance instead of keeping duplicate text

Keep one canonical chunk but preserve all source URLs.

```json
{
  "text": "VF8 price/spec content...",
  "sources": [
    "https://vinfastauto.com/vn_vi/...",
    "https://shop.vinfastauto.com/vn_vi/..."
  ]
}
```

### 3. Use diversity-aware retrieval

After retrieval, collapse near-duplicate results:

```python
def diversify_results(results):
    seen_hashes = set()
    final = []
    for r in results:
        if r.dedupe_hash not in seen_hashes:
            final.append(r)
            seen_hashes.add(r.dedupe_hash)
    return final
```

### 4. Downrank low-value blocks

For VinFast pages, downrank or exclude:

```text
navigation
footer
cookie banner
country selector
social tracking assets
generic repeated menu text
```

The parsed homepage currently includes menu/footer/cookie content, which should not dominate retrieval.

---

## Recommended Metadata Schema

Add these fields to each chunk:

```json
{
  "chunk_id": "...",
  "source": "https://vinfastauto.com/vn_vi",
  "canonical_url": "https://vinfastauto.com/vn_vi",
  "source_type": "url",
  "page_type": "homepage_product_listing",
  "language": "vi",
  "title": "VinFast site",
  "section": "Dòng xe D-SUV",
  "section_path": ["Ô tô", "Dòng xe D-SUV"],
  "entity_type": "car",
  "entity_name": "VF 8",
  "vehicle_segment": "D-SUV",
  "attribute_group": "pricing_specs",
  "normalized_text": "...",
  "page_hash": "...",
  "content_hash": "...",
  "dedupe_hash": "...",
  "embedding_model": "text-embedding-3-large",
  "fetched_at": "2026-06-10T07:08:00Z",
  "is_noise": false,
  "retrieval_weight": 1.0
}
```

---

## Implementation Plan for Assist Code / Codex

### Step 1: Fix chunk-level hashes

Ask Codex:

```text
Update the ingestion pipeline so `content_hash` is computed from each normalized chunk, not from the full page. Add `page_hash` for the full parsed page. Keep `dedupe_hash` for aggressive duplicate detection. Add tests proving that two different chunks from the same page have different `content_hash` values unless their normalized text is identical.
```

### Step 2: Add metadata enrichment

```text
Add an entity metadata enrichment step after chunking. Extract entity_type, entity_name, vehicle_segment, and attribute_group from section headings, product-card text, URLs, and known VinFast model names. Do not rely only on section names such as `Xe máy điện` or `Dòng xe D-SUV`.
```

### Step 3: Add exact dedupe

```text
Before embedding generation, check whether `dedupe_hash` already exists in the chunk store. If yes, skip embedding and merge provenance into the existing canonical chunk. Preserve duplicate source URL, section path, fetched_at, and original chunk_id for audit.
```

### Step 4: Add blocking

```text
Group chunks by `(canonical_domain, page_type, entity_type, entity_name, attribute_group, language)`. Only run embedding similarity comparison inside each block. Add fallback blocks for chunks with missing entity metadata, but mark them as lower confidence.
```

### Step 5: Add embedding similarity decisions

```text
Inside each metadata block, compute embedding similarity. If similarity > 0.98 and extracted facts match, merge as near-duplicate. If similarity > 0.90 but extracted numeric/date facts differ, flag as possible conflict. Do not auto-merge chunks with different entity_name or different attribute_group.
```

### Step 6: Add retrieval-time dedupe

```text
After BM25+dense retrieval and before reranking/LLM generation, collapse results by dedupe_hash or canonical_chunk_id. Keep the highest-scoring result and attach duplicate provenance as extra citations.
```

---

## Evaluation Metrics

Measure whether duplicate detection improves the system.

### Latency Metrics

```text
embedding_calls_before vs embedding_calls_after
vector_count_before vs vector_count_after
retrieval_latency_ms_before vs retrieval_latency_ms_after
rerank_latency_ms_before vs rerank_latency_ms_after
LLM_context_tokens_before vs LLM_context_tokens_after
```

### Relevance Metrics

```text
Recall@5
MRR@5
nDCG@5
duplicate_rate_in_top_k
unique_source_count_in_top_k
citation_diversity
answer_groundedness_score
```

### Conflict Metrics

```text
conflict_candidates_found
false_merge_count
missed_duplicate_count
wrong_delete_count
```

Most important custom metric:

```text
duplicate_rate_in_top_k = duplicate_or_near_duplicate_results / total_top_k_results
```

If duplicate detection is working, this should go down.

---

## Expected Improvements

### Latency

Expected improvements are strongest when the crawl contains repeated menus, repeated cards, repeated policies, or copied product sections.

Likely improvements:

```text
Embedding cost: lower
Vector DB size: lower
Retrieval latency: lower
Reranking latency: lower
LLM context tokens: lower
```

### Relevance

Expected improvements:

```text
Higher diversity in top-k results
Fewer repeated citations
Better coverage of price/spec/policy/support evidence
Lower chance of repeated noisy footer/menu chunks
Better conflict detection for price/range/date changes
```

### Risk

The main risk is false merging.

Danger example:

```text
Dòng xe D-SUV, price 819.180.000 VNĐ
Dòng xe D-SUV, price 835.580.000 VNĐ
```

These may look similar but may refer to different models or variants. Do not merge unless entity metadata and extracted facts match.

---

## Final Recommendation

For your pipeline, implement duplicate detection in this order:

```text
P0: Fix chunk-level content_hash
P0: Add exact dedupe before embeddings
P0: Add metadata blocking
P0: Add retrieval-time dedupe before LLM context construction
P1: Add embedding similarity inside blocks
P1: Add conflict detection for similar chunks with different values
P2: Add supervised/LLM duplicate classifier only after you have enough labeled examples
```

The biggest immediate wins are:

```text
1. Correct chunk-level hashing
2. Remove exact duplicates before embedding
3. Prevent duplicated chunks from dominating top-k retrieval
4. Use metadata blocking to avoid false merges and reduce comparison cost
```
