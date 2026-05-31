# PDF Ingestion Subproject

Thư mục này là boundary riêng cho PDF ingestion. Những phần chỉ phục vụ PDF
ingestion, bao gồm parser baseline, chunking và benchmark parser, được giữ trong
thư mục này để không làm rò rỉ trách nhiệm sang module khác.

## Mục tiêu hiện tại

Phase hiện tại ưu tiên tạo baseline end-to-end để unblock các phase tiếp theo
của RAG pipeline. Parser baseline là Docling: module PDF dùng Docling để chuyển
PDF cục bộ sang Markdown, sau đó tách Markdown thành `Chunk` objects theo
contract dùng chung.

Benchmark workflow với OmniDocBench vẫn được giữ để so sánh và tối ưu parser ở
các vòng sau. Nói cách khác: triển khai Docling trước để có pipeline chạy được,
rồi dùng benchmark và review thủ công để quyết định thay thế hoặc tinh chỉnh
parser sau.

## Chạy PDF ingestion baseline

Từ root repository:

```bash
uv sync
uv run python -c "from agentic_rag.ingestion.pdf import load_pdf_chunks; print(load_pdf_chunks('path/to/file.pdf'))"
```

Public API của module vẫn là:

```python
from agentic_rag.ingestion.pdf import load_pdf_chunks

chunks = load_pdf_chunks("path/to/file.pdf")
```

`load_pdf_chunks()` chỉ trả về `Chunk` trong memory và không tự ghi file debug.
Nếu cần lưu output để kiểm tra parser hoặc đánh giá chunking, dùng helper riêng
được mô tả ở phần bên dưới.

Mỗi `Chunk` trả về có metadata chính:

- `source`: đường dẫn PDF đầu vào.
- `source_type`: luôn là `pdf`.
- `file_name`: tên file PDF.
- `page`: hiện là `None` trong baseline Markdown chunking.
- `section`: heading Markdown gần nhất nếu có.
- `parser`: `docling`.
- `chunk_index`: thứ tự chunk bắt đầu từ 1.

## Lưu artifact để debug và đánh giá

Khi cần quan sát Markdown sau parser và danh sách chunk sau chunking, chạy helper
rõ ràng thay vì thêm side effect vào loader chính:

```bash
uv run python -c "from agentic_rag.ingestion.pdf import save_pdf_ingestion_artifacts; print(save_pdf_ingestion_artifacts('path/to/file.pdf').model_dump())"
```

Mặc định helper ghi vào thư mục đã được ignore:

```text
src/agentic_rag/ingestion/pdf/.data/artifacts/<pdf-stem>/<run-id>/
  parsed.md
  chunks.jsonl
  manifest.json
```

Ý nghĩa các file:

- `parsed.md`: Markdown do Docling export từ PDF gốc.
- `chunks.jsonl`: mỗi dòng là một shared `Chunk` sau bước chunking.
- `manifest.json`: metadata của lần chạy, gồm input path, parser, run id, đường
  dẫn artifact và số lượng chunk.

Không commit nội dung trong `.data/`; đây chỉ là dữ liệu phục vụ debug và
evaluation cục bộ.

## Benchmark tự động

OmniDocBench là nguồn benchmark lập trình được cho phase tối ưu parser. Repo này
không vendor benchmark dataset hoặc mã nguồn OmniDocBench; developer cần cung
cấp ground-truth JSON, thư mục Markdown parser output và môi trường Docker hoặc
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

Human evaluation không được encode thành Pydantic scoring model. Reviewer sẽ tự
đối chiếu PDF gốc hoặc ground truth chính thức với output Markdown của parser,
rồi ghi nhận judgement thủ công. Mục tiêu là giữ phần benchmark tự động dựa trên
benchmark hợp lệ, còn phần human review vẫn là quá trình kiểm tra trực quan hoặc
cross-reference do reviewer thực hiện.

Các file trong `.data/` không được commit.

RAGFlow chỉ dùng làm benchmark/reference, không phải dependency hay main
platform của repo trong phase này.

## Chạy như subproject

PDF ingestion có `pyproject.toml` riêng để thành viên có thể chạy kiểm tra cục
bộ mà không cần thao tác ở root project.

Từ root repository:

```bash
uv --directory src/agentic_rag/ingestion/pdf sync --locked
uv --directory src/agentic_rag/ingestion/pdf run ruff format --check .
uv --directory src/agentic_rag/ingestion/pdf run ruff check .
uv --directory src/agentic_rag/ingestion/pdf run mypy
uv --directory src/agentic_rag/ingestion/pdf run pytest -q
```

Root CI vẫn chạy toàn bộ test của repo, bao gồm `tests/` của PDF subproject.
