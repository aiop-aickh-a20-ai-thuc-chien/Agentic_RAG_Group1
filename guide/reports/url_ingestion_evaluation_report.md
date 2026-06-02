# URL/Text Ingestion Evaluation Report

Source evaluated:

`src/agentic_rag/ingestion/url`

Related benchmark template:

`guide/reports/ingestion_benchmark.md`

## Hiện tại URL/Text đang hoạt động thế nào

Flow hiện tại:

```text
URL input
-> urllib.request fetch with User-Agent
-> stdlib HTMLParser extracts title + h1/h2/h3 sections
-> removes script/style/nav/footer/header/aside
-> normalizes whitespace
-> deterministic character-overlap chunking
-> returns shared Chunk objects
-> optionally writes parsed.md, chunks.jsonl, manifest.json
```

Entry points:

- `load_url_chunks(url)`
- `load_html_chunks(html, source=..., source_url=...)`
- `load_text_chunks(text, source=...)`

Artifacts:

- `src/agentic_rag/ingestion/url/data/artifacts/<source>/<run_id>/parsed.md`
- `src/agentic_rag/ingestion/url/data/artifacts/<source>/<run_id>/chunks.jsonl`
- `src/agentic_rag/ingestion/url/data/artifacts/<source>/<run_id>/manifest.json`

Chunk metadata currently includes:

- `source`
- `source_type`
- `file_name`
- `url`
- `page`
- `section`
- `title`
- `fetched_at`
- `content_hash`
- `chunk_index`
- `chunking_method`
- `chunking_provider`
- `chunking_model`

Optional model-assisted chunking exists in:

`src/agentic_rag/ingestion/url/model_chunking.py`

It supports OpenAI/Gemini adapters through injected clients and deterministic fake-client tests. Default ingestion does not call external APIs.

## Trace/log cho thấy vấn đề gì

Observed real-data tests:

1. VinFast motorbike listing

```text
URL: https://shop.vinfastauto.com/vn_vi/xe-may-dien-vinfast.html
listing chunks: 16
detail pages discovered: 9
detail chunk counts: 4, 4, 34, 36, 38, 19, 19, 6, 16
```

Result:

- Listing page and detail pages were fetched.
- `parsed.md`, `chunks.jsonl`, and `manifest.json` were created.
- Clickable image/link discovery was tested manually outside the core parser.
- One discovered detail URL appeared to redirect/finalize back to the listing URL.

2. Vinhomes Smart City article

```text
URL: https://market.vinhomes.vn/blog/dia-chi-vinhomes-smart-city
initial result: MemoryError
fix: split_markdown now forces start to advance when overlap would stall
after fix: 20 chunks
URL test suite: 26 passed
```

Result:

- The chunking loop had an edge case where overlap could prevent progress.
- A regression test was added for split progress.
- The URL was ingested successfully after the fix.

3. Quality gate observations

```text
uv --directory src/agentic_rag/ingestion/url run ruff format --check .
uv --directory src/agentic_rag/ingestion/url run ruff check .
uv --directory src/agentic_rag/ingestion/url run pytest -q
uv --directory src/agentic_rag/ingestion/url run mypy
```

Result:

- URL subproject checks passed after adding `pyproject.toml` and `uv.lock`.
- Root quality gate also passed in the latest checked run: `88 passed`.

## Điểm tốt hiện tại

- Fetch has a User-Agent and timeout.
- Invalid non-HTTP URLs are rejected early.
- Redirect final URL is used as `source` and `url` for `load_url_chunks`.
- Parser removes common boilerplate tags.
- Section metadata is extracted from `h1`, `h2`, and `h3`.
- Chunk IDs are deterministic from source, section, and index.
- Chunk metadata follows the shared `Chunk` contract.
- Text input supports direct ingestion through `load_text_chunks`.
- Empty text returns no chunks instead of invalid empty chunks.
- Artifact output is explicit and local-only.
- `data/.gitignore` prevents generated artifacts from being committed.
- Optional OpenAI/Gemini chunking can be tested without API keys by injecting fake clients.
- URL package has its own subproject tooling: `pyproject.toml` and `uv.lock`.
- Vinhomes `MemoryError` bug is fixed by guaranteeing chunk split progress.

## Điểm yếu hiện tại

- Main-content extraction is still a lightweight stdlib baseline, not production-grade.
- `trafilatura` is not used yet.
- No JS rendering support, so dynamic pages may be incomplete.
- No canonical URL extraction from `<link rel="canonical">` or Open Graph metadata.
- No `publish_date`, `author`, `description`, or `language` extraction.
- Current `parsed.md` is Markdown-like but not a full structural Markdown conversion.
- Chunking is character-based, not token-aware.
- `tiktoken` is not added yet.
- Chunking is not sentence-aware.
- Current parser does not discover images, PDF links, `iframe`, or `object` assets as structured metadata.
- URL ingestion does not route direct PDF responses to PDF ingestion yet.
- Boilerplate can still leak from menu, CTA, footer, and repeated product blocks.
- `source_url` and final URL behavior should be made explicit in manifest for redirect audit.

## Giải pháp cải tiến đề xuất

Short-term improvements:

1. Add canonical metadata extraction:
   - `<link rel="canonical">`
   - `og:url`
   - `og:title`
   - `og:description`
   - article published date if present

2. Add asset discovery:
   - images: `src`, `alt`, `title`, nearby caption
   - clickable image target URL
   - PDF links
   - `iframe` and `object` source URLs

3. Improve manifest:
   - keep `input_url`
   - keep `final_url`
   - keep `canonical_url`
   - keep discovered related assets

4. Add direct PDF detection:
   - if `Content-Type` is `application/pdf`
   - or URL path ends with `.pdf`
   - route to PDF ingestion instead of HTML parser

5. Add `trafilatura` as default extractor with stdlib fallback.

Medium-term improvements:

1. Add heading-aware Markdown chunking.
2. Add sentence-aware split fallback.
3. Add `tiktoken` for token-aware chunking when using OpenAI embedding/generation.
4. Add duplicate chunk detection by content hash.
5. Add real benchmark fixtures for Vietnamese pages.

Advanced improvements:

1. Add Crawl4AI or Playwright for JS-rendered pages.
2. Add OCR or OpenAI/Gemini vision for important image-only content.
3. Add model-assisted chunk grouping only as an optional post-processing strategy.

## Tool/framework nên thử

Recommended order:

1. `trafilatura`
   - Best next default for static content extraction.
   - Useful for cleaner main text, metadata, and Markdown-like output.

2. `readability-lxml`
   - Good fallback comparison for article pages.
   - Lighter than browser rendering.

3. `tiktoken`
   - Use for token-aware chunk sizing.
   - Especially useful for OpenAI embedding/generation budgets.

4. Crawl4AI or Playwright
   - Use only for pages where raw HTML misses JS-rendered content.
   - Heavier dependency/runtime, should be team-approved.

5. OpenAI/Gemini vision
   - Use only for images that carry important retrievable information.
   - Store extraction method and confidence in metadata.

## Thay đổi nào nên làm ngay

These are low-risk and should not break the shared `Chunk` contract:

- Add canonical/Open Graph metadata extraction.
- Add `original_url`, `final_url`, and `canonical_url` fields in manifest.
- Add asset discovery for images/PDF/iframe/object without ingesting them automatically.
- Add tests for direct PDF URL detection and asset discovery.
- Add duplicate chunk hash checks in artifact/report utilities.
- Keep current stdlib parser as fallback.

## Thay đổi nào cần họp nhóm trước khi code

These affect dependencies, runtime, or schema decisions:

- Add `trafilatura` as a runtime dependency.
- Add `tiktoken` as a runtime dependency.
- Add browser runtime such as Playwright/Crawl4AI.
- Decide whether URL ingestion should automatically crawl child URLs.
- Decide whether image OCR/vision output should become first-class chunks.
- Decide final metadata schema for assets, canonical URLs, and child sources.
- Decide routing contract between URL ingestion and PDF ingestion for PDF links.

## Scorecard

| Hạng mục | Điểm (0-10) | Ghi chú |
| --- | ---: | --- |
| Fetch & parse | 7 | Fetch works with timeout/User-Agent; no canonical metadata yet. |
| Content extraction | 5 | Removes basic tags, but boilerplate still leaks and no trafilatura yet. |
| Chunking quality | 6 | Stable deterministic chunks and MemoryError fixed; not sentence/token-aware. |
| Metadata completeness | 7 | Required contract fields present; missing publish date/language/author/canonical. |
| Edge case handling | 6 | Invalid URL/blank text handled; PDF/assets/JS pages not fully handled. |
| Retrieval readiness | 6 | Chunks are usable, but token range and duplicate checks are not enforced. |
| **Total** | **37/60** | Solid baseline, needs stronger extraction and metadata before production use. |

## Final recommendation

Keep the current implementation as the deterministic baseline. The next implementation slice should focus on:

1. `trafilatura` extraction with stdlib fallback.
2. canonical/Open Graph metadata.
3. asset discovery for image/PDF/iframe/object.
4. token-aware chunking with `tiktoken`.
5. explicit PDF routing rather than parsing PDF URLs as HTML.
