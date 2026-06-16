# URL Ingestion

This module turns a URL or HTML document into clean Markdown, RAG-ready chunks,
and optional local artifacts for inspection.

The implementation is intentionally bounded to URL/HTML ingestion. PDF URLs or
PDF responses are rejected here and should be routed to the PDF ingestion module.

## Supported Inputs And Page Types

URL ingestion can currently ingest:

- Absolute `http://` and `https://` URLs that return HTML-like content.
- Static HTML pages that can pass the quality gate without browser rendering.
- JavaScript-rendered React/Next/root-container pages when the browser
  extractor is enabled.
- Direct HTML strings through `load_html_chunks()` or
  `load_html_with_artifacts()`.
- Plain text strings through `load_text_chunks()`.

The URL page profiler currently recognizes these live page types:

| Page type | Typical URL/content | Rendering policy |
| --- | --- | --- |
| `article` | News, blog, or editorial URLs | Static can pass when quality is sufficient |
| `policy` | Privacy, terms, warranty, legal, and policy pages | Static can pass when quality is sufficient |
| `faq` | FAQ or `cau-hoi-thuong-gap` pages | Static can pass when quality is sufficient |
| `product_detail` | VinFast model pages or shop `.html` product pages | Rendered parser required when enabled |
| `product_listing` | Shop/category listing pages | Rendered parser required when enabled |
| `homepage_product_listing` | VinFast homepage product grids | Rendered parser required when enabled |
| `vehicle_configurator` | Configurator or `cau-hinh` pages | Rendered parser required when enabled |
| `booking_flow` | Deposit/booking pages such as `dat-coc` | Rendered parser required when enabled |
| `interactive_application` | Interactive app-like pages | Rendered parser required when enabled |
| `dynamic_application` | React/Next/root-shell pages detected from HTML signals | Rendered parser required when enabled |
| `generic` | Other HTML pages | Static can pass when quality is sufficient |

The module rejects non-HTTP(S) URLs, PDF-looking URLs, and PDF content types.
Those sources should be diverted to the right ingestion owner, especially
`src/agentic_rag/ingestion/pdf` for PDF data.

## Module Map

- `loader.py`: public ingestion boundary for URL, HTML, and text inputs.
- `acquisition/fetcher.py`: URL validation, HTTP fetch, request headers,
  redirects, content type, and PDF rejection.
- `rendering/browser.py`: optional browser-rendered extraction attempts and
  rendering diagnostics.
- `interactions/`: rule-based JavaScript interaction capture for booking and
  configurator pages where option buttons change product facts such as color,
  image URL, price, and variant availability.
- `parser.py`: stdlib HTML parser that extracts page metadata, links, images,
  and other page assets.
- `extractor.py`: Crawl-link-style DOM Markdown extractor, optional Playwright
  rendered-page extractor, and Trafilatura fallback.
- `normalizer.py`: deterministic Markdown cleanup rules for CTA, cookie/privacy,
  navigation, related-card, and product/listing noise.
- `dom/blocks.py`: semantic DOM block detection for product cards, FAQ items,
  tables, policy sections, and related URL-owned structures.
- `entities/extractor.py`: structured entity candidates derived from DOM blocks.
- `metadata/enrichment.py`: URL-specific page, DOM, entity, and source metadata
  attached to shared `Chunk` objects.
- `metadata_explained.md`: field guide for using URL chunk metadata in
  retrieval, deduplication, conflict detection, evaluation, and frontend review.
- `schema.md`: short Vietnamese-friendly metadata schema for rule-based
  integration.
- `quality/diagnostics.py`: URL-local parse/chunk quality diagnostics.
- `quality/strategy.py`: page-type detection, render-required signals, latency
  budgets, and quality-gated parser selection.
- `chunking/`: deterministic Markdown chunking strategies.
- `artifact.py`: persistence for staged inspection files such as
  `source.html`, `cleaned.html`, `parsed_sections.txt`, `extracted.md`,
  `parsed.md`, `quality.json`, `chunks.jsonl`, and `manifest.json`.
- `evaluation/scoring.py`: pass/fail scoring against curated golden data.
- `golden_data/`: curated URL run lists, templates, and golden expectations.
- `guide/demo/url-golden-review-react/`: React demo that runs the current URL
  loader against golden data and displays URL quality metadata.
- `TODO_scripts.md`: reminders for operational scripts that may upload,
  backfill, or inspect URL-ingested data.
- `TODO_dedup.md`: reminders for the metadata handoff to duplicate/conflict
  workflows without moving those decisions into URL ingestion.
- `TODO_rulebased.md`: deterministic plan for capturing JavaScript interaction
  states such as color, image, and price changes on configurator/booking pages.
- `TODO_LLM.md`: evidence-first plan for LLM-assisted review of dynamic
  interaction artifacts without trusting hallucinated facts.
- `benchmarking/`: small local parser benchmark helpers.
- `tests/`: URL ingestion unit tests.
- `data/`: local generated artifacts. This is for inspection and should not be
  treated as the committed source of truth.

Folder `__init__.py` files should stay small and only re-export public helpers
from the named modules above. Put new implementation in named files so each
stage stays easy to review.

## Quality-First Parse Strategy

The default URL path is:

1. `load_url_with_artifacts(url)` validates that the input is an absolute HTTP
   or HTTPS URL and rejects PDF inputs.
2. Live URL ingestion fetches static HTML first, classifies page type, detects
   dynamic React/Next/root-container signals, and builds a static parser
   candidate.
3. The static candidate is scored before acceptance. Static article/policy/FAQ
   pages can pass quickly when useful content is present.
4. Product detail, product listing, homepage product listing, booking, vehicle
   configurator, and dynamic application pages require a rendered-parser attempt
   when browser extraction is enabled.
5. The optional Playwright extractor renders the page, expands tab/accordion
   content, walks the DOM in document order, extracts H1-H6 headings, pairs
   product specs, and normalizes UI noise before chunking.
6. Static and rendered candidates are compared with `UrlQualityGate`; the
   higher-quality candidate wins even when it costs more latency.
7. If the primary rendered attempt fails, rendering retries with a lighter
   `domcontentloaded` wait strategy before static fallback is accepted.
8. When a render cache directory is provided, rendered Markdown, rendered HTML,
   extractor payload, and a manifest are reused for repeated verification runs.
9. If rendering is disabled or fails, static fallback chunks are returned only
   with explicit `url_quality_gate.accepted = false` / rejected or partial
   metadata when the quality score does not pass.
10. The loader removes common script/config/cookie boilerplate from Markdown.
11. The loader chunks global Markdown with heading-aware metadata.
12. DOM, entity, source, and quality helpers enrich `Chunk.metadata` with URL
    metadata such as original URL, canonical URL, language, page type, semantic
    block counts, entity names, and URL-local quality diagnostics.

The Crawl-link-style extractor is preferred because it preserves rendered content
that simple static parsers often miss, especially tabs, accordions, product
specs, price blocks, and H4-H6 detail headings. Trafilatura remains as a fallback
for pages where the DOM extractor cannot produce useful Markdown.

Quality is intentionally first and latency second. Page-type latency budgets are
recorded in `url_quality_gate.latency_budget_seconds` and passed into
`RenderOptions.timeout_seconds` for Playwright rendering. Product pages get more
time than simple article/policy pages because missing prices, specs, tabs, or
accordions is worse than a slower ingestion run.

The evaluation runner stores render cache files under its report output
directory, so live verification can be repeated without paying the full browser
cost for pages that have already rendered successfully.

## Metadata For Dedupe And Retrieval

URL chunks provide the metadata needed by downstream duplicate detection and
knowledge-quality modules, without owning merge/conflict decisions:

- `page_hash`: stable hash of the normalized parsed page Markdown.
- `content_hash`: stable hash of the normalized chunk text.
- `dedupe_hash`: aggressively normalized chunk hash for exact duplicate
  blocking.
- `normalized_text`: normalized chunk text used for hashing.
- `entity_type`, `entity_name`, `entity_hash`, `vehicle_segment`, and
  `attribute_group`: URL-owned hints for blocking and retrieval filtering.
- `is_noise` and `retrieval_weight`: local signals for downranking footer,
  cookie, navigation, and other low-value chunks.
- `url_quality` and `url_quality_gate`: parser/chunk diagnostics and the final
  static-vs-rendered selection decision.

## Chunking Strategy

The default chunking method is `hierarchical-markdown-subsection-overlap`.

The strategy is designed for Markdown:

1. Split global Markdown into heading-scoped sections.
2. Detect implicit subsections such as numbered lines (`1. Specs`) and bold
   lead labels (`**Battery:**`).
3. Preserve heading and subsection context in `section_path`, `full_path`,
   `depth`, `part_index`, and `part_total` metadata.
4. Merge short sibling blocks under the same parent when they fit the chunk
   budget.
5. Split long blocks by paragraph, line, then sentence-like boundaries with a
   small character overlap.
6. Count tokens with `tiktoken` when available, falling back to word counts.

This keeps chunks more useful for RAG than plain character slicing because
headings, section paths, product-spec labels, and split positions are less
likely to be lost.

## Artifacts

When `data_artifact_dir` is provided, ingestion writes:

- `source.html`: the static or rendered HTML snapshot used by the selected
  parser candidate.
- `cleaned.html`: semantic HTML rebuilt from final cleaned Markdown, aligned
  with the content used to create chunks.
- `parsed_sections.txt`: visible text sections parsed from the HTML snapshot.
- `extracted.md`: Markdown before URL noise cleanup.
- `parsed.md`: final cleaned Markdown used for chunking and inspection.
- `quality.json`: URL quality and quality-gate diagnostics when available.
- `chunks.jsonl`: serialized shared `Chunk` records.
- `manifest.json`: run metadata, source metadata, artifact paths, parser name,
  stage paths, and chunk count.

Example:

```python
from pathlib import Path

from agentic_rag.ingestion.url.loader import load_url_with_artifacts

document = load_url_with_artifacts(
    "https://example.com/article",
    data_artifact_dir=Path("src/agentic_rag/ingestion/url/data"),
    run_id="example-url-run",
)

print(len(document.chunks))
print(document.artifacts.run_dir if document.artifacts else None)
```

## RAG Suitability

URL chunks use the shared `agentic_rag.core.contracts.Chunk` contract. This makes
them directly usable by retrieval and generation modules without importing
private URL ingestion details.

For RAG, inspect:

- chunk text readability,
- section metadata,
- URL/canonical URL metadata,
- chunk length distribution,
- whether top retrieval results contain content rather than boilerplate.

If retrieval ranks footer, cookie, script, or related-post chunks too highly,
improve ingestion-side filtering before changing retrieval or generation.

## Quality Gate

Run the module tests after changing URL ingestion:

```bash
uv run pytest src/agentic_rag/ingestion/url/tests -q
```

Run the project gate before opening or updating a PR:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```
