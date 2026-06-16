# PDF Review Demo

Small local demo for checking PDF ingestion output.

It runs the current PDF ingestion boundary, saves parser/chunk artifacts, checks
the shared metadata contract, and writes a short review report.

## Run

From the repository root:

```powershell
uv run python guide/demo/pdf-review/run_pdf_review.py path/to/file.pdf
```

Optional:

```powershell
uv run python guide/demo/pdf-review/run_pdf_review.py `
  src/agentic_rag/ingestion/pdf/.data/VF3-ERG_VN_V4.pdf `
  --chunker deterministic `
  --output-dir guide/demo/pdf-review/output `
  --run-id vf3-check
```

## Output

The demo writes:

- `review_summary.json`: machine-readable review result.
- `review_report.md`: human-readable inspection report.
- `artifacts/<pdf-name>/<run-id>/parsed.md`: parsed Markdown.
- `artifacts/<pdf-name>/<run-id>/chunks.jsonl`: shared `Chunk` objects.
- `artifacts/<pdf-name>/<run-id>/chunks.md`: readable chunk dump.
- `artifacts/<pdf-name>/<run-id>/manifest.json`: artifact manifest.

If `--run-id` is omitted, the PDF artifact helper creates a timestamped run id.

## What To Check

- `review_status` should be `pass`.
- `metadata_contract.missing_required_count` should be `0`.
- Every chunk should include shared fields:
  - `source` as the concrete PDF path
  - `source_type` as a shared category. Local PDFs should be `internal`.
  - `updated_date`
  - `updated_date_source = ingestion_start`
- `created_date` is optional and should only appear when PDF ingestion can
  extract source modified metadata from the PDF data.
- `language` is optional.
