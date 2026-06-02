# Ingestion Benchmark — URL/Text Pipeline

> Dùng file này để kiểm tra chất lượng ingestion pipeline (Phần 2).
> Tick `[x]` khi pass. Điền điểm vào scorecard cuối file.

---

## Test Cases

### TC-01 — Web tĩnh (báo/blog)
Test URL mẫu: `https://vnexpress.net/bai-viet-bat-ky`

- [ ] Main content tách được khỏi menu, sidebar, footer _(đo bằng `len(clean)` vs `len(raw_text)`)_
- [ ] Heading h1/h2/h3 được giữ lại và map vào metadata `section`
- [ ] Không còn text quảng cáo, script inline, cookie banner
- [ ] Các field `title`, `url`, `publish_date` extract được

---

### TC-02 — Web động / JS-rendered
Test URL mẫu: `https://docs.anthropic.com/en/docs/...`

- [ ] Nội dung render sau JS được lấy đủ _(so sánh output `requests` vs `Playwright`)_
- [ ] Code block / table không bị vỡ format
- [ ] Không timeout, có fallback nếu JS load chậm
- [ ] `canonical URL` được extract đúng

---

### TC-03 — Text input thuần
`source_type: "text"` — user paste trực tiếp

- [ ] Clean whitespace thừa, ký tự lạ (`\u200b`, BOM, `\r\n` lẫn lộn)
- [ ] Chunk không bị cắt giữa câu
- [ ] Metadata có `source_type="text"`, `chunk_id` tăng dần và không trùng
- [ ] Text ngắn (< 1 chunk) xử lý đúng, không raise lỗi

---

### TC-04 — Trang nhiều section (Wikipedia / docs dài)
Test URL mẫu: trang Wikipedia hoặc trang docs có nhiều heading

- [ ] Mỗi chunk biết mình thuộc heading nào (`metadata.section = "Giới thiệu / Cài đặt / ..."`)
- [ ] Chunk không trộn lẫn nội dung từ 2 section khác nhau
- [ ] `chunk_id` là chuỗi duy nhất, stable, có thể reproduce (`hash(url + section + index)`)
- [ ] Overlapping chunk (nếu dùng sliding window) không duplicate heading text

---

### TC-05 — Edge cases
Các trường hợp bất thường cần xử lý gracefully

- [ ] URL 404 → trả lỗi rõ ràng, không crash toàn pipeline
- [ ] Paywall / nội dung bị khóa → cảnh báo khi `len(clean) < 200 chars`
- [ ] URL redirect chuỗi dài vẫn resolve được canonical URL cuối
- [ ] Text rỗng hoặc toàn ký tự đặc biệt → không trả về chunk rỗng, không silent fail

---

### TC-06 — Retrieval readiness
Kiểm tra output có phù hợp để đẩy vào vector store không

- [ ] Token count mỗi chunk nằm trong khoảng **200–600 tokens** _(đo bằng `tiktoken` với `cl100k_base`)_
- [ ] Tất cả 5 metadata field bắt buộc đều có (xem phần Metadata bên dưới)
- [ ] Citation URL có thể dùng trực tiếp, có section anchor nếu có thể (`#heading-slug`)
- [ ] Không có chunk trùng lặp hoàn toàn _(kiểm tra bằng hash của content)_

---

## Checklist chất lượng chi tiết

### Fetch & Parse

- [ ] Fetch thành công với timeout hợp lý (< 10s)
- [ ] `User-Agent` header được set để tránh bị block
- [ ] HTML được parse đúng encoding (UTF-8 / theo `meta charset`)
- [ ] `Canonical URL` được extract (`og:url` hoặc `<link rel="canonical">`)

### Content Extraction

- [ ] Menu, nav, footer, sidebar bị loại bỏ khỏi text
- [ ] Quảng cáo, cookie notice, script inline không còn trong output
- [ ] Tỷ lệ text useful / text total **> 60%** (`len(clean) / len(raw_text)`)
- [ ] Heading structure (h1/h2/h3) được giữ lại hoặc đánh dấu trong text

### Chunking

- [ ] Chunk không bị cắt giữa câu (sentence-aware splitting)
- [ ] Chunk boundary ưu tiên theo heading/section boundary trước
- [ ] Token count mỗi chunk: 200–600 (đo bằng `tiktoken`)
- [ ] Overlap chunk giữ lại context đủ để hiểu (nếu dùng sliding window)

### Metadata — 5 field bắt buộc

- [ ] `url` — đúng, canonical, không bị redirect truncate
- [ ] `title` — lấy từ `og:title` hoặc `<h1>`, không phải browser tab title
- [ ] `section` — heading gần nhất phía trên chunk đó
- [ ] `chunk_id` — unique, stable, reproducible (`hash(url + section + index)`)
- [ ] `source_type` — `"url"` hoặc `"text"`, không được là `None`

### Metadata — nice-to-have (nên thêm)

- [ ] `publish_date` — từ `og:article:published_time` hoặc trafilatura
- [ ] `description` — từ `og:description`
- [ ] `language` — từ `lang` attribute hoặc `langdetect`
- [ ] `author` — từ `og:author` hoặc schema.org
- [ ] `section_anchor` — `#heading-slug` để citation URL trỏ đúng đoạn

---

## So sánh Tool Extraction

| Tool | Web tĩnh | Web động | Loại boilerplate | Metadata | Ghi chú |
|---|---|---|---|---|---|
| `trafilatura` | ✅ Tốt nhất | ❌ Không | ✅ Tự động | ✅ date/lang/author | **Dùng làm default** |
| `readability-lxml` | ✅ Tốt | ❌ Không | ✅ Tốt | ⚠️ Hạn chế | Mozilla Readability port, giữ HTML structure |
| `BeautifulSoup` | ⚠️ Cần rule | ❌ Không | ❌ Phải tự viết | ❌ Không | Flexible nhưng phải custom nhiều |
| `Crawl4AI` | ✅ Tốt | ✅ Tốt | ✅ Output Markdown | ⚠️ Cơ bản | Cần browser, output sạch hơn Playwright |
| `Playwright` | ✅ OK | ✅ Tốt nhất | ❌ Phải tự parse | ❌ Không | Dùng cho SPA/login/dynamic, chậm và nặng |

### Chiến lược gợi ý

```
URL request
│
├─ Thử fetch bằng requests/httpx
│   ├─ len(content) > threshold? ──► trafilatura extract ──► done
│   └─ len(content) < threshold (web động?)
│       └─ Crawl4AI hoặc Playwright render JS ──► trafilatura extract ──► done
│
└─ source_type = "text" ──► clean trực tiếp, bỏ qua fetch
```

---

## Scorecard

> Chạy xong các test case, điền điểm từng hạng mục (thang 0–10).

| Hạng mục | Điểm (0–10) | Ghi chú / lỗi phát hiện |
|---|---|---|
| Fetch & parse | `/10` | |
| Content extraction (boilerplate removal) | `/10` | |
| Chunking quality (sentence/section aware) | `/10` | |
| Metadata completeness (5 field bắt buộc) | `/10` | |
| Edge case handling | `/10` | |
| Retrieval readiness (token range, no dup) | `/10` | |
| **Tổng** | `/60` | |

---

## Comment template — điền sau khi benchmark xong

```md
## Hiện tại URL/Text đang hoạt động thế nào
<!-- Mô tả ngắn flow: fetch → extract → clean → chunk → metadata -->

## Trace/log cho thấy vấn đề gì
<!-- Paste log thực tế: URL test, len(raw) vs len(clean), chunk count, sample chunk -->

## Điểm tốt hiện tại
<!-- Ví dụ: fetch OK, metadata url/title có, chunk không bị cắt câu -->

## Điểm yếu hiện tại
<!-- Ví dụ: menu/footer còn dính, section metadata thiếu, web động trả về rỗng -->

## Giải pháp cải tiến đề xuất
<!-- Cụ thể: đổi sang trafilatura, thêm heading-aware chunker, thêm field publish_date -->

## Tool/framework nên thử
<!-- trafilatura, readability-lxml, Crawl4AI — theo kết quả TC-01 đến TC-06 -->

## Thay đổi nào nên làm ngay
<!-- Không ảnh hưởng API/schema, không cần họp: ví dụ thêm User-Agent, fix encoding -->

## Thay đổi nào cần họp nhóm trước khi code
<!-- Ảnh hưởng schema metadata, chunk strategy, hoặc cần thêm browser runtime -->
```
