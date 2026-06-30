# Ingestion Verification Demos

This directory documents the ingestion verification scripts provided in `guide_2/`. These scripts allow you to locally evaluate the output of the ingestion pipeline (both for URLs and local files) against ground truth data.

The verifiers are local-first by default:
- They do **not** require an LLM to produce pass/fail checks.
- They compare ground-truth facts against a combined evidence corpus (`parsed.md` + ingestion artifacts).
- They provide semantic diffs and structural verification metrics.

## Available Verifiers

1. **URL Ingestion Verifier** (`guide_2/verify_url_ingestion.py`): Best for evaluating crawled web pages, extracting interaction artifacts, and checking routing rules (like `modelId`).
2. **File Ingestion Verifier** (`guide_2/verify_file_ingestion.py`): Designed to evaluate the ingestion of local files (like PDFs). It extracts markdown, captures chunk metadata, and handles file-specific parsing rules (such as visual chunking).

---

## 1. URL Ingestion Verification

### What it does

1. **Runs ingestion (optional)** with `load_url_with_artifacts(...)` when `--url` is provided.
2. **Loads ground truth** from a provided directory/file.
3. **Builds local evidence corpus** from URL artifacts (`source.html`, `cleaned.html`, `parsed.md`, `chunks.jsonl`, `interaction_states.json`, etc.).
4. **Computes deterministic checks**: text similarity, key-fact coverage, `modelId` routing checks, and pass/fail verdict.
5. **Optionally appends LLM qualitative review** when `--use-llm` is enabled.

### Quick start (URL)

#### Run local verification from URL
```bash
uv run python guide_2/verify_url_ingestion.py \
  --url "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9" \
  --ground-truth-dir "guide_2/ground_truth/https-shop-vinfastauto-com-vn-vi-dat-coc-o-to-dien-vinfast-html-modelid-products-car-VF9" \
  --output-dir "guide_2/demo/verify_ingestion/output"
```

#### Verify from existing `actual_output.md` (no recrawl)
```bash
uv run python guide_2/verify_url_ingestion.py \
  --actual-md "guide_2/demo/verify_ingestion/output/actual_output.md" \
  --source-url "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9" \
  --artifact-dir "guide_2/demo/verify_ingestion/output/ingestion_artifacts/artifacts/..." \
  --ground-truth-dir "guide_2/ground_truth/https-shop-vinfastauto-com-vn-vi-dat-coc-o-to-dien-vinfast-html-modelid-products-car-VF9" \
  --output-dir "guide_2/demo/verify_ingestion/output"
```

---

## 2. File Ingestion Verification

### What it does

1. **Runs ingestion (optional)** with `load_pdf_with_markdown(...)` when `--file` is provided.
2. **Loads ground truth** from a provided directory/file.
3. **Builds local evidence corpus** from file artifacts (`parsed.md`, `chunks.jsonl`, etc.).
4. **Computes deterministic checks**: text similarity, key-fact coverage, and pass/fail verdict.
5. **Optionally appends LLM qualitative review** when `--use-llm` is enabled.

### Quick start (File)

#### Run local verification from a PDF file
```bash
uv run python guide_2/verify_file_ingestion.py \
  --file "path/to/sample.pdf" \
  --ground-truth-dir "guide_2/ground_truth/sample_pdf_ground_truth" \
  --output-dir "guide_2/demo/verify_ingestion/output_file"
```

#### Verify from existing `actual_output.md` (no re-ingestion)
```bash
uv run python guide_2/verify_file_ingestion.py \
  --actual-md "guide_2/demo/verify_ingestion/output_file/actual_output.md" \
  --source-file "path/to/sample.pdf" \
  --ground-truth-dir "guide_2/ground_truth/sample_pdf_ground_truth" \
  --output-dir "guide_2/demo/verify_ingestion/output_file"
```

---

## CLI Options Reference

### URL Verifier (`verify_url_ingestion.py`)
- `--url`: Crawl and ingest URL before verification.
- `--actual-md`: Compare an existing actual markdown file; skips crawl.
- `--source-url`: Original URL to preserve routing checks when using `--actual-md`.
- `--artifact-dir`: Explicit artifact directory to include in evidence corpus.
- `--ground-truth-dir`: Ground truth directory or markdown file path.
- `--output-dir`: Output directory for report and summary artifacts.
- `--use-llm`: Append optional LLM qualitative evaluation.
- `--llm-role`: Model-runtime role for LLM review (`evaluation` by default).

### File Verifier (`verify_file_ingestion.py`)
- `--file`: Ingest a local file (e.g., PDF) before verification.
- `--actual-md`: Compare an existing actual markdown file; skips ingestion.
- `--source-file`: Original file path to preserve source tracking when using `--actual-md`.
- `--artifact-dir`: Explicit artifact directory to include in evidence corpus.
- `--ground-truth-dir`: Ground truth directory or markdown file path.
- `--output-dir`: Output directory for report and summary artifacts.
- `--use-llm`: Append optional LLM qualitative evaluation.
- `--llm-role`: Model-runtime role for LLM review (`evaluation` by default).

## Output files

Both scripts write the following to the `--output-dir`:
- `ingestion_artifacts/`: The full output artifacts from the ingestion run.
- `evaluation_report.md`: Human-readable verification report.
- `comparison_summary.json`: Machine-readable metrics and verdict inputs.
- `ground_truth_diff.patch`: Unified diff (`ground_truth.md` vs `actual_output.md`).
- `actual_output.md`: Snapshot used for comparison.
- `ground_truth.md`: Ground truth snapshot used for comparison.
