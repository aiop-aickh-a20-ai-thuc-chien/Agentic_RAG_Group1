## Parent

Related to `agentic-rag-notebooks#146` and branch `feature/url-ingestion-benchmarking`.

## What to build

Review and merge the current URL/Text ingestion implementation into `develop`. This slice closes the setup/baseline phase for URL ingestion: `load_url_chunks()`, `load_html_chunks()`, and `load_text_chunks()` return shared `Chunk` objects, parser/chunking/artifact helpers are explicit, local benchmark helpers are documented, and colocated tests are in place.

## Acceptance criteria

- [ ] Pull Request is opened from `feature/url-ingestion-benchmarking` into `develop`.
- [ ] PR includes commit `162cbc3 feat(ingestion): implement url ingestion` and later equivalent/rebased changes.
- [ ] CI passes: Ruff format check, Ruff lint, mypy, and pytest.
- [ ] Reviewer confirms `load_url_chunks(url: str) -> list[Chunk]` returns contract-compatible chunks.
- [ ] Reviewer confirms `load_text_chunks(text: str, source: str) -> list[Chunk]` is available for plain text ingestion.
- [ ] Reviewer confirms debug artifacts are optional and are not written unless an explicit debug artifact directory is provided.
- [ ] Reviewer confirms generated local `guide/` results are not required for commit.
- [ ] PR is merged into `develop` after review.

## Blocked by

None - can start immediately.
