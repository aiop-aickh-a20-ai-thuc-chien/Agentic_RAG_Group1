## Parent

Related to `agentic-rag-notebooks#146`, the URL ingestion real-data quality task, and the existing URL benchmark workflow.

## What to build

Use the existing URL benchmark workflow plus real-data observations to compare the current stdlib parser baseline against at least one alternative parser strategy. The goal is not to prematurely optimize, but to make the next parser decision evidence-based after the current baseline has unblocked the RAG pipeline.

## Acceptance criteria

- [ ] Define parser candidates and evaluation inputs before running comparisons.
- [ ] Include the current stdlib parser baseline.
- [ ] Include at least one alternative parser strategy, such as Trafilatura, BeautifulSoup cleanup, Readability, Playwright/Crawl4AI for JS-heavy pages, or a documented dry-run if dependency setup is deferred.
- [ ] Run the existing benchmark wrapper or a documented dry-run when official benchmark data is unavailable.
- [ ] Include Vietnamese HTML samples or real-page snapshots where possible.
- [ ] Compare outputs on text completeness, Vietnamese decoding quality, boilerplate removal, section metadata, chunking suitability, runtime, and operational complexity.
- [ ] Record a parser decision note: keep stdlib baseline, tune stdlib parser, add fallback parser, or schedule replacement.
- [ ] Do not vendor external benchmark datasets into the repository.

## Blocked by

- URL ingestion merge/review task.
- URL ingestion real-data quality task.
- #15
