# URL Ingestion

This module turns a URL or HTML document into clean Markdown, RAG-ready chunks,
and optional local artifacts for inspection.

The implementation is intentionally bounded to URL/HTML ingestion. PDF URLs or
PDF responses are rejected here and should be routed to the PDF ingestion module.

## Module Map

- `loader.py`: public ingestion boundary for URL, HTML, and text inputs.
- `parser.py`: stdlib HTML parser that extracts headings, body text, metadata,
  links, images, and other page assets.
- `extractor.py`: Trafilatura adapter for main-content Markdown extraction.
- `chunking/`: deterministic Markdown chunking strategies.
- `model_chunking.py`: optional LLM-assisted chunking strategy adapters.
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
2. The page is fetched with a deterministic project user agent.
3. `parse_html()` extracts structured page metadata and section boundaries from
   the HTML.
4. `extract_markdown_with_trafilatura()` tries to extract clean main-content
   Markdown.
5. If Trafilatura cannot extract content, or if it drops heading structure that
   the builtin parser can preserve, the loader falls back to Markdown built from
   builtin parser sections.
6. The loader removes common script/config/cookie boilerplate from Markdown.
7. The loader chunks global Markdown with heading-aware metadata and enriches
   each `Chunk.metadata` with URL metadata such as original URL, final URL,
   canonical URL, language, author, description, and asset count.

Trafilatura is preferred because it removes much of the boilerplate from real web
pages and preserves useful Markdown constructs such as headings, links, lists,
and emphasis. The builtin parser remains as a deterministic fallback for local
HTML and test cases.

## Chunking Strategy

The default chunking method is `hybrid-markdown-aware-token-overlap`.

The strategy is designed for Markdown:

1. Split global Markdown into heading-scoped sections.
2. Preserve heading context in chunk text and store `section_level` plus
   `section_path` in chunk metadata.
3. Pack paragraphs under each section with a token budget.
4. Count tokens with `tiktoken` when available, falling back to word counts.
5. Preserve a small paragraph overlap between chunks.
6. If one paragraph is too large, split it into sentences with `pysbd`.
7. Detect Vietnamese text with a lightweight diacritic heuristic and use the
   Vietnamese `pysbd` segmenter; otherwise use English.
8. If sentence segmentation is unavailable, fall back to regex and word splitting.

This keeps chunks more useful for RAG than character slicing because headings,
section paths, paragraphs, and sentence boundaries are less likely to be broken.

Optional strategies:

- `TiktokenChunkingStrategy`: deterministic token-window splitting.
- `RAGFlowChunkingStrategy`: optional RAGFlow-backed chunking.
- `ModelChunkingStrategy`: optional OpenAI/Gemini-assisted splitting.
- RAGFlow-assisted strategy can be selected by strategy object, while keeping
  integration code outside this module.

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
