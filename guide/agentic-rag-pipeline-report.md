# Agentic RAG Pipeline Report

Date: 2026-06-11

Scope: this report summarizes the current `src/agentic_rag` package so the next
research pass can start from a clear map of the runtime pipeline.

## Executive Summary

`agentic_rag` is organized around a contract-first RAG pipeline:

1. Sources are uploaded through the API as PDF, URL, or raw text.
2. Ingestion converts those sources into shared `Chunk` objects.
3. A source provider stores raw/parsed/chunked data and optionally writes dense
   vectors to a vector backend.
4. Retrieval combines lexical BM25, dense search, optional hybrid Qdrant search,
   fusion, score thresholds, and reranking.
5. Generation builds a grounded evidence context and produces an answer with
   validated citations.
6. Optional agent mode wraps retrieval and answer generation in a LangGraph-style
   workflow.
7. Evaluation and observability modules record traces, review runs, and quality
   metrics.

The most important design point is that the internal pipeline is centered on
shared contracts in `agentic_rag.core.contracts`. Ingestion modules, retrieval,
generation, and integrations should exchange those contracts instead of private
module-specific shapes.

## High-Level Flow

```text
FastAPI / UI / scripts
        |
        v
agentic_rag.api
        |
        +-- /sources/upload  -> PDF ingestion
        +-- /sources/url     -> URL ingestion
        +-- /sources/text    -> text ingestion
        |
        v
SourceEvidenceProvider
        |
        +-- LocalPdfEvidenceProvider
        |       |
        |       +-- ingestion/pdf
        |       +-- ingestion/url
        |       +-- ingestion/chunking
        |       +-- local JSONL / Postgres / S3 source store
        |       +-- TurboVector / pgvector / Qdrant dense index
        |
        +-- RAGFlow provider
        |
        v
retrieval/search.py
        |
        +-- query preprocessing
        +-- BM25 lexical search
        +-- dense search
        +-- optional Qdrant hybrid search
        |
        v
retrieval/fusion.py
        |
        +-- threshold filtering
        +-- RRF / weighted RRF / normalized-score fusion
        +-- reranking
        +-- evidence context construction
        |
        v
generation/answering.py
        |
        +-- grounded prompt
        +-- LLM or deterministic fallback
        +-- citation validation
        |
        v
Answer
```

## Core Contracts

The shared models live in `src/agentic_rag/core/contracts.py`. They are strict
Pydantic models and are the main compatibility layer between modules.

Key contracts:

- `Chunk`: the canonical unit produced by ingestion and consumed by retrieval.
  It carries `id`, `text`, `source`, optional `page`, optional `section`, and
  free-form `metadata`.
- `SearchResult`: a retrieved chunk plus score, rank, retriever name, and
  metadata.
- `Citation`: a citation attached to an answer.
- `Answer`: generated answer text, status, citations, confidence, and metadata.
- `WorkflowRunInput` / `WorkflowRunOutput`: request and response shapes for
  answer workflows.
- `RetrievalInput` / `RetrievalOutput`: retrieval-stage request and result.
- `EvidenceResolutionInput` / `EvidenceResolutionOutput`: evidence-building
  interface.
- `SourceDocumentUpload` / `SourceDocumentChunks`: source ingestion contracts.
- `LLMCompletionInput` / `LLMCompletionOutput`: model runtime contract.
- `EmbeddingInput` / `EmbeddingOutput`: embedding runtime contract.
- `RerankInput` / `RerankOutput`: reranking runtime contract.

The port protocols live in `src/agentic_rag/core/ports.py`. Important ports are:

- `PdfIngestor`
- `UrlIngestor`
- `SourceEvidenceProvider`
- `BM25Searcher`
- `DenseSearcher`
- `HybridFusion`
- `LLMClient`
- `EmbeddingClient`
- `Reranker`
- `Generator`
- `WorkflowRunner`
- `EvidenceResolver`

Research implication: any new feature should first decide which contract it
extends. If it cannot be expressed through `Chunk`, `SearchResult`, `Answer`, or
provider ports, the feature probably needs a contract update before
implementation.

## API Entry Points

The application entry point is `src/agentic_rag/app.py`, which runs
`agentic_rag.api:api` with Uvicorn.

`src/agentic_rag/api.py` owns the public FastAPI surface:

- `GET /health`: service health and active evidence backend.
- `POST /answer`: non-streaming question answering.
- `POST /answer/stream`: streaming answer generation.
- `POST /sources/upload`: upload a PDF/source document.
- `POST /sources/url`: ingest a URL.
- `POST /sources/text`: ingest raw text as a source.
- `GET /sources`: list known sources.
- `GET /sources/{document_id}/chunks`: inspect chunks for a source.
- `GET /sources/{document_id}/debug`: inspect debug information.
- `GET /sources/{document_id}/raw`: inspect raw source content.
- `DELETE /sources`: clear sources.
- `DELETE /sources/{document_id}`: delete one source.

The API chooses the evidence backend using `EVIDENCE_PROVIDER`:

- `local_pdf`: local source provider. Despite the name, this handles PDF, URL,
  and text ingestion.
- `ragflow`: RAGFlow-backed provider.
- `request`: request-provided evidence chunks.
- `mock`: deterministic mock evidence.

Important behavior:

- `AGENT_MODE=true` routes `/answer` through the agent workflow.
- When `AGENT_MODE` is false, `/answer` retrieves evidence and calls generation
  directly.
- URL upload through `local_pdf` uses the URL ingestion pipeline.
- URL upload through `ragflow` uses a simpler HTML-to-text path before upload.
  That means URL behavior can differ substantially by `EVIDENCE_PROVIDER`.

## Runtime Configuration

`src/agentic_rag/model_runtime/config.py` and
`src/agentic_rag/model_runtime/factory.py` own model configuration.

Model roles:

- `query_rewrite`
- `query_transform`
- `generation`
- `ingestion`
- `evaluation`

Main model runtime behavior:

- LLM clients are created through LiteLLM when a role has a configured provider.
- If the LLM provider is `none`, generation can fall back to deterministic
  evidence summarization.
- Embeddings default to
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Reranking defaults to a simple score reranker unless a model provider is
  configured.
- Sentence-transformers can be used for embeddings and reranking, but it is not
  treated as an LLM provider.

Research implication: model role separation is already present, so future work
can tune query rewriting, generation, ingestion parsing, and evaluation
independently.

## Ingestion Pipeline

The ingestion package has four important areas:

- `ingestion/pdf`
- `ingestion/url`
- `ingestion/chunking`
- `ingestion/dedup_detect`

### Shared Chunking

`src/agentic_rag/ingestion/chunking` contains shared Markdown-oriented chunking
tools:

- Markdown section parsing.
- Deterministic chunking.
- Section-aware chunk candidates.
- Shared output shapes used by PDF and URL ingestion.

This is the preferred location for common chunking behavior. URL-specific or
PDF-specific code should stay in their own modules only when the behavior is
truly source-specific.

### PDF Ingestion

`src/agentic_rag/ingestion/pdf` is Markdown-first.

Main flow:

```text
PDF file
  -> parser pipeline
  -> parsed Markdown
  -> chunker
  -> Chunk list
  -> optional artifacts
```

Current parser strategy:

- `ocr/docling` is the default registered pipeline.
- `vlm/mineru` is registered as a future seam but is not wired as an installed
  runtime path.

Chunker choices include:

- deterministic Markdown chunker.
- Docling page-aware chunker.
- Docling hybrid chunker with fallback behavior.

Artifacts can include:

- `parsed.md`
- `chunks.jsonl`
- `chunks.md`
- `manifest.json`
- multimodal assets when available.

### URL Ingestion

`src/agentic_rag/ingestion/url` turns a URL, HTML string, or text into chunks.

Main public functions:

- `load_url_chunks()`
- `load_url_with_artifacts()`
- `load_html_chunks()`
- `load_html_with_artifacts()`
- `load_text_chunks()`

Main flow:

```text
URL
  -> browser extractor attempt
  -> static fetch fallback
  -> DOM / Trafilatura / builtin parser fallback
  -> Markdown normalization
  -> URL-aware chunking
  -> Chunk list
  -> optional artifacts
```

The browser extractor uses Playwright/Chromium behavior:

- Vietnamese locale and headers.
- Browser-like user agent.
- Cloudflare/loading wait helpers.
- Scrolling.
- Accordion/tab expansion.
- DOM text extraction.
- product/spec/price extraction from rendered DOM.

Static/fallback parsing uses:

- BeautifulSoup DOM extraction.
- optional Trafilatura.
- builtin parser for title, headings, paragraphs, lists, metadata, and assets.

URL metadata can include:

- `url`
- `domain`
- `original_url`
- `canonical_url`
- `language`
- `author`
- `published_at`
- `page_type`
- `is_product`
- assets and artifact paths.

Current limitation:

- The current URL package is stronger for one page than for full site crawling.
  Child-page discovery and selector-style multi-URL ingestion should be treated
  as a feature layer on top of the current single-URL ingestion path.

### Text Ingestion

Raw text upload is handled through the local evidence provider and shared
chunking. It is the simplest source path:

```text
text
  -> chunking
  -> Chunk list
  -> source store
  -> optional dense index
```

### Duplicate Detection

`src/agentic_rag/ingestion/dedup_detect` is a detection-oriented package for
duplicate and near-duplicate analysis.

Intended layers:

1. Exact duplicate detection with SHA-256 of normalized text.
2. Near-duplicate detection with SimHash.
3. Semantic similarity through the shared embedding runtime configuration.
   The relevant environment variables are the existing `EMBEDDING_*` values from
   `.env.example`, for example `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`,
   `EMBEDDING_API_BASE`, `EMBEDDING_API_KEY`, `EMBEDDING_DIMENSIONS`, and
   `EMBEDDING_TIMEOUT_SECONDS`.

If OpenAI embeddings are used, they should be configured through the same
embedding provider/key variables used by retrieval.

Current research note:

- This package should remain detection-only unless an explicit auto-merge or
  auto-delete policy is later designed.
- The main ingestion upload path should expose duplicate metadata before it
  attempts any destructive resolution.
- `.env.example` currently shows the sentence-transformers embedding defaults:
  `EMBEDDING_PROVIDER=sentence_transformers` and
  `EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
  For OpenAI or another API-based embedding provider, use the same
  `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_API_BASE`, and
  `EMBEDDING_API_KEY` contract instead of adding dedup-only variables.

## Local Source Provider

`src/agentic_rag/integrations/local_pdf/providers.py` is the main local evidence
provider. The name is historical: it handles PDF, URL, and text sources.

Upload responsibilities:

- Validate source input.
- Call the correct ingestion loader.
- Persist raw source, parsed Markdown, chunks, and manifest.
- Upsert dense embeddings when a persistent vector backend is configured.
- Return upload metadata and traces.

Retrieval responsibilities:

- Load chunks from the selected source set.
- Build or read lexical and dense indexes.
- Run BM25 and dense retrieval.
- Apply threshold gates.
- Fuse results.
- Rerank results.
- Attach pipeline trace metadata.

Storage options:

- Local JSONL files.
- Postgres-backed source store.
- S3-backed source store.

Vector options:

- TurboVector in-memory/local flow.
- pgvector search path.
- Qdrant hybrid/dense path.

Research implication: if URL ingestion improves but `/answer` still behaves
poorly, inspect `LocalPdfEvidenceProvider.retrieve()` next. The issue may be
thresholding, fusion, reranking, or selected-source filtering rather than
ingestion.

## Retrieval Pipeline

`src/agentic_rag/retrieval/search.py` owns query preprocessing and base search.

Main stages:

1. Normalize/query preprocess.
2. Optional LLM-assisted query transform.
3. BM25 lexical retrieval.
4. Dense embedding retrieval.
5. Optional Qdrant hybrid retrieval.
6. Merge results for decomposed queries.

`src/agentic_rag/retrieval/fusion.py` owns later ranking support:

- Reranking with configured reranker.
- Score-reranker fallback when model runtime fails.
- Evidence context construction for generation.

Fusion strategies are exposed through retrieval modules:

- Reciprocal rank fusion.
- Weighted reciprocal rank fusion.
- Normalized score fusion.

Threshold configuration supports filtering at multiple stages:

- pre-fusion thresholding.
- post-fusion thresholding.
- rerank thresholding.

Research implication: retrieval quality depends heavily on metadata and chunk
structure. Better URL/PDF chunking improves both lexical and dense retrieval.

## Generation Pipeline

`src/agentic_rag/generation/evidence.py` selects evidence.

Evidence priority:

1. Explicit request evidence chunks.
2. Configured source provider retrieval.
3. Mock evidence only when explicitly enabled.
4. Empty evidence.

`src/agentic_rag/generation/answering.py` creates the final answer.

Main safeguards:

- Empty question produces a `needs_clarification` style response.
- Empty evidence produces a not-found answer.
- Very short evidence contexts are guarded against.
- The prompt tells the model to answer only from evidence.
- Citations are validated against retrieved chunk metadata.
- The generator can fall back to deterministic answer construction if no LLM is
  configured.

Citation metadata can use:

- source
- page
- section
- URL
- chunk ID

Research implication: if the source chunks are messy, generation may still cite
them correctly but produce confusing answers. Chunk quality and citation quality
are tightly coupled.

## Optional Agent Workflow

The API supports an optional agentic path behind `AGENT_MODE=true`.

At a high level, the agent package contains:

- graph assembly.
- workflow state.
- node implementations.
- grading logic.
- node-level contracts.

The expected path is:

```text
question
  -> retrieve evidence
  -> grade/check evidence
  -> answer or route/fallback
  -> final workflow output
```

Research implication: agent mode should be evaluated separately from direct RAG
mode. Otherwise it is hard to know whether a quality issue comes from retrieval,
evidence grading, answer generation, or graph routing.

## Evaluation And Review

The evaluation package provides:

- metrics.
- evaluation runners.
- RAGAS integration.
- review endpoints/tools.

The broader package also includes `autodata_eval`, which has database models,
router code, worker logic, run recovery, and configuration snapshots.

Practical evaluation flows:

- Run ingestion on a known source.
- Inspect artifacts and chunks.
- Ask fixed evaluation questions.
- Score answer groundedness, answer relevance, citation quality, and retrieval
  quality.
- Compare outputs across branches or ingestion strategies.

Research implication: the URL ingestion demo and evaluation scripts should share
the same ingestion path. If a script and browser demo produce different chunks,
the first suspect is configuration or provider path mismatch, not the crawler
itself.

## Observability

`src/agentic_rag/observability` provides trace writing.

The API records:

- answer traces.
- source upload traces.
- local provider pipeline metadata.

Trace data is important for diagnosing:

- which provider was used.
- which sources were selected.
- how many chunks were available.
- which retrievers contributed results.
- which fusion/rerank thresholds were applied.
- why generation returned not-found.

Research implication: for future URL work, every crawl attempt should emit
machine-readable diagnostics: extractor used, failure reason, content length,
chunk count, quality-gate result, and artifact paths.

## Current Pipeline Risks

### URL Provider Split

`EVIDENCE_PROVIDER=local_pdf` and `EVIDENCE_PROVIDER=ragflow` do not ingest URLs
the same way. The local provider uses the URL ingestion package; the RAGFlow path
uses a simpler HTML-to-text path.

Research question: should RAGFlow URL upload also reuse the local URL parser
before pushing text to RAGFlow?

### URL Dynamic Page Reliability

The URL extractor has Playwright support, static fallback, DOM parsing,
Trafilatura, and builtin parsing. However, messy React/SPA pages can still return
visually correct pages with poor extracted text.

Research questions:

- How should the extractor detect "visual content exists but text extraction is
  low quality"?
- Should screenshots, accessibility snapshots, rendered DOM text, and network
  JSON payloads be compared as separate evidence channels?
- Should product/spec tables become structured records before Markdown
  generation?

### Chunk Structure

Some URL chunks can merge unrelated product rows, prices, specs, and CTA text.
This harms retrieval and generation because the chunk is technically full of
useful tokens but semantically unclear.

Research questions:

- Should URL chunking preserve page sections, cards, tables, and product grids as
  separate structural units?
- Should crossed-out/current prices be represented explicitly as
  `original_price` and `discount_price` metadata?
- Should low-signal chunks be split or downranked before indexing?

### Duplicate Detection Integration

Duplicate detection exists as a package, but the main source upload path should
still be reviewed for end-to-end integration.

Research questions:

- Should duplicate metadata be attached per chunk, per source, or both?
- Should exact and near-duplicate groups be exposed in API debug endpoints?
- Should conflict detection be separate from duplicate detection?

### Provider Naming

`LocalPdfEvidenceProvider` now handles more than PDFs. This is understandable
historically but confusing for future work.

Research question: should it eventually become `LocalSourceEvidenceProvider`
while preserving compatibility aliases?

### Query Transform Contract

The retrieval preprocessor has LLM-assisted query transformation behavior. This
area should be checked carefully against the current `LLMClient` protocol before
expanding it.

Research question: should query rewriting and decomposition use typed
`LLMCompletionInput` everywhere?

## Recommended Research Map

Use this order for further research:

1. URL ingestion quality
   - rendered DOM extraction.
   - accessibility tree extraction.
   - product/spec structured extraction.
   - price/status normalization.
   - child URL discovery.

2. Chunk quality
   - structural chunking.
   - semantic parent-child chunks.
   - low-signal chunk detection.
   - metadata-rich product chunks.

3. Duplicate and conflict detection
   - exact duplicates.
   - near duplicates.
   - semantic duplicates.
   - same-entity conflicting facts.

4. Retrieval tuning
   - BM25 versus dense contribution.
   - fusion weights.
   - rerank thresholds.
   - source filtering.

5. Evaluation
   - branch comparison.
   - source-level chunk quality scoring.
   - answer-level groundedness scoring.
   - citation correctness.

## Suggested Guide Files To Add Next

These would make the guide folder easier to use as a research workspace:

- `guide/research/url-rendered-dom-extraction.md`
- `guide/research/url-structured-product-markdown.md`
- `guide/research/chunk-quality-gates.md`
- `guide/research/dedup-detect-integration-plan.md`
- `guide/research/conflict-detection-for-rag-sources.md`
- `guide/research/retrieval-threshold-tuning.md`
- `guide/research/evaluation-dataset-design.md`

## Fast Debug Checklist

When a URL or document gives poor answers:

1. Check source upload trace.
2. Check `parsed.md`.
3. Check `chunks.jsonl`.
4. Check chunk count and low-signal chunks.
5. Check duplicate metadata if available.
6. Check dense embedding/index status.
7. Check retrieval trace: BM25 hits, dense hits, fusion result, rerank result.
8. Check evidence context sent to generation.
9. Check final citations.
10. Compare direct RAG mode and `AGENT_MODE=true` separately.

## Bottom Line

The project already has a solid contract-first RAG spine. The highest-leverage
next research is not a new end-to-end pipeline; it is improving the quality of
what enters the existing contracts:

- cleaner URL extraction.
- more structural Markdown.
- richer chunk metadata.
- duplicate/conflict detection.
- traceable quality gates.

Once those source-side improvements are stable, retrieval and generation should
benefit without requiring a large rewrite of the rest of the system.
