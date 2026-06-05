# Auto Data Tool

Auto Data Tool hỗ trợ nạp dữ liệu URL/PDF, chạy đúng pipeline ingestion của repo, kiểm tra kết quả parse/chunking và tạo cặp Question/Answer cho evaluation dataset.

Tool này nằm trong `guide/reports/auto_data_tool` và lưu kết quả QA vào `guide/reports/result.xlsx`.

## Chức năng chính

- Nạp danh sách URL từ file `.txt`.
- Nạp PDF từ một thư mục local.
- Gọi trực tiếp ingestion pipeline của repo qua `python_parser.py`.
- Hiển thị danh sách vector chunks để review và label.
- Tự động sinh Question/Answer bằng LLM gateway.
- Lưu từng QA hoặc batch QA vào Excel.
- Lazy-load Question/Answer đã có trong Excel theo `chunk_id` khi người dùng chọn chunk.
- Review raw document, parsed Markdown và chunk highlight trong tab riêng.

## Kiến trúc hoạt động

### Frontend

Frontend dùng HTML/CSS/JavaScript thuần trong thư mục `public`.

Các màn hình chính:

- `Label QA`: dùng để chọn chunk, xem context, sinh hoặc chỉnh sửa Question/Answer.
- `Review parsing / chunking`: dùng để kiểm tra raw document, Markdown sau parse và các chunk được tô màu.

### Backend Node.js

`server.js` cung cấp các API local:

```text
POST /api/parse_list
POST /api/chunk
POST /api/generate
POST /api/generate_batch
POST /api/excel
POST /api/excel_batch
GET  /api/processed
GET  /api/label?chunkId=<chunk_id>
```

Backend chịu trách nhiệm:

- Đọc danh sách URL/PDF từ input path.
- Gọi Python parser để dùng ingestion thật của repo.
- Gọi LLM gateway để sinh QA.
- Đọc/ghi `guide/reports/result.xlsx`.
- Lazy-load QA đã label từ Excel theo `chunk_id`.

### Python parser

`python_parser.py` không tự implement parser/chunker riêng. File này gọi trực tiếp module ingestion của repo:

```python
agentic_rag.ingestion.url.loader.load_url_with_artifacts
agentic_rag.ingestion.pdf.loader.load_pdf_chunks
```

Với URL, parser trả về:

```json
{
  "success": true,
  "chunks": [...],
  "markdown": "parsed markdown used by ingestion"
}
```

Điều này giúp Auto Data Tool review đúng Markdown và chunks mà hệ thống RAG thật đang dùng.

## Pipeline URL hiện tại

URL ingestion hiện dùng pipeline mới đã port từ bản `Crawl link`:

- Render/extract theo hướng DOM Markdown.
- Giữ cấu trúc heading H1-H6.
- Bắt nội dung trong tab/accordion khi có thể.
- Ghép các dòng thông số dạng label/value.
- Normalize noise như nav, footer, cookie, CTA, dialog.
- Chunk theo `hierarchical-markdown-subsection-overlap`.

Với live URL, loader sẽ thử Playwright extractor nếu môi trường có Python Playwright. Nếu chưa có hoặc browser extraction lỗi, pipeline fallback về fetch HTML thường để tool vẫn chạy được.

## Cài đặt

Cài dependencies Node.js trong thư mục tool:

```bash
cd guide/reports/auto_data_tool
npm install
```

Repo Python environment cần được sync trước ở root project:

```bash
uv sync
```

Nếu không dùng `uv`, cần đảm bảo `.venv` của repo tồn tại và import được package `agentic_rag`.

## Chạy tool

Từ thư mục `guide/reports/auto_data_tool`:

```bash
node server.js
```

Sau đó mở:

```text
http://localhost:3000
```

Có thể đổi port bằng `.env` cùng cấp `server.js`:

```env
PORT=3000
```

## Cách sử dụng

### 1. Nạp dữ liệu

Nhập một trong hai nguồn:

```text
TXT File Path (URLs)
PDF Folder Path
```

Sau đó bấm:

```text
+ Nạp Document Chunk
```

Tool sẽ gọi `/api/parse_list`, sau đó gọi `/api/chunk` cho từng source.

### 2. Review parsing và chunking

Chọn một chunk trong bảng, sau đó mở tab:

```text
Review parsing / chunking
```

Tab này hiển thị:

- Raw document source bằng iframe nếu source là URL HTTP/HTTPS.
- Nút mở trang gốc trong tab browser mới.
- Parsed Markdown sau HTML/PDF ingestion.
- Danh sách chunk theo màu để dễ kiểm tra boundary.
- Chunk đang chọn được highlight riêng.

Nếu raw preview bị website chặn iframe, dùng nút `Mở trang gốc` để xem trực tiếp.

### 3. Label QA

Mở tab:

```text
Label QA
```

Khi chọn chunk, tool sẽ gọi:

```text
GET /api/label?chunkId=<chunk_id>
```

Nếu Excel đã có QA cho chunk đó, Question/Answer sẽ được fill tự động. Cách này tránh load toàn bộ Excel lên frontend.

Nếu chưa có QA:

- Nhập API key nếu cần.
- Chọn model.
- Bấm `Tự động sinh QA cặp`.
- Review lại Question/Answer.
- Bấm `Lưu Excel`.

### 4. Batch QA

Cấu hình:

```text
Độ trễ nhịp (ms)
Số chunk / batch
```

Bấm:

```text
Chạy hàng loạt
```

Tool sẽ duyệt các chunk chưa có QA, gọi LLM theo batch và lưu Excel theo batch.

## File kết quả

Kết quả được ghi vào:

```text
guide/reports/result.xlsx
```

Các cột chính:

```text
id
section_name
question
expected_answer
ground_truth_chunk_ids
ground_truth_doc
is_out_of_scope
custom_preconds
```

`ground_truth_chunk_ids` dùng `chunk_id` từ ingestion pipeline, nên có thể map ngược về chunk trong tool hoặc hệ thống RAG.

## Ghi chú về generated artifacts

Không commit các file kết quả hoặc artifact local như:

```text
guide/reports/result.xlsx
src/agentic_rag/ingestion/Crawl link/*.jsonl
src/agentic_rag/ingestion/Crawl link/*.json
src/agentic_rag/ingestion/Crawl link/*.txt
.playwright-cli/
```

Các artifact này chỉ dùng để debug/review local hoặc comment trong PR nếu cần minh họa kết quả.

## Kiểm tra nhanh sau khi sửa tool

Các check tối thiểu liên quan:

```bash
node --check guide/reports/auto_data_tool/server.js
node --check guide/reports/auto_data_tool/public/app.js
.\.venv\Scripts\python.exe -m py_compile guide/reports/auto_data_tool/python_parser.py
.\.venv\Scripts\python.exe -m pytest src/agentic_rag/ingestion/url/tests tests/test_ingestion_chunking.py -q
```
