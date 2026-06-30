# Replacement Map

This file lists concrete `src` locations inspected after pulling `develop`, and
what should be replaced or extended there.

## 1. URL HTML Parsing and Markdown Extraction

### Current files

- `src/agentic_rag/ingestion/url/parser.py`
- `src/agentic_rag/ingestion/url/extractor.py`
- `src/agentic_rag/ingestion/url/loader.py`

### Replace or extend

- Replace duplicated HTML walking logic with a shared parser/DOM adapter layer.
- Keep `parser.py` focused on page metadata, assets, and readable sections.
- Keep `extractor.py` focused on Markdown extraction strategies.
- Move reusable DOM traversal helpers into `url/dom/` so `parser.py`,
  `extractor.py`, `blocks.py`, and `visual_semantics.py` do not each invent
  separate skip/tag rules.

### Why

There are several separate HTML walkers:

- `MainContentParser` in `parser.py`.
- `_DomMarkdownParser` and Playwright JS walkers in `extractor.py`.
- `_SemanticBlockParser` in `dom/blocks.py`.
- `_VisualSemanticsParser` in `dom/visual_semantics.py`.

They are useful, but the skip rules and interpretation rules can drift.

## 2. DOM and Entity Metadata

### Current files

- `src/agentic_rag/ingestion/url/dom/blocks.py`
- `src/agentic_rag/ingestion/url/dom/visual_semantics.py`
- `src/agentic_rag/ingestion/url/entities/extractor.py`
- `src/agentic_rag/ingestion/url/metadata/enrichment.py`

### Replace or extend

- Keep DOM block detection, but output one stable JSON shape for:
  `semantic_blocks`, `visual_semantics`, `entities`, and `product_specs`.
- Replace scattered scalar fields where possible with both:
  - compact scalar aliases for retrieval, such as `product_model`, `page_type`;
  - structured source facts, such as `product_specs`, `visual_semantics`.
- Add `entities_canonical` during ingestion or immediately after LLM enrichment.

### Why

Retrieval needs compact filterable fields, while debugging needs source-backed
facts. Mixing everything as ad hoc top-level metadata makes consumers fragile.

## 3. CSS and Visual Semantics

### Current files

- `src/agentic_rag/ingestion/url/dom/visual_semantics.py`
- `src/agentic_rag/ingestion/url/loader.py`
- `src/agentic_rag/ingestion/url/artifact.py`

### Replace or extend

- Keep the current regex extractor for simple cases:
  old prices, hidden text, generated labels.
- Add a CSS parser only if visual facts must cover external CSS, multiple
  selectors, or more complex pseudo-content.
- Preferred future package: `tinycss2`.
- Use Playwright computed styles when correctness matters more than speed.

### Why

Regex is fast and low-risk for inline style patterns. It is not a full CSS
parser and cannot resolve cascade, inheritance, media queries, or external CSS.

## 4. Shared Metadata Schema

### Current files

- `src/agentic_rag/ingestion/metadata/schema.py`
- `src/agentic_rag/ingestion/metadata/extract.py`
- `src/agentic_rag/ingestion/metadata/normalize.py`
- `src/agentic_rag/core/contracts.py`

### Replace or extend

- Replace the stub implementation in `normalize.py` with real normalization for:
  `source_type`, `document_type`, `language`, `product_model`, `entities`,
  `entities_canonical`, list fields, date aliases, and empty values.
- Add `entities_canonical` to `ChunkMetadata` if it is a first-class retrieval field.
- Reconcile `QDRANT_INDEX_FIELDS` with the fields actually indexed in
  `retrieval/search.py`.
- Decide whether `topic_tags` is live or dead. If dead, remove it from index plans.

### Why

`ChunkMetadata` is now the shared contract, but normalization is still mostly a
stub. This makes producers and consumers responsible for cleanup individually.

## 5. Storage and Index Payloads

### Current files

- `src/agentic_rag/integrations/local_pdf/storage.py`
- `src/agentic_rag/integrations/local_pdf/providers.py`
- `src/agentic_rag/retrieval/search.py`

### Replace or extend

- Write `[P]` metadata first, then write `[L]` metadata after LLM enrichment.
- After enrichment, update both source storage and dense/vector payloads.
- Ensure Qdrant payload indexes are derived from the shared schema, not a second
  hard-coded list.
- Ensure `entities_canonical` is backfilled before enabling Qdrant entity filter.

### Why

The current storage flow is close, but index field definitions exist in multiple
places. That makes it easy to store a useful field that retrieval never indexes.

## 6. Retrieval Consumers

### Current files

- `src/agentic_rag/retrieval/search.py`
- `src/agentic_rag/retrieval/boosting.py`
- `src/agentic_rag/retrieval/evidence_metadata.py`
- `src/agentic_rag/agent/nodes.py`
- `src/agentic_rag/integrations/local_pdf/providers.py`

### Replace or extend

- Keep entity hard-filter only for Qdrant and only with safe fallback to unfiltered search.
- Wire `quality_score`, `retrieval_weight`, and `trusted_for_retrieval` into boosting
  after evaluation proves they help.
- Make question-index results survive agent path fusion if the experiment is enabled.
- Add pipeline traces showing which metadata signals affected rank.

### Why

Metadata should be observable. If a result is filtered, boosted, demoted, or
excluded because of metadata, the trace should say so.

