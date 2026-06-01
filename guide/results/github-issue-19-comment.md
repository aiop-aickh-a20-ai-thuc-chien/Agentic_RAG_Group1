## Báo cáo tóm tắt URL ingestion hiện tại

Mình đã thử pipeline hiện tại với các file kết quả trong `guide/results`:

- `url-ingestion-vinfastauto.com.md`
- `url-ingestion-vintechvietnam.com.md`
- `chunk-samples.md`
- `url-ingestion-summary-report.md`

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
- output là normalized text theo section, chưa phải Markdown chuẩn

Kết quả thử nghiệm cho thấy baseline chạy được, nhưng vẫn còn hạn chế:

- một số menu/footer/CTA vẫn lọt vào text
- một số output tiếng Việt trong sample bị lỗi encoding
- trang có nhiều navigation như VinFast bị noise nhiều hơn

### 3. Đang chunk dữ liệu thế nào?

Chunking nằm ở:

`src/agentic_rag/ingestion/url/chunking.py`

Hiện tại dùng deterministic character-based chunking:

- `chunk_size = 1200`
- `chunk_overlap = 150`
- normalize whitespace
- ưu tiên cắt ở word boundary
- giữ metadata section từ parser

Chunk metadata hiện có:

- `source`
- `source_type`
- `url`
- `section`
- `title`
- `fetched_at`
- `content_hash`
- `chunk_index`

Hiện tại chưa dùng OpenAI/Gemini cho chunking, chưa semantic chunking, và chưa token-aware chunking.

### 4. URL sample nên dùng tiếp

Mình đề xuất sample data nên có một `domain/source` với nhiều URL con, không chỉ homepage. Như vậy test được cùng một source có nhiều page, duplicate navigation, section metadata, chunk quality, và citation metadata.

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

### 5. Đề xuất hướng cải thiện

Mình đề xuất giữ implementation hiện tại làm deterministic baseline, sau đó cải thiện theo thứ tự:

1. Fix/verify encoding cho tiếng Việt.
2. Thêm `trafilatura` làm parser chính để extract main content và output Markdown.
3. Giữ stdlib parser hiện tại làm fallback khi `trafilatura` fail hoặc trả rỗng.
4. Nâng chunking lên Markdown heading-aware trước, sau đó mới fixed/token split.
5. Có thể thêm `tiktoken` để token-aware chunking nếu dùng OpenAI embedding.
6. OpenAI/Gemini API chưa cần dùng cho basic extraction; nên để cho embeddings, semantic grouping, contextual chunk summaries, hoặc quality evaluation sau.

### Kết luận

Baseline hiện tại đủ để unblock URL ingestion và tạo `Chunk` theo contract, nhưng chưa phải production-quality parser. Bước tiếp theo hợp lý nhất là thêm `trafilatura` Markdown extraction + fallback parser, rồi cải thiện chunking thành heading-aware/token-aware.
