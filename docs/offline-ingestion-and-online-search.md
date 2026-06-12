# Offline Ingestion And Online Search

This guide is the handoff path for teammates who need to run the internal RAG
pipeline locally. It separates two workflows:

- Offline ingestion: parse sources, chunk them, persist chunks and artifacts.
- Online search: run the API, retrieve indexed chunks, fuse/rerank evidence, and
  generate grounded answers.

For the complete LLM, embedding, and reranker environment contract, read
[`model-runtime-configuration.md`](model-runtime-configuration.md).

## 1. Install

Use `uv` from the repository root:

```bash
uv sync
```

Optional extras:

```bash
# In-process sentence-transformers embedding and reranker.
uv sync --extra local-models

# Evaluation workbook tooling and deferred RAGAS dependencies.
uv sync --extra evaluation

# LangSmith trace integration.
uv sync --extra observability
```

`uv.lock` is intentionally local and ignored in this repo. Do not include it in a
PR.

### Local Model Torch Setup

`local-models` installs `sentence-transformers` and `torch` for in-process
embeddings and reranking:

```bash
uv sync --extra local-models
```

Torch wheel selection is machine-specific, so this repo does not pin a global
CUDA wheel or PyTorch index in `pyproject.toml`.

- Windows/Linux CPU: use `EMBEDDING_DEVICE=cpu` and `RERANK_DEVICE=cpu`.
- Windows/Linux NVIDIA CUDA: install the torch build recommended by the official
  PyTorch selector for the machine's CUDA target, then use
  `EMBEDDING_DEVICE=cuda` and `RERANK_DEVICE=cuda`.
- macOS: start with `auto`; use `mps` only when the installed PyTorch and
  sentence-transformers stack supports it, otherwise use `cpu`.

Verify local torch/device behavior with:

```bash
uv run python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available())"
```

## 2. Baseline Local Environment

Copy `.env.example` to `.env`, then start from this local setup:

```env
EVIDENCE_PROVIDER=local_pdf

LOCAL_PDF_STORE_DIR=storage/local_pdf
LOCAL_PDF_PIPELINE=ocr
LOCAL_PDF_STRATEGY=docling
LOCAL_PDF_CHUNKER=deterministic
LOCAL_SOURCE_STORE=jsonl

VECTOR_STORE_PROVIDER=turbovec
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

RERANK_PROVIDER=score
AGENT_MODE=false

LLM_PROVIDER=none
LLM_MODEL=
```

This setup works without API keys for ingestion and retrieval smoke tests. Answer
generation stays extractive/fallback when `LLM_PROVIDER=none`.

To enable answer generation through an API provider:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your_api_key
```

Role-specific keys such as `GENERATION_LLM_MODEL` are optional overrides. Leave
them blank to inherit the global `LLM_*` profile.

## 3. Offline Ingestion Pipeline

Offline ingestion converts sources into persisted chunks. It does not require the
question-answer API to be running.

### Parse One PDF With The CLI

Use this when validating parser/chunker behavior before indexing through the API:

```bash
uv run python -m agentic_rag.ingestion.pdf.cli parse path/to/file.pdf \
  --pipeline ocr \
  --strategy docling \
  --chunker deterministic \
  --output-json
```

For artifact inspection:

```bash
uv run python -m agentic_rag.ingestion.pdf.cli parse path/to/file.pdf \
  --pipeline ocr \
  --strategy docling \
  --chunker deterministic \
  --write-artifacts \
  --output-root storage/local_pdf/parser-artifacts
```

If the path contains spaces, quote it:

```bash
uv run python -m agentic_rag.ingestion.pdf.cli parse "data/Lux A-ENG.pdf" --output-json
```

### Ingest Sources Through The API

Start the API:

```bash
uv run uvicorn agentic_rag.api:api --reload --port 8000
```

Upload a PDF:

```bash
curl -X POST http://127.0.0.1:8000/sources/upload \
  -F "file=@path/to/file.pdf"
```

Upload a URL:

```bash
curl -X POST http://127.0.0.1:8000/sources/url \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/page"}'
```

Upload raw text:

```bash
curl -X POST http://127.0.0.1:8000/sources/text \
  -H "Content-Type: application/json" \
  -d '{"title":"Warranty note","text":"Pin VF8 duoc bao hanh 8 nam."}'
```

Inspect indexed sources:

```bash
curl "http://127.0.0.1:8000/sources?include_chunks=true"
```

Inspect chunks for one document:

```bash
curl http://127.0.0.1:8000/sources/{document_id}/chunks
```

Inspect parser/chunker debug data:

```bash
curl http://127.0.0.1:8000/sources/{document_id}/debug
```

### Dedup New And Existing Sources

Upload-time dedup runs in the `local_pdf` provider after chunks receive local
metadata and before chunks are persisted/indexed. It marks only
`duplicate_candidate` chunks; canonical chunks are left unmarked and referenced
from the candidate metadata.

Canonical selection is deterministic. New uploads keep existing chunks as
canonical. Legacy backfill prefers chunks/documents already referenced by eval
questions, then older `created_at` timestamps when available, then
`document_id`, chunk index, and `chunk_id`.

Dedup uses three layers by default:

- exact SHA-256 over normalized text
- SimHash near-duplicate detection
- embedding cosine similarity using the shared `EMBEDDING_*` runtime

Relevant environment variables:

```env
INGESTION_DEDUP_ENABLED=true
DEDUP_ENABLE_EXACT=true
DEDUP_ENABLE_SIMHASH=true
DEDUP_ENABLE_EMBEDDING=true
DEDUP_SIMHASH_HAMMING_THRESHOLD=6
DEDUP_EMBEDDING_SIMILARITY_THRESHOLD=0.92
DEDUP_EMBEDDING_BATCH_SIZE=64
```

For documents uploaded before dedup existed, run a backfill:

```bash
uv run python scripts/backfill_dedup.py --dry-run
uv run python scripts/backfill_dedup.py
```

`--dry-run` reports the candidate count without writing. The real run rewrites
stored chunk metadata and re-upserts dense payloads so the vector store also has
the updated dedup metadata. Use `--strict-embedding` if Layer 3 embedding failure
should stop the job instead of falling back to exact/SimHash.

Review candidates in the internal UI:

```text
/internal/dedup-review
```

### Knowledge-Quality Conflicts

Inspect knowledge-quality conflicts and duplicates:

```bash
curl http://127.0.0.1:8000/sources/{document_id}/quality
curl http://127.0.0.1:8000/knowledge-quality
curl -X POST http://127.0.0.1:8000/knowledge-quality/scan
```

The knowledge-quality scan is offline-first and only supports
`EVIDENCE_PROVIDER=local_pdf`. It writes compact summaries to
`Chunk.metadata["knowledge_quality"]` and returns detailed facts/findings for
review. See [knowledge-quality-conflict-detection.md](knowledge-quality-conflict-detection.md)
for the research framing, demo fixture, and evaluation template.

## 4. Online Search Pipeline

Online search answers questions using the currently configured evidence provider.
For the internal pipeline, keep:

```env
EVIDENCE_PROVIDER=local_pdf
```

Then ask a question:

```bash
curl -X POST http://127.0.0.1:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"Pin VF8 duoc bao hanh bao lau?"}'
```

Limit search to selected source documents:

```bash
curl -X POST http://127.0.0.1:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"Pin VF8 duoc bao hanh bao lau?","document_ids":["doc-id-1"]}'
```

Streaming answer endpoint:

```bash
curl -N -X POST http://127.0.0.1:8000/answer/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"Pin VF8 duoc bao hanh bao lau?"}'
```

The online path is:

```text
question
-> optional agent query rewrite
-> BM25 retrieval
-> dense retrieval
-> fusion
-> optional reranker
-> evidence context
-> answer generation
-> citations
```

## 5. Cloud Prototype Storage

Use S3 for source files/artifacts and Qdrant for dense vectors:

```env
EVIDENCE_PROVIDER=local_pdf
LOCAL_SOURCE_STORE=s3
AWS_DEFAULT_REGION=ap-southeast-1
AWS_S3_BUCKET=your-bucket
AWS_S3_PREFIX=agentic-rag/sources
# Optional on developer machines only:
# AWS_PROFILE=agentic-rag

VECTOR_STORE_PROVIDER=qdrant
VECTOR_STORE_URL=https://your-qdrant.example
VECTOR_STORE_API_KEY=your_qdrant_key
VECTOR_STORE_COLLECTION=agentic_rag_chunks
```

Use a new `VECTOR_STORE_COLLECTION` when switching embedding provider, model, or
vector dimension. Older pgvector indexes that relied on the previous implicit
`document` collection must set `VECTOR_STORE_COLLECTION=document` or be reindexed
into `agentic_rag_chunks`.

## 6. RAGFlow Baseline

RAGFlow is a baseline/fallback provider. It is not the internal ingestion
pipeline.

```env
EVIDENCE_PROVIDER=ragflow
RAGFLOW_BASE_URL=http://127.0.0.1:9380
RAGFLOW_API_KEY=your_ragflow_api_key
RAGFLOW_DATASET_ID=your_dataset_id
```

With this setup, `/answer` retrieves chunks from RAGFlow, converts them into
shared `SearchResult` contracts, and still uses this app's generation/citation
boundary.

## 7. Quality Gate

Before handing off a branch or opening a PR:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

If dependency metadata changes, refresh the local ignored lockfile as needed:

```bash
uv lock
```

Do not stage `uv.lock`.
