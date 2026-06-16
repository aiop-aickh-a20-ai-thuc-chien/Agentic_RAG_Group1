# Worklog

## 2026-06-16 - Shared Metadata, PDF Alignment, And Dedup Check Demo

### Added / Updated

- Pulled `origin/develop` before the metadata work; result was already up to
  date.
- Added the shared ingestion metadata minimum in
  `src/agentic_rag/ingestion/metadata/schema.py`:
  - `source_type` is required for every chunk.
  - `document_type` is optional and should only be added when the parser or
    enrichment step can infer it safely.
  - Helper functions now report or raise on missing required metadata:
    `missing_required_metadata()`, `has_required_metadata()`, and
    `require_metadata()`.
- Updated `src/agentic_rag/ingestion/metadata/__init__.py` to export the shared
  metadata constants and helper functions.
- Updated PDF ingestion in `src/agentic_rag/ingestion/pdf/loader.py` so PDF
  chunks now satisfy the same shared metadata contract:
  - `source_type` is always `pdf`.
  - `page_number` mirrors `page` when page provenance exists.
  - `heading` mirrors the chunk section.
  - `breadcrumb` mirrors `section_path` or falls back to `[section]`.
  - `token_count` is stamped from the chunker when available, otherwise from a
    word-count fallback.
  - `require_metadata()` is called before each PDF `Chunk` is returned.
- Updated `src/agentic_rag/ingestion/pdf/README.md` to document the new shared
  PDF metadata aliases and the rule that `document_type` stays optional.
- Updated URL ingestion documentation in
  `src/agentic_rag/ingestion/url/README.md` and
  `src/agentic_rag/ingestion/url/schema.md` so the URL module states clearly:
  - URL ingestion owns URL/HTML/text extraction.
  - PDF URLs and PDF responses are rejected before HTML parsing.
  - PDF data should be routed to `src/agentic_rag/ingestion/pdf`.
  - URL-local quality uses `url_status` / `url_quality_gate`; top-level
    `quality_score` is left for rule-based or LLM enrichment.
- Updated duplicate detection metadata helpers in
  `src/agentic_rag/ingestion/dedup_detect/metadata.py`:
  - `chunk_metadata_contract_issues()` lists chunks missing required metadata.
  - `chunk_metadata_contract_summary()` summarizes required-field readiness,
    `source_type` counts, and optional `document_type` counts before dedup
    review.
- Updated `src/agentic_rag/ingestion/dedup_detect/__init__.py` and
  `src/agentic_rag/ingestion/dedup_detect/README.md` so the dedup module can
  check shared metadata from PDF, URL, HTML, and text chunks without owning
  ingestion.
- Added focused tests:
  - `tests/test_ingestion_metadata_schema.py`
  - `tests/test_dedup_detect_metadata_contract.py`
  - Updated `src/agentic_rag/ingestion/pdf/tests/test_loader.py`
- Added the offline dedup verification demo in `guide/demo/check-dedup/`:
  - `README.md`
  - `check_dedup.py`
  - `sample_chunks.jsonl`
  - The demo reads sample chunks, checks the shared metadata contract, runs
    exact/SimHash dedup, and writes JSON/JSONL/Markdown outputs.
- Updated the existing URL dedup review demo in
  `guide/demo/dedup-detect-url-review/run_url_dedup_review.py` so reports now
  include `metadata_contract.json` and a Metadata Contract section.

### Deleted / Removed / Cleaned

- No tracked file deletion is present in the current `git status --short`
  output; the current work is mainly additions and updates.
- Cleaned generated verification leftovers after local checks:
  - `guide/demo/check-dedup/output-test/`
  - `guide/demo/check-dedup/__pycache__/`
  - `guide/demo/dedup-detect-url-review/__pycache__/`
- `Worklog.md` is currently untracked in this checkout, so this entry preserves
  the recreated log instead of assuming an older tracked version exists.

### PDF And URL Boundary Answer

- URL ingestion can now share metadata with PDF ingestion, dedup detection, and
  downstream retrieval because both URL and PDF chunks use the same `Chunk`
  contract and the same required `source_type` rule.
- URL ingestion does not directly call PDF functions yet. It rejects direct PDF
  URLs and `application/pdf` responses using
  `src/agentic_rag/ingestion/url/acquisition/fetcher.py` and raises a clear
  route-to-PDF error.
- To make URL automatically utilize PDF functions, add a higher-level ingestion
  router or dispatcher above URL/PDF ingestion. That router should detect PDF
  URLs or PDF responses, download/store the PDF safely, then call
  `src/agentic_rag/ingestion/pdf.load_pdf_with_markdown()` or
  `load_pdf_chunks()`. The URL loader itself should stay HTML-focused.

### Verification Commands

```powershell
uv run ruff format src/agentic_rag/ingestion/chunking/models.py src/agentic_rag/ingestion/metadata src/agentic_rag/ingestion/pdf/loader.py src/agentic_rag/ingestion/pdf/tests/test_loader.py src/agentic_rag/ingestion/dedup_detect src/agentic_rag/ingestion/url/schema.md guide/demo/dedup-detect-url-review/run_url_dedup_review.py tests/test_ingestion_metadata_schema.py tests/test_dedup_detect_metadata_contract.py
uv run ruff check src/agentic_rag/ingestion/chunking/models.py src/agentic_rag/ingestion/metadata src/agentic_rag/ingestion/pdf/loader.py src/agentic_rag/ingestion/pdf/tests/test_loader.py src/agentic_rag/ingestion/dedup_detect guide/demo/dedup-detect-url-review/run_url_dedup_review.py tests/test_ingestion_metadata_schema.py tests/test_dedup_detect_metadata_contract.py
uv run pytest tests/test_ingestion_metadata_schema.py tests/test_dedup_detect_metadata_contract.py src/agentic_rag/ingestion/pdf/tests/test_loader.py -q
uv run pytest src/agentic_rag/ingestion/url/tests -q
uv run python -m py_compile guide/demo/dedup-detect-url-review/run_url_dedup_review.py guide/demo/check-dedup/check_dedup.py
uv run python guide/demo/check-dedup/check_dedup.py --output-dir guide/demo/check-dedup/output-test
```

### Verification Result

- Shared metadata + dedup + PDF loader tests passed: `15 passed`.
- URL ingestion tests passed: `86 passed`.
- Python compile check passed for both dedup demo scripts.
- Offline check-dedup demo wrote the expected output files during the smoke
  test, then the temporary output directory was removed.

## 2026-06-15 - URL Staged Artifact Persistence

### Completed

- Extended URL ingestion artifacts so `data_artifact_dir` writes staged
  inspection files for clarity: `source.html`, `parsed_sections.txt`,
  `extracted.md`, final `parsed.md`, `quality.json`, `chunks.jsonl`, and
  `manifest.json`.
- Added stage paths to `manifest.json` and optional paths to
  `IngestionArtifacts`.
- Updated URL loader tests to verify the staged files and manifest entries.
- Updated `src/agentic_rag/ingestion/url/README.md` artifact documentation.

### Test Commands

```powershell
uv run ruff format --check src/agentic_rag/ingestion/url/artifact.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/url/tests/test_loader.py
uv run ruff check src/agentic_rag/ingestion/url/artifact.py src/agentic_rag/ingestion/url/loader.py src/agentic_rag/ingestion/url/tests/test_loader.py
uv run pytest src/agentic_rag/ingestion/url/tests -q
```

## 2026-06-15 - URL Golden Review React Demo

### Completed

- Added `guide/demo/url-golden-review-react/`, a new React browser demo that
  targets the current URL ingestion contract instead of the legacy crawl-review
  payload.
- Added a Node API/static server with `GET /api/health`, `GET /api/golden`, and
  `POST /api/run`.
- Added `run_ingestion_review.py` so the demo runs `load_url_with_artifacts()`,
  scores selected URLs with `evaluate_sample()`, and returns chunk previews,
  golden failures, URL quality metadata, product specs, and artifact paths.
- Documented the `ve-chung-toi` issue: the old demo saw title-only Markdown and
  zero chunks, while current URL ingestion should recover useful chunks from
  metadata descriptions and image alt text.
- Linked the new demo from `guide/README.md` and `src/agentic_rag/ingestion/url/README.md`,
  and clarified in `TODO.md` that `url-crawl-review` is now the legacy
  compatibility path.

### Test Commands

```powershell
node --check guide/demo/url-golden-review-react/server.js
node --check guide/demo/url-golden-review-react/public/app.js
uv run ruff format --check guide/demo/url-golden-review-react/run_ingestion_review.py
uv run ruff check guide/demo/url-golden-review-react/run_ingestion_review.py
uv run python guide/demo/url-golden-review-react/run_ingestion_review.py --list --output guide/demo/url-golden-review-react/output/catalog_smoke.json
uv run python guide/demo/url-golden-review-react/run_ingestion_review.py --url https://vinfastauto.com/vn_vi/ve-chung-toi --no-browser --output guide/demo/url-golden-review-react/output/ve_chung_toi_smoke.json --output-dir guide/demo/url-golden-review-react/output
```

### Verification Notes

- The catalog smoke loaded 322 golden URLs and 322 golden samples.
- The `ve-chung-toi` smoke is `unscored` because that URL is not in the golden
  JSON, but current ingestion returned 3 chunks, 3 usable chunks, and recovery
  sections `Page Summary` and `Visual Content`.
- Local server verification returned HTTP 200 for `/` and `/api/golden`; the
  page includes the React root and the API reports the expected golden counts.

## 2026-06-13 - URL Supported Types, TODO Split, And Golden Test

### Completed

- Created `src/agentic_rag/ingestion/url/TODO_scripts.md` to keep
  script/database/vector-store reminders near URL ingestion without mixing them
  into loader logic.
- Created `src/agentic_rag/ingestion/url/TODO_dedup.md` to document the URL
  metadata handoff for `dedup_detect` and `knowledge_quality`.
- Cleaned `src/agentic_rag/ingestion/url/TODO.md` so the main roadmap stays
  focused on URL extraction, chunking, metadata, quality, and evaluation.
- Updated `src/agentic_rag/ingestion/url/README.md`,
  `guide/url-ingestion-guide.md`, `guide/README.md`, and `guide/guide.md` with
  the supported URL input/page types and the new TODO reminder files.
- Checked the current golden URL list type inventory:
  322 URLs total, including 106 `product_detail`, 16 `product_listing`,
  15 `booking_flow`, 29 `faq`, 17 `policy`, 5 `article`, and 134 `generic`
  pages.
- Ran the full browser-backed golden-data evaluation:
  `guide/reports/url_ingestion_golden_types_20260613/`
  processed 322 URLs, passed 235, failed 87, and errored 0.
- Created the verification report:
  `guide/reports/url_ingestion_golden_types_20260613/verification_report.md`.

### Test Commands

```powershell
uv run ruff format --check src/agentic_rag/ingestion/url
uv run ruff check src/agentic_rag/ingestion/url
uv run pytest src/agentic_rag/ingestion/url/tests -q
uv run python -m agentic_rag.ingestion.url.evaluation.runner --output-dir guide/reports/url_ingestion_golden_types_20260613 --no-resume
```

### Current Status

- URL ingestion focused checks are green: format passed, lint passed, and
  78 tests passed.
- Full golden-data crawl completed with 0 runtime errors.
- The live golden dataset is still a baseline rather than a green gate:
  87 samples fail current expectations, mostly price/VND snippets,
  navigation/cookie/support noise, chunk-count bounds, and metadata
  preservation checks.

## 2026-06-13 - URL Golden Product-Spec Evaluation Update

### Completed

- Extended URL golden-data evaluation with optional `product_spec_checks` so
  samples can pass/fail on structured product metadata emitted by URL
  ingestion.
- Exported `UrlProductSpecCheck` from the URL evaluation package.
- Updated golden-data templates and evaluation docs to describe product/spec
  checks for model, price, driving range, battery capacity, and charging time.
- Kept conflict-detection implementation ownership in `knowledge_quality`; URL
  ingestion now documents only the metadata handoff and fixture TODOs.
- Ran the full browser-backed golden-data evaluation:
  `guide/reports/url_ingestion_golden_product_specs_20260613/`
  processed 322 URLs, passed 233, failed 89, and errored 0.
- Created the verification report:
  `guide/reports/url_ingestion_golden_product_specs_20260613/verification_report.md`.

### Test Commands

```powershell
uv run ruff format --check src/agentic_rag/ingestion/url
uv run ruff check src/agentic_rag/ingestion/url
uv run pytest src/agentic_rag/ingestion/url/tests -q
uv run python -m agentic_rag.ingestion.url.evaluation.runner --output-dir guide/reports/url_ingestion_golden_product_specs_20260613 --no-resume
```

### Current Status

- URL ingestion unit tests are green: 78 passed.
- Full golden-data run completed with 0 runtime errors.
- The committed VinFast golden JSON does not yet enable `product_spec_checks`,
  so this run validates backward compatibility plus the existing base contract.
- The full 322-link golden dataset is still a live baseline, not a green release
  gate yet: 89 samples still fail base expectations.

## 2026-06-13 - URL Ingestion Golden Verification

### Completed

- Built out the URL ingestion structure under `src/agentic_rag/ingestion/url`
  for acquisition, DOM handling, entity extraction, metadata, quality strategy,
  rendering, golden data, and evaluation.
- Added quality-first URL ingestion behavior: static fetch inspection,
  rendered-parser fallback, page-type profiling, render retry, report-local
  render cache, metadata propagation, and noise cleanup.
- Added and exercised golden-data evaluation from
  `src/agentic_rag/ingestion/url/golden_data/Link_data.txt` against
  `vinfast_url_golden_samples.json`.
- Verified the focused regression subset:
  `guide/reports/url_ingestion_verification_subset_complete_final2/`
  processed 12 URLs, passed 12, failed 0, and errored 0.
- Ran the full live golden-data verification:
  `guide/reports/url_ingestion_golden_verification_20260613/`
  processed 322 URLs, passed 219, failed 103, and errored 0.
- Created the full verification report:
  `guide/reports/url_ingestion_golden_verification_20260613/verification_report.md`.

### Test Commands

```powershell
uv run ruff format --check src/agentic_rag/ingestion/url
uv run ruff check src/agentic_rag/ingestion/url
uv run pytest src/agentic_rag/ingestion/url/tests -q
uv run python -m agentic_rag.ingestion.url.evaluation.runner --output-dir guide/reports/url_ingestion_golden_verification_20260613 --no-resume
```

### Current Status

- URL ingestion unit tests are green: 74 passed.
- The 12-link verification subset is green.
- The full 322-link golden dataset is a live baseline, not a green release gate
  yet: 103 samples still fail base expectations.

### Next Triage

- Review whether price-related required snippets on shop product pages should
  stay as base pass/fail requirements or move to optional/advanced checks.
- Fix empty required snippets in FAQ/product golden samples.
- Continue cleanup for residual navigation/footer snippets such as `Home`,
  `Cookie`, `Support`, and login text.
- Inspect canonical URL, query parameter, and language metadata failures.
