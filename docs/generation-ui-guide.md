# Hướng dẫn phần #149 - Generation, Guardrails và Next.js UI

Ngày tạo: 31/05/2026

Tài liệu này mô tả phần việc của `hotrandinhnguyen` trong issue #149. Phạm vi chính gồm generation, citation, guardrails, backend endpoint phục vụ UI và Next.js frontend. PDF/URL/text ingestion tự build của nhóm vẫn thuộc phần trước; trong phần này chỉ có source import tạm qua RAGFlow để demo không bị block.

## Tech stack

Backend:

- Python 3.12
- FastAPI
- OpenAI API
- Model mặc định: `gpt-4o-mini`

Frontend:

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn-style local components
- lucide-react icons

## Env

Backend dùng:

```text
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

Frontend dùng:

```text
NEXT_PUBLIC_AGENTIC_RAG_API_URL=http://127.0.0.1:8000
```

Không commit file `.env` thật. Dùng `.env.example` ở root repo và `frontend/.env.example` làm mẫu.

## Backend

Các file chính:

```text
src/agentic_rag/generation/llm.py
src/agentic_rag/generation/answering.py
src/agentic_rag/api.py
src/agentic_rag/app.py
```

Chạy backend:

```bash
uv sync
uv run python -m agentic_rag.app
```

Endpoint chính:

```text
POST /answer
GET /health
```

Request tối thiểu:

```json
{
  "question": "Pin VF8 duoc bao hanh bao lau?",
  "use_mock_evidence": true
}
```

Khi `use_mock_evidence` là `true`, backend dùng `sample_search_results()` để phần #149 chạy được dù #145-#148 chưa xong.

## Generation behavior

`generate_answer(...)` giữ contract:

```python
generate_answer(
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> Answer
```

Hành vi:

- Không có question hoặc không có evidence hợp lệ thì trả `not_found`.
- Có `OPENAI_API_KEY` thì gọi OpenAI.
- Không có `OPENAI_API_KEY` thì fallback bằng câu trả lời grounded từ evidence đầu tiên.
- Citation chỉ được tạo từ metadata của `evidence_chunks`.
- Citation giả hoặc sai source/page/section/url sẽ bị reject.

## Frontend

Frontend nằm ở:

```text
frontend/
```

Cài dependencies:

```bash
cd frontend
npm install
```

Chạy dev server:

```bash
npm run dev
```

Frontend mặc định gọi backend ở:

```text
http://127.0.0.1:8000
```

## UI scope

UI hiện tại thuộc phạm vi #149:

- Source panel cho PDF/URL/Text.
- PDF upload có thể nạp tài liệu thật vào RAGFlow qua `/sources/upload`.
- URL import fetch nội dung trang trong backend, rồi upload text vào RAGFlow qua `/sources/url`.
- Text import upload văn bản người dùng vào RAGFlow qua `/sources/text`.
- Chat panel để gửi question.
- Answer panel.
- Citation panel.
- Không tự build parse/chunk/retrieval khi chưa có phần #145-#148.
- Không fusion/rerank.

Khi các phần #145-#148 hoàn thành, chỉ cần thay `EVIDENCE_PROVIDER=ragflow` bằng provider của pipeline nhóm. Contract `Answer`, `Citation`, `SearchResult` không đổi.

## RAGFlow fallback

RAGFlow được dùng theo từng tầng, không gọi all-in-one chat answer:

```text
PDF/Text import -> RAGFlow parse/chunk/index
URL import -> backend fetch/normalize URL -> RAGFlow chunk/index
question -> RAGFlow retrieval chunks
retrieval chunks -> SearchResult
SearchResult -> generate_answer() của project
```

Ghi chú: RAGFlow docs mới có endpoint URL runtime attachment
`/v1/document/upload_info?url=...`, nhưng RAGFlow self-host `v0.25.6` trong môi trường
demo hiện trả `404`, nên URL dùng fallback backend fetch để không block demo.

Backend endpoints:

```text
POST /sources/upload
POST /sources/url
POST /sources/text
GET  /sources/{document_id}/chunks
POST /answer
POST /answer/stream
```

Env cần bật:

```bash
EVIDENCE_PROVIDER=ragflow
RAGFLOW_BASE_URL=http://127.0.0.1:9380
RAGFLOW_API_KEY=...
RAGFLOW_DATASET_ID=...
```

## Local PDF provider

When the PDF modules are ready to run without RAGFlow, switch only the evidence
provider. The API endpoints stay the same, so the frontend does not need a
separate flow:

```bash
EVIDENCE_PROVIDER=local_pdf
LOCAL_PDF_STORE_DIR=storage/local_pdf
LOCAL_PDF_RETRIEVAL_TOP_K=5
LOCAL_PDF_RETRIEVAL_CANDIDATE_K=20
```

Flow:

```text
PDF upload -> local PDF parser -> local chunks JSONL
question -> query preprocessing
chunks + query -> BM25 retrieval + dense retrieval
BM25 + dense -> RRF fusion
RRF candidates -> rerank
final SearchResult -> build_evidence_context()
SearchResult + evidence context -> generate_answer() of module #149
```

Use `EVIDENCE_PROVIDER=ragflow` again when comparing against the RAGFlow
baseline.

Trace log:

```bash
RAG_TRACE_ENABLED=true
RAG_TRACE_PROVIDER=jsonl
RAG_TRACE_PATH=logs/rag_runs.jsonl
```

Optional LangSmith tracing:

```bash
pip install -e ".[observability]"
RAG_TRACE_PROVIDER=langsmith
LANGSMITH_API_KEY=...
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=agentic-rag-group1
```

Use `RAG_TRACE_PROVIDER=both` to keep local JSONL logs while also sending runs
to LangSmith.

Trace events:

```text
source_ingestion:
  source_upload -> parse -> chunking -> index_write

rag_answer:
  retrieve-evidence -> generate-grounded-answer -> citation-validation
```

## Verification

Backend:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

Frontend:

```bash
cd frontend
npm run build
```

