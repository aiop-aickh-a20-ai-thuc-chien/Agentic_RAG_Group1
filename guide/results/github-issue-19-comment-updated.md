## Báo cáo tóm tắt URL ingestion hiện tại

Mình đã thử pipeline hiện tại với các file kết quả trong `guide/results` và artifact local trong:

`src/agentic_rag/ingestion/url/data/artifacts`

### 1. Đang dùng gì để fetch URL?

Hiện tại dùng Python stdlib `urllib.request` trong:

`src/agentic_rag/ingestion/url/loader.py`

Entry point chính:

- `load_url_chunks(url)`
- `load_html_chunks(html, source, source_url)`
- `load_text_chunks(text, source)`

Pipeline hiện chỉ nhận URL dạng absolute `http` hoặc `https`.

### 2. Đang dùng gì để extract / clean nội dung?

Hiện tại chưa dùng `trafilatura`.

Đang dùng parser tự viết nhẹ bằng Python stdlib `html.parser.HTMLParser` trong:

`src/agentic_rag/ingestion/url/parser.py`

Parser hiện tại:

- lấy `title`
- gom section theo heading `h1`, `h2`, `h3`
- bỏ các tag noise cơ bản: `script`, `style`, `nav`, `footer`, `header`, `aside`
- output là normalized text theo section
- có thể lưu `parsed.md`, `chunks.jsonl`, `manifest.json` vào `src/agentic_rag/ingestion/url/data/artifacts`

Baseline chạy được, nhưng vẫn còn hạn chế:

- một số menu/footer/CTA vẫn lọt vào text
- một số trang VinFast còn noise nhiều
- parser hiện chưa xử lý tốt nội dung nằm trong ảnh, PDF, hoặc file attachment

### 3. Đang chunk dữ liệu thế nào?

Chunking nằm ở:

`src/agentic_rag/ingestion/url/chunking.py`

Mặc định dùng deterministic character-based chunking:

- `chunk_size = 1200`
- `chunk_overlap = 150`
- normalize whitespace
- ưu tiên cắt ở word boundary
- giữ metadata section từ parser

Ngoài ra đã có optional model-assisted chunking trong:

`src/agentic_rag/ingestion/url/model_chunking.py`

Có thể so sánh config model OpenAI/Gemini bằng fake client trong test, không cần API key/network. Khi dùng thật:

- OpenAI dùng `OPENAI_API_KEY`
- Gemini dùng `GEMINI_API_KEY` hoặc `GOOGLE_API_KEY`

### 4. `tiktoken` đã thêm chưa?

Chưa.

Hiện tại `tiktoken` chưa có trong `pyproject.toml` và `uv.lock`. Chunking vẫn là character-based mặc định. Nếu muốn token-aware chunking cho OpenAI embedding/generation thì nên thêm `tiktoken` ở bước sau.

Đề xuất:

- Sprint hiện tại: giữ character-based baseline để ổn định.
- Iteration tiếp theo: thêm `tiktoken` để đếm token và cắt chunk theo token budget.
- Với Gemini, nếu không dùng tokenizer chính thức thì có thể dùng fallback approximate token/char ratio hoặc chỉ dùng model-assisted chunking.

### 5. Nếu URL có ảnh thì cần làm gì?

Có 3 mức xử lý:

1. Basic:
   - lấy `alt`, `title`, caption gần ảnh
   - lưu metadata ảnh: `image_url`, `alt_text`, `caption`, `source_url`
   - nếu ảnh nằm trong thẻ link clickable thì lưu cả target URL

2. Intermediate:
   - tải ảnh về artifact local nếu cần audit
   - OCR ảnh chứa chữ bằng OCR engine hoặc vision model
   - đưa OCR text vào `parsed.md` theo section tương ứng

3. Advanced:
   - dùng OpenAI/Gemini vision để mô tả ảnh, bảng, infographic
   - chỉ dùng khi ảnh thật sự chứa thông tin cần retrieval
   - lưu rõ metadata `extraction_method = vision` để phân biệt với text HTML

Với trang listing có ảnh clickable, như VinFast xe máy điện, nên crawl link trong `<a><img ...></a>` và ingest từng detail URL riêng. Mình đã test được listing page và 9 detail URLs, artifact đã lưu trong `src/agentic_rag/ingestion/url/data/artifacts`.

### 6. Nếu URL là PDF hoặc có link PDF thì cần làm gì?

Không nên để URL HTML parser xử lý PDF như HTML.

Đề xuất:

- Nếu URL response có `Content-Type: application/pdf` hoặc path kết thúc `.pdf`:
  - route sang `src/agentic_rag/ingestion/pdf`
  - lưu metadata gốc: `source_url`, `downloaded_file`, `content_type`
  - không parse bằng URL HTML parser

- Nếu trang HTML có link PDF:
  - giữ link PDF trong metadata của page
  - tạo child source cho từng PDF nếu cần ingest
  - PDF child source nên dùng PDF ingestion pipeline riêng

- Nếu trang HTML embed PDF bằng `iframe`/`object`:
  - detect `src`
  - lưu vào manifest như related asset
  - optional: tải và ingest bằng PDF pipeline

Nói ngắn gọn: URL ingestion xử lý HTML/text và discovery; PDF ingestion xử lý PDF content.

### 7. URL sample nên dùng tiếp

Sample data nên có một `domain/source` với nhiều URL con, không chỉ homepage. Như vậy test được cùng một source có nhiều page, duplicate navigation, section metadata, chunk quality, và citation metadata.

Nguồn Vintech nên dùng:

- `https://vintechvietnam.com/`
- `https://vintechvietnam.com/gioi-thieu/`
- `https://vintechvietnam.com/thuong-hieu/`
- `https://vintechvietnam.com/giai-phap/`
- `https://vintechvietnam.com/du-an/`

Nguồn VinFast nên dùng thêm:

- product detail page
- support / FAQ page
- policy / service page
- listing page có clickable image dẫn tới detail page

### 8. Đề xuất hướng cải thiện

Mình đề xuất giữ implementation hiện tại làm deterministic baseline, sau đó cải thiện theo thứ tự:

1. Fix/verify encoding cho tiếng Việt.
2. Thêm `trafilatura` làm parser chính để extract main content và output Markdown.
3. Giữ stdlib parser hiện tại làm fallback khi `trafilatura` fail hoặc trả rỗng.
4. Detect asset trong HTML: image, PDF, iframe/object.
5. Với clickable image, lưu `image_url`, `alt_text`, `target_url`, rồi ingest target URL nếu cùng domain và đúng scope.
6. Với PDF link hoặc PDF response, route sang PDF ingestion.
7. Nâng chunking lên Markdown heading-aware trước, sau đó thêm `tiktoken` cho token-aware chunking.
8. Dùng OpenAI/Gemini API optional cho semantic grouping, contextual chunk summaries, vision/OCR quality, hoặc quality evaluation.

### Kết luận

Baseline hiện tại đủ để unblock URL ingestion và tạo `Chunk` theo contract, nhưng chưa phải production-quality parser. Bước tiếp theo hợp lý nhất là thêm `trafilatura`, asset discovery cho image/PDF, routing PDF sang PDF pipeline, rồi cải thiện chunking thành heading-aware/token-aware.
