# URL Ingestion

URL ingestion lives in:

```text
src/agentic_rag/ingestion/url
```

Public helpers:

- `load_url_chunks(url: str) -> list[Chunk]`
- `load_html_chunks(html: str, source: str, source_url: str | None = None) -> list[Chunk]`
- `load_text_chunks(text: str, source: str) -> list[Chunk]`

## Behavior

`load_url_chunks` fetches an absolute `http` or `https` URL, cleans HTML boilerplate, chunks
content by detected sections, and returns shared `Chunk` objects.

The implementation uses Python standard library tools only:

- `urllib` for URL fetching
- `html.parser` for HTML cleanup and section detection
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
