Mình đã research các hướng từ ChatGPT, Gemini, Claude, Perplexity và đối chiếu với contract hiện tại của project. Phần code nên bắt đầu ở `src/agentic_rag/ingestion/url`, output bám theo schema chung `Chunk`.

## Mình dự định dùng tech nào để fetch URL?

Mình dự định dùng `httpx` làm lựa chọn chính.

Lý do:

- Hỗ trợ sync/async tốt, dễ mở rộng khi cần ingest nhiều URL.
- Có timeout, redirect, header `User-Agent` rõ ràng.
- Nhẹ hơn browser automation, phù hợp Sprint 1.

Fallback/nâng cao:

- `Playwright` hoặc `Crawl4AI` nếu gặp trang render bằng JavaScript.
- Firecrawl API chỉ nên dùng khi site bị block hoặc cần managed crawling.

## Dùng tech nào để extract main content?

Mình dự định dùng `trafilatura` để extract main content từ HTML sang text/Markdown.

Lý do:

- Tự loại nhiều boilerplate như menu, sidebar, footer, ads.
- Output Markdown/text phù hợp cho chunking và citation.
- Phù hợp với hướng RAGFlow/baseline vì RAGFlow cũng dùng các tool extract HTML/main content tương tự.

Fallback:

- `BeautifulSoup4` + `lxml` nếu `trafilatura` trả rỗng hoặc cần custom rule theo tag/class.

## Cách loại bỏ noise HTML?

Pipeline dự kiến:

1. Fetch HTML bằng `httpx`.
2. Chạy `trafilatura.extract(..., output_format="markdown")` để lấy nội dung chính.
3. Nếu kết quả rỗng hoặc quá nhiễu, dùng `BeautifulSoup` để remove các tag:
   - `script`
   - `style`
   - `nav`
   - `footer`
   - `header`
   - `aside`
4. Normalize text: bỏ khoảng trắng dư, giữ heading/list/link cần thiết cho citation.

## Dùng tech nào để chunk URL/text?

Mình dự định dùng `langchain-text-splitters`.

Hướng chunk:

- Với URL/HTML: ưu tiên chunk theo heading/section trước.
- Sau đó dùng `RecursiveCharacterTextSplitter` để chia các section quá dài.
- Default ban đầu: chunk khoảng 700-1000 tokens hoặc cấu hình tương đương theo character, overlap 100-150 tokens.

Lý do:

- Giữ được ngữ cảnh section tốt hơn split cố định.
- Dễ gắn metadata `section`.
- Dễ test và thay thế bằng custom chunker nếu cần.

## Metadata URL/section lưu thế nào?

Mỗi chunk sẽ trả về `Chunk` theo schema chung:

```python
Chunk(
    chunk_id="url_<hash>_c001",
    text="Nội dung chunk...",
    metadata={
        "source": "https://example.com",
        "source_type": "url",
        "file_name": None,
        "url": "https://example.com",
        "page": None,
        "section": "Tên heading gần nhất hoặc main",
    },
)
```

Metadata bổ sung có thể đặt trong `metadata` nếu cần:

- `title`
- `fetched_at`
- `content_hash`
- `chunk_index`
- `domain`

## Recommendation cho Sprint 1

Start low-cost/basic:

```text
httpx -> trafilatura -> BeautifulSoup fallback -> heading-aware chunking -> list[Chunk]
```

Advanced/high-cost để sau:

```text
Playwright/Crawl4AI cho JS-heavy pages
Firecrawl cho blocked/production crawling
Hosted embeddings/vector DB chỉ dùng khi demo/deployment cần
```

Như vậy scope nhỏ, dễ test, không tốn chi phí ban đầu, và khớp với yêu cầu:

```python
load_url_chunks(url: str) -> list[Chunk]
load_text_chunks(text: str, source: str) -> list[Chunk]
```
