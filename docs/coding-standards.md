# Quy Chuẩn Coding

Tài liệu này định nghĩa các tiêu chuẩn chung cho thành viên và AI Assistant.
Tài liệu bổ sung cho `docs/git-workflow.md`.

## Quản lý package

- Dùng `uv` cho mọi thao tác quản lý dependency và môi trường Python.
- Không commit virtual environment, cache, local index, file upload, secret hoặc
  lockfile cục bộ.
- Chỉ thêm runtime dependency khi module thật sự cần.
- Thêm development tool vào dependency group `dev`.
- Dùng `uv sync` trong CI; không enforce lockfile trong workflow hiện tại.

## Style Python

- Target Python 3.12 trở lên.
- Dùng type hint cho public function, protocol method và shared contract.
- Dùng generic type built-in như `list[Chunk]` và `dict[str, Any]`; không dùng
  legacy `typing.List`.
- Dùng mypy với Pydantic plugin làm static typing gate.
- Ưu tiên module nhỏ, mỗi module có một trách nhiệm rõ ràng.
- Giữ shared contracts trung lập về framework; không import thư viện framework
  cụ thể trong `agentic_rag.core.contracts` hoặc `agentic_rag.core.ports`.
- Dùng Pydantic v2 `BaseModel` cho shared boundary đi qua nhiều module.
- Giữ top-level shared model strict và frozen; field linh hoạt theo nguồn dữ
  liệu đặt trong `Chunk.metadata`.
- Tránh global mutable state trong implementation module.
- Raise exception rõ ràng cho input local không hợp lệ, nhưng hành vi
  `"not_found"` dành cho người dùng nằm ở generation boundary.

## Format và lint

- Dùng Ruff cho format và lint.
- Chạy trước khi mở Pull Request:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest -q
```

- CI enforce:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

## Test

- Thêm hoặc cập nhật test khi thay đổi business logic.
- Test không được yêu cầu API key, network access, external vector database,
  UI server.
- Dùng `agentic_rag.testing.fixtures` cho module test cần sample chunks hoặc
  search results dùng chung.
- Ưu tiên deterministic test thay vì test phụ thuộc live LLM output.

## Ranh giới module

- Implementation bên trong module có thể chọn thư viện riêng.
- Public input và output phải tương thích với `Chunk`, `SearchResult`,
  `Citation` và `Answer`.
- Public contract object nên là instance của shared Pydantic models, hoặc dữ
  liệu mà Pydantic có thể validate thành các models đó.
- Nếu module cần metadata bổ sung, thêm vào `Chunk.metadata` và không xóa các
  key dùng chung.
- Không coupling một module với chi tiết implementation private của module khác.

## Bảo mật và secret

- Không commit `.env`, API key, credential, downloaded model cache, vector index
  hoặc generated artifact.
- Giữ credential theo provider trong environment variables.
- Document environment variables bắt buộc trong `.env.example` trước khi phụ
  thuộc vào chúng.

## Tài liệu

- Cập nhật README hoặc docs liên quan khi thêm command, module, dependency hoặc
  hành vi người dùng nhìn thấy.
- Tách riêng cập nhật trạng thái/comment project-management bên ngoài khỏi thay
  đổi code, trừ khi đã được phê duyệt rõ ràng.
