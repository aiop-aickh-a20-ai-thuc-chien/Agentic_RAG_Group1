# URL Ingestion Supported-Type Golden Verification

Date: 2026-06-13

## Scope

- Updated URL ingestion documentation to state the currently supported input
  and page types.
- Added URL-local reminder files for script/database operations and dedup
  handoff work.
- Ran the focused URL ingestion quality checks.
- Ran the full browser-backed golden-data evaluation from
  `src/agentic_rag/ingestion/url/golden_data/Link_data.txt`.

## Supported Inputs

URL ingestion currently supports:

- HTTP(S) HTML pages.
- Static article, blog, policy, legal, warranty, and FAQ pages.
- Browser-rendered product detail, product listing, homepage product listing,
  booking/deposit, configurator, interactive, and dynamic React/Next pages when
  Playwright extraction is enabled.
- Direct HTML fixture strings through `load_html_chunks()` and
  `load_html_with_artifacts()`.
- Plain text strings through `load_text_chunks()`.

URL ingestion rejects:

- PDF-looking URLs.
- PDF response content types.
- Non-HTTP(S) URLs.

PDF data should be diverted to `src/agentic_rag/ingestion/pdf`.

## Golden URL Type Inventory

The current URL classifier sees these page types in `Link_data.txt`:

| Page type | URL count |
| --- | ---: |
| `article` | 5 |
| `booking_flow` | 15 |
| `faq` | 29 |
| `generic` | 134 |
| `policy` | 17 |
| `product_detail` | 106 |
| `product_listing` | 16 |

Total: 322 URLs.

## Verification Commands

```powershell
uv run ruff format --check src/agentic_rag/ingestion/url
uv run ruff check src/agentic_rag/ingestion/url
uv run pytest src/agentic_rag/ingestion/url/tests -q
uv run python -m agentic_rag.ingestion.url.evaluation.runner --output-dir guide/reports/url_ingestion_golden_types_20260613 --no-resume
```

## Results

- Format check: passed, 43 files already formatted.
- Ruff lint: passed.
- URL ingestion tests: passed, 78 tests.
- Full golden evaluation:
  - Started: 2026-06-13T14:03:52.203897+00:00.
  - Completed: 2026-06-13T15:11:55.842696+00:00.
  - Browser extractor: enabled.
  - URLs selected: 322.
  - Processed: 322.
  - Passed: 235.
  - Failed: 87.
  - Errors: 0.
  - Skipped: 0.

## Results By Page Type

| Page type | Passed | Failed |
| --- | ---: | ---: |
| `article` | 0 | 5 |
| `booking_flow` | 11 | 4 |
| `faq` | 21 | 8 |
| `generic` | 114 | 20 |
| `policy` | 9 | 8 |
| `product_detail` | 64 | 42 |
| `product_listing` | 16 | 0 |

## Failure Pattern Summary

Most failures are golden-contract misses, not crawl/runtime errors.

| Failing check | Count |
| --- | ---: |
| `required_text_snippet` | 57 |
| `forbidden_text_snippet` | 24 |
| `strip_navigation` | 20 |
| `chunk_count` | 19 |
| `preserve_canonical_url` | 14 |
| `language_expected` | 13 |
| `required_metadata_keys` | 7 |
| `preserve_query_params` | 6 |

Most common missing/forbidden snippets:

| Snippet | Count |
| --- | ---: |
| `gia` / `giá` | 29 |
| `VND` / `VNĐ` | 22 |
| `Home` | 15 |
| empty required snippet | 6 |
| `Cookie` | 5 |
| `Support` | 4 |

## Output Files

- `guide/reports/url_ingestion_golden_types_20260613/base_results.jsonl`
- `guide/reports/url_ingestion_golden_types_20260613/base_summary.json`
- `guide/reports/url_ingestion_golden_types_20260613/base_summary.md`
- `guide/reports/url_ingestion_golden_types_20260613/render_cache/`

## Notes

- The crawler path completed without runtime errors.
- The full golden dataset remains a live baseline, not a green release gate.
- Next triage should focus on product price/VND expectations, empty FAQ/product
  required snippets, residual navigation/footer snippets, canonical/query
  metadata checks, and article/policy chunk-count expectations.

