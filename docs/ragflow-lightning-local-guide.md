# Chạy RAGFlow trên Lightning và dùng với app local

Tài liệu này mô tả cách chạy RAGFlow trên Lightning AI Studio, còn backend/frontend của project chạy trên máy local.

## 1. Chạy RAGFlow trên Lightning

Trong terminal Lightning:

```bash
git clone https://github.com/infiniflow/ragflow.git
cd ragflow
git fetch --tags
git checkout v0.25.6
```

Kiểm tra image:

```bash
cat docker/.env | grep RAGFLOW_IMAGE
```

Nên thấy:

```env
RAGFLOW_IMAGE=infiniflow/ragflow:v0.25.6
```

Start RAGFlow:

```bash
docker compose -f docker/docker-compose.yml pull
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps
```

Kiểm tra API nội bộ:

```bash
curl -v http://127.0.0.1:9380
```

Nếu trả `404 Not Found` là bình thường; miễn là không bị connection reset/refused.

## 2. Mở UI RAGFlow

Trong Lightning Ports/Port Viewer, mở port:

```text
80
```

Vào UI RAGFlow, sau đó:

1. Vào `Avatar -> Settings -> Model providers`.
2. Thêm provider OpenAI hoặc provider bạn dùng.
3. Set default models:
   - `LLM`: ví dụ `gpt-4o-mini`
   - `Embedding`: ví dụ `text-embedding-3-small`
4. Tạo dataset, ví dụ:

```text
agentic-rag-group1-nguyen
```

Chọn chunking method đơn giản như `naive`/default.

## 3. Lấy API key và dataset id

Lấy API key trong UI:

```text
Avatar -> API -> copy API key
```

Không commit hoặc gửi API key lên chat/GitHub.

Lấy dataset id trong terminal Lightning:

```bash
curl --request GET \
  --url "http://127.0.0.1:9380/api/v1/datasets?page=1&page_size=20" \
  --header "Authorization: Bearer RAGFLOW_API_KEY"
```

Copy field `id` của dataset cần dùng.

## 4. Tạo proxy public cho RAGFlow API

Lightning có thể không publish trực tiếp port `9380` vì root `/` trả `404`. Dùng proxy port `18080`.

Trong terminal Lightning:

```bash
cat > ragflow_proxy.py <<'PY'
from fastapi import FastAPI, Request, Response
import httpx

app = FastAPI()
TARGET = "http://127.0.0.1:9380"

@app.get("/")
def health():
    return {"status": "ok", "target": TARGET}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    async with httpx.AsyncClient(timeout=120) as client:
        body = await request.body()
        resp = await client.request(
            request.method,
            f"{TARGET}/{path}",
            params=request.query_params,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            content=body,
        )

    excluded = {"content-encoding", "transfer-encoding", "connection"}
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={k: v for k, v in resp.headers.items() if k.lower() not in excluded},
    )
PY
uv run --no-project --with fastapi --with uvicorn --with httpx \
  uvicorn ragflow_proxy:app --host 0.0.0.0 --port 18080
```

Giữ terminal proxy này chạy.

Trong Lightning Ports/Port Viewer, mở port:

```text
18080
```

URL public sẽ có dạng:

```text
https://18080-...cloudspaces.litng.ai
```

Test URL đó trên browser. Nếu thấy JSON `{"status":"ok", ...}` là proxy chạy đúng.

## 5. Cấu hình app local

Tạo file `.env` ở root project local:

```env
EVIDENCE_PROVIDER=ragflow
RAGFLOW_BASE_URL=https://18080-...cloudspaces.litng.ai
RAGFLOW_API_KEY=your_ragflow_api_key
RAGFLOW_DATASET_ID=your_dataset_id
RAG_TRACE_ENABLED=true
RAG_TRACE_PATH=logs/rag_runs.jsonl

LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your_openai_api_key
```

Tạo/sửa `frontend/.env.local`:

```env
NEXT_PUBLIC_AGENTIC_RAG_API_URL=http://127.0.0.1:8000
```

## 6. Chạy backend và frontend local

Backend:

```powershell
cd C:\Users\ACER\Downloads\Agentic_RAG_Group1
.\.venv\Scripts\python.exe -m uvicorn agentic_rag.api:api --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd C:\Users\ACER\Downloads\Agentic_RAG_Group1\frontend
npm run dev
```

Mở:

```text
http://127.0.0.1:3000/citation-chat
```

Nếu Next tự chạy port `3001`, mở:

```text
http://127.0.0.1:3001/citation-chat
```

## 7. Test

1. Upload PDF trong UI local.
2. Chờ trạng thái `Sẵn sàng hỏi đáp`.
3. Nhập câu hỏi.
4. Xem trace:

```powershell
Get-Content logs\rag_runs.jsonl -Tail 1 | ConvertFrom-Json | ConvertTo-Json -Depth 20
```

Trace sẽ có question, chunks, scores, metadata, answer và citations.

## Lỗi thường gặp

### Backend báo thiếu RAGFlow config

Kiểm tra `.env` có đủ:

```env
RAGFLOW_BASE_URL=
RAGFLOW_API_KEY=
RAGFLOW_DATASET_ID=
```

Restart backend sau khi sửa.

### Frontend báo `Failed to fetch`

Kiểm tra backend:

```powershell
curl.exe http://127.0.0.1:8000/health
```

Nếu backend chạy port khác, sửa `frontend/.env.local` và restart frontend.

### RAGFlow API không connect được

Trên Lightning kiểm tra:

```bash
curl -v http://127.0.0.1:9380
curl -v http://127.0.0.1:18080
```

Nếu proxy tắt, chạy lại:

```bash
uvicorn ragflow_proxy:app --host 0.0.0.0 --port 18080
```

### Upload xong nhưng hỏi trả `Không có trong tài liệu`

Chờ RAGFlow parse/chunk xong. UI local sẽ chỉ cho hỏi khi có chunk.
