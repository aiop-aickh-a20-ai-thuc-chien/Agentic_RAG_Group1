# Local Embedding Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an automatic OpenAI-to-local embedding selection path for Qdrant indexing and retrieval while keeping Hugging Face explicit and preventing incompatible vectors from sharing a fixed collection.

**Architecture:** Introduce a focused embedding configuration/client boundary under `agentic_rag.retrieval`, then make `search.py` consume its resolved provider metadata and validated vectors. vLLM and SGLang remain external services and are accessed through their shared OpenAI-compatible `/v1/embeddings` API. Qdrant keeps one configured collection and validates its dense-vector size plus a stored provider/model profile before every upsert and query.

**Tech Stack:** Python 3.12, LangChain OpenAI/Hugging Face embeddings, qdrant-client, pytest, Ruff, mypy, uv

---

### Task 1: Add deterministic embedding provider resolution

**Files:**
- Create: `src/agentic_rag/retrieval/embeddings.py`
- Create: `tests/test_retrieval_embeddings.py`

- [ ] Write failing tests for `auto`, explicit `openai`, explicit `local_openai`, explicit `huggingface`, unknown providers, and missing required configuration.
- [ ] Verify tests fail because the new module and interfaces do not exist.
- [ ] Add immutable `EmbeddingConfig` and `EmbeddingProfile` records plus `EmbeddingConfigurationError`.
- [ ] Implement `resolve_embedding_config()` with these rules:
  - `auto` is the default.
  - `auto` resolves to OpenAI only when `OPENAI_API_KEY` is non-empty.
  - Otherwise `auto` resolves to `local_openai` and requires `LOCAL_EMBEDDING_BASE_URL` plus `LOCAL_EMBEDDING_MODEL`.
  - Explicit providers never fall back.
  - Hugging Face remains explicit.
- [ ] Run `uv run pytest tests/test_retrieval_embeddings.py -q` and confirm all provider-resolution tests pass.

### Task 2: Build embedding clients and validate vectors

**Files:**
- Modify: `src/agentic_rag/retrieval/embeddings.py`
- Modify: `tests/test_retrieval_embeddings.py`

- [ ] Write failing tests proving OpenAI receives `OPENAI_EMBEDDING_DIMENSIONS` (default `1536`), local OpenAI-compatible clients receive base URL/model/optional key but no dimensions argument, and Hugging Face preserves the current model configuration.
- [ ] Write failing tests for empty vectors, inconsistent vector lengths, and configured `DENSE_EMBEDDING_DIMENSIONS` mismatches.
- [ ] Implement client construction using `OpenAIEmbeddings` for both OpenAI and `local_openai`; disable OpenAI-specific token-length checking for local model names.
- [ ] Treat `DENSE_EMBEDDING_DIMENSIONS` as an optional expected size. Infer the native size from the first vector when unset and validate every vector.
- [ ] Do not send the dimensions parameter to local OpenAI-compatible endpoints.
- [ ] Run `uv run pytest tests/test_retrieval_embeddings.py -q`.

### Task 3: Integrate resolved embedding profiles into retrieval

**Files:**
- Modify: `src/agentic_rag/retrieval/search.py`
- Modify: `tests/test_retrieval_search.py`
- Modify: `tests/test_local_pdf_provider.py`

- [ ] Write failing tests for provider/model/dimension metadata in successful Qdrant traces and for precise configuration/indexing errors in `index_write.dense_index`.
- [ ] Replace direct environment branching in `search.py` with the embedding boundary for document and query embeddings.
- [ ] Return requested provider, resolved provider, fallback reason, model, and actual dimensions in dense metadata and upsert traces.
- [ ] Preserve the current upload behavior: S3 source storage succeeds first, and embedding/index failures are captured without rolling it back.
- [ ] Confirm runtime OpenAI failures propagate as errors and never trigger local fallback.
- [ ] Run `uv run pytest tests/test_retrieval_embeddings.py tests/test_retrieval_search.py tests/test_local_pdf_provider.py -q`.

### Task 4: Protect the fixed Qdrant collection

**Files:**
- Modify: `src/agentic_rag/retrieval/search.py`
- Modify: `tests/test_retrieval_search.py`

- [ ] Write failing tests for collection creation with the actual vector size, matching profile acceptance, dimension mismatch, provider/model mismatch, and legacy populated collections without profile metadata.
- [ ] Validate the existing named dense vector dimension before upsert and query.
- [ ] Store `_embedding_profile` in each point payload with schema version, provider, model, and dimensions.
- [ ] Inspect an existing point before upsert/query and require an exact provider/model/dimension match.
- [ ] Allow an empty existing collection to adopt the active profile.
- [ ] Reject populated legacy or incompatible collections with instructions to change `QDRANT_COLLECTION` or delete and reindex.
- [ ] Never delete, recreate, or rename a collection automatically.
- [ ] Run `uv run pytest tests/test_retrieval_search.py -q`.

### Task 5: Document configuration and local serving

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/generation-ui-guide.md`

- [ ] Set the documented default to `DENSE_EMBEDDING_PROVIDER=auto`.
- [ ] Document `DENSE_EMBEDDING_DIMENSIONS`, `OPENAI_EMBEDDING_DIMENSIONS`, `LOCAL_EMBEDDING_BASE_URL`, `LOCAL_EMBEDDING_MODEL`, and `LOCAL_EMBEDDING_API_KEY`.
- [ ] Add uv-managed vLLM and SGLang launch examples and an `/v1/embeddings` smoke test.
- [ ] State that vLLM/SGLang are external serving environments and must not be added to the RAG application's dependencies.
- [ ] Document model/provider switching as an explicit new-collection or delete-and-reindex operation.

### Task 6: Verify the complete change

- [ ] Run:

```bash
uv run pytest tests/test_retrieval_embeddings.py tests/test_retrieval_search.py tests/test_local_pdf_provider.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

- [ ] Confirm tests require no API keys, model downloads, network access, live Qdrant, or local serving process.
- [ ] Review the final diff for secret leakage, public contract changes, and accidental vLLM/SGLang dependencies.

## Assumptions

- vLLM and SGLang expose an OpenAI-compatible `/v1/embeddings` endpoint.
- Local model selection and server startup remain operator responsibilities.
- Query and document embeddings use the same model and dimensions.
- A fixed Qdrant collection contains exactly one embedding profile.
- Failed historical indexing is not automatically backfilled; users re-upload or explicitly reindex later.
- Existing public API response models and shared `Chunk`/`SearchResult` contracts remain unchanged.
