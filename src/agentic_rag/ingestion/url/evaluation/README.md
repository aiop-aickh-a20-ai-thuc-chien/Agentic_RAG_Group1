# Evaluation

URL evaluation compares ingestion output with golden expectations from
`url/golden_data`.

## Current Golden Dataset

Use:

- `src/agentic_rag/ingestion/url/golden_data/Link_data.txt`
- `src/agentic_rag/ingestion/url/golden_data/vinfast_url_golden_samples.json`

The JSON is not a byte-for-byte snapshot. It is a pass/fail contract for broad
ingestion quality:

- chunk count stays within expected bounds,
- all chunks carry required metadata,
- required content snippets appear,
- forbidden navigation/footer/cookie snippets do not appear,
- product/spec metadata appears when a sample enables `product_spec_checks`,
- canonical URL and language metadata are preserved when required,
- repeated UI text is not dominant,
- enabled entity-boundary checks pass.

Optional snippets are diagnostics only. They help reviewers understand whether a
page captured nice-to-have text, but they do not fail a sample.

## API

```python
from agentic_rag.ingestion.url.evaluation import (
    evaluate_sample,
    load_golden_dataset,
)

dataset = load_golden_dataset(
    "src/agentic_rag/ingestion/url/golden_data/vinfast_url_golden_samples.json"
)
sample = dataset.samples[0]
result = evaluate_sample(sample, markdown=loaded.markdown, chunks=loaded.chunks)

assert result.passed
```

For multiple URL outputs, use `evaluate_results_by_url(dataset, results_by_url)`,
where each value is a `(markdown, chunks)` pair.

## Base Crawl Run

To run the base evaluation against every URL in `Link_data.txt`:

```powershell
uv run python -m agentic_rag.ingestion.url.evaluation.runner
```

The runner:

- reads `src/agentic_rag/ingestion/url/golden_data/Link_data.txt`,
- crawls each URL with `load_url_with_artifacts()`,
- evaluates the result with `evaluate_sample()`,
- writes one JSONL result per URL as it progresses,
- writes `base_summary.json` and `base_summary.md` at the end.

Default output:

```text
guide/reports/url_ingestion_base_evaluation/
```

For a quick smoke run:

```powershell
uv run python -m agentic_rag.ingestion.url.evaluation.runner --limit 3 --no-browser
```

Use `--no-browser` when you want a faster static-fetch baseline. Omit it when
you want the full URL ingestion path with browser extraction. The runner resumes
from `base_results.jsonl` by default; pass `--no-resume` to start over.

## Pass/Fail Policy

Hard failures use `severity="error"`:

- chunk count outside min/max,
- missing required metadata keys,
- missing required snippets,
- forbidden snippets present,
- required product-spec metadata missing or mismatched,
- failed normalization checks,
- enabled entity-boundary checks failing.

Non-failing diagnostics use `severity="info"`:

- optional snippet presence or absence,
- optional product-spec checks,
- disabled entity-boundary checks.

## Product Spec Checks

Samples can require structured product metadata emitted by URL ingestion:

```json
{
  "name": "VF 8 driving range",
  "field": "driving_range",
  "expected_contains": "471 km",
  "required": true
}
```

Supported fields include `model_name`, `price`, `driving_range`,
`battery_capacity`, `charging_time`, and any key stored under
`Chunk.metadata["product_specs"]`. The evaluator also accepts shortcut metadata
such as `product_model`, `product_price`, `driving_range`, `battery_capacity`,
and `charging_time`.

## Advanced Scoring

Use `src/agentic_rag/ingestion/url/golden_data/advanced_template/advanced_scorecard.json`
when pass/fail is not enough.

Advanced scoring should be layered on top of this evaluator:

1. Call `evaluate_sample()` or `evaluate_results_by_url()`.
2. Treat failing `severity="error"` checks as hard failures.
3. If the base result passes, calculate weighted dimensions such as content
   coverage, noise control, metadata fidelity, chunk shape, DOM/entity readiness,
   and artifact reviewability.

The advanced template is intentionally data-only. It describes how to score
without making live URL tests overly rigid.

Generated live-crawl reports should stay under `guide/demo/` or
`guide/reports/`.
