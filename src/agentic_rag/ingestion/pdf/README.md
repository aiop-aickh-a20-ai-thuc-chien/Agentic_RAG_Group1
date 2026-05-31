# PDF Ingestion Subproject

Thư mục này là boundary riêng cho PDF ingestion. Những phần chỉ phục vụ PDF
ingestion, bao gồm benchmark parser, manifest URL và helper chấm điểm parser,
được giữ trong thư mục này để không làm rò rỉ trách nhiệm sang module khác.

## Mục tiêu hiện tại

Phase hiện tại là benchmark-first parser selection. Chưa chọn ngay một backend
như PaddleOCR, MinerU, Docling, Surya/Chandra/Marker hoặc dots.ocr. Thay vào
đó, module PDF định nghĩa một tập public Vietnamese PDFs và các check nhẹ để
đánh giá parser trước khi triển khai `load_pdf_chunks`.

## Dữ liệu benchmark

- Manifest: `benchmarking/manifest.json`
- PDF tải về cục bộ: `.data/raw/`
- Parser outputs cục bộ: `.data/outputs/`

Các file trong `.data/` không được commit. Manifest chỉ lưu URL và ghi chú
nguồn để giảm rủi ro bản quyền và tránh làm phình repo.

## Tiêu chí đánh giá

Parser cần được đánh giá bằng hybrid review:

- Automated checks: snippet tiếng Việt, dấu tiếng Việt, metadata và coverage.
- Human review: `vietnamese_text`, `reading_order`, `table_fidelity`,
  `formula_fidelity`, `chart_image_usefulness`, `rag_readiness`.

RAGFlow chỉ dùng làm benchmark/reference, không phải dependency hay main
platform của repo trong phase này.


## Chạy như subproject

PDF ingestion có `pyproject.toml` riêng để thành viên có thể chạy kiểm tra cục bộ mà không cần thao tác ở root project.

Từ root repository:

```bash
uv --directory src/agentic_rag/ingestion/pdf sync --locked
uv --directory src/agentic_rag/ingestion/pdf run ruff format --check .
uv --directory src/agentic_rag/ingestion/pdf run ruff check .
uv --directory src/agentic_rag/ingestion/pdf run mypy
uv --directory src/agentic_rag/ingestion/pdf run pytest -q
```

Root CI vẫn chạy toàn bộ test của repo, bao gồm `tests/` của PDF subproject.
