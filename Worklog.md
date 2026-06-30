# Worklog

## 2026-06-26 - GraphRAG Presentation Showcase Creation

### Completed

- **Created GraphRAG Interactive Presentation**:
  - Developed [presentation_graphrag.html](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/presentation_graphrag.html) to showcase the end-to-end GraphRAG design in this workspace.
  - Styled with a premium dark cyber theme (neon green/blue/purple gradients, custom Outfit/monospace fonts, glassmorphism card panels, slide progress indicator, and responsive grid layouts).
  - Built a live interactive Graph Simulator in JavaScript/CSS directly inside Slide 4. Users can click buttons to simulate **1-Hop** (direct neighbors) and **2-Hop** BFS expansion starting from a seed entity node (`VF 8`), showing how the graph dynamically connects entities like `PIN LFP`, `SẠC 7.4KW`, `CATL`, etc.
  - Documented Offline KG Construction including LLM structured relation extraction (`(head, relation, tail, strength)` payload) fallback to Co-occurrence graph from `entities_canonical` in chunks, normalized via `normalize_entity()`.
  - Documented Online Graph-Enhanced Retrieval using BFS expansion inside `_entity_prefilter_for()`, fused via RRF (Reciprocal Rank Fusion) with BM25 and Dense Qdrant/pgvector search pathways, and reranked using Cross-Encoders.
  - Outlined RAG Integration and Guardrails (LangGraph, Citation validation, LLM-as-judge evaluation, and future roadmap containing HippoRAG PPR and Leiden community clustering).

### Verification
- Verified HTML structure and interactive script execution on browser.

## 2026-06-25 - GraphRAG System Integration & Reference Documentation

### Completed

- **System Reference Manual & Setup Guides**:
  - Authored [manual.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/docs/manual.md) to serve as the blueprint reference manual for the hybrid GraphRAG + RAG system, detailing directory structures, ingestion block-diagrams, and frontend nav paths.
  - Developed [neo4j-setup-guide.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/docs/neo4j-setup-guide.md) mapping out Docker local deployments, Neo4j Desktop configurations, AuraDB Cloud instance options, and Python connector configurations.
- **GraphStore Implementation**:
  - Built the core [graph_store.py](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/src/agentic_rag/retrieval/graph_store.py) backend.
  - Implemented dual backends: Local JSON adjacency list (`storage/local_pdf/graph_store.json`) and scalable Neo4j Graph Database Bolt connection (`neo4j` Python driver).
  - Programmed relationship extraction matching: reads chunk metadata `relations` list (populated by LLM parser) or automatically builds fallback co-occurrence edges between entities in `entities_canonical`.
  - Implemented BFS neighbors lookup `get_neighbors(seeds, max_depth)` to traverse connections in real-time.
  - Created Neo4j sync script in `scripts/sync_to_neo4j.py` to synchronize ingested vector storage items into Neo4j nodes/relationships.
- **Retrieval and Boosting Integration**:
  - Integrated `_entity_prefilter_for` query expansion in [search.py](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/src/agentic_rag/retrieval/search.py) to automatically load `GraphStore` neighbors and expand seed filters.
  - Mapped toggles (`RETRIEVAL_GRAPH_ENABLED` and `RETRIEVAL_GRAPH_HOPS`) inside retrieve nodes of LangGraph.
  - Created [boosting.py](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/src/agentic_rag/retrieval/boosting.py) for metadata trust score adjustments.

### Verification
- Verified local unit tests and database connection connectivity.

## 2026-06-22 - Rule-Based Metadata and V2 Deduplication / LLM Review

### Completed

- **L2 Metadata Blocking and LLM Review Layer**:
  - Implemented L2 metadata-based blocking and LLM-assisted duplicate review (`metadata_llm` layer) in [pipeline.py](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/src/agentic_rag/ingestion/dedup_detect/pipeline.py).
  - Structured metadata key construction ([metadata_block_key](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/src/agentic_rag/ingestion/dedup_detect/blocking/keys.py#L37)) using static and dynamic block fields (e.g., `source_type`, `document_type`, `domain`, `product_model`, `language`, `scope_type`, `attribute_group`).
  - Introduced [DuplicateReview](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/src/agentic_rag/ingestion/dedup_detect/models.py#L67) model to represent conservative L2 classification with confidence, reason, compared metadata fields, evidence refs, and pair categories (e.g., cross-model, same-state-replay, sibling-state).
  - Added a state-guard review ([_state_guard_review](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/src/agentic_rag/ingestion/dedup_detect/llm_review/reviewer.py#L74)) to deterministically identify non-duplicates based on critical dynamic-state differences (e.g., `edition_id`, `exterior_id`, `surcharge`, etc.) or same-state replays.
- **Shared Ingestion Metadata Normalization**:
  - Upgraded shared metadata schemas and normalization in [normalize.py](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/src/agentic_rag/ingestion/metadata/normalize.py).
  - Ensured that standard required fields (`source_type`, `updated_date`) are properly populated and validated across PDF and URL loaders.
- **RAG Ingestion and Retrieval Enhancements**:
  - Integrated question-index contribution tracing and Qdrant index fields.
  - Excluded debug-only chunks from local retrieval and optimized metadata pre-filtering.

### Verification

```powershell
uv run pytest -q
```

### Current Status

- All unit and integration tests pass: 560 passed.
- Robust, conservative L2 deduplication layer with deterministic state guards and LLM review integration is complete and tested.

## 2026-06-19 - Crawlee Renderer for Ill-Structured URL Pages

### Completed

- Added optional `crawlee[playwright]` support under the `crawling` extra.
- Added a Crawlee-backed Playwright extractor that returns the existing
  `ExtractedMarkdown` contract, including rendered HTML, final URL, product
  tables, and embedded JSON hydration.
- Updated render options to allow `timeout_seconds=None` for explicit
  unbounded Crawlee runs while still validating positive bounded timeouts.
- Routed render-required URL profiles through Crawlee first, then direct
  Playwright fallback if Crawlee is unavailable or fails.
- Added sleep/retry settling for slow or inactive configurators. When
  `timeout_seconds` is set, each sleep is bounded by the remaining budget.
- Added focused tests for unbounded render options and Crawlee-first loader
  selection.

### Verification

```powershell
uv run ruff format src/agentic_rag/ingestion/url/extractor.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/url/rendering/browser.py src/agentic_rag/ingestion/url/tests/test_acquisition_rendering_quality.py src/agentic_rag/ingestion/url/tests/test_loader.py
uv run ruff check src/agentic_rag/ingestion/url/extractor.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/url/rendering/browser.py src/agentic_rag/ingestion/url/rendering/__init__.py src/agentic_rag/ingestion/url/tests/test_acquisition_rendering_quality.py src/agentic_rag/ingestion/url/tests/test_loader.py
uv run pytest src/agentic_rag/ingestion/url/tests/test_acquisition_rendering_quality.py src/agentic_rag/ingestion/url/tests/test_loader.py -q
```

### Current Status

- Focused rendering and loader tests pass: 36 passed.
- Ruff check passes for the touched URL rendering files.
- Existing Pydantic serializer warnings for flexible chunk metadata still appear.
- Live VF 9 verification still needs to be rerun with the optional `crawling`
  extra installed.

## 2026-06-19 - VF 9 Configurator DOM Entity Extraction

### Completed

- Preserved configurator `data-*` attributes on semantic DOM blocks, including
  values such as `data-price-value` and `data-bs-target`.
- Added primary page entity inference from title, path, and query parameters
  such as `modelId=Products-Car-VF9`.
- Filtered semantic DOM blocks against the primary model before structure-aware
  Markdown and entity extraction, reducing cross-sell model promotion.
- Extended product spec extraction with nested `editions` and `colors` while
  keeping existing flat shortcut fields for retrieval compatibility.
- Added embedded JSON state hydration for `application/json` and `__NEXT_DATA__`
  scripts, rendering edition pricing into stable Markdown tables.
- Added a BeautifulSoup helper for CSS grid/flex sibling label-value pairs.
- Added regression tests for data attributes, primary-model filtering,
  Eco/Plus pricing, label-value pairs, and embedded JSON hydration.

### Verification

```powershell
uv run ruff format src/agentic_rag/ingestion/url/extractor.py src/agentic_rag/ingestion/url/dom/blocks.py src/agentic_rag/ingestion/url/dom/entities.py src/agentic_rag/ingestion/url/entities/__init__.py src/agentic_rag/ingestion/url/entities/extractor.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/url/metadata/enrichment.py src/agentic_rag/ingestion/url/tests/test_dom_entities_metadata.py
uv run pytest src/agentic_rag/ingestion/url/tests/test_dom_entities_metadata.py src/agentic_rag/ingestion/url/tests/test_loader.py -q
uv run ruff check src/agentic_rag/ingestion/url/extractor.py src/agentic_rag/ingestion/url/dom/blocks.py src/agentic_rag/ingestion/url/dom/entities.py src/agentic_rag/ingestion/url/entities/__init__.py src/agentic_rag/ingestion/url/entities/extractor.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/url/metadata/enrichment.py src/agentic_rag/ingestion/url/tests/test_dom_entities_metadata.py
```

### Current Status

- Focused DOM/entity and loader tests pass: 31 passed.
- Ruff check passes for the touched URL ingestion files.
- Existing Pydantic serializer warnings for flexible chunk metadata still appear.
- A live `guide_2/verify_ingestion.py` rerun is still needed to measure the VF 9
  score change against the real page.

## 2026-06-19 - Promoted Interaction Artifacts in Main URL Output

### Completed

- Updated URL ingestion so promoted dynamic interaction chunks are rendered into
  the primary `LoadedUrlDocument.markdown`.
- Rewrote primary URL ingestion artifacts after interaction promotion so
  `parsed.md`, `chunks.jsonl`, and `manifest.json` stay aligned with the
  returned chunks.
- Added evaluatable Markdown plus fenced JSON for promoted interaction facts,
  making selected model and deposit amount fields visible to
  `guide_2/verify_ingestion.py`.
- Added a focused loader regression test covering promoted interaction chunks,
  artifact Markdown, JSONL chunks, and manifest counters.
- Updated `guide_2/TODO.md` to mark the main verifier merge path complete.

### Verification

```powershell
uv run ruff format src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/url/tests/test_loader.py
uv run pytest src/agentic_rag/ingestion/url/tests/test_loader.py -q
```

### Current Status

- Focused URL loader tests pass: 22 passed.
- Existing Pydantic serializer warnings for flexible chunk metadata still appear.
- VF 9 edition tables, color tables, warranty extraction, CTA extraction, and
  cross-model filtering remain open in `guide_2/TODO.md`.

## 2026-06-19 - Structure-Aware URL Ingestion Pass

### Completed

- Added DOM structure-aware Markdown augmentation before URL chunking:
  product cards, comparison rows/tables, and FAQ-like blocks can emit generated
  `## Structured DOM Content` sections.
- Added dedupe fingerprints for generated structural blocks via
  `structure_dedupe_hash`.
- Added chunk metadata for downstream filtering/dedup:
  `section_origin`, `structure_aware`, `structure_block_types`,
  `structure_block_ids`, and `structure_dedupe_hashes`.
- Exported DOM structure and visual-semantic helpers from
  `agentic_rag.ingestion.url.dom`.
- Promoted model-scoped deposit network payloads from interaction capture into
  normal dynamic chunks. `CarsDeposit-BankInfo` payloads now preserve
  `selected_model_id`, `selected_product_model`, and `deposit_amount`.
- Updated `guide_2/TODO.md` with the structure-aware implementation status and
  remaining VF 9 evaluation follow-ups.

### Verification

```powershell
uv run ruff check src\agentic_rag\ingestion\url\dom\blocks.py src\agentic_rag\ingestion\url\dom\__init__.py src\agentic_rag\ingestion\url\loader.py src\agentic_rag\ingestion\url\tests\test_dom_entities_metadata.py src\agentic_rag\ingestion\url\tests\test_loader.py
uv run pytest src\agentic_rag\ingestion\url\tests\test_dom_entities_metadata.py src\agentic_rag\ingestion\url\tests\test_loader.py src\agentic_rag\ingestion\url\tests\test_visual_semantics.py src\agentic_rag\ingestion\url\tests\test_url_package_exports.py -q
uv run ruff check src\agentic_rag\ingestion\url\interactions\extractor.py src\agentic_rag\ingestion\url\tests\test_interactions.py src\agentic_rag\ingestion\url\loader.py src\agentic_rag\ingestion\url\tests\test_loader.py
uv run pytest src\agentic_rag\ingestion\url\tests\test_interactions.py src\agentic_rag\ingestion\url\tests\test_loader.py -q
```

### Current Status

- Focused URL ingestion slice passes: 33 passed.
- Focused interaction and loader slice passes: 42 passed.
- 2026-06-19 verifier rerun still scores 3/10. Interaction artifacts now include
  one normal promoted VF 9 deposit chunk, but the primary URL ingestion chunks
  still lack deposit context and remain cross-model noisy.
- Existing Pydantic metadata serialization warnings still appear in artifact
  tests.

## 2026-06-19 - Metadata Utilization Implementation

### Completed

- Implemented shared metadata normalization in
  `src/agentic_rag/ingestion/metadata/normalize.py`:
  list coercion, enum cleanup, date alias alignment, blank-value handling, and
  canonical entity derivation.
- Added `entities_canonical` to `ChunkMetadata` and aligned
  `QDRANT_INDEX_FIELDS` with retrieval payload indexes.
- Extended URL metadata enrichment to store:
  `semantic_blocks`, `url_entities`, and `entities_canonical`.
- Preserved leaf chunk `section` while mapping `heading` and `breadcrumb` to
  page-level context for URL chunks.
- Normalized local PDF/URL/text metadata at storage boundaries and after LLM
  enrichment.
- Excluded debug-only chunks from local retrieval before BM25/dense indexes are
  built.
- Added Qdrant filter exclusion for `metadata.metadata_prefilter_exclude=true`.
- Made Qdrant payload indexes derive from the shared metadata schema, with a
  boolean schema for `metadata.metadata_prefilter_exclude`.
- Added opt-in metadata boost factors for `quality_score`, `retrieval_weight`,
  and retrieval trust, with per-result `metadata_boost` trace output.
- Preserved non-`bm25`/`dense` retriever results in the agent provider split so
  question-index results can survive agent path retrieval.
- Added question-index contribution tracing in the local provider RRF trace.
- Updated `guide_2/TODO.md` to mark implemented phases.

### Verification

```powershell
uv run ruff format src/agentic_rag/ingestion/metadata/normalize.py src/agentic_rag/ingestion/metadata/schema.py src/agentic_rag/ingestion/url/metadata/enrichment.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/integrations/local_pdf/providers.py src/agentic_rag/agent/nodes.py src/agentic_rag/retrieval/boosting.py src/agentic_rag/retrieval/search.py tests/test_ingestion_metadata_schema.py tests/test_retrieval_search.py
uv run ruff check src/agentic_rag/ingestion/metadata/normalize.py src/agentic_rag/ingestion/metadata/schema.py src/agentic_rag/ingestion/url/metadata/enrichment.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/integrations/local_pdf/providers.py src/agentic_rag/agent/nodes.py src/agentic_rag/retrieval/boosting.py src/agentic_rag/retrieval/search.py tests/test_ingestion_metadata_schema.py tests/test_retrieval_search.py
uv run pytest src/agentic_rag/ingestion/url/tests/test_loader.py src/agentic_rag/ingestion/url/tests/test_visual_semantics.py tests/test_ingestion_metadata_schema.py tests/test_retrieval_search.py -q
```

### Current Status

- Focused metadata, URL loader, visual semantics, and retrieval tests pass:
  60 passed.
- Ruff check passes for touched implementation and test files.
- Warnings remain from existing deprecated vector-store env aliases and flexible
  Pydantic metadata serialization.

## 2026-06-18 - URL Information Gain Interaction Discovery

### Completed

- Reframed Playwright interaction handling from safe-option discovery toward
  information-gain discovery.
- Added per-click DOM diff gain storage for:
  `new_text_tokens`, `changed_nodes`, `new_tables`, `new_prices`, and
  `new_specs`.
- Added per-click API gain storage for:
  `new_endpoints`, `new_json_fields`, and `new_entities`.
- Added entity gain storage for:
  `new_models` and `new_variants`.
- Added `gain_score = dom_gain + api_gain + entity_gain` to
  `InteractionPanelDiff`, `InteractionStateRecord`, and chunk metadata.
- Prioritized captured states by `gain_score` before truncating to
  `InteractionOptions.max_states`.
- Added Bootstrap modal trigger discovery for controls such as:
  `a[data-bs-toggle="modal"]`, `data-toggle="modal"`, `data-bs-target`,
  `data-target`, `aria-expanded`, `role="dialog"`, `role="tab"`, and
  `role="button"`.
- Ensured hidden modal content such as `.modal-body` is captured after click
  and can emit price/spec state evidence.

### Changed Parts

```json
{
  "interaction_panel_diff": {
    "dom_gain": 31,
    "api_gain": 22,
    "entity_gain": 10,
    "gain_score": 63,
    "information_gain": {
      "dom": {
        "new_text_token_count": 12,
        "changed_node_count": 2,
        "new_tables": 1,
        "new_prices": ["1.499.000.000 VND"],
        "new_specs": {
          "driving_range": "626 km"
        }
      },
      "api": {
        "new_endpoints": ["/api/specifications"],
        "new_json_fields": ["specifications.range"],
        "new_entities": ["VF 9 Plus"]
      },
      "entity": {
        "new_models": ["VF 9"],
        "new_variants": ["VF 9 Plus"]
      }
    }
  },
  "bootstrap_modal_trigger": {
    "before": "DOM without #rollingUpCostPopUp modal-body content",
    "action": "click('Chi tiet')",
    "after": "DOM with .modal-body visible",
    "extract": ["new_prices", "new_specs", "changed_nodes"]
  }
}
```

Pseudo-code:

```python
for control in discover_information_controls(page):
    before_dom = capture_panels(page)
    before_api_count = len(network_payloads)

    click(control)
    wait()

    after_dom = capture_panels(page)
    new_api = network_payloads[before_api_count:]

    gain = measure_gain(before_dom, after_dom, new_api)
    if gain.gain_score > 0:
        store_diff(control, gain)
        store_state(control, gain)

states = sorted(states, key=lambda state: state.gain_score, reverse=True)
```

### Test Commands

```powershell
uv run ruff format src/agentic_rag/ingestion/url/interactions/models.py src/agentic_rag/ingestion/url/interactions/extractor.py src/agentic_rag/ingestion/url/interactions/playwright.py src/agentic_rag/ingestion/url/tests/test_interactions.py
uv run ruff check src/agentic_rag/ingestion/url/interactions/models.py src/agentic_rag/ingestion/url/interactions/extractor.py src/agentic_rag/ingestion/url/interactions/playwright.py src/agentic_rag/ingestion/url/tests/test_interactions.py
uv run pytest src/agentic_rag/ingestion/url/tests/test_interactions.py -q -p no:cacheprovider --basetemp .pytest-tmp3
uv run mypy src/agentic_rag/ingestion/url/interactions src/agentic_rag/ingestion/url/tests/test_interactions.py
```

### Current Status

- Focused URL interaction tests pass: 18 passed.
- Focused mypy passes for URL interaction modules and tests.
- Existing Pydantic serializer warnings for flexible chunk metadata still
  appear in artifact persistence tests.

## 2026-06-18 - URL API And Right-Panel Spec Mapping

### Completed

- Added structured `specifications` to URL interaction state records so model
  specs from API payloads or visible right-panel/modal content survive into
  retrieval chunks.
- Mapped common product spec labels into canonical metadata keys such as
  `driving_range`, `battery_capacity`, `seats`, `power`, `torque`,
  `dimensions`, and `charging_time`.
- Promoted API-backed spec states into normal retrieval chunks while keeping
  hidden API price-only states debug-only unless visible DOM evidence exists.
- Expanded Playwright control discovery so safe spec/detail/technical buttons
  can be clicked, including right-panel or popup/modal spec windows.
- Expanded panel capture to include modal/dialog/spec/table content and parse
  right-panel text into `product_specs`.

### Changed Parts

```json
{
  "interaction_state": {
    "before": {
      "price": "string | null",
      "image_url": "string | null"
    },
    "after": {
      "price": "string | null",
      "specifications": {
        "driving_range": "626 km",
        "battery_capacity": "123 kWh",
        "seats": "7"
      },
      "image_url": "string | null"
    }
  },
  "chunk_metadata": {
    "product_specs": "state.specifications",
    "attribute_group": "pricing_specs when price or specifications exist",
    "dedupe_text": "normalized interaction text"
  },
  "promotion_rule": {
    "api_specs": "network state with changed_fields=['specifications'] -> normal retrieval chunk",
    "hidden_api_price": "network price without DOM evidence -> debug_only"
  },
  "playwright_capture": {
    "discover_controls": [
      "spec",
      "specification",
      "technical",
      "detail",
      "thong so",
      "chi tiet"
    ],
    "capture_panels": [
      "right_panel",
      "role=dialog",
      "modal",
      "popup",
      "table",
      "dl"
    ]
  }
}
```

Pseudo-code:

```python
def state_from_payload(candidate):
    specs = specifications_from_candidate(candidate)
    if not price and not image and not specs:
        return None
    return InteractionStateRecord(
        option_group="specifications" if specs else "variant",
        specifications=specs,
        changed_fields=["specifications"] if specs else [],
    )


def promoted(state):
    if state.evidence_source == "network" and state.specifications:
        return True
    return has_visible_dom_fact(state)
```

### Test Commands

```powershell
uv run ruff format src/agentic_rag/ingestion/url/interactions/models.py src/agentic_rag/ingestion/url/interactions/extractor.py src/agentic_rag/ingestion/url/interactions/playwright.py src/agentic_rag/ingestion/url/interactions/__init__.py src/agentic_rag/ingestion/url/tests/test_interactions.py
uv run ruff check src/agentic_rag/ingestion/url/interactions/models.py src/agentic_rag/ingestion/url/interactions/extractor.py src/agentic_rag/ingestion/url/interactions/playwright.py src/agentic_rag/ingestion/url/interactions/__init__.py src/agentic_rag/ingestion/url/tests/test_interactions.py
uv run pytest src/agentic_rag/ingestion/url/tests/test_interactions.py -q -p no:cacheprovider --basetemp .pytest-tmp
```

### Current Status

- Focused URL interaction tests pass: 15 passed.
- Existing Pydantic serializer warnings for flexible chunk metadata still
  appear in artifact persistence tests.

## 2026-06-18 - URL Chunk Dedupe Text Bridge

### Completed

- Added explicit `dedupe_text` metadata to URL/text chunk creation so
  duplicate detection can reuse URL-specific normalization instead of
  recomputing from raw chunk text.
- Updated `dedup_detect` exact and SimHash layers to read canonical dedupe text
  from `DedupDocument.metadata["dedupe_text"]`, then fall back to
  `normalized_text`, then raw text normalization.
- Updated `documents_from_chunks()` to serialize Pydantic `ChunkMetadata`
  safely, replace document text with the canonical dedupe text, and record
  `dedup_text_source` for review/debugging.
- Hardened dedup metadata helpers to work with both dict metadata and
  `ChunkMetadata` model instances.
- Exported `VisualEvidenceSource` from the URL DOM package so typed URL loader
  checks remain clean.
- Added focused regression coverage for the URL chunking -> dedup handoff.

### Changed Parts

```json
{
  "url_chunk_metadata": {
    "before": {
      "dedupe_hash": "short_hash(normalize_for_dedupe_hash(chunk_text))"
    },
    "after": {
      "dedupe_text": "normalize_for_dedupe_hash(chunk_text)",
      "dedupe_hash": "short_hash(dedupe_text)"
    }
  },
  "dedup_text_resolution": [
    "metadata.dedupe_text",
    "metadata.normalized_text",
    "normalize_text(document.text)"
  ],
  "documents_from_chunks": {
    "metadata": "ChunkMetadata -> dict via model_dump(...)",
    "text": "dedup_text(document)",
    "trace": "metadata.dedup_text_source"
  },
  "exact_and_simhash": {
    "fingerprint_input": "dedup_text(document)"
  }
}
```

Pseudo-code:

```python
def dedup_text(document):
    if document.metadata.get("dedupe_text"):
        return normalize_text(document.metadata["dedupe_text"])
    if document.metadata.get("normalized_text"):
        return normalize_text(document.metadata["normalized_text"])
    return normalize_text(document.text)


def documents_from_chunks(chunks):
    docs = [DedupDocument(text=chunk.text, metadata=as_dict(chunk.metadata)) for chunk in chunks]
    return [
        doc.copy(text=dedup_text(doc), metadata={**doc.metadata, "dedup_text_source": source})
        for doc in docs
    ]
```

### Test Commands

```powershell
.venv\Scripts\ruff.exe check src/agentic_rag/ingestion/url/chunking/core.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/dedup_detect/normalization.py src/agentic_rag/ingestion/dedup_detect/exact.py src/agentic_rag/ingestion/dedup_detect/simhash.py src/agentic_rag/ingestion/dedup_detect/pipeline.py src/agentic_rag/ingestion/dedup_detect/metadata.py src/agentic_rag/ingestion/url/dom/__init__.py src/agentic_rag/ingestion/url/tests/test_chunking.py src/agentic_rag/ingestion/url/tests/test_loader.py tests/test_dedup_detect_pipeline.py
.venv\Scripts\mypy.exe src/agentic_rag/ingestion/dedup_detect src/agentic_rag/ingestion/url/chunking/core.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/url/dom/__init__.py
.venv\Scripts\pytest.exe -q -p no:cacheprovider --basetemp .pytest-tmp tests/test_dedup_detect_pipeline.py src/agentic_rag/ingestion/url/tests/test_chunking.py src/agentic_rag/ingestion/url/tests/test_loader.py tests/test_ingestion_chunking.py tests/test_dedup_detect_metadata_contract.py tests/test_dedup_detect_embedding.py
```

### Current Status

- Focused lint passed.
- Targeted mypy passed for the touched ingestion modules.
- Focused regression tests passed: 39 passed, with 2 existing Pydantic
  serializer warnings in URL artifact tests.

## 2026-06-16 - Source Category Metadata And PDF Review Demo

### Completed

- Corrected shared `source_type` semantics to match the PDF/general schema:
  `official`, `internal`, `partner`, `news`, `community`, or `unknown`.
- Kept `source` as the exact source value: URL for URL ingestion, local PDF path
  for PDF ingestion, and source name/path for HTML/text ingestion.
- Updated URL ingestion so VinFast official domains map to `official`, unknown
  external URLs map to `unknown`, and local/manual text or HTML maps to
  `internal`.
- Preserved readable URL/text chunk ID prefixes (`url_`, `html_`, `text_`) while
  storing category values in `metadata["source_type"]`.
- Updated PDF ingestion so local PDF chunks use `source_type = internal` and
  keep PDF identity in `source`, `file_name`, and `pdf_...` chunk IDs.
- Added `guide/demo/pdf-review/`, a local PDF review demo that writes parsed
  Markdown, chunks, manifest, metadata-contract summary, and a readable report.
- Updated URL/PDF/dedup metadata docs and focused tests for the corrected
  source-category contract.

## 2026-06-16 - Shared Date Metadata Clarification

### Completed

- Clarified the shared metadata contract for URL/PDF/rule-based consumers:
  - `source_type` is required.
  - `updated_date` is required and means ingestion start time.
  - `created_date` is optional and means source modified date extracted from
    URL/PDF data when available.
  - `language` is optional.
  - `document_type` is optional.
- Updated URL ingestion so `updated_date` stays tied to the URL ingestion start
  timestamp and `updated_date_source` is `ingestion_start`.
- Updated URL metadata enrichment so HTML source modified metadata
  (`article:modified_time` and similar parser output) maps to optional
  `created_date`, not `updated_date`.
- Updated PDF ingestion so `updated_date` is the PDF load start timestamp, not
  filesystem modification time.
- Added `Explain.md` as a short repo-level explanation for teammates integrating
  rule-based metadata checks.
- Updated URL/PDF/dedup/demo documentation to reflect the corrected field
  meanings.

### Current Rule

```text
source_type: required
updated_date: required, ingestion start time
created_date: optional, source modified date if URL/PDF can find it
language: optional
document_type: optional
fetched_at: URL-local debug field, not shared schema
```

## 2026-06-16 - Shared Metadata, PDF Alignment, And Dedup Check Demo

### Added / Updated

- Pulled `origin/develop` before the metadata work; result was already up to
  date.
- Added the shared ingestion metadata minimum in
  `src/agentic_rag/ingestion/metadata/schema.py`:
  - `source_type` is required for every chunk.
  - `document_type` is optional and should only be added when the parser or
    enrichment step can infer it safely.
  - Helper functions now report or raise on missing required metadata:
    `missing_required_metadata()`, `has_required_metadata()`, and
    `require_metadata()`.
- Updated `src/agentic_rag/ingestion/metadata/__init__.py` to export the shared
  metadata constants and helper functions.
- Updated PDF ingestion in `src/agentic_rag/ingestion/pdf/loader.py` so PDF
  chunks now satisfy the same shared metadata contract:
  - `source_type` is the shared category; local PDF files use `internal`.
  - `page_number` mirrors `page` when page provenance exists.
  - `heading` mirrors the chunk section.
  - `breadcrumb` mirrors `section_path` or falls back to `[section]`.
  - `token_count` is stamped from the chunker when available, otherwise from a
    word-count fallback.
  - `require_metadata()` is called before each PDF `Chunk` is returned.
- Updated `src/agentic_rag/ingestion/pdf/README.md` to document the new shared
  PDF metadata aliases and the rule that `document_type` stays optional.
- Updated URL ingestion documentation in
  `src/agentic_rag/ingestion/url/README.md` and
  `src/agentic_rag/ingestion/url/schema.md` so the URL module states clearly:
  - URL ingestion owns URL/HTML/text extraction.
  - PDF URLs and PDF responses are rejected before HTML parsing.
  - PDF data should be routed to `src/agentic_rag/ingestion/pdf`.
  - URL-local quality uses `url_status` / `url_quality_gate`; top-level
    `quality_score` is left for rule-based or LLM enrichment.
- Updated duplicate detection metadata helpers in
  `src/agentic_rag/ingestion/dedup_detect/metadata.py`:
  - `chunk_metadata_contract_issues()` lists chunks missing required metadata.
  - `chunk_metadata_contract_summary()` summarizes required-field readiness,
    `source_type` counts, and optional `document_type` counts before dedup
    review.
- Updated `src/agentic_rag/ingestion/dedup_detect/__init__.py` and
  `src/agentic_rag/ingestion/dedup_detect/README.md` so the dedup module can
  check shared metadata from PDF, URL, HTML, and text chunks without owning
  ingestion.
- Added focused tests:
  - `tests/test_ingestion_metadata_schema.py`
  - `tests/test_dedup_detect_metadata_contract.py`
  - Updated `src/agentic_rag/ingestion/pdf/tests/test_loader.py`
- Added the offline dedup verification demo in `guide/demo/check-dedup/`:
  - `README.md`
  - `check_dedup.py`
  - `sample_chunks.jsonl`
  - The demo reads sample chunks, checks the shared metadata contract, runs
    exact/SimHash dedup, and writes JSON/JSONL/Markdown outputs.
- Updated the existing URL dedup review demo in
  `guide/demo/dedup-detect-url-review/run_url_dedup_review.py` so reports now
  include `metadata_contract.json` and a Metadata Contract section.

### Deleted / Removed / Cleaned

- No tracked file deletion is present in the current `git status --short`
  output; the current work is mainly additions and updates.
- Cleaned generated verification leftovers after local checks:
  - `guide/demo/check-dedup/output-test/`
  - `guide/demo/check-dedup/__pycache__/`
  - `guide/demo/dedup-detect-url-review/__pycache__/`
- `Worklog.md` is currently untracked in this checkout, so this entry preserves
  the recreated log instead of assuming an older tracked version exists.

### PDF And URL Boundary Answer

- URL ingestion can now share metadata with PDF ingestion, dedup detection, and
  downstream retrieval because both URL and PDF chunks use the same `Chunk`
  contract and the same required `source_type` rule.
- URL ingestion does not directly call PDF functions yet. It rejects direct PDF
  URLs and `application/pdf` responses using
  `src/agentic_rag/ingestion/url/acquisition/fetcher.py` and raises a clear
  route-to-PDF error.
- To make URL automatically utilize PDF functions, add a higher-level ingestion
  router or dispatcher above URL/PDF ingestion. That router should detect PDF
  URLs or PDF responses, download/store the PDF safely, then call
  `src/agentic_rag/ingestion/pdf.load_pdf_with_markdown()` or
  `load_pdf_chunks()`. The URL loader itself should stay HTML-focused.

### Verification Commands

```powershell
uv run ruff format src/agentic_rag/ingestion/chunking/models.py src/agentic_rag/ingestion/metadata src/agentic_rag/ingestion/pdf/loader.py src/agentic_rag/ingestion/pdf/tests/test_loader.py src/agentic_rag/ingestion/dedup_detect src/agentic_rag/ingestion/url/schema.md guide/demo/dedup-detect-url-review/run_url_dedup_review.py tests/test_ingestion_metadata_schema.py tests/test_dedup_detect_metadata_contract.py
uv run ruff check src/agentic_rag/ingestion/chunking/models.py src/agentic_rag/ingestion/metadata src/agentic_rag/ingestion/pdf/loader.py src/agentic_rag/ingestion/pdf/tests/test_loader.py src/agentic_rag/ingestion/dedup_detect guide/demo/dedup-detect-url-review/run_url_dedup_review.py tests/test_ingestion_metadata_schema.py tests/test_dedup_detect_metadata_contract.py
uv run pytest tests/test_ingestion_metadata_schema.py tests/test_dedup_detect_metadata_contract.py src/agentic_rag/ingestion/pdf/tests/test_loader.py -q
uv run pytest src/agentic_rag/ingestion/url/tests -q
uv run python -m py_compile guide/demo/dedup-detect-url-review/run_url_dedup_review.py guide/demo/check-dedup/check_dedup.py
uv run python guide/demo/check-dedup/check_dedup.py --output-dir guide/demo/check-dedup/output-test
```

### Verification Result

- Shared metadata + dedup + PDF loader tests passed: `15 passed`.
- URL ingestion tests passed: `86 passed`.
- Python compile check passed for both dedup demo scripts.
- Offline check-dedup demo wrote the expected output files during the smoke
  test, then the temporary output directory was removed.

## 2026-06-15 - URL Staged Artifact Persistence

### Completed

- Extended URL ingestion artifacts so `data_artifact_dir` writes staged
  inspection files for clarity: `source.html`, `parsed_sections.txt`,
  `extracted.md`, final `parsed.md`, `quality.json`, `chunks.jsonl`, and
  `manifest.json`.
- Added stage paths to `manifest.json` and optional paths to
  `IngestionArtifacts`.
- Updated URL loader tests to verify the staged files and manifest entries.
- Updated `src/agentic_rag/ingestion/url/README.md` artifact documentation.

### Test Commands

```powershell
uv run ruff format --check src/agentic_rag/ingestion/url/artifact.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/url/tests/test_loader.py
uv run ruff check src/agentic_rag/ingestion/url/artifact.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/url/tests/test_loader.py
uv run pytest src/agentic_rag/ingestion/url/tests -q
```

## 2026-06-15 - URL Golden Review React Demo

### Completed

- Added `guide/demo/url-golden-review-react/`, a new React browser demo that
  targets the current URL ingestion contract instead of the legacy crawl-review
  payload.
- Added a Node API/static server with `GET /api/health`, `GET /api/golden`, and
  `POST /api/run`.
- Added `run_ingestion_review.py` so the demo runs `load_url_with_artifacts()`,
  scores selected URLs with `evaluate_sample()`, and returns chunk previews,
  golden failures, URL quality metadata, product specs, and artifact paths.
- Documented the `ve-chung-toi` issue: the old demo saw title-only Markdown and
  zero chunks, while current URL ingestion should recover useful chunks from
  metadata descriptions and image alt text.
- Linked the new demo from `guide/README.md` and `src/agentic_rag/ingestion/url/README.md`,
  and clarified in `TODO.md` that `url-crawl-review` is now the legacy
  compatibility path.

### Test Commands

```powershell
node --check guide/demo/url-golden-review-react/server.js
node --check guide/demo/url-golden-review-react/public/app.js
uv run ruff format --check guide/demo/url-golden-review-react/run_ingestion_review.py
uv run ruff check guide/demo/url-golden-review-react/run_ingestion_review.py
uv run python guide/demo/url-golden-review-react/run_ingestion_review.py --list --output guide/demo/url-golden-review-react/output/catalog_smoke.json
uv run python guide/demo/url-golden-review-react/run_ingestion_review.py --url https://vinfastauto.com/vn_vi/ve-chung-toi --no-browser --output guide/demo/url-golden-review-react/output/ve_chung_toi_smoke.json --output-dir guide/demo/url-golden-review-react/output
```

### Verification Notes

- The catalog smoke loaded 322 golden URLs and 322 golden samples.
- The `ve-chung-toi` smoke is `unscored` because that URL is not in the golden
  JSON, but current ingestion returned 3 chunks, 3 usable chunks, and recovery
  sections `Page Summary` and `Visual Content`.
- Local server verification returned HTTP 200 for `/` and `/api/golden`; the
  page includes the React root and the API reports the expected golden counts.

## 2026-06-13 - URL Supported Types, TODO Split, And Golden Test

### Completed

- Created `src/agentic_rag/ingestion/url/TODO_scripts.md` to keep
  script/database/vector-store reminders near URL ingestion without mixing them
  into loader logic.
- Created `src/agentic_rag/ingestion/url/TODO_dedup.md` to document the URL
  metadata handoff for `dedup_detect` and `knowledge_quality`.
- Cleaned `src/agentic_rag/ingestion/url/TODO.md` so the main roadmap stays
  focused on URL extraction, chunking, metadata, quality, and evaluation.
- Updated `src/agentic_rag/ingestion/url/README.md`,
  `guide/url-ingestion-guide.md`, `guide/README.md`, and `guide/guide.md` with
  the supported URL input/page types and the new TODO reminder files.
- Checked the current golden URL list type inventory:
  322 URLs total, including 106 `product_detail`, 16 `product_listing`,
  15 `booking_flow`, 29 `faq`, 17 `policy`, 5 `article`, and 134 `generic`
  pages.
- Ran the full browser-backed golden-data evaluation:
  `guide/reports/url_ingestion_golden_types_20260613/`
  processed 322 URLs, passed 235, failed 87, and errored 0.
- Created the verification report:
  `guide/reports/url_ingestion_golden_types_20260613/verification_report.md`.

### Test Commands

```powershell
uv run ruff format --check src/agentic_rag/ingestion/url
uv run ruff check src/agentic_rag/ingestion/url
uv run pytest src/agentic_rag/ingestion/url/tests -q
uv run python -m agentic_rag.ingestion.url.evaluation.runner --output-dir guide/reports/url_ingestion_golden_types_20260613 --no-resume
```

### Current Status

- URL ingestion focused checks are green: format passed, lint passed, and
  78 tests passed.
- Full golden-data crawl completed with 0 runtime errors.
- The live golden dataset is still a baseline rather than a green gate:
  87 samples fail current expectations, mostly price/VND snippets,
  navigation/cookie/support noise, chunk-count bounds, and metadata
  preservation checks.

## 2026-06-13 - URL Golden Product-Spec Evaluation Update

### Completed

- Extended URL golden-data evaluation with optional `product_spec_checks` so
  samples can pass/fail on structured product metadata emitted by URL
  ingestion.
- Exported `UrlProductSpecCheck` from the URL evaluation package.
- Updated golden-data templates and evaluation docs to describe product/spec
  checks for model, price, driving range, battery capacity, and charging time.
- Kept conflict-detection implementation ownership in `knowledge_quality`; URL
  ingestion now documents only the metadata handoff and fixture TODOs.
- Ran the full browser-backed golden-data evaluation:
  `guide/reports/url_ingestion_golden_product_specs_20260613/`
  processed 322 URLs, passed 233, failed 89, and errored 0.
- Created the verification report:
  `guide/reports/url_ingestion_golden_product_specs_20260613/verification_report.md`.

### Test Commands

```powershell
uv run ruff format --check src/agentic_rag/ingestion/url
uv run ruff check src/agentic_rag/ingestion/url
uv run pytest src/agentic_rag/ingestion/url/tests -q
uv run python -m agentic_rag.ingestion.url.evaluation.runner --output-dir guide/reports/url_ingestion_golden_product_specs_20260613 --no-resume
```

### Current Status

- URL ingestion unit tests are green: 78 passed.
- Full golden-data run completed with 0 runtime errors.
- The committed VinFast golden JSON does not yet enable `product_spec_checks`,
  so this run validates backward compatibility plus the existing base contract.
- The full 322-link golden dataset is still a live baseline, not a green release
  gate yet: 89 samples still fail base expectations.

## 2026-06-13 - URL Ingestion Golden Verification

### Completed

- Built out the URL ingestion structure under `src/agentic_rag/ingestion/url`
  for acquisition, DOM handling, entity extraction, metadata, quality strategy,
  rendering, golden data, and evaluation.
- Added quality-first URL ingestion behavior: static fetch inspection,
  rendered-parser fallback, page-type profiling, render retry, report-local
  render cache, metadata propagation, and noise cleanup.
- Added and exercised golden-data evaluation from
  `src/agentic_rag/ingestion/url/golden_data/Link_data.txt` against
  `vinfast_url_golden_samples.json`.
- Verified the focused regression subset:
  `guide/reports/url_ingestion_verification_subset_complete_final2/`
  processed 12 URLs, passed 12, failed 0, and errored 0.
- Ran the full live golden-data verification:
  `guide/reports/url_ingestion_golden_verification_20260613/`
  processed 322 URLs, passed 219, failed 103, and errored 0.
- Created the full verification report:
  `guide/reports/url_ingestion_golden_verification_20260613/verification_report.md`.

### Test Commands

```powershell
uv run ruff format --check src/agentic_rag/ingestion/url
uv run ruff check src/agentic_rag/ingestion/url
uv run pytest src/agentic_rag/ingestion/url/tests -q
uv run python -m agentic_rag.ingestion.url.evaluation.runner --output-dir guide/reports/url_ingestion_golden_verification_20260613 --no-resume
```

### Current Status

- URL ingestion unit tests are green: 74 passed.
- The 12-link verification subset is green.
- The full 322-link golden dataset is a live baseline, not a green release gate
  yet: 103 samples still fail base expectations.

### Next Triage

- Review whether price-related required snippets on shop product pages should
  stay as base pass/fail requirements or move to optional/advanced checks.
- Fix empty required snippets in FAQ/product golden samples.
- Continue cleanup for residual navigation/footer snippets such as `Home`,
  `Cookie`, `Support`, and login text.
- Inspect canonical URL, query parameter, and language metadata failures.
