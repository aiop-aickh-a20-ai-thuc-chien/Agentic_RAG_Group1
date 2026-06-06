# Agentic RAG Group 1

Scaffold trung lập về tech stack cho phần triển khai Agentic RAG của nhóm.

## Mục đích

Repository này định nghĩa nền tảng mã nguồn dùng chung cho dự án nhóm. Scaffold
không chọn sẵn LangChain, LlamaIndex, Streamlit, Gradio, vector database hay LLM
provider cho toàn bộ thành viên.

Mỗi thành viên có thể chọn thư viện phù hợp bên trong module mình phụ trách,
nhưng các module phải trao đổi dữ liệu thông qua Pydantic v2 models trong
`src/agentic_rag/core/contracts.py`.

## Cấu trúc dự án

```text
src/agentic_rag/
  core/
    contracts.py        Pydantic models dùng chung: Chunk, SearchResult, Citation, Answer
    ports.py            Protocol interfaces cho ranh giới module
  ingestion/
    pdf/                Module xử lý PDF ingestion
    url/                Module xử lý URL ingestion
  retrieval/
    search.py           Ranh giới query, BM25 và dense retrieval
    fusion.py           Ranh giới hybrid fusion và evidence context
  generation/
    answering.py        Ranh giới generation, citation và guardrail
  evaluation/
    metrics.py          Ranh giới đánh giá Recall@k và MRR@k
  app.py                Ranh giới app, chưa khóa UI framework
  testing/fixtures.py   Dữ liệu mẫu dùng chung cho test module

docs/
  ai-collaboration-guide.md
                         Hướng dẫn làm việc với AI Coding Assistant
  coding-standards.md   Quy chuẩn kỹ thuật chung
  git-workflow.md       Quy trình branch, commit và Pull Request
  module-contracts.md   Contract tích hợp giữa các module

tests/
  test_contracts.py
  test_ports.py
  test_fixtures.py
```

## Phát triển

Dự án dùng `uv` để quản lý package và môi trường Python.

```bash
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

Khi CI chạy hoặc khi `uv.lock` đã tồn tại, dùng lệnh cài đặt khóa phiên bản:

```bash
uv sync 
```

## Phát triển với AI Coding Assistant

Phần lớn thành viên làm việc cùng AI Coding Assistant. Hãy đọc
`docs/ai-collaboration-guide.md` trước khi bắt đầu task để prompt, ranh giới
module, quality gate và quy tắc an toàn thống nhất trong cả nhóm.

## Ranh giới module

| Phần | Boundary |
| --- | --- |
| PDF ingestion + chunking | `agentic_rag.ingestion.pdf` |
| URL ingestion + chunking | `agentic_rag.ingestion.url` |
| BM25/dense retrieval | `agentic_rag.retrieval.search` |
| Hybrid fusion + evidence context | `agentic_rag.retrieval.fusion` |
| Generation + citations + UI | `agentic_rag.generation.answering`, `agentic_rag.app` |
| Evaluation report | `agentic_rag.evaluation.metrics` |

## Storage backends

Local development can run with JSONL source manifests and the in-process
`turbovec` dense store. Cloud prototype mode keeps `EVIDENCE_PROVIDER=local_pdf`
but can set `LOCAL_SOURCE_STORE=s3` and `DENSE_VECTOR_STORE=qdrant` so S3 stores
raw source files, parsed Markdown, debug artifacts, and chunk manifests while
Qdrant stores the persistent hybrid retrieval index.

## Dense embedding providers

`DENSE_EMBEDDING_PROVIDER=auto` uses OpenAI when `OPENAI_API_KEY` is configured.
Without that key it selects `local_openai`, which expects an OpenAI-compatible
`/v1/embeddings` service:

```env
DENSE_EMBEDDING_PROVIDER=auto
DENSE_EMBEDDING_DIMENSIONS=
OPENAI_EMBEDDING_DIMENSIONS=1536
LOCAL_EMBEDDING_BASE_URL=http://127.0.0.1:8000/v1
LOCAL_EMBEDDING_MODEL=your-embedding-model
LOCAL_EMBEDDING_API_KEY=
```

Run vLLM in an isolated uv environment:

```bash
uv run --isolated --with vllm \
  vllm serve your-embedding-model --runner pooling --port 8000
```

Or run SGLang without adding it to this application's dependencies:

```bash
uv run --isolated --with "sglang[all]" \
  python -m sglang.launch_server \
  --model-path your-embedding-model \
  --is-embedding \
  --port 30000
```

For SGLang, set `LOCAL_EMBEDDING_BASE_URL=http://127.0.0.1:30000/v1`.
`DENSE_EMBEDDING_PROVIDER=huggingface` remains an explicit in-process option and
is never selected automatically.

Smoke-test either local server:

```bash
curl http://127.0.0.1:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"your-embedding-model","input":["embedding smoke test"]}'
```

One `QDRANT_COLLECTION` may contain only one provider/model/dimension profile.
When changing the embedding model or provider, use a new collection name or
delete the existing collection and reindex. The app does not recreate an
incompatible collection automatically.

## Quality Gate

Mỗi Pull Request cần pass các lệnh sau:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

CI chạy cùng các lệnh này trong `.github/workflows/ci.yml`.
