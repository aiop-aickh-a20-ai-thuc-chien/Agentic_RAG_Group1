# URL Ingestion

This module turns a URL or HTML document into clean Markdown, RAG-ready chunks,
and optional local artifacts for inspection.

The implementation is intentionally bounded to URL/HTML ingestion. PDF URLs or
PDF responses are rejected here and should be routed to the PDF ingestion module.

## Module Map

- `loader.py`: public ingestion boundary for URL, HTML, and text inputs.
- `parser.py`: stdlib HTML parser that extracts page metadata, links, images,
  and other page assets.
- `extractor.py`: Crawl-link-style DOM Markdown extractor, optional Playwright
  rendered-page extractor, and Trafilatura fallback.
- `normalizer.py`: deterministic Markdown cleanup rules for CTA, cookie/privacy,
  navigation, related-card, and product/listing noise.
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
2. For live URLs, the loader first tries the optional Playwright extractor from
   the Crawl link pipeline. This renders the page, expands tab/accordion content,
   walks the DOM in document order, extracts H1-H6 headings, pairs product specs,
   and normalizes UI noise before chunking.
3. If Python Playwright is unavailable or browser extraction fails, the page is
   fetched with a deterministic project user agent.
4. For fetched HTML or local HTML input, `parse_html()` extracts page metadata
   while `extract_markdown_from_html()` builds Crawl-link-style Markdown from the
   HTML body.
5. If the DOM extractor cannot produce headed Markdown, the loader falls back to
   Trafilatura and finally to Markdown built from builtin parser sections.
6. The loader removes common script/config/cookie boilerplate from Markdown.
7. The loader chunks global Markdown with heading-aware metadata and enriches
   each `Chunk.metadata` with URL metadata such as original URL, final URL,
   canonical URL, language, author, description, and asset count.

The Crawl-link-style extractor is preferred because it preserves rendered content
that simple static parsers often miss, especially tabs, accordions, product
specs, price blocks, and H4-H6 detail headings. Trafilatura remains as a fallback
for pages where the DOM extractor cannot produce useful Markdown.

## Chunking Strategy

The default chunking method is `hierarchical-markdown-subsection-overlap`.

The strategy is designed for Markdown:

1. Split global Markdown into heading-scoped sections.
2. Detect implicit subsections such as numbered lines (`1. Specs`) and bold
   lead labels (`**Battery:**`).
3. Preserve heading and subsection context in `section_path`, `full_path`,
   `depth`, `part_index`, and `part_total` metadata.
4. Merge short sibling blocks under the same parent when they fit the chunk
   budget.
5. Split long blocks by paragraph, line, then sentence-like boundaries with a
   small character overlap.
6. Count tokens with `tiktoken` when available, falling back to word counts.

This keeps chunks more useful for RAG than plain character slicing because
headings, section paths, product-spec labels, and split positions are less
likely to be lost.

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
