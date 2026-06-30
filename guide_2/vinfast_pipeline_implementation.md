# VinFast pipeline implementation

Implementation cho checklist nằm tại
`src/agentic_rag/ingestion/integration/url/vinfast/`:

- `browser.py`: Chrome channel, browser profile, random viewport và human-like click helper.
- `models.py`: `VinFastProduct`, validation và deterministic product ID.
- `pipeline.py`: retry exponential backoff và network -> DOM -> VLM fallback chain.
- `structured.py`: Instructor adapters cho text và screenshot GPT-4o Vision.
- `storage.py`: canonical content hash, `hashes.json`, versioned snapshot và failed URL JSONL.
- `chunking.py`: semantic RAG chunks với metadata sản phẩm đầy đủ.
- `scheduler.py`: factory cho APScheduler daily job lúc 02:00.

Optional runtime dependencies:

```powershell
uv sync --extra vinfast-pipeline
```

Core fallback, schema, hashing và chunking không cần network hoặc API key. Instructor/VLM chỉ
được gọi khi adapter VLM là stage cuối cùng và hai nguồn network/DOM không trả về product hợp
lệ.

Verification mục tiêu:

```powershell
uv run pytest -q tests/test_vinfast_pipeline.py tests/test_url_ingestion_integration.py
uv run ruff check src/agentic_rag/ingestion/integration/url/vinfast tests/test_vinfast_pipeline.py
uv run mypy src/agentic_rag/ingestion/integration/url/vinfast tests/test_vinfast_pipeline.py
```
