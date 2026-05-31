# Hướng dẫn phần #149 - Generation, Guardrails và Next.js UI

Ngày tạo: 31/05/2026

Tài liệu này mô tả phần việc của `hotrandinhnguyen` trong issue #149. Phạm vi chỉ gồm generation, citation, guardrails, backend endpoint phục vụ UI và Next.js frontend. Các phần PDF ingestion, URL/text ingestion, retrieval và fusion không nằm trong phạm vi này.

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

- Source panel cho PDF/URL/Text ở mức input placeholder.
- Chat panel để gửi question.
- Answer panel.
- Citation panel.
- Không parse PDF.
- Không fetch URL.
- Không build retrieval.
- Không fusion/rerank.

Khi các phần #145-#148 hoàn thành, chỉ cần thay mock evidence bằng evidence thật từ phần #148. Contract `Answer`, `Citation`, `SearchResult` không đổi.

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

