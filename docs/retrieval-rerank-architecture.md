# Retrieval & Rerank Architecture

This document explains how retrieval and reranking are wired, which knobs are
selectable, and — importantly — the boundary between the **in-memory path** and
the **Qdrant path**, because SPLADE / ColBERT / the N-way hybrid currently only
run on the in-memory path. It also records a known configuration footgun and the
ownership boundaries between contributors.

## Storage axes are independent

`LOCAL_SOURCE_STORE` and the vector store are **two orthogonal axes**:

| Axis | Env | What it stores |
|---|---|---|
| Source store | `LOCAL_SOURCE_STORE` = `jsonl` \| `s3` \| `postgres` | Raw PDFs, `chunks.jsonl`, metadata. **No vectors.** |
| Vector store | `VECTOR_STORE_PROVIDER` (legacy alias `DENSE_VECTOR_STORE`) = `turbovec` \| `pgvector` \| `qdrant` | Dense / sparse vectors for search. |

So "the DB is on S3" only means the **source** store is S3. Vectors live in
turbovec (in RAM, rebuilt per request) or in Qdrant/pgvector — never in S3.

## Two retrieval paths

`LocalPdfEvidenceProvider.retrieve()` branches on the vector store:

### A. In-memory path (`turbovec`, default) — **TesWy's scope**

Builds an in-memory `Store(chunks)` per request and runs retrieval at query time.
This is where SPLADE / ColBERT / the N-way hybrid live.

- **Legacy two-way (default):** one sparse leg (`SPARSE_PROVIDER`) + one dense leg
  (`DENSE_PROVIDER`), fused by `FUSION_METHOD`. Behaviour unchanged from before.
- **N-way hybrid (opt-in via `RETRIEVERS`):** runs every listed retriever and
  fuses them with weighted RRF / normalized-score. See "Selecting retrievers".

### B. Qdrant path (`qdrant`) — **NAT's scope**

Server-side hybrid in `qdrant_hybrid_search`: dense (HNSW) + a sparse vector that
is a **hashed bag-of-words** (`_sparse_vector`), fused by Qdrant RRF. This path
**does not read `SPARSE_PROVIDER` / `DENSE_PROVIDER` / `RETRIEVERS`** — SPLADE and
ColBERT are **not integrated into Qdrant yet** (see "Phase 2").

## Selecting retrievers (in-memory path)

| Env | Values | Effect |
|---|---|---|
| `SPARSE_PROVIDER` | `bm25` (default), `neural` | Legacy single sparse leg. `neural` = SPLADE (BGE-M3 lexical). |
| `DENSE_PROVIDER` | `vector_store` (default), `colbert` | Legacy single dense leg. `colbert` = BGE-M3 late interaction. |
| `RETRIEVERS` | e.g. `bm25,neural,colbert` | **Opt-in N-way hybrid.** Runs all listed retrievers together. Unset ⇒ legacy two-way. |
| `FUSION_METHOD` | `rrf` (default), `weighted_rrf`, `normalized_score` | Fusion strategy (applies to both two-way and N-way). |
| `FUSION_{BM25,SPLADE,DENSE,COLBERT}_WEIGHT` | floats | Per-retriever weights for `weighted_rrf` / `normalized_score`. |
| `{BM25,SPLADE,DENSE,COLBERT}_MIN_SCORE` | floats | Per-retriever pre-fusion score thresholds. |

Retriever → `SearchResult.retriever` tag: `bm25`→`bm25`, `neural`→`splade`,
`vector_store`→`dense`, `colbert`→`colbert`; the fused output is tagged `hybrid`.

SPLADE and ColBERT share one BGE-M3 model load and one corpus encode per
chunk-set (`agentic_rag/retrieval/bgem3.py`): when both are active, the corpus is
encoded once for sparse + ColBERT (single forward pass), and the result is cached
so `Store` rebuilds do not re-encode.

## Reranking

`RERANK_PROVIDER` selects the reranker (default `score` = no-op deterministic sort):

| Value | Reranker | Notes |
|---|---|---|
| `score` | `ScoreReranker` | Default. No model. |
| `sentence_transformers` | `SentenceTransformersReranker` | Local CrossEncoder (`local-models` extra). |
| `listwise_llm` | `ListwiseLLMReranker` | HuggingFace ranking LLM (e.g. RankZephyr) via the `listwise-reranking` extra. Heavy; **OFF by default**. Loads a ~7B causal LM and runs a sliding-window listwise prompt. Falls back to `ScoreReranker` on any load/invocation error. |
| any other | `LiteLLMReranker` | API rerank endpoint (Cohere / Jina / Voyage / vLLM) via LiteLLM. |

In the agent flow, the provider fuses internally and the agent reranks the fused
candidate pool once with the original question.

## Indexing & re-indexing with SPLADE / ColBERT

SPLADE and ColBERT do **not** change chunking, so the chunks in S3 are reused as-is.

- **In-memory (turbovec):** no re-index. Vectors are computed at query time from
  the existing chunks; switching `SPARSE_PROVIDER`/`RETRIEVERS` takes effect on the
  next request (cost: BGE-M3 encodes the candidate document's chunks, cached).
- **Qdrant:** a re-index **into Qdrant** would be required (and the code to store
  SPLADE/ColBERT vectors there does not exist yet — Phase 2). S3 is never touched.

## ⚠️ Configuration footgun: `VECTOR_STORE_PROVIDER` vs `DENSE_VECTOR_STORE`

Two pieces of code decide "is Qdrant active" using **different env vars**:

- `resolve_vector_store_config()` honors `VECTOR_STORE_PROVIDER` (canonical) **or**
  `DENSE_VECTOR_STORE` (legacy). Used by upsert / `qdrant_hybrid_search`.
- `_qdrant_vector_store_enabled()` (the `retrieve()`/ingest branch selector) reads
  **only `DENSE_VECTOR_STORE`**.

Consequence: setting only `VECTOR_STORE_PROVIDER=qdrant` (as the README suggests)
makes `retrieve()` still take the **in-memory** branch. To run the Qdrant path,
set `DENSE_VECTOR_STORE=qdrant` (or both). This split is owned by the Qdrant code
(NAT) and should be reconciled so the two agree.

Quick check of what is actually active:

```bash
python -c "from agentic_rag.integrations.local_pdf.providers import local_pdf_backend_status; print(local_pdf_backend_status())"
```

## Ownership boundaries (PICs)

| Area | PIC | Notes |
|---|---|---|
| SPLADE / ColBERT / listwise, in-memory N-way hybrid | **TesWy** | This document's main scope. |
| Qdrant vector store (`qdrant_hybrid_search`, config standardization, the env split above) | **NAT** | SPLADE/ColBERT not wired here. |
| `retrieve()` wiring / chunking / dedup | **hotran** | Sits between the two paths. |

## Phase 2 (deferred — needs coordination with NAT)

Make SPLADE / ColBERT / the N-way hybrid work on the Qdrant path:

1. Store SPLADE lexical weights as a Qdrant **named sparse vector** and ColBERT as
   a **multivector (MAX_SIM)** alongside the dense vector.
2. Rewrite `qdrant_hybrid_search` to multi-prefetch + RRF over the active legs.
3. Backfill existing documents into Qdrant from their stored chunks (read S3 →
   encode BGE-M3 → upsert Qdrant; **S3 is not modified**), following the pattern of
   `scripts/backfill_dedup.py`.
4. Fix `_qdrant_vector_store_enabled()` to use `resolve_vector_store_config()`.
