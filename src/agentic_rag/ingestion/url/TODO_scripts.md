# URL Ingestion TODO - Scripts

Operational scripts can read or write database, vector-store, backend, S3, or
evaluation state. Keep them as deployment/evaluation tools around URL
ingestion, not as URL ingestion internals.

## Script Touchpoints

- `scripts/setup_eval_db.sql` creates evaluation tables.
- `scripts/migrate_dataset_fk_set_null.sql` alters evaluation schema
  relationships.
- `scripts/migrate_frozen_question_ids.sql` alters frozen-question schema
  state.
- `scripts/migrate_excel_to_neon.py` writes datasets, questions, approved
  questions, runs, and results into Neon/PostgreSQL.
- `scripts/rerun_failed_questions.py` deletes failed `eval_results` rows,
  updates `eval_runs.failed`, and writes replacement results.
- `scripts/scan_conflicts.py` can replace conflict findings and corpus stats in
  Neon when not run with `--dry-run`.
- `scripts/backfill_dedup.py` can write dedup metadata or vector payload
  updates through the configured local source provider when not run with
  `--dry-run`.
- `scripts/bulk_upload.py` posts URL sources to the backend upload endpoint and
  can create or retry source documents.
- `scripts/check_coverage.py` reads S3 and Qdrant coverage state for uploaded
  chunks.
- `scripts/check_missing_chunks.py` reads S3 and Qdrant state to find source
  documents without indexed chunks.

## Before Using Scripts With URL Data

- Confirm the target backend URL, database, S3 bucket, and vector store before
  running anything that writes external state.
- Prefer available `--dry-run` modes before a write path.
- Keep generated upload files, failure lists, and temporary exports out of
  `src/agentic_rag/ingestion/url`.
- Treat DB/vector writes as an operational step after URL ingestion emits clean
  chunks and metadata.
- After upload or backfill, run the golden-data evaluator and keep reports under
  `guide/reports/`.

