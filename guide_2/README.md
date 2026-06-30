# Ingestion Review Demo

This demo provides a simple "pseudo-front-end" to inspect the ingestion output for a given source (e.g., a URL). It is designed to help review the results of the metadata-focused ingestion pipeline as planned in `guide_2`.

The tool runs the appropriate ingestion loader from `src/agentic_rag/ingestion/` and generates a single `review.html` file.

## What it shows

The HTML report is a self-contained file that shows:

- **Chunks (Priority):** A table displaying each generated chunk, including its text and full metadata. This is the primary focus for review.
- **Parsed Markdown (Debug):** The final normalized Markdown content that was used for chunking.
- **JSON Artifacts (Debug):** Other JSON files generated during ingestion, such as `quality.json` and `manifest.json`.

These debug sections are collapsible to keep the focus on the chunks.

## How to run

Run the review from the repository root.

### For a URL

```bash
uv run python guide_2/demo/review.py <URL>
```

Example:
```bash
uv run python guide_2/demo/review.py https://vinfastauto.com/vn_vi/ve-chung-toi
```

### Output

The output is written to `guide_2/demo/output/review.html`. You can open this file in your browser to inspect the results.