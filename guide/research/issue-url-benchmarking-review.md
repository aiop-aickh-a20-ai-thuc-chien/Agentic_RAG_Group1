# Review URL ingestion benchmarking helpers

## Context

This issue is for reviewing the current URL ingestion benchmarking helpers in:

```text
src/agentic_rag/ingestion/url/benchmarking
```

Current files:

```text
benchmarking/
  __init__.py
  cli.py
  custom_benchmark.py
```

Related tests:

```text
src/agentic_rag/ingestion/url/tests/benchmarking
```

## Current Purpose

The benchmarking helpers are local, deterministic, and dependency-light. They are intended to help compare URL/HTML parser behavior before adding heavier dependencies or live benchmark services.

They currently support:

- running built-in custom HTML benchmark cases
- parsing one local HTML file into benchmark-friendly JSON
- reporting parser score, matched terms, missing terms, detected sections, and extracted character count
- running without network access, API keys, external vector stores, or paid services

## Current CLI Shape

Run custom local benchmark cases:

```bash
uv run python -m agentic_rag.ingestion.url.benchmarking.custom_benchmark
```

Or via the benchmark CLI:

```bash
uv run python -m agentic_rag.ingestion.url.benchmarking.cli custom
```

Parse one local HTML file:

```bash
uv run python -m agentic_rag.ingestion.url.benchmarking.cli parse-html --html-file path/to/page.html
```

## Questions For Review

Please comment if anything should change before this becomes the team baseline.

Specific things to review:

- Is the folder name `benchmarking` OK?
- Is the file name `custom_benchmark.py` clear enough?
- Should the CLI command be `custom`, `local`, `html`, or something else?
- Are the current benchmark outputs enough for Sprint 1?
- Should benchmark cases include Vietnamese HTML samples?
- Should benchmark cases compare multiple parser adapters later, such as stdlib parser vs Trafilatura vs BeautifulSoup?
- Should benchmark result files be saved to a standard folder, such as `guide/results` or `artifacts/benchmarking`?

## Recommendation

Keep the current implementation local and deterministic for Sprint 1:

```text
custom_benchmark.py -> small fixed parser benchmark cases
cli.py              -> wrapper for benchmark and local HTML parsing commands
tests/benchmarking -> deterministic tests for CLI and benchmark output
```

Only add heavier parser comparisons after the URL ingestion baseline is stable.
