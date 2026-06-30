# Agentic RAG Metadata Filtering TODO

This TODO is written from the URL ingestion folder because the need appeared
there first, but the design is meant for all of `src/agentic_rag`.

Metadata filtering should be shared across URL, PDF, retrieval, generation,
evaluation, and future ingestion sources. Source-specific packages can add
adapters and rules, but the contract should not be URL-only.

## Goal

Metadata filtering should help the pipeline keep the right chunks at the right
time:

```text
Query
  -> Pre-filter
  -> Vector Search
  -> Post-filter
  -> Reranking
  -> LLM
```

1. `pre-filter`: query-time metadata constraints applied before vector search.
2. `post-filter`: query-aware filtering after vector search and before
   reranking.

Quality goal:

- avoid searching irrelevant sources when the query gives clear constraints,
- preserve source evidence and citation metadata,
- support exact source/document/entity filtering for retrieval,
- remove weak candidates before reranking,
- keep generation grounded in chunks with valid metadata.

Note: source cleanup before indexing is still useful, but it is ingestion
hygiene, not the common RAG meaning of metadata pre-filter.

## Recommended Shared Folder Location

Create shared filtering contracts and generic rules under:

```text
src/agentic_rag/metadata_filtering/
  __init__.py
  schemas.py
  pre_filter.py
  post_filter.py
  rules.py
  query_constraints.py
  vector_filters.py
  trace.py
```

Reason:

- Metadata filtering is cross-source. URL and PDF chunks both flow into the
  same `Chunk`, `SearchResult`, `Citation`, and `Answer` contracts.
- Retrieval/generation should not import URL-private modules to filter
  evidence.
- Shared filtering can enforce common metadata fields such as `source`,
  `source_type`, `document_type`, `document_id`, `url`, `file_name`, `page`,
  `section`, `language`, `created_date`, and `updated_date`.

## Source-Specific Adapter Locations

Keep source-specific rules close to each ingestion package, but expose them
through the shared filtering contract.

Recommended source adapters:

```text
src/agentic_rag/ingestion/url/metadata/filtering/
  __init__.py
  rules.py
  adapter.py

src/agentic_rag/ingestion/pdf/metadata/filtering/
  __init__.py
  rules.py
  adapter.py
```

URL adapter examples:

- navigation/footer/cookie/support CTA noise,
- dynamic JavaScript provenance,
- product/spec metadata,
- asset references such as images and PDF links.

PDF adapter examples:

- OCR noise,
- repeated headers/footers,
- page-number artifacts,
- table row/header preservation,
- source modified date and page citation fields.

## Optional Test And Evaluation Locations

Shared tests:

```text
tests/metadata_filtering/
  test_pre_filter.py
  test_post_filter.py
  test_query_constraints.py
```

Source-specific tests:

```text
src/agentic_rag/ingestion/url/tests/test_metadata_filtering.py
src/agentic_rag/ingestion/pdf/tests/test_metadata_filtering.py
```

Evaluation helpers:

```text
src/agentic_rag/evaluation/metadata_filtering.py
```

## Step 1: Pre-Filter

Pre-filter runs after the user query is received and before vector search. It
turns query constraints into metadata filters for the vector store, sparse
store, or hybrid retrieval layer.

Primary purpose:

- reduce the search space before retrieval,
- search only relevant source/document/entity slices when the query is clear,
- keep vector search fast and precise,
- avoid pulling in chunks that are impossible matches by metadata,
- keep fallback broad search when the query is ambiguous.

Suggested shared input:

```python
{
    "query": str,
    "document_ids": list[str] | None,
    "available_metadata_schema": dict,
    "source_kind": "url | pdf | text | unknown | mixed",
}
```

Suggested shared output:

```python
{
    "query": str,
    "query_constraints": dict,
    "vector_filter": dict | None,
    "fallback_to_unfiltered": bool,
    "filter_stage": "pre_filter",
    "trace": dict,
}
```

Shared pre-filter TODO:

1. Extract metadata constraints from the query:
   - `document_ids`
   - `source_type`
   - `document_type`
   - `language`
   - `product_model` / `entity_name`
   - `section` / `page`
   - `created_date` / `updated_date` ranges when explicitly asked
2. Build vector-store filter payloads from constraints.
3. Support provider-specific filter translation:
   - Qdrant filter syntax,
   - pgvector/LangChain metadata filter syntax,
   - local in-memory fallback filter.
4. Use only high-confidence constraints before vector search.
5. Fall back to unfiltered search when constraints are ambiguous or would
   return zero candidates.
6. Keep a trace explaining every filter:
   - extracted constraint,
   - confidence,
   - vector filter expression,
   - fallback reason.
7. Never pre-filter away possible evidence based only on low-confidence LLM
   inference.
8. Exclude debug-only ingestion artifacts by default:
   - `metadata_prefilter_exclude == true`,
   - `retrieval_visibility == "debug_only"`,
   - `chunk_type == "visual_debug"`,
   - `chunk_type == "interaction_debug"`,
   - `semantic_application_status == "unmapped"`,
   unless the user query or UI mode explicitly asks for ingestion/debug/review
   artifacts.

URL-specific pre-filter TODO:

1. Convert URL query hints into filters:
   - exact URL/domain,
   - `document_type` such as policy, FAQ, article, product page, booking flow,
   - `product_model` such as `VF 8`, `VF8`, `VF 9`, `Klara`, or `Evo`,
   - `section_kind` when query asks about dynamic/static facts.
2. Use dynamic filters only when the query asks about selected variant, color,
   configuration, price after selection, image state, or availability.
3. Prefer source-backed section origins when pre-filtering dynamic URL chunks:
   - `source_data_static`
   - `source_data_rendered`
   - `dynamic_interaction`
   - `dynamic_state_payload`
4. Do not pre-filter to `generated_artifact` chunks unless the query is about
   review/debug artifacts.
5. Preserve `requested_url` and query params when they identify page state.
6. Keep visual fallback chunks available for demos and audits, but exclude them
   from normal RAG retrieval. The relevant semantic chunk must carry the
   source-backed value, for example `Original price ~~1.699.000.000 VND~~`,
   plus metadata such as `visual_semantics`, `original_price`, `css_evidence`,
   and `trusted_for_retrieval=true`.
7. Keep raw JavaScript/interaction capture chunks available for demos and
   audits, but exclude them from normal RAG retrieval. They should use
   `chunk_type=interaction_debug`, `retrieval_visibility=debug_only`,
   `metadata_prefilter_exclude=true`, and `trusted_for_retrieval=false`.
8. Only allow interaction-derived facts into normal retrieval after applying
   them to a relevant semantic chunk with
   `semantic_application_status=applied_to_semantic_chunk`,
   `retrieval_visibility=normal`, and `trusted_for_retrieval=true`.

PDF-specific pre-filter TODO:

1. Convert PDF query hints into filters:
   - `file_name`,
   - `document_type`,
   - `page` / `page_number`,
   - `section` / `heading`,
   - `language`.
2. Use page filters only when the user explicitly asks for a page or the UI
   passes page scope.
3. Avoid filtering out OCR-derived chunks unless query constraints are exact.

## Step 2: Post-Filter

Post-filter runs after vector search returns `SearchResult` candidates and
before reranking. Reranking should work on a cleaner candidate set.

Primary purpose:

- improve precision for the user query,
- enforce metadata constraints inferred from the query,
- remove irrelevant chunks pulled in by lexical/dense retrieval,
- keep citations grounded and source-appropriate.

Recommended shared implementation:

```text
src/agentic_rag/metadata_filtering/post_filter.py
```

Integration points:

```text
query
  -> metadata_filtering.pre_filter
  -> vector search
  -> metadata_filtering.post_filter
  -> rerank
  -> build_evidence_context()
  -> generation
```

Do not hard-code URL-only logic inside shared retrieval. Use source adapters or
rule registries.

Post-filter TODO:

1. Infer query constraints:
   - source type, such as official/internal/partner/news/community,
   - document type, such as manual, FAQ, policy, article, spec sheet,
   - product/entity name,
   - fact type, such as price, date, warranty, range, battery, page section,
   - language.
2. Prefer exact metadata matches over broad chunks.
3. Prefer source-backed chunks over generated review chunks.
4. Remove or downrank chunks whose `entity_name`, `product_model`,
   `document_type`, or `language` conflicts with inferred query constraints.
5. Downrank low `retrieval_weight` chunks and chunks with high noise labels.
6. Keep at least one broader page/section chunk when it helps explain exact
   evidence, but do not let it replace exact fact chunks.
7. Prefer exact `spec_fact`, table row, page, or section matches before broad
   overview chunks.
8. Preserve citation-critical metadata through the final evidence list.

Suggested output:

```python
{
    "results": list[SearchResult],
    "post_filter_trace": {
        "query_constraints": {},
        "removed": [],
        "downranked": [],
        "kept": [],
    },
}
```

## Shared Metadata Fields Used By Filters

Required or highly useful across source types:

- `source`
- `source_type`
- `document_type`
- `document_id`
- `url`
- `file_name`
- `page`
- `section`
- `section_path`
- `heading`
- `language`
- `created_date`
- `updated_date`
- `chunk_type`
- `entity_type`
- `entity_name`
- `product_model`
- `attribute_group`
- `product_specs`
- `retrieval_weight`
- `is_noise`
- `filter_labels`

URL-specific fields:

- `requested_url`
- `canonical_url`
- `final_url`
- `section_kind`
- `section_origin`
- `evidence_source`
- `interaction_step`
- `artifact_ref`
- `llm_fallback_used`
- `llm_evidence_refs`

PDF-specific fields:

- `page_number`
- `ocr_confidence`
- `table_id`
- `row_id`
- `source_modified_date`
- `parser`

## Pass Criteria

- Shared filters work with `Chunk` and `SearchResult`, not URL-private models.
- URL and PDF can add source-specific rules without changing shared contracts.
- Ingestion hygiene can mark or downrank noise before indexing, but common
  `pre-filter` means query-time metadata filtering before vector search.
- Pre-filter creates safe query-time metadata filters before vector search.
- Post-filter improves candidates before reranking without hiding necessary
  context.
- Dynamic URL chunks are used only when provenance supports the query.
- PDF citations keep page/source metadata intact.
- Filter traces explain why chunks were kept, removed, or downranked.
