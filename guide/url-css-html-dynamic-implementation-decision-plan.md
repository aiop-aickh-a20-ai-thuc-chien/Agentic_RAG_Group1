# URL CSS/HTML/JS Implementation Decision Plan

This document maps the CSS/HTML/JavaScript-to-Markdown guide onto the actual
`src/agentic_rag` source tree. It chooses where implementation should happen and
where it should not happen.

Reference guide:

- `guide/url-css-html-dynamic-markdown-guide.md`

## Truth From The Current Source Tree

The current `src/agentic_rag/ingestion/url` package already has the right
pipeline folders for this work:

```text
url/
  acquisition/
  rendering/
  dom/
  entities/
  interactions/
  metadata/
  chunking/
  artifact.py
  extractor.py
  loader.py
  normalizer.py
  parser.py
  quality/
  evaluation/
  golden_data/
  tests/
```

Important existing facts:

- `loader.py` is the public URL boundary and already coordinates fetch, render,
  parse, Markdown, chunks, metadata, quality, and artifacts.
- `rendering/browser.py` owns browser rendering attempts and render cache
  files.
- `dom/blocks.py` already detects semantic blocks such as product cards, FAQ
  items, policy sections, and tables.
- `interactions/` already captures safe JavaScript interaction states and
  creates chunks for color/trim/price/image variants.
- `metadata/enrichment.py` already attaches URL, entity, product-spec, and
  retrieval metadata to `Chunk.metadata`.
- `chunking/markdown.py` already wraps shared Markdown chunking to protect URL
  pages from value-only pseudo headings.
- `artifact.py` already persists staged URL artifacts such as source HTML,
  cleaned HTML, parsed Markdown, chunks, quality, and manifest.
- `evaluation/scoring.py`, `golden_data/`, and `tests/` already provide the
  right place for deterministic checks.
- Shared `ChunkMetadata` allows extra fields, and required shared fields are
  `source_type` and `updated_date`. URL-only fields should stay inside
  `Chunk.metadata`.

## Folder Ownership Decisions

| Concern | Implement in | Decision |
| --- | --- | --- |
| HTTP fetch, redirects, content type, PDF diversion | `src/agentic_rag/ingestion/url/acquisition/` | No CSS/visual logic here. Keep it source acquisition only. |
| Browser rendering, render cache, network capture, computed style capture | `src/agentic_rag/ingestion/url/rendering/` | Extend this folder when Playwright must collect rendered DOM, computed styles, pseudo-element content, accessibility text, and network payload excerpts. |
| Semantic DOM blocks, CSS meaning, hidden/visible decisions, table-like layout detection | `src/agentic_rag/ingestion/url/dom/` | Main owner for CSS/HTML semantic interpretation. Add URL-local helpers here instead of spreading CSS rules through `loader.py`. |
| Product/entity extraction after DOM interpretation | `src/agentic_rag/ingestion/url/entities/` | Use for product model, spec, price, image, and row/entity facts after DOM or visual semantics identify the block. |
| Safe JavaScript option state capture | `src/agentic_rag/ingestion/url/interactions/` | Main owner for button/swatch/tab/variant state changes. Extend existing models instead of creating a second dynamic pipeline. |
| Markdown extraction adapters | `src/agentic_rag/ingestion/url/extractor.py` | Orchestrate DOM-to-Markdown conversion, but keep new CSS/visual rules in `dom/` helper modules. |
| Markdown cleanup | `src/agentic_rag/ingestion/url/normalizer.py` | Only deterministic cleanup of known noise. Do not put semantic CSS conversion here. |
| URL metadata attachment | `src/agentic_rag/ingestion/url/metadata/` | Attach visual/dynamic provenance fields to chunks after extraction and chunking. |
| URL-specific Markdown chunk safety | `src/agentic_rag/ingestion/url/chunking/` | Keep label/value, table row, old/current price, and dynamic-state text together during chunking. |
| URL artifacts | `src/agentic_rag/ingestion/url/artifact.py` | Persist visual evidence, computed-style summaries, interaction diffs, screenshot/image references, and LLM review notes. |
| URL pass/fail checks | `src/agentic_rag/ingestion/url/evaluation/` and `golden_data/` | Add checks for strike-through prices, CSS tables, hidden payloads, generated labels, dynamic variants, and LLM validation. |
| URL-local LLM fallback for visual/dynamic review | New `src/agentic_rag/ingestion/url/llm_review/` | Create only when implementing LLM fallback. Keep it URL-local because shared metadata LLM extraction has a different purpose. |

## Folders Not Chosen For This Plan

Do not implement the CSS/HTML/JS Markdown plan in these folders:

| Folder | Reason |
| --- | --- |
| `src/agentic_rag/core/` | No public `Chunk` contract changes are needed. |
| `src/agentic_rag/ingestion/pdf/` | PDF ingestion has different layout evidence and should not absorb URL CSS/JS logic. |
| `src/agentic_rag/ingestion/dedup_detect/` | Dedup consumes URL metadata later; it should not decide how CSS/JS becomes Markdown. |
| `src/agentic_rag/ingestion/knowledge_quality/` | Conflict detection consumes source-backed facts later; URL ingestion should only provide clean facts and provenance. |
| `src/agentic_rag/ingestion/metadata/extract.py` | Existing shared LLM metadata extraction is for summary, keywords, questions, entities, document type, and language. Visual/dynamic evidence mapping needs a URL-local review contract. |
| `src/agentic_rag/retrieval/` | Retrieval should benefit from better chunks and metadata without needing implementation changes first. |
| `src/agentic_rag/generation/` | Generation should receive cleaner evidence; do not patch prompts to compensate for bad ingestion. |

## Recommended New URL Files

Add these files only when implementation starts:

```text
src/agentic_rag/ingestion/url/dom/visual_semantics.py
src/agentic_rag/ingestion/url/dom/table_semantics.py
src/agentic_rag/ingestion/url/dom/visibility.py
src/agentic_rag/ingestion/url/llm_review/__init__.py
src/agentic_rag/ingestion/url/llm_review/models.py
src/agentic_rag/ingestion/url/llm_review/reviewer.py
src/agentic_rag/ingestion/url/llm_review/validation.py
```

Suggested responsibility:

- `visual_semantics.py`: old/current price, emphasis, badge/status, generated
  labels, and CSS meaning records.
- `table_semantics.py`: real HTML tables and CSS grid/flex/table-like layouts.
- `visibility.py`: visible, hidden, collapsed, aria-hidden, and payload-only
  decisions.
- `llm_review/models.py`: strict URL-local LLM review input/output schemas.
- `llm_review/reviewer.py`: optional LLM call wrapper.
- `llm_review/validation.py`: deterministic validation before any LLM proposal
  can become trusted Markdown or metadata.

## Current Implementation Status

Implemented in `src/agentic_rag`:

- `url/dom/visual_semantics.py` extracts deterministic visual facts for
  strike-through old prices, hidden text, and simple CSS-generated labels.
- `url/loader.py` applies old-price Markdown evidence such as
  `~~1.699.000.000 VND~~` into the relevant existing chunk text when possible,
  falls back to a small visual evidence section only when the value is missing
  from extracted Markdown, marks fallback visual chunks as debug-only for
  metadata pre-filter exclusion, attaches visual provenance into
  `Chunk.metadata`, and keeps the public `Chunk` API unchanged.
- `url/interactions/extractor.py` marks raw JavaScript/interaction state chunks
  as debug-only by default. These chunks preserve capture evidence for demos and
  audits, but metadata pre-filter should remove them from normal RAG retrieval
  until a validated interaction fact is applied to a relevant semantic chunk.
- `url/artifact.py` can persist `visual_semantics.json` and exposes the path in
  the artifact manifest.
- `url/llm_review/` provides the optional evidence-first LLM fallback contract.
  It uses the existing ingestion LLM runtime, so OpenAI works through
  `LLM_PROVIDER` / `LLM_API_KEY` or the role-specific
  `INGESTION_LLM_PROVIDER` / `INGESTION_LLM_API_KEY` settings.
- `ingestion/chunking/splitters.py` falls back to word counting when tokenizer
  assets cannot be loaded, which keeps offline ingestion tests deterministic.

Still planned:

- CSS grid/flex/table reconstruction in `url/dom/table_semantics.py`.
- Rich computed-style and pseudo-element snapshots from `url/rendering/`.
- LLM review wiring into the dynamic interaction runner.
- Advanced evaluation gates for CSS tables, hidden state payloads, and
  accepted/rejected LLM proposals.

## Metadata Decision

Do not add top-level fields to `Chunk`.

Use `Chunk.metadata` for all URL-specific evidence fields:

```json
{
  "section_kind": "static | dynamic | generated",
  "section_origin": "source_data_static | source_data_rendered | dynamic_interaction | dynamic_state_payload | generated_artifact",
  "evidence_source": "raw_html | rendered_dom | computed_style | dom_after_interaction | network_payload | json_state | ocr_text | ingestion_adapter",
  "selector": "...",
  "dom_path": "...",
  "state_path": "...",
  "artifact_ref": "...",
  "dynamic_state_id": "...",
  "interaction_step": "...",
  "css_evidence": ["text-decoration: line-through"],
  "css_generated_content": false,
  "original_price": "...",
  "product_price": "...",
  "product_currency": "VND",
  "variant_options": {},
  "image_url": "...",
  "image_snapshot_ref": "...",
  "llm_fallback_used": false,
  "llm_confidence": null,
  "trusted_for_retrieval": true,
  "retrieval_visibility": "normal | debug_only",
  "metadata_prefilter_exclude": false,
  "semantic_application_status": "unmapped | applied_to_semantic_chunk",
  "debug_reason": null
}
```

Keep current fields such as `interaction_state_id`, `interaction_state`,
`image_snapshot_ref`, `product_specs`, `product_model`, `product_price`,
`attribute_group`, `url_quality`, and `url_quality_gate`. Add aliases such as
`dynamic_state_id` only when they improve clarity for dynamic chunks.

## Implementation Order

1. Add deterministic fixtures and tests first.
   - Old/current price with `s`, `del`, and CSS line-through.
   - CSS grid/flex layout that behaves like a table.
   - Hidden content versus visible content.
   - `::before` or `::after` generated label evidence.
   - Color/trim option changing image and price.
   - JSON/network state that is not visible in DOM.
   - LLM proposal accepted only after deterministic evidence validation.
   - LLM invented price rejected from trusted metadata.

2. Implement static visual semantics in `url/dom/`.
   - Build records for visual meaning before Markdown generation.
   - Detect strike-through price evidence.
   - Detect hidden/collapsed content.
   - Detect table-like CSS layouts only when stable label/value structure is
     recoverable.

3. Extend rendering evidence in `url/rendering/`.
   - Persist rendered HTML as today.
   - Add optional computed-style and pseudo-content snapshots for selected DOM
     blocks.
   - Add network payload excerpts needed by dynamic pages.
   - Keep this bounded so rendering does not become business logic.

4. Wire visual semantics into Markdown extraction.
   - `extractor.py` should call URL DOM helpers.
   - Old prices become `~~old price~~`.
   - Recovered tables become Markdown tables.
   - Uncertain layouts become self-contained bullets.
   - Generated grouping text is marked as generated, not source fact.

5. Extend `url/interactions/`.
   - Add `section_kind`, `section_origin`, `dynamic_state_id`, `interaction_step`,
     `state_path`, and richer `evidence_source` values.
   - Keep safe-click rules and mutation avoidance.
   - Preserve current behavior for existing interaction tests.

6. Enrich metadata in `url/metadata/`.
   - Add provenance fields from DOM, rendering, and interaction records.
   - Keep `source_type` and `updated_date` present.
   - Keep URL-specific extras inside metadata.

7. Protect chunk quality in `url/chunking/`.
   - Keep old/current price text together.
   - Keep table headers with row values.
   - Keep dynamic variant facts self-contained.
   - Continue demoting value-only pseudo headings for URL pages.

8. Persist review artifacts in `url/artifact.py`.
   - Include visual evidence summaries.
   - Include computed-style snapshots when available.
   - Include dynamic diffs and image snapshot references.
   - Include LLM review notes separately from trusted chunks.

9. Add URL-local LLM fallback.
   - Put it in `url/llm_review/`.
   - Use strict schemas and bounded artifact slices.
   - Validate every proposed fact against deterministic evidence.
   - Store unvalidated output as review notes only.

10. Add evaluation gates.
    - Extend `url/evaluation/` and `golden_data/advanced_template`.
    - Score old/current price handling, CSS table reconstruction, hidden content
      handling, dynamic state provenance, image references, and LLM validation.

## Acceptance Criteria

The implementation is ready only when:

- URL ingestion can represent old/current prices without turning prices into
  isolated headings.
- CSS table-like layouts become Markdown tables only when row/header recovery is
  reliable.
- Dynamic JavaScript states are separate from static page chunks.
- Product facts include deterministic evidence provenance.
- LLM fallback cannot write unvalidated product facts into trusted Markdown or
  metadata.
- Artifacts make it possible to inspect why a Markdown chunk was produced.
- Existing URL, PDF, dedup, retrieval, and generation public contracts remain
  stable.

## First PR Boundary

The first implementation PR should be small:

1. Add `url/dom/visual_semantics.py`.
2. Add tests for strike-through old price, hidden content, and generated label
   evidence.
3. Wire only static HTML visual semantics into extraction.
4. Update artifacts with visual evidence summaries.

Dynamic interactions, CSS table reconstruction, and LLM fallback should follow
after the static visual layer is proven.
