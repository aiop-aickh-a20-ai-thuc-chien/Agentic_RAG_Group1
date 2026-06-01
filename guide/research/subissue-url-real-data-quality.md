## Parent

Related to `agentic-rag-notebooks#146` and the URL ingestion merge/review task.

## What to build

Run the URL ingestion pipeline on representative real URLs and produce a short quality assessment. Use `load_url_chunks()` and optional debug artifact output to inspect extracted text, section metadata, chunk boundaries, URL/source metadata, and noisy content. The output should help decide whether the current stdlib parser/chunker is sufficient as the baseline or which parser/chunking weaknesses must be optimized next.

## Acceptance criteria

- [ ] Select at least 2 representative domains.
- [ ] Include at least one domain with multiple related child URLs, such as homepage + about/brand/solution/project pages.
- [ ] Run `load_url_chunks()` for each selected URL.
- [ ] Inspect extracted text for Vietnamese decoding quality, text order, missing text, and noisy content.
- [ ] Inspect chunk boundaries for section quality, overlap behavior, metadata completeness, and retrieval-readiness.
- [ ] Inspect metadata for `source`, `source_type`, `url`, `section`, `title`, `content_hash`, and `chunk_index`.
- [ ] Record sample outputs under ignored/local-only result paths, such as `guide/results`, or another agreed ignored artifact path.
- [ ] Produce a concise evaluation note with pass/fail observations and recommended parser/chunking improvements.

## Blocked by

- URL ingestion merge/review task.
