# URL Ingestion Golden Verification Report

Run date: 2026-06-13

## Scope

This verification ran the live URL ingestion evaluator against the committed
VinFast golden dataset:

- URL list: `src/agentic_rag/ingestion/url/golden_data/Link_data.txt`
- Golden expectations: `src/agentic_rag/ingestion/url/golden_data/vinfast_url_golden_samples.json`
- Output directory: `guide/reports/url_ingestion_golden_verification_20260613/`
- Browser extractor: enabled

Command:

```powershell
uv run python -m agentic_rag.ingestion.url.evaluation.runner --output-dir guide/reports/url_ingestion_golden_verification_20260613 --no-resume
```

## Result

The full golden run completed without crawler/runtime errors, but the complete
dataset is not green yet.

| Metric | Value |
| --- | ---: |
| Golden URLs | 322 |
| Golden samples | 322 |
| Processed | 322 |
| Passed | 219 |
| Failed | 103 |
| Errors | 0 |
| Skipped | 0 |
| Pass rate | 68.01% |
| Average URL elapsed time | 14.699 seconds |
| Total URL elapsed time | 4,732.997 seconds |
| Slowest URL elapsed time | 30.959 seconds |

Run timestamps from `base_summary.md`:

- Started: `2026-06-13T09:45:44.871178+00:00`
- Completed: `2026-06-13T11:04:38.452347+00:00`

## Failure Breakdown

Failures by domain:

| Domain | Failed URLs |
| --- | ---: |
| `vinfastauto.com` | 58 |
| `shop.vinfastauto.com` | 45 |

Top failing check types:

| Check | Count |
| --- | ---: |
| `required_text_snippet` | 56 |
| `chunk_count` | 34 |
| `preserve_canonical_url` | 29 |
| `forbidden_text_snippet` | 27 |
| `language_expected` | 27 |
| `strip_navigation` | 22 |
| `required_metadata_keys` | 20 |
| `preserve_query_params` | 6 |

Top missing required snippets:

| Missing snippet | Count |
| --- | ---: |
| `gia` / `gia ban` price wording | 28 |
| `VND` price currency wording | 22 |
| Empty snippet expectation | 6 |

Top forbidden snippets still appearing:

| Forbidden snippet | Count |
| --- | ---: |
| `Home` | 15 |
| `Cookie` | 6 |
| `Support` | 5 |
| `Dang nhap` / login text | 1 |

## Interpretation

- The live ingestion path is stable enough to crawl the whole golden set:
  `322/322` URLs produced evaluation records and there were `0` runtime errors.
- The previously verified focused subset remains the clean confidence check:
  `guide/reports/url_ingestion_verification_subset_complete_final2/` passed
  `12/12` selected URLs.
- Most `shop.vinfastauto.com` failures are near-pass product pages where live
  output is missing price-related snippets. These should be triaged as either
  dynamic content extraction gaps or overly strict live golden expectations.
- Several `vinfastauto.com` failures are chunk-count, canonical/language
  metadata, and residual navigation/footer cleanup issues.
- Six FAQ/product samples have an empty required snippet expectation and should
  be corrected in golden data before treating them as ingestion failures.

## Artifacts

- Full result stream:
  `guide/reports/url_ingestion_golden_verification_20260613/base_results.jsonl`
- Machine summary:
  `guide/reports/url_ingestion_golden_verification_20260613/base_summary.json`
- Human summary:
  `guide/reports/url_ingestion_golden_verification_20260613/base_summary.md`
- Render cache:
  `guide/reports/url_ingestion_golden_verification_20260613/render_cache/`
- Runner stdout:
  `guide/reports/url_ingestion_golden_verification_20260613/runner_stdout.log`
- Runner stderr:
  `guide/reports/url_ingestion_golden_verification_20260613/runner_stderr.log`

## Follow-Up

1. Move unstable live price requirements from base golden checks into optional
   diagnostics or the advanced scorecard unless a static fixture proves that
   price text should always be extracted.
2. Fix empty required snippets in the FAQ/product golden samples.
3. Tighten cleanup for residual `Home`, `Cookie`, `Support`, and login text on
   main-site pages.
4. Inspect canonical URL and language metadata failures where rendered fallback
   or redirect handling changes the final URL.
5. Re-run a failed-only subset after triage, then run the full golden set again.
