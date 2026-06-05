# URL Ingestion

For the current Crawl4AI-first improved pipeline, fallback order, metadata, and
downstream implementation checklist, see
[`docs/improved-url-ingestion.md`](improved-url-ingestion.md).

URL ingestion lives in:

```text
src/agentic_rag/ingestion/url
```

Public helpers:

- `load_url_chunks(url: str) -> list[Chunk]`
- `load_html_chunks(html: str, source: str, source_url: str | None = None) -> list[Chunk]`
- `load_text_chunks(text: str, source: str) -> list[Chunk]`

## Module Layout

- `loader.py`: ingestion and chunking boundary.
- `parser.py`: parser adapters for HTML cleanup and section extraction.
- `chunking.py`: URL compatibility exports plus URL-specific chunk metadata construction.
- `artifact.py`: optional debug artifact persistence.
- `benchmarking/`: local benchmark CLI and parser benchmark helpers.

## Behavior

`load_url_chunks` fetches an absolute `http` or `https` URL, cleans HTML boilerplate, chunks
content by detected sections, and returns shared `Chunk` objects. URL parsing remains
URL-local, but normalized text is passed through the shared chunking boundary in
`agentic_rag.ingestion.chunking` before URL metadata is attached.

The implementation uses Python standard library tools only:

- `urllib` for URL fetching
- `html.parser` for HTML cleanup and section detection
- shared deterministic chunking primitives from `agentic_rag.ingestion.chunking`
- deterministic SHA-256 based chunk IDs

## Metadata

Each chunk includes the shared metadata keys:

- `source`
- `source_type`
- `file_name`
- `url`
- `page`
- `section`

Additional URL ingestion metadata may include:

- `title`
- `fetched_at`
- `content_hash`
- `chunk_index`

## Testing

URL ingestion tests are colocated with the module:

```text
src/agentic_rag/ingestion/url/tests
```

Run them with:

```bash
uv run pytest src/agentic_rag/ingestion/url/tests -q
```
