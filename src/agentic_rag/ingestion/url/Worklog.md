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
