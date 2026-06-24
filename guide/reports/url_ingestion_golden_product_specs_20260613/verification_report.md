# URL Ingestion Golden Product-Spec Evaluation Report

Run date: 2026-06-13

## Scope

This run verified the full VinFast URL golden dataset after adding
`product_spec_checks` support to the URL golden evaluator.

- URL list: `src/agentic_rag/ingestion/url/golden_data/Link_data.txt`
- Golden expectations: `src/agentic_rag/ingestion/url/golden_data/vinfast_url_golden_samples.json`
- Output directory: `guide/reports/url_ingestion_golden_product_specs_20260613/`
- Browser extractor: enabled

Command:

```powershell
uv run python -m agentic_rag.ingestion.url.evaluation.runner --output-dir guide/reports/url_ingestion_golden_product_specs_20260613 --no-resume
```

## Result

| Metric | Value |
| --- | ---: |
| URLs selected | 322 |
| Processed | 322 |
| Passed | 233 |
| Failed | 89 |
| Errors | 0 |
| Skipped | 0 |
| Pass rate | 72.36% |
| Average URL elapsed time | 13.397 seconds |
| Total URL elapsed time | 4,313.972 seconds |
| Slowest URL elapsed time | 33.074 seconds |

Run timestamps from `base_summary.md`:

- Started: `2026-06-13T12:09:40.741456+00:00`
- Completed: `2026-06-13T13:21:35.825922+00:00`

## Failure Breakdown

Failures by domain:

| Domain | Failed URLs |
| --- | ---: |
| `shop.vinfastauto.com` | 45 |
| `vinfastauto.com` | 44 |

Top failing check types:

| Check | Count |
| --- | ---: |
| `required_text_snippet` | 57 |
| `forbidden_text_snippet` | 23 |
| `chunk_count` | 22 |
| `strip_navigation` | 19 |
| `preserve_canonical_url` | 17 |
| `language_expected` | 16 |
| `required_metadata_keys` | 10 |
| `preserve_query_params` | 6 |

## Notes

- The full live crawl completed with `0` runtime errors.
- The committed VinFast golden JSON does not yet enable `product_spec_checks`,
  so this run validates backward compatibility for the existing base contract.
- `product_spec_checks` are now available in templates for future strict
  product/model spec fixtures.
- Compared with the previous full live baseline
  `guide/reports/url_ingestion_golden_verification_20260613/`, the pass count
  improved from `219` to `233`.

## Artifacts

- Results JSONL:
  `guide/reports/url_ingestion_golden_product_specs_20260613/base_results.jsonl`
- Machine summary:
  `guide/reports/url_ingestion_golden_product_specs_20260613/base_summary.json`
- Human summary:
  `guide/reports/url_ingestion_golden_product_specs_20260613/base_summary.md`
- Render cache:
  `guide/reports/url_ingestion_golden_product_specs_20260613/render_cache/`
- Runner stdout:
  `guide/reports/url_ingestion_golden_product_specs_20260613/runner_stdout.log`
- Runner stderr:
  `guide/reports/url_ingestion_golden_product_specs_20260613/runner_stderr.log`
