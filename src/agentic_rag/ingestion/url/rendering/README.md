# Rendering

Target home for dynamic-page extraction.

Responsibilities:

- Run optional browser rendering.
- Expand tabs, accordions, and lazy UI when supported.
- Decide when to fall back to static HTML.
- Preserve diagnostics that explain which extraction path was used.

Current code: `src/agentic_rag/ingestion/url/extractor.py`.

## Crawlee renderer

Ill-structured dynamic pages can use the optional Crawlee/Apify Playwright path:

```powershell
uv sync --extra crawling
playwright install
```

When a URL profile requires rendering, the loader tries Crawlee first and falls
back to the direct Playwright extractor if Crawlee is unavailable or fails.
Crawlee render options support `timeout_seconds=None` for an explicit unbounded
wait. When a timeout is provided, slow or inactive interactive pages are retried
with sleeps that are bounded by the remaining timeout budget.
