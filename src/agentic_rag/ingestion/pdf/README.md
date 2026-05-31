# PDF Ingestion Subproject

Thư mục này là boundary riêng cho PDF ingestion. Những phần chỉ phục vụ PDF
ingestion, bao gồm benchmark parser và adapter chạy benchmark ngoài, được giữ
trong thư mục này để không làm rò rỉ trách nhiệm sang module khác.

## Mục tiêu hiện tại

Phase hiện tại là benchmark-first parser selection. Chưa chọn ngay một backend
như PaddleOCR, MinerU, Docling, Surya/Chandra/Marker hoặc dots.ocr. Thay vào
đó, module PDF cung cấp wrapper để chuẩn hóa cách chạy OmniDocBench với output
Markdown của parser trước khi triển khai `load_pdf_chunks`.

## Benchmark tự động

OmniDocBench là nguồn benchmark lập trình được cho phase này. Repo này không
vendor benchmark dataset hoặc mã nguồn OmniDocBench; developer cần cung cấp
ground-truth JSON, thư mục Markdown parser output và môi trường Docker hoặc
checkout OmniDocBench cục bộ.

Wrapper hỗ trợ hai backend:

- `docker`: dựng command Docker và mount ground truth, predictions, config và
  result directory vào container OmniDocBench.
- `local`: chạy `python pdf_validation.py --config <config>` từ checkout
  OmniDocBench cục bộ.

Ví dụ dry-run từ root repository:

```bash
uv --directory src/agentic_rag/ingestion/pdf run python -m agentic_rag.ingestion.pdf.benchmarking.cli run-omnidocbench \
  --backend docker \
  --ground-truth /path/to/OmniDocBench.json \
  --predictions /path/to/parser_markdown_outputs \
  --output-dir src/agentic_rag/ingestion/pdf/.data/omnidocbench/results \
  --config-output src/agentic_rag/ingestion/pdf/.data/omnidocbench/config.yaml \
  --dry-run
```

CI chỉ kiểm tra wrapper, config generation và dry-run behavior. CI không tải
dataset, không gọi Docker, không yêu cầu network và không yêu cầu checkout
OmniDocBench.

## Đánh giá thủ công

Human evaluation không được encode thành Pydantic scoring model. Reviewer sẽ
tự đối chiếu PDF gốc hoặc ground truth chính thức với output Markdown của
parser, rồi ghi nhận judgement thủ công. Mục tiêu là giữ phần benchmark tự động
dựa trên benchmark hợp lệ, còn phần human review vẫn là quá trình kiểm tra trực
quan/cross-reference do reviewer thực hiện.

Các file trong `.data/` không được commit.

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
