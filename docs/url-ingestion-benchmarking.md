# URL Ingestion Benchmarking

Benchmark helpers for URL and HTML ingestion live under:

```text
src/agentic_rag/ingestion/url/benchmarking
```

## Built-in Local Benchmark

Run deterministic local HTML parser benchmark cases:

```bash
uv run python -m agentic_rag.ingestion.url.benchmarking.famous_benchmark
```

Write the benchmark output to JSON:

```bash
uv run python -m agentic_rag.ingestion.url.benchmarking.famous_benchmark --output benchmark.json
```

## Local HTML Parser Output

Parse one local HTML file into benchmark-friendly JSON:

```bash
uv run python -m agentic_rag.ingestion.url.benchmarking.cli parse-html --html-file path/to/page.html
```

The output includes:

- parser name
- source path or URL
- source type
- extracted character count
- detected sections
- cleaned text

These helpers are intentionally local and dependency-light. They do not fetch network URLs or require
API keys, so they can run in CI and unit tests.
