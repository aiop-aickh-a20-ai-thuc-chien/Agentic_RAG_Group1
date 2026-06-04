# URL Ingestion

This module turns a URL or HTML document into clean Markdown, RAG-ready chunks,
and optional local artifacts for inspection.

The implementation is intentionally bounded to URL/HTML ingestion. PDF URLs or
PDF responses are rejected here and should be routed to the PDF ingestion module.

## Module Map

- `loader.py`: public ingestion boundary for URL, HTML, and text inputs.
- `crawler.py`: Crawl4AI adapter used as the preferred live URL crawler.
- `parser.py`: stdlib HTML parser that extracts headings, body text, metadata,
  links, images, and other page assets.
- `extractor.py`: Trafilatura adapter for main-content Markdown extraction.
- `chunking/`: deterministic Markdown chunking strategies.
- `artifact.py`: persistence for `parsed.md`, `chunks.jsonl`, and
  `manifest.json`.
- `benchmarking/`: small local parser benchmark helpers.
- `tests/`: URL ingestion unit tests.
- `data/`: local generated artifacts. This is for inspection and should not be
  treated as the committed source of truth.

## Parse Strategy

The default URL path is:

1. `load_url_with_artifacts(url)` validates that the input is an absolute HTTP
   or HTTPS URL and rejects PDF inputs.
2. The page is fetched with Crawl4AI first so rendered/dynamic pages, card-heavy
   layouts, and browser-discovered links can be captured.
3. If Crawl4AI is unavailable or fails, the loader falls back to the deterministic
   `urllib` fetch path with the project user agent.
4. `parse_html()` extracts structured page metadata and section boundaries from
   the HTML.
5. The loader builds candidate Markdown from available sources:
   Crawl4AI rendered Markdown, Trafilatura main-content Markdown, and builtin
   parser Markdown.
6. Candidate Markdown is scored for useful content, headings, title match, price
   values, and boilerplate risk. The highest-quality candidate is selected rather
   than blindly preferring the longest output.
7. The loader removes common script/config/cookie/login/cart/menu boilerplate
   from Markdown.
8. VinFast vehicle price-card text is normalized so current prices and old
   crossed prices remain explicit in Markdown.
9. The loader chunks global Markdown with heading-aware metadata and enriches
   each `Chunk.metadata` with URL metadata such as original URL, final URL,
   canonical URL, language, author, description, crawler name, parser name,
   source URL, section path, asset count, and dedupe hash.

Crawl4AI is preferred for live URLs because it can capture rendered content that
static HTML fetches often miss. Trafilatura remains useful for main-content
cleanup, and the builtin parser remains the deterministic fallback for local HTML
and tests.

## Child Pages

`load_url_with_artifacts()` and `load_url_chunks()` support `max_child_pages`.
When this is greater than zero, the loader follows same-origin links discovered
by Crawl4AI and combines parent/child chunks.

Child crawling intentionally skips:

- external domains,
- PDF links,
- the original URL,
- duplicate normalized chunk text.

This is useful for listing/card pages where the parent page links to product or
article detail pages. Keep `max_child_pages=0` for deterministic single-page
ingestion.

## Chunking Strategy

The default chunking method is `hybrid-markdown-aware-token-overlap`.

The strategy is designed for Markdown:

1. Split global Markdown into heading-scoped sections.
2. Preserve heading context in chunk text and store `section_level` plus
   `section_path` in chunk metadata.
3. Pack paragraphs under each section with a token budget.
4. Count tokens with `tiktoken` when available, falling back to word counts.
5. For URL ingestion, avoid paragraph overlap by default to reduce duplicated
   evidence in retrieval results.
6. If one paragraph is too large, split it into sentences with `pysbd`.
7. Detect Vietnamese text with a lightweight diacritic heuristic and use the
   Vietnamese `pysbd` segmenter; otherwise use English.
8. If sentence segmentation is unavailable, fall back to regex and word splitting.
9. Add lightweight search aliases for VinFast model names such as `VF9`, `VF 9`,
   `VinFast VF9`, and `xe VF 9` so retrieval can match common multilingual query
   forms without changing retrieval code.

This keeps chunks more useful for RAG than character slicing because headings,
section paths, paragraphs, and sentence boundaries are less likely to be broken.

## Price And Product Cleanup

The loader includes URL-side cleanup for vehicle price cards. For example, a raw
rendered card like:

```md
VF 9 Eco
Gia ban tu
1.229.180.000
VND
1.499.000.000
VND
```

is normalized into:

```md
- VF 9 Eco: Gia ban tu 1.229.180.000 VND; gia niem yet cu ~~1.499.000.000 VND~~.
```

This makes RAG evidence clearer because current price and old/listed price are
not collapsed into one ambiguous number sequence.

## Artifacts

When `data_artifact_dir` is provided, ingestion writes:

- `parsed.md`: cleaned Markdown used for inspection.
- `chunks.jsonl`: serialized shared `Chunk` records.
- `manifest.json`: run metadata, source metadata, artifact paths, parser name,
  and chunk count.

Example:

```python
from pathlib import Path

from agentic_rag.ingestion.url.loader import load_url_with_artifacts

document = load_url_with_artifacts(
    "https://example.com/article",
    data_artifact_dir=Path("src/agentic_rag/ingestion/url/data"),
    run_id="example-url-run",
)

print(len(document.chunks))
print(document.artifacts.run_dir if document.artifacts else None)
```

## RAG Suitability

URL chunks use the shared `agentic_rag.core.contracts.Chunk` contract. This makes
them directly usable by retrieval and generation modules without importing
private URL ingestion details.

For RAG, inspect:

- chunk text readability,
- section metadata,
- URL/canonical URL metadata,
- chunk length distribution,
- whether top retrieval results contain content rather than boilerplate.

If retrieval ranks footer, cookie, script, or related-post chunks too highly,
improve ingestion-side filtering before changing retrieval or generation.

## Known Follow-up

Some configurator pages expose important state in JavaScript data rather than in
the currently visible HTML. For example, VinFast car deposit pages can store
variant/color price options in `window.carDeposit.products`.

The current URL ingestion can crawl the page and preserve visible content, but it
does not yet convert that JavaScript state into first-class structured chunks.
For a stronger contract, add a dedicated configurator extractor that emits
records such as:

- variant code,
- variant label,
- base price,
- color price delta,
- final price,
- availability,
- asset/reference links.

Image alt text and color assets should be stored as metadata or reference links
when possible, instead of repeated heavily inside chunk text.

## Quality Gate

Run the module tests after changing URL ingestion:

```bash
uv run pytest src/agentic_rag/ingestion/url/tests -q
```

Run the project gate before opening or updating a PR:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```
