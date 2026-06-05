# Worklog - URL Ingestion

## [2026-06-03] Implementation of Hybrid Markdown-aware Chunking

Based on the recommendations from `guide/reports/vinfast_url_chunking_strategy_test.md`, the URL ingestion pipeline has been updated to improve RAG retrieval quality and reduce noise.

### Summary of Changes

1.  **Promoted Hybrid Markdown-aware Chunking as Default**:
    - Updated `src/agentic_rag/ingestion/url/loader.py` to utilize the global Markdown context by default when no specific strategy is provided.
    - This ensures that heading hierarchies (H1, H2, H3) are preserved across chunks, providing better context for retrieval compared to isolated section processing.

2.  **Added Boilerplate Noise Filtering**:
    - Implemented a new utility `_clean_markdown_noise` in `loader.py` to strip out common web UI artifacts.
    - This filters out JSON-like configuration blocks, cookie policies, and legal disclaimers that often pollute extracted content and negatively impact BM25/Dense retrieval scores.

3.  **Documentation Updates**:
    - Updated `src/agentic_rag/ingestion/url/README.md` to reflect the shift to `hybrid-markdown-aware-chunking`.
    - Added details regarding paragraph-based packing, token guardrails with `tiktoken`, and multilingual sentence splitting.

### Impacts on RAG
- **Coherence**: Chunks now respect semantic boundaries (paragraphs/headings) rather than arbitrary character windows.
- **Citations**: Enhanced metadata preservation allows retrieval to point to specific sections (`section_path`, `section_level`).
- **Accuracy**: Removal of boilerplate prevents "noise" chunks from ranking highly in retrieval results.

## [2026-06-04] Code Optimization: Removal of Optional Chunking Strategies

To optimize code complexity and reduce overhead for AI-assisted development, the optional and model-assisted chunking strategies (Tiktoken, RAGFlow, Model Chunking) have been removed from the primary ingestion flow.

### Summary of Changes
1. **Simplified API**: Removed `chunking_strategy` parameter from public loading functions in `loader.py`.
2. **Consolidated Logic**: Removed legacy branching in `load_html_with_artifacts` that supported custom strategies, making the Hybrid Markdown-aware chunking the sole path.
3. **File Cleanup**: Deleted `model_chunking.py` to remove unused LLM-assisted chunking code and reduce maintenance overhead.
4. **Final File Deletion**: Deleted `chunking/token.py` to remove the deprecated sliding-window token strategy.
5. **Architecture Cleanup**: Removed strategy protocols and metadata placeholders (`chunking_provider`, `chunking_model`) from `core.py` and `loader.py`.
6. **Export Cleanup**: Cleaned up `__init__.py` files to remove references to deleted components.
7. **Documentation Cleanup**: Removed the "Optional strategies" section from `README.md` as they are no longer supported in the codebase.

### Next Steps
- Implement specific paragraph-based packing logic in `src/agentic_rag/ingestion/url/chunking/markdown.py`.
- Add unit tests for the noise filtering regex patterns.

## [2026-06-04] Hotfix: Crawl4AI Default URL Crawler

This hotfix adds Crawl4AI as the default URL crawling path so URL ingestion can
handle dynamic pages, rendered cards, and same-domain child pages more accurately.

### Summary of Changes

1. **Added Crawl4AI crawler adapter**
   - Added `src/agentic_rag/ingestion/url/crawler.py`.
   - Uses Crawl4AI `AsyncWebCrawler` through a synchronous wrapper because the
     public URL ingestion API is currently synchronous.
   - Extracts rendered HTML, rendered Markdown, final URL, and discovered links.

2. **Made Crawl4AI the default URL fetch path**
   - Updated `loader.py` so `_fetch_url()` tries Crawl4AI first.
   - If Crawl4AI, browser runtime, or async context is unavailable, the loader
     falls back to the previous `urllib` static HTML fetcher.
   - This keeps deterministic CI/unit tests stable while improving live URL crawl
     quality when Crawl4AI is installed correctly.

3. **Preferred rendered Markdown for dynamic pages**
   - When Crawl4AI returns Markdown, URL ingestion uses it directly as the parse
     source.
   - The built-in HTML parser is still used for metadata, canonical URL, assets,
     and fallback behavior.
   - Parser metadata now records `crawl4ai-markdown+builtin-html-parser`.

4. **Added optional child-page crawling**
   - Added `max_child_pages` to `load_url_chunks()` and `load_url_with_artifacts()`.
   - When enabled, the loader follows same-origin child links discovered by
     Crawl4AI.
   - External links, PDF links, and the original URL are skipped.

5. **Reduced duplicated chunks across parent/child pages**
   - Added chunk deduplication based on normalized text hash when parent and
     child pages are combined.
   - This prevents repeated card/listing text from being indexed multiple times
     when the parent page and child page expose the same content.

6. **Dependency updates**
   - Added `crawl4ai>=0.8,<1` to both the root project and URL subproject
     `pyproject.toml` files.

7. **Tests added**
   - Crawl4AI Markdown is preferred over static HTML.
   - Crawl4AI failure falls back to `urllib`.
   - Child-page crawl deduplicates repeated chunks.

### Expected Impact

- Dynamic URL pages should produce more accurate `parsed.md` than static HTML
  fetch alone.
- Card-heavy pages should preserve clearer rendered Markdown sections.
- Listing pages with child pages can be crawled with `max_child_pages` without
  duplicating repeated chunks.
- Existing static HTML tests remain deterministic because Crawl4AI can be mocked
  or fallback safely.

## [2026-06-04] Hotfix: Better RAG Evidence for VinFast Dynamic Pages

This update focuses on making URL chunks clearer for retrieval/generation without
changing `src/agentic_rag/retrieval` or `src/agentic_rag/generation`.

### Summary of Changes

1. **Markdown candidate quality selection**
   - `loader.py` no longer blindly prefers Crawl4AI Markdown whenever it exists.
   - The loader now scores available candidates from:
     - built-in HTML parser Markdown
     - Crawl4AI rendered Markdown
     - trafilatura Markdown
   - The selected candidate favors real content, headings, title match, and
     price values, while penalizing short shell pages, excessive images, and
     cookie/login/cart boilerplate.
   - This fixed the VF9 case where Crawl4AI sometimes returned a longer but
     less useful menu-heavy Markdown, while the built-in parser captured the
     real price/spec content.

2. **Expanded boilerplate section filtering**
   - Added section-level skips for common UI/modal areas such as:
     - cookie preference sections
     - page not found
     - cart invalid
     - forgot password / reset password
     - success registration modal
     - support/menu sections
     - shopping/menu sections
     - consultation forms
   - Goal: prevent retrieval from ranking cookie/login/modal chunks above
     product evidence.

3. **Search aliases for VinFast model names**
   - Added model aliases to chunk text for patterns such as `VF 9`:
     - `VF9`
     - `VF 9`
     - `VinFast VF9`
     - `VinFast VF 9`
     - `xe VF9`
     - `xe VF 9`
   - This helps BM25 match multilingual/implicit queries such as:
     - `Could you tell me about SPEC of VF9?`
     - `ban hay cho toi biet chi tiet ve VF9`
   - Retrieval is unchanged; ingestion provides text that retrieval can read
     more clearly.

4. **Price-card normalization**
   - Added cleanup for vehicle price-card patterns like:
     - variant name
     - `Gia ban tu`
     - current price
     - currency
     - old/crossed price
     - currency
   - The normalized Markdown now makes current and old prices explicit:

```md
- VF 9 Eco: Gia ban tu 1.229.180.000 VND; gia niem yet cu ~~1.499.000.000 VND~~.
- VF 9 Plus: Gia ban tu 1.393.180.000 VND; gia niem yet cu ~~1.699.000.000 VND~~.
```

   - The live VF9 page now preserves old crossed prices using Markdown
     strikethrough, so RAG can distinguish "current price" from "old/listed
     price".

5. **Configurator/button-page investigation**
   - Tested:
     `https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9`
   - Current URL ingestion captures some rendered configurator text, but it does
     not yet reliably normalize all button states from the dynamic configurator.
   - Playwright confirmed the live button states:
     - `VF 9 Plus tuy chon ghe co truong`: `1.731.000.000 VND`
     - `VF 9 Plus tuy chon 7 cho`: `1.699.000.000 VND`
     - `VF 9 Eco`: `1.499.000.000 VND`
   - The page's `window.carDeposit.products` structured data contains these
     values through `Products-Car-VF9` option records:
     - `NE3NV`: `1731000000`
     - `NE3MV`: `1699000000`
     - `NE3LV`: `1499000000`
   - Advanced color data also appears in the same structured data. For example,
     some advanced colors for VF9 show prices such as `1.743.000.000 VND`, which
     equals the base `1.731.000.000 VND` plus `12.000.000 VND`.

### Tests / Reports

- `uv run pytest src\agentic_rag\ingestion\url\tests -q`
  - Result: `47 passed, 1 skipped`
- `uv run ruff check src\agentic_rag\ingestion\url\loader.py src\agentic_rag\ingestion\url\tests\test_loader.py`
  - Result: passed
- Live reports created under `guide/reports`:
  - `vf9_price_ingestion_check.md`
  - `vf9_configurator_button_check.md`
  - `check_vf9_configurator_buttons.py`
  - `read_vf9_configurator_option_data.py`
  - `read_vf9_car_deposit_data.py`

### Remaining Work

- Add a dedicated extractor for VinFast configurator structured data from
  `window.carDeposit.products`.
- Convert each variant/color option into clean Markdown records, for example:

```md
- VF 9 Plus tuy chon ghe co truong: Gia xe kem pin 1.731.000.000 VND.
- VF 9 Plus tuy chon ghe co truong + mau nang cao: Gia xe kem pin 1.743.000.000 VND.
- VF 9 Plus tuy chon 7 cho: Gia xe kem pin 1.699.000.000 VND.
- VF 9 Eco: Gia xe kem pin 1.499.000.000 VND.
```

- Keep image/color assets as metadata or reference links instead of repeating
  alt text inside chunk text.

## [2026-06-04] Hotfix: Interactive Configurator Probe

This update addresses frontend usage where another feature only sends a pasted
URL to ingestion. Dynamic configurator pages can hide important price/state data
behind JS interactions, so ingestion now attempts a narrow probe before chunking.

### Summary of Changes

1. **Added interactive probe module**
   - Added `src/agentic_rag/ingestion/url/probe.py`.
   - The first supported probe targets VinFast car deposit configurator URLs
     such as `dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9`.
   - The probe reads `window.carDeposit.products` from the rendered page and
     converts variant/color state into Markdown.

2. **Connected probe output to chunking**
   - `crawler.py` now returns optional `probe_markdown`.
- `loader.py` appends probe Markdown before cleanup/chunking.
- Result: `parsed.md` and `chunks.jsonl` can include interactive state such
  as:
  - `VF 9 Plus tuy chon 7 cho`: `1.699.000.000 VND`
  - `VF 9 Eco`: `1.499.000.000 VND`
  - `Mau nang cao`: `+ 12.000.000 VND`
- Probe records are split with H3 headings per variant so each selectable state
  can become its own chunk/section instead of one large mixed chunk.
- Probe also captures and deduplicates visible configurator notes containing
  `NEDC`/range disclaimer text so human review can inspect that evidence.

3. **Demo app support**
   - Updated `guide/demo/url-ingestion-review-app` with a `Probe` tab.
   - Reviewers can paste one URL and inspect whether probe chunks were created.

### Verification

- `uv run ruff format ... --check`
  - Result: passed for modified URL ingestion files.
- `uv run ruff check ...`
  - Result: passed for modified URL ingestion files.
- `uv run mypy src\agentic_rag\ingestion\url\probe.py src\agentic_rag\ingestion\url\crawler.py src\agentic_rag\ingestion\url\loader.py`
  - Result: passed.
- `uv run pytest src\agentic_rag\ingestion\url\tests -q`
  - Result: `50 passed, 1 skipped`.

### Remaining Work

- Generalize probe contracts for other configurator/e-commerce pages.
- Store variant/color options as structured metadata records in addition to
  Markdown when a shared contract is agreed.
- Keep the probe optional and narrow so normal article/listing ingestion remains
  stable.

## [2026-06-04] Hotfix: Chunk Metadata for Retrieval Review

This update improves chunk review quality without changing the shared `Chunk`
contract.

### Summary of Changes

1. **Moved search aliases out of chunk text**
   - Removed the prepended text line like
     `Search aliases: VF9, VF9, VF9, VF9, VF 9...`.
   - Aliases now live in `Chunk.metadata["search_aliases"]`.
   - Reason: repeating aliases inside many chunks makes those chunks look too
     similar and can pollute retrieval/evaluation.

2. **Added chunk continuation metadata**
   - Added `chunk_group_id`, `chunk_group_index`, `chunk_group_size`,
     `previous_chunk_id`, `next_chunk_id`, `is_continuation`, and
     `continues_to_next`.
   - This lets reviewers know whether a chunk was cut from a longer section and
     how to follow adjacent chunks.

3. **Added image reference metadata**
   - Chunks now include `image_reference_count` and `image_references`.
   - Image references are selected by alt/title overlap with chunk text when
     possible.
   - This gives evaluation a visible image reference signal without repeating
     alt text heavily inside `chunk.text`.

### Notes

- Retrieval can still use aliases later if it is updated to read metadata.
- Current ingestion keeps `chunk.text` cleaner and closer to actual evidence.
- A future multimodal contract can promote `image_references` into a shared
  first-class evidence/reference structure.

## [2026-06-05] Demo Review: Markdown, Chunk, and Quality-Check Audit

This update adds guide-side demos for reviewing the improved Crawl4AI-first URL
ingestion pipeline with human-readable outputs.

### Summary of Changes

1. **Human-review demo now reports problems explicitly**
   - Updated `guide/demo/url-ingestion-human-review/run_demo.py`.
   - The demo still writes `summary.md`, `parsed.md`, `chunks.jsonl`, and
     `manifest.json`.
   - It now also writes:
     - `review_report.json`
     - one `human_review_<case>.md` file per case
   - The report flags likely problems such as:
     - missing or very short Markdown
     - no generated chunks
     - boilerplate/noise chunks
     - duplicate chunks
     - missing review/retrieval metadata
     - ambiguous multi-price chunks
     - missing configurator probe chunks
     - possible wrong parser quality-check decisions

2. **Added shared guide review helpers**
   - Added `guide/demo/url_ingestion_review_lib.py`.
   - The helper loads simple `.env` `KEY=VALUE` pairs into `os.environ` when
     values are not already set by the shell.
   - Secret values are not printed or written to reports.
   - Useful detected variables include `OPENAI_API_KEY`, `OPENAI_MODEL`,
     `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `LLM_PROVIDER`, and
     `LLM_TIMEOUT_SECONDS`.

3. **Added frontend-vs-improved comparison demo**
   - Added `guide/demo/url-ingestion-comparison-review`.
   - The demo compares:
     - `frontend_src_agentic_rag`: direct public API usage, like a frontend call
       into `src/agentic_rag.ingestion.url`
     - `guide_demo_improved_agentic_rag`: the same ingestion output plus
       guide-side improved human-review diagnostics
   - Outputs include:
     - `comparison_summary.md`
     - `comparison_report.json`
     - `human_review_comparison.md`
     - per-path artifact directories for parsed Markdown, chunks, and manifests

4. **Added interactive browser apps for both review demos**
   - `guide/demo/url-ingestion-human-review/server.py` serves the human-review
     app at `http://127.0.0.1:8770`.
   - `guide/demo/url-ingestion-comparison-review/server.py` serves the
     comparison app at `http://127.0.0.1:8771`.
   - Reviewers can paste URLs, run ingestion/comparison, inspect Markdown and
     chunks, edit human-review Markdown, and save review files under each
     demo's `output/` directory.

### Expected Impact

- Reviewers can inspect Markdown and chunks without reading implementation code.
- Quality-check decisions are auditable through `markdown_quality` metadata and
  generated review notes.
- The comparison demo shows whether frontend-facing ingestion and guide-side
  review output diverge before changes are promoted.

### Notes

- These demos live under `guide/` and are intended for local review artifacts.
- The demos do not expose `.env` secret values.
- Live URL runs still require network/browser availability; offline fixtures are
  available for deterministic review.

## [2026-06-05] Human Review Fixes: Price Semantics And Cleaner Fallback

Human review outputs under `guide/demo/url-ingestion-human-review/output` and
`guide/demo/url-ingestion-comparison-review/output` highlighted three ingestion
issues:

1. Configurator probe chunks needed clearer arithmetic so RAG would not mix the
   base price of one VF9 variant with the option delta of another variant.
2. Product/accessory listing chunks contained prices inside raw Markdown links,
   which made human review flag ambiguous multi-price chunks.
3. Crawl4AI could return useful but image-heavy/gallery-heavy Markdown; a
   cleaner Trafilatura candidate should win when it has enough content and lower
   image/link/boilerplate noise.

### Summary of Changes

- Updated `probe.py` so VinFast configurator records:
  - prefix short edition labels with the model inferred from `modelId`,
  - state the exact price rule,
  - emit explicit `base price + option delta = final price` lines.
- Updated `loader.py` quality scoring to:
  - cap the score contribution from repeated prices,
  - track `image_count` and `link_count`,
  - select lower-noise Trafilatura/BM25/builtin candidates when they have enough
    signal.
- Updated product cleanup to normalize product-price links into explicit
  current-price bullets.
- Corrected `image_reference_count` so it matches the actual image references
  attached to each chunk.
- Added `guide/reports/url_ingestion_external_owner_comment.md` for retrieval,
  generation, frontend, and evaluation owners outside ingestion.

### Verification

- `uv run pytest src\agentic_rag\ingestion\url\tests -q`
  - Result: `59 passed, 1 skipped`
- `uv run ruff check src\agentic_rag\ingestion\url\probe.py src\agentic_rag\ingestion\url\loader.py src\agentic_rag\ingestion\url\tests\test_probe.py src\agentic_rag\ingestion\url\tests\test_loader.py`
  - Result: passed

## [2026-06-05] Fetch Fallback: Trafilatura Before urllib

The live URL fetch order is now explicit:

1. Crawl4AI remains the primary crawler for rendered/dynamic pages.
2. If Crawl4AI fails, Trafilatura `fetch_url()` is tried as a lightweight HTML
   fetch fallback.
3. If Trafilatura fetch fails or returns empty HTML, `urllib` is used as the
   deterministic final fallback.

### Summary of Changes

- Added `fetch_html_with_trafilatura()` to `extractor.py`.
- Added `_fetch_url_trafilatura()` to `loader.py`.
- Updated `_fetch_url()` to preserve the Crawl4AI failure in `crawler_error`,
  then append Trafilatura failure details if the final fetch path is `urllib`.
- Added regression coverage for:
  - Crawl4AI failure using Trafilatura fetch before `urllib`.
  - Crawl4AI + Trafilatura failure falling back to `urllib`.

## [2026-06-05] Audit: Primary Chunk Preservation for Quality Review

To allow human reviewers to audit the quality-check selection logic, ingestion now preserves the "primary" chunks (usually from Crawl4AI) even when a fallback (like Trafilatura or BM25) is selected.

### Summary of Changes

1.  **Updated LoadedUrlDocument**: Added `primary_chunks` field to hold chunks from the primary crawler before quality selection.
2.  **Double-Chunking on Fallback**: In `loader.py`, if the quality scorer selects a fallback, the loader now generates a second set of chunks from the discarded primary candidate.
3.  **Demo Support**: Updated the human-review server payload to include these primary chunks, enabling side-by-side comparison in the browser UI to decide if quality check is necessary or too aggressive.

### Verification

- `uv run pytest src\agentic_rag\ingestion\url\tests -q`
  - Result: `60 passed, 1 skipped`

## [2026-06-05] Hotfix: Ingestion Support for Dynamic VinFast Shop Pages

Fixed issues where the VinFast deposit and configurator pages (e.g., VF9) returned empty content due to aggressive selector exclusion and boilerplate filtering.

### Summary of Changes

1.  **Relaxed Crawler Exclusions**: Removed `.dat-coc-steps` and wizard-related classes from the crawler's exclusion list. These containers hold the main price and configuration evidence for VinFast shop pages.
2.  **Increased Render Delay**: Increased the browser settling delay to 5 seconds to allow complex dynamic price cards to fully render before extraction.
3.  **Refined Boilerplate Filtering**: Removed "Shopping" and "Consultation" from the `loader.py` boilerplate list, as these sections often house valid product options.
4.  **Improved Search & UI**:
    - Added **Semantic Reranking** to the Q&A review tool using OpenAI.
    - Implemented VinFast model name normalization (e.g., "VF 9" -> "vf9") for better retrieval match rates.
    - Enhanced the UI with color-coded term highlighting and a "Primary Chunks (Raw)" tab for auditing quality-check decisions.

### Verification

- Confirmed capture of VF9 configurator content at `shop.vinfastauto.com`.

## [2026-06-05] Diagnostic: Visibility for "0 Chunk" Failures

Improved the human-review demo to diagnose why ingestion produces 0 chunks with no fallback reason.

1. **Candidate Comparison**: Added a table to `index.html` showing metrics for all parsers (Built-in, Crawl4AI, Trafilatura).
2. **Crawler Error Reporting**: The UI now explicitly displays Crawl4AI execution errors (timeouts, browser crashes) trapped in the manifest.
3. **Fallback Clarity**: Clarified that `Fallback Reason: none` occurs when only one usable candidate (the empty shell) is found.

## [2026-06-05] Hotfix: Increased Crawl4AI Timeout for Heavy Dynamic Pages

Increased Crawl4AI timeouts and rendering delays to prevent "0 chunk" failures on heavy pages like the VinFast configurator.

### Summary of Changes
1. **Increased rendering delay**: Bumped `delay_before_return_html` from 5.0s to 10.0s.
2. **Increased page timeout**: Bumped `page_timeout` from 60s to 90s.

## [2026-06-05] Hotfix: Robust Waiting for Perpetual Network Activity

Fixed "0 chunk" failures on pages where `networkidle` never completes due to background analytics or chat widgets.

### Summary of Changes
1. **Shifted Wait Strategy**: Changed `wait_until` from `networkidle` to `load`.
2. **Added Targeted Wait**: Introduced `wait_for` targeting `[data-edition]` and `.dat-coc-steps` to ensure React hydration completes even if the network remains busy.

## [2026-06-05] Diagnostic: Visibility for Blocked and Filtered URLs

Enhanced the human-review demo to surface link metadata captured during crawling.

### Summary of Changes
1. **Link Metadata Capture**: Updated `crawler.py` to explicitly preserve categorized links (internal, external, blocked) in the diagnostic payload.
2. **Network Resources View**: Added a scrollable links inspector to the Diagnostics panel in `index.html` to help debug link filtering and resource blocking.

## [2026-06-05] Diagnostic: Surface Resource Loading Errors

Improved diagnostic visibility for failed sub-resources (images, scripts).

### Summary of Changes
1. **Image Metadata Preservation**: Updated `crawler.py` to include raw image metadata in the diagnostic payload.
2. **Failed Resource Reporter**: Updated the human-review UI to detect and display 404/500 errors from images and metadata-reported resource errors.

## [2026-06-05] Diagnostic: Capture Script Loading Errors via JS Probing

Configured Crawl4AI to capture script loading failures that are not typically included in the default resource timing metadata.

### Summary of Changes
1. **JS Probe for Scripts**: Added a `js_code` snippet to `CrawlerRunConfig` in `crawler.py` that identifies scripts with 0 duration or protocol failures via the Performance API.
2. **Metadata Augmentation**: Updated `_crawl_url_with_crawl4ai` to extract the probe results and merge them into `metadata["resource_errors"]` for UI visibility.

## [2026-06-05] Diagnostic: Global Variable Initialization Probe

Added a JS probe to detect if critical global variables (React, ReactDOM, carDeposit) are initialized.

### Summary of Changes
1. **Enhanced JS Probe**: Updated the `js_code` in `crawler.py` to return a structured object containing both resource errors and initialization checks.
2. **Metadata Capture**: Updated `_crawl_url_with_crawl4ai` to store `initialization_status` in metadata.

## [2026-06-05] Diagnostic: Flag Critical Probe Failures in Review App

Configured the human-review app to automatically flag a warning if critical JavaScript variables (like `carDeposit`) are missing on configurator pages.

### Summary of Changes
1. **Automated Issue Detection**: Updated `server.py` to inspect `initialization_status` in chunk metadata and inject a `WARNING / probe` issue when `carDeposit` is missing on relevant URLs.
2. **Review Visibility**: This ensures that hydration failures are prominently listed in both the browser UI and the generated Markdown report.
3. **UI Display**: Updated the human-review demo to show initialization status in the Diagnostics panel.

## [2026-06-05] Review Checks: Question to Chunk Citation

Pulled the latest `develop` into the hotfix branch and resolved URL ingestion conflicts by keeping the Crawl4AI/probe workflow while preserving the newer extractor/normalizer path from `develop`.

### Summary of Changes

1. **Loader compatibility**: `loader.py` now accepts both the newer string-returning Trafilatura extractor and the older result-object shape used by the hotfix tests.
2. **Chunk metadata cleanup**: VinFast search aliases are deduplicated and remain in metadata only, so repeated aliases do not pollute chunk text.
3. **Develop chunker compatibility**: URL chunks now pass `root_title` into the shared hierarchical Markdown splitter and record the merged strategy as `hierarchical-markdown-probe-aware-overlap`.
4. **Review-app citation checks**: The local demo now emits deterministic Q&A checks. Each found answer includes a `citation_chunk_id`, so human reviewers can confirm whether a question can be derived from the produced chunks.
5. **Regression coverage**: Added assertions that VF9 price, advanced color surcharge, and NEDC note questions map back to concrete chunk IDs.

### Human Review Flow

1. Run `uv run python guide/demo/url-ingestion-review-app/server.py`.
2. Paste a URL and run ingestion.
3. Open **Q&A Checks** to inspect derived questions and citation chunk IDs.
4. Cross-check the cited chunk in **Chunks** or `chunks.jsonl`.

## [2026-06-05] Hotfix: Avoid Title-Only Crawl4AI Output

Live review of `https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html`
showed two different failure modes:

1. Crawl4AI timed out because the generic crawler config waited for configurator
   selectors (`[data-edition], .dat-coc-steps`) on a page that is not the
   configurator.
2. After removing the strict wait for non-configurator URLs, Crawl4AI succeeded
   but its `cleaned_html` contained only the `<title>`, so ingestion produced one
   title-only chunk.

### Summary of Changes

- Added URL-aware Crawl4AI wait selection:
  - configurator URL: wait for `[data-edition], .dat-coc-steps`;
  - model/deposit page URL: do not use the configurator wait selector.
- Added `_best_html_attr()` so Crawl4AI raw `html` is preferred when
  `cleaned_html` is title-only.
- Added loader fallback from Crawl4AI-success-but-title-only to Trafilatura fetch
  before returning chunks.
- Added regression tests for both wait selection and title-only fallback.

### Live Verification

Review app run:

```text
URL: https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html
Run ID: vf9_review_check_title_only_fallback
Result: parsed.md length 7698, chunk_count 6
```

The page now captures VF9 text, specs, and Eco/Plus price cards instead of only:

```md
# Xe điện VinFast VF 9 - Giá bán và chương trình ưu đãi | VinFast
```

No PostgreSQL or repeated crawl loop is needed for this fix. The problem was
source extraction quality, not missing persistence. The local review app already
stores each run as `parsed.md`, `chunks.jsonl`, and `manifest.json`.

## [2026-06-05] Hotfix: Crawl4AI React SPA Snapshot Strategy

Applied the local `guide/crawl4ai_react_spa_solution.md` guidance to the URL
crawler.

### Summary of Changes

- Added React-aware `wait_for` conditions:
  - configurator pages wait for `window.carDeposit.products` or meaningful body
    text;
  - generic React pages wait for `main`, `[data-loaded]`, `.main-content`,
    `#root`, `#app`, or enough body text.
- Replaced single diagnostic JS with a Crawl4AI `js_code` sequence that:
  - scrolls to the bottom and back to trigger lazy rendering;
  - clicks collapsed accordions and tabs;
  - waits after interactions;
  - returns script-resource and initialization diagnostics.
- Added support for Crawl4AI list-style `js_execution_result` so diagnostics
  remain visible when multiple JS snippets run.
- Parser metadata now records pipeline supplements, for example
  `builtin-html-parser+crawl4ai-rendered-html+interactive-probe`, so reviewers
  can tell when base Markdown came from builtin parsing but dynamic state came
  from Crawl4AI/probe.

### Verification

```text
URL: https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9
Result: chunks 22, markdown_len 27131, crawler crawl4ai, has_probe True, has_color True
```
