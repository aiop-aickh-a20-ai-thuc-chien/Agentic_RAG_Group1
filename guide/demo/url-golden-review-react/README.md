# URL Golden Review React Demo

React review app for the current URL ingestion contract.

Use this demo when you want to run URLs from
`src/agentic_rag/ingestion/url/golden_data/Link_data.txt`, compare the output
against `vinfast_url_golden_samples.json`, and inspect current URL ingestion
metadata such as `url_quality`, `url_quality_gate`, `page_type`,
`product_specs`, `is_noise`, and `retrieval_weight`.

The older `guide/demo/url-crawl-review` app is still useful for legacy crawl
diagnosis, but it expects Crawl4AI-style fields. This demo talks directly to
the current URL loader and golden-data scorer.

## Run

From the repository root:

```bash
node guide/demo/url-golden-review-react/server.js
```

Then open:

```text
http://127.0.0.1:8784
```

If port `8784` is already used:

```bash
$env:PORT=8785; node guide/demo/url-golden-review-react/server.js
```

The browser uses React from a CDN. The backend itself has no npm dependency and
starts a fresh Python process through `uv run python` for each review run, so it
uses the same URL ingestion code as the CLI.

## What It Checks

- Loads the 322 golden URLs from `Link_data.txt`.
- Shows whether each URL has a matching golden sample.
- Runs `load_url_with_artifacts()` with current URL ingestion settings.
- Scores the result with `evaluate_sample()`.
- Shows hard failing checks, metadata, product specs, chunk previews, and
  artifact paths.
- Allows arbitrary smoke URLs. URLs that are not in the golden JSON are marked
  `unscored` but still show ingestion diagnostics and chunks.

## `ve-chung-toi` Smoke Check

The demo includes a quick-run button for:

```text
https://vinfastauto.com/vn_vi/ve-chung-toi
```

The old demo failed this URL because static HTML parsing produced only:

```markdown
# Gioi Thieu Ve VinFast
```

That title-only Markdown produced zero chunks. Current URL ingestion now
augments low-signal title-only pages with metadata descriptions and meaningful
image alt text before chunking. In the new demo, inspect the result for:

- nonzero `chunk_count`,
- nonzero `usable_chunk_count`,
- sections such as `Page Summary` or `Visual Content`,
- a populated `url_quality` / `url_quality_gate` block.

## API

```text
GET  /api/health
GET  /api/golden
POST /api/run
```

`POST /api/run` accepts:

```json
{
  "urls": ["https://vinfastauto.com/vn_vi/ve-chung-toi"],
  "no_browser": true
}
```

Generated artifacts are written under:

```text
guide/demo/url-golden-review-react/output/
```

The folder is ignored by the demo-local `.gitignore`.
