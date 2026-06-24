# URL Ingestion Guide

This guide explains the learning path for URL ingestion: how a URL is fetched,
converted to Markdown, chunked, and exposed to the rest of the RAG pipeline.

## What To Learn First

URL ingestion lives under `src/agentic_rag/ingestion/url`. The public boundary is
in `loader.py`:

- `load_url_chunks(url, ...) -> list[Chunk]`
- `load_url_with_artifacts(url, ...) -> LoadedUrlDocument`
- `load_html_chunks(html, source=..., ...) -> list[Chunk]`
- `load_html_with_artifacts(html, source=..., ...) -> LoadedUrlDocument`

Use `load_url_chunks()` when the caller only needs chunks. Use
`load_url_with_artifacts()` when debugging parser output, rendered HTML, final
URL, or generated artifacts.

## Pipeline Shape

```text
URL
  -> optional Playwright/browser extraction
  -> static HTTP fallback when browser extraction is unavailable or fails
  -> HTML parsing and Markdown extraction
  -> URL-aware Markdown chunking
  -> shared Chunk objects
  -> optional debug and ingestion artifacts
```

The loader rejects PDF URLs and PDF responses. PDF ingestion belongs in
`src/agentic_rag/ingestion/pdf`, while URL ingestion expects HTML-like content.

## What URL Ingestion Can Ingest Now

Use URL ingestion for HTML-like web content:

- `http://` and `https://` URLs that return HTML.
- Static pages such as articles, blogs, policies, legal pages, warranty pages,
  and FAQ pages.
- Rendered product/detail/listing pages when Playwright is available, including
  VinFast model pages, shop product pages, home product grids, booking/deposit
  flows, configurators, and other React/Next-style applications.
- Direct HTML strings for deterministic fixture tests.
- Plain text strings when a caller already has extracted text and only needs URL
  chunking behavior.

Do not force these into URL ingestion:

- PDF URLs or responses. Divert them to `src/agentic_rag/ingestion/pdf`.
- Non-HTTP(S) schemes such as local files, S3 URIs, or database rows.
- Database/vector-store upload work. Keep that in operational scripts and use
  `src/agentic_rag/ingestion/url/TODO_scripts.md` as the reminder list.
- Duplicate merge/delete or conflict decisions. URL ingestion emits metadata for
  those workflows; `dedup_detect` and `knowledge_quality` own the decisions.

The current page-type strategy is quality-first:

| Page type | Examples | Parser expectation |
| --- | --- | --- |
| `article` | News or blog URLs | Static can pass if useful |
| `policy` | Privacy, terms, warranty, legal pages | Static can pass if useful |
| `faq` | FAQ pages | Static can pass if useful |
| `product_detail` | VinFast model or shop product pages | Rendered parser required when enabled |
| `product_listing` | Shop/catalog listings | Rendered parser required when enabled |
| `homepage_product_listing` | Product grids on homepage-like pages | Rendered parser required when enabled |
| `vehicle_configurator` | Configurator pages | Rendered parser required when enabled |
| `booking_flow` | Deposit or booking flows | Rendered parser required when enabled |
| `interactive_application` | App-like interactive pages | Rendered parser required when enabled |
| `dynamic_application` | React/Next/root-shell pages | Rendered parser required when enabled |
| `generic` | Other HTML pages | Static can pass if useful |

## Key Files

| File | Purpose |
| --- | --- |
| `src/agentic_rag/ingestion/url/loader.py` | Public loading boundary and artifact orchestration |
| `src/agentic_rag/ingestion/url/extractor.py` | Browser, trafilatura, and HTML-to-Markdown extraction helpers |
| `src/agentic_rag/ingestion/url/parser.py` | Built-in HTML parsing and visible content extraction |
| `src/agentic_rag/ingestion/url/chunking/` | URL-specific Markdown chunk construction |
| `src/agentic_rag/ingestion/url/entities/` | Entity and product-spec extraction helpers |
| `src/agentic_rag/ingestion/url/metadata/` | URL, entity, quality, and product-spec metadata enrichment |
| `src/agentic_rag/ingestion/url/artifact.py` | Debug and ingestion artifact models |
| `src/agentic_rag/ingestion/url/tests/` | Deterministic tests for loader, parser, extractor, artifacts, and chunking |
| `src/agentic_rag/ingestion/url/TODO_scripts.md` | Script/database/vector-store reminders for URL-ingested data |
| `src/agentic_rag/ingestion/url/TODO_dedup.md` | URL-to-dedup/conflict metadata handoff reminders |

## Chunk Contract

URL ingestion must return `agentic_rag.core.contracts.Chunk` objects. URL-specific
details belong in `Chunk.metadata`, not in new top-level contract fields.

Useful metadata can include:

- `url`
- `source_url`
- `original_url`
- `final_url`
- `canonical_url`
- `product_specs`
- `product_model`
- `product_price`
- `driving_range`
- `battery_capacity`
- `charging_time`
- parser or extraction diagnostics

## Retrieval-Aware Chunking

Retrieval and generation currently use chunks in two different ways:

- BM25 and dense retrieval search over `Chunk.text`.
- Qdrant/hybrid retrieval preserves metadata for filters and reconstruction.
- Generation builds evidence lines from `source`, `page`, `section`,
  `section_path`, `chunk_id`, score, metadata hints, and chunk text.
- Citation validation only accepts citations that match retrieved chunk
  metadata.

This means URL chunks should be self-contained answer units. A chunk like
`849.150.000 VND` is too weak. A chunk like `VF 8 listed price:
849.150.000 VND` can be retrieved by exact text, embedded semantically, and
used safely in a cited answer.

Recommended URL chunk types:

- `page_overview`: page title, page purpose, canonical source, major sections.
- `section`: one heading or policy/article section.
- `entity_card`: one vehicle, product, FAQ item, policy link, or repeated card.
- `table_overview`: table title, compared entities, and attribute groups.
- `table_row`: one entity row with headers repeated beside values.
- `spec_fact`: one exact product fact such as price, range, battery, charging
  time, warranty, or availability.
- `dynamic_state`: facts captured after safe JavaScript interaction.
- `asset_reference`: PDF/image/snapshot references that need separate routing
  or review.

For tables and product specs, never split labels from values. Repeat enough
context inside the text:

```text
VF 8 Eco driving range: 471 km under the listed standard.
```

Keep the same fact structured in metadata when possible:

```json
{
  "entity_name": "VF 8 Eco",
  "attribute_group": "driving_range",
  "product_specs": {"driving_range": "471 km"}
}
```

For dynamic pages, keep static and dynamic facts separate. Mark generated
review text as generated so retrieval and conflict detection do not treat it as
source evidence.

When visual HTML, CSS, or JavaScript changes the meaning of content, use
`guide/url-css-html-dynamic-markdown-guide.md` as the rulebook before changing
extractors or chunking. It defines how to represent old prices, CSS tables,
highlighted states, generated CSS labels, image references, and dynamic
interaction states as Markdown plus `Chunk.metadata`.

## Downstream Handoff

URL ingestion should extract clean facts, not decide whether facts conflict.
Structured product fields in `Chunk.metadata` are intended for downstream
quality modules:

```text
URL ingestion product_specs
  -> dedup_detect duplicate/near-duplicate metadata
  -> knowledge_quality fact extraction and conflict findings
```

Use `guide/knowledge-quality-conflict-detection-guide.md` when product specs
need to be compared across pages, versions, or sources.

## Debugging Workflow

1. Reproduce with `load_url_with_artifacts()` so the Markdown and artifacts are
   visible. For booking/configurator pages, pass `include_interactions=True`
   to append promoted `dynamic_state` chunks from safe UI interactions.
2. Check whether browser extraction or static fallback produced the selected
   content.
3. Inspect parsed Markdown before inspecting chunks. Bad chunks usually start as
   noisy or missing Markdown.
4. Compare chunk boundaries against page structure: headings, product cards,
   tables, repeated navigation, and call-to-action text.
5. If repeated chunks appear across pages, move to
   `guide/duplicate-detection-guide.md`.

## Demo Workflow

The URL crawl review demo is the fastest way to inspect live URL behavior:

```powershell
uv run python guide/demo/url-crawl-review/run_review.py https://example.com --max-child-pages 3
```

For the browser review app:

```powershell
node guide/demo/url-crawl-review/server.js
```

Then open:

```text
http://127.0.0.1:8782
```

Read `guide/demo/url-crawl-review/README.md` for the full demo options and
output locations.

## Quality Checks

For URL-only changes, start with the focused tests:

```powershell
uv run pytest src/agentic_rag/ingestion/url/tests -q
```

Before review, run the project quality gate from `docs/coding-standards.md`.

## Deeper References

- `src/agentic_rag/ingestion/url/README.md`
- `src/agentic_rag/ingestion/url/TODO.md`
- `src/agentic_rag/ingestion/url/TODO_scripts.md`
- `src/agentic_rag/ingestion/url/TODO_dedup.md`
- `guide/url-css-html-dynamic-markdown-guide.md`
- `guide/knowledge-quality-conflict-detection-guide.md`
- `guide/demo/url-crawl-review/README.md`
- `guide/agentic-rag-pipeline-report.md`
- `docs/module-contracts.md`
