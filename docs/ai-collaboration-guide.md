# Hướng Dẫn Phát Triển Với AI Coding Assistant

Tài liệu này dành cho thành viên sử dụng AI Coding Assistant khi làm việc trong
repository. Nội dung mô tả tiêu chuẩn của repo, workflow kỳ vọng và các bước
kiểm tra cần pass trước khi gửi review.

## Cần đọc trước

Trước khi yêu cầu AI Assistant sửa code, hãy cung cấp hoặc yêu cầu assistant đọc
các file sau:

- `AGENTS.md`
- `docs/git-workflow.md`
- `docs/coding-standards.md`
- `docs/module-contracts.md`
- `README.md`

Assistant cần kiểm tra trạng thái file hiện tại trước khi đề xuất hoặc thực hiện
thay đổi. Không dựa vào giả định từ một cuộc trò chuyện trước đó.

## Workflow với AI Assistant

1. Bắt đầu từ branch đúng theo `docs/git-workflow.md`.
2. Giữ mỗi task nhỏ và có phạm vi rõ ràng.
3. Yêu cầu assistant giải thích file và boundary dự định thay đổi trước khi sửa.
4. Giữ implementation trong đúng domain package.
5. Giữ nguyên public contracts từ `agentic_rag.core`.
6. Thêm hoặc cập nhật test khi thay đổi logic.
7. Chạy full quality gate trước khi yêu cầu review.
8. Tự review diff trước khi commit hoặc mở Pull Request.

Không yêu cầu assistant commit trực tiếp vào các nhánh được bảo vệ.

## Prompt mẫu

Có thể dùng prompt dạng này khi giao việc implementation:

```text
Task: <tên task ngắn>

Scope:
- Chỉ làm trong <package/file>.
- Không refactor module không liên quan.
- Giữ input/output public tương thích với contracts trong agentic_rag.core.

Requirements:
- <hành vi 1>
- <hành vi 2>
- <edge case>

Verification:
- uv run ruff format --check .
- uv run ruff check .
- uv run mypy
- uv run pytest -q
```

Nếu task phụ thuộc vào external API, model hoặc service, hãy nêu rõ hành vi khi
không có credential hoặc không có network.

## Cấu trúc codebase

Repository dùng domain packages:

```text
agentic_rag/
  core/          Contracts và protocol boundaries dùng chung
  ingestion/     PDF và URL ingestion
  retrieval/     Query preprocessing, sparse retrieval, dense retrieval, fusion
  generation/    Grounded answer generation và citation validation
  evaluation/    Metrics cho retrieval và answer quality
  app.py         Ranh giới application, chưa khóa UI framework
```

Dùng `agentic_rag.core.contracts` cho Pydantic models dùng chung:

- `Chunk`
- `SearchResult`
- `Citation`
- `Answer`

Dùng `agentic_rag.core.ports` cho protocol boundaries.

## Quy tắc package và tooling

- Dùng `uv` để quản lý dependency và môi trường Python.
- Chỉ thêm runtime dependency khi module thật sự cần.
- Thêm development tool vào dependency group `dev`.
- Commit `uv.lock`.
- Dùng generic type built-in của Python 3.12 như `list[Chunk]` và `dict[str, Any]`.
- Không dùng kiểu cũ `typing.List` hoặc `typing.Dict`.

## Quality Gate

Chạy trước khi gửi review:

```bash
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

Nếu format fail, chạy:

```bash
uv run ruff format .
```

Sau đó chạy lại full quality gate.

## Kỳ vọng về test

- Test phải deterministic.
- Test không được yêu cầu API key, network access, external vector database,
  UI server.
- Dùng `agentic_rag.testing.fixtures` cho sample chunks và search results dùng chung.
- Ưu tiên module test nhỏ thay vì end-to-end test lớn khi chưa có integration code.
- Khi thay scaffold placeholder bằng logic thật, cần cập nhật test cho behavior
  được implement.

## Kỳ vọng về tài liệu

Cập nhật tài liệu khi thay đổi ảnh hưởng đến:

- Lệnh setup
- Dependencies
- Ranh giới module
- Public contracts
- Quality gates
- Hành vi người dùng nhìn thấy

Không đưa tham chiếu project-management bên ngoài vào comment code hoặc docs của
repo trừ khi nhóm đã thống nhất rõ ràng.

## Quy tắc an toàn

- Không commit secrets, file `.env`, local indexes, uploaded documents, model
  caches hoặc generated artifacts.
- Không dùng lệnh Git phá hủy dữ liệu nếu chưa được phê duyệt rõ ràng.
- Không refactor diện rộng nếu task không yêu cầu.
- Không che giấu test fail hoặc type error bằng cách nới lỏng quality gate.

## Checklist trước Pull Request

Trước khi mở Pull Request:

- Branch tuân thủ `docs/git-workflow.md`.
- Diff nằm trong phạm vi task.
- Public contracts vẫn dùng Pydantic models từ `agentic_rag.core`.
- Behavior mới có test.
- Tài liệu được cập nhật nếu cần.
- Full quality gate pass ở local.
