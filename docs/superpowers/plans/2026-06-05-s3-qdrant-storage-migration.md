# S3 Qdrant Storage Migration Plan

## Objective

Implement the cloud storage migration described in
`docs/superpowers/specs/2026-06-05-s3-qdrant-storage-migration-design.md`.

The target v1 architecture is:

- AWS S3 stores source files, URL/text records, parsed Markdown, debug artifacts,
  chunk manifests, and source manifests.
- Qdrant stores the persistent retrieval index for cloud mode.
- Cloud retrieval uses Qdrant hybrid search instead of rebuilding BM25 from S3
  chunks on every request.
- Existing API contracts and shared `Chunk` and `SearchResult` models remain
  compatible.

## Constraints

- Do not add Postgres for v1.
- Do not implement deduplication for v1.
- Keep `EVIDENCE_PROVIDER=local_pdf` as the API-facing provider path.
- Preserve local fallback modes: JSONL, Postgres source store, turbovec, and
  pgvector.
- Tests must be deterministic and must not require AWS credentials, Qdrant
  network access, external vector databases, or live API services.
- Avoid unrelated refactors.

## Implementation Steps

1. Add cloud configuration.

- Extend `.env.example` with `LOCAL_SOURCE_STORE=s3`, `AWS_REGION`,
  `AWS_S3_BUCKET`, optional `AWS_S3_PREFIX`, `DENSE_VECTOR_STORE=qdrant`,
  `QDRANT_URL`, `QDRANT_API_KEY`, and `QDRANT_COLLECTION`.
- Add small config helpers for required S3 and Qdrant settings.
- Fail fast with clear errors when required cloud settings are missing.

2. Add an S3 source store adapter.

- Implement an S3-backed source store in the local source integration boundary.
- Store each document under a deterministic prefix:

```text
<prefix>/<document_id>/
  manifest.json
  raw/source.pdf
  raw/source.txt
  parsed/document.md
  chunks/chunks.jsonl
  debug/...
  artifacts/...
```

- Preserve the current chunk manifest shape by serializing existing `Chunk`
  objects as JSONL.
- Support document write, chunk read, all-chunks read, selected-document chunk
  read, source listing, single delete, and delete-all behavior.

3. Route provider writes through S3 mode.

- Extend `LocalPdfEvidenceProvider.from_env()` so
  `LOCAL_SOURCE_STORE=s3` builds the S3 source store.
- Keep local temporary files only where current parsers require file paths.
- Update trace payloads so cloud mode reports S3 object keys and Qdrant index
  status instead of JSONL paths.
- Keep `/sources/{document_id}/raw` behavior stable by streaming the S3 object
  through the API.

4. Add Qdrant vector storage and retrieval.

- Add `DENSE_VECTOR_STORE=qdrant` support in the retrieval layer.
- Upsert one Qdrant point per chunk with deterministic point IDs and payloads
  containing `document_id`, `chunk_id`, `storage_chunk_id`, `source_type`,
  `source`, `url`, `page`, `section`, `text`, and original metadata.
- Store dense and sparse vectors so cloud mode can use Qdrant hybrid retrieval.
- Reconstruct `SearchResult` objects from Qdrant payloads.
- Support filtering by selected `document_ids`.
- Support deleting Qdrant points by `document_id`.

5. Preserve local retrieval behavior.

- Keep the current in-memory BM25 path for local JSONL/Postgres modes.
- Do not make S3 chunk manifests part of the normal cloud retrieval hot path.
- Keep existing fusion/generation behavior compatible with returned
  `SearchResult` objects.

6. Update API, docs, and tests.

- Update docs to explain S3 as durable source/artifact storage and Qdrant as the
  cloud retrieval index.
- Add mocked unit tests for S3 storage behavior.
- Add mocked unit tests for Qdrant upsert, hybrid retrieval reconstruction,
  document filtering, and delete behavior.
- Add API/provider regression tests for upload, URL upload, text upload, list,
  debug, raw streaming, retrieval, and delete in cloud mode.

## Verification

Run targeted tests first:

```bash
uv run pytest tests/test_local_pdf_provider.py tests/test_api.py tests/test_retrieval_search.py -q
```

Then run the full quality gate:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

## Goal Message

```text
/goal Implement the S3 + Qdrant storage migration from docs/superpowers/plans/2026-06-05-s3-qdrant-storage-migration.md. Preserve existing public API contracts and shared Chunk/SearchResult models. Add LOCAL_SOURCE_STORE=s3 using AWS S3 for raw PDF files, URL/text source records, parsed Markdown, debug artifacts, chunk manifests, and source manifests. Add DENSE_VECTOR_STORE=qdrant using Qdrant for persistent dense+sparse hybrid retrieval, with document_id filtering and SearchResult reconstruction from Qdrant payloads. Keep EVIDENCE_PROVIDER=local_pdf as the API-facing provider, keep jsonl/postgres/turbovec/pgvector fallback modes, skip deduplication and Postgres for v1, stream raw S3 objects through the existing /sources/{document_id}/raw endpoint, implement delete for both S3 prefixes and Qdrant document points, update .env.example and docs, and verify with mocked deterministic tests that require no AWS credentials, Qdrant network, external vector database, or live API services. Run uv run pytest tests/test_local_pdf_provider.py tests/test_api.py tests/test_retrieval_search.py -q plus uv run ruff format --check ., uv run ruff check ., uv run mypy, and uv run pytest -q.
```
