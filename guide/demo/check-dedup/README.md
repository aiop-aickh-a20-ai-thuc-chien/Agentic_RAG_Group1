# Check Dedup Demo

Offline demo for checking shared ingestion metadata and duplicate detection.

Use this when you want a fast smoke test without crawling URLs or parsing PDFs.
It reads sample chunks, checks the shared metadata contract, runs Layer 1/Layer 2
dedup detection, and writes a short report.

## Run

```powershell
uv run python guide/demo/check-dedup/check_dedup.py
```

Outputs:

- `output/metadata_contract.json`
- `output/dedup_report.json`
- `output/chunks_with_dedup.jsonl`
- `output/check_dedup_report.md`

## Metadata Rule

- `source_type` is required.
- `updated_date` is required and means ingestion start time.
- `created_date` is optional and means source modified date when URL/PDF can
  extract it from the source data.
- `language` is optional.
- `document_type` is optional.

This demo intentionally includes one sample chunk without `source_type` so the
metadata contract section shows what a failure looks like. That bad sample also
omits `updated_date`.
