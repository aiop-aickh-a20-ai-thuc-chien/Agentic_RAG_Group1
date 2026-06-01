# URL Ingestion Summary Report

## Scope

This report summarizes the current URL ingestion implementation and the sample outputs stored in `guide/results`.

Sample result files:

- `url-ingestion-vinfastauto.com.md`
- `url-ingestion-vintechvietnam.com.md`
- `chunk-samples.md`

## What Is Used Now

### Fetching URL

- Current implementation: Python stdlib `urllib.request`
- Entry point: `agentic_rag.ingestion.url.load_url_chunks(url)`
- User agent: `AgenticRAGGroup1/0.1`
- Supports absolute `http` and `https` URLs only.

### Extracting And Cleaning Data

- Current implementation: Python stdlib `html.parser.HTMLParser`
- Parser file: `src/agentic_rag/ingestion/url/parser.py`
- Noise tags removed:
  - `script`
  - `style`
  - `nav`
  - `footer`
  - `header`
  - `aside`
- Section metadata is created from:
  - `h1`
  - `h2`
  - `h3`
- Current parser does not use `trafilatura` yet.
- Current parser does not output full standard Markdown yet; it outputs normalized readable text grouped by section.

### Chunking Data

- Current implementation: deterministic character-based chunking.
- Chunk file: `src/agentic_rag/ingestion/url/chunking.py`
- Default settings:
  - `chunk_size = 1200`
  - `chunk_overlap = 150`
- Split behavior:
  - normalize whitespace
  - split by fixed character window
  - prefer word boundary when possible
  - preserve section metadata from parser output
- Current chunking does not use OpenAI, Gemini, semantic chunking, or token-aware splitting yet.

### Metadata Stored Per Chunk

Each chunk stores:

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

## Sample Output Observations

### VinFast URL

- URL: `https://vinfastauto.com/vn_vi/dat-coc-xe-vf-mpv7?...`
- Result: success
- Chunk count: 3
- Observation:
  - Main product information was extracted.
  - Some repeated navigation/footer-like content remained.
  - Vietnamese text showed encoding issues in the saved sample output.
  - This page is useful as a stress test because it has marketing content, product specs, and repeated site navigation.

### Vintech Vietnam URL

- URL: `https://vintechvietnam.com/`
- Result: success
- Chunk count: 19
- Observation:
  - Multiple sections were detected from headings.
  - Section metadata is more useful than the VinFast page.
  - Some noisy text such as skip links and repeated navigation still appears.
  - Vietnamese text also showed encoding issues in the saved sample output.

## Suggested URL Sample Set

Use a sample structure with one domain containing multiple URLs instead of only one homepage. This better tests same-source grouping, page-level metadata, duplicate navigation, and section-level chunking.

Recommended Vintech source:

- Domain/source: `vintechvietnam.com`
- URLs:
  - `https://vintechvietnam.com/`
  - `https://vintechvietnam.com/gioi-thieu/`
  - `https://vintechvietnam.com/thuong-hieu/`
  - `https://vintechvietnam.com/giai-phap/`
  - `https://vintechvietnam.com/du-an/`

Recommended VinFast source:

- Domain/source: `vinfastauto.com`
- URLs:
  - a product detail page
  - a support or FAQ page
  - a policy or service page

## Recommended Next Improvements

### Low-cost baseline improvement

- Keep current stdlib parser as fallback.
- Fix/verify encoding handling for Vietnamese content.
- Improve boilerplate filtering for repeated menus, country selectors, footer links, and CTA blocks.

### Parser improvement

- Add `trafilatura` as the main extraction adapter.
- Use `trafilatura.extract(..., output_format="markdown")` to produce cleaner Markdown.
- Keep current parser as fallback when `trafilatura` fails or returns empty content.

### Chunking improvement

- Add Markdown heading-aware chunking before fixed-size splitting.
- Add token-aware splitting with `tiktoken` for OpenAI-compatible chunk size control.
- Keep deterministic fallback chunking for tests and offline execution.

### Optional OpenAI/Gemini usage

- Do not use OpenAI/Gemini for basic HTML extraction by default.
- Use OpenAI or Gemini later for:
  - embeddings
  - semantic chunk grouping
  - contextual chunk summaries
  - extraction quality evaluation

## Current Decision

The current implementation is acceptable as a deterministic baseline, but it should be improved before production-quality URL ingestion. The next most valuable change is adding `trafilatura` Markdown extraction plus a fallback path, then upgrading chunking to Markdown heading-aware and token-aware splitting.
