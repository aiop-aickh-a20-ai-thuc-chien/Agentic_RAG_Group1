## Đánh giá real-data URL ingestion: VinFast xe máy điện

Mình đã test URL:

`https://shop.vinfastauto.com/vn_vi/xe-may-dien-vinfast.html`

Artifact local được lưu tại:

`src/agentic_rag/ingestion/url/data/artifacts`

### Kết quả chạy

Listing page:

- URL: `https://shop.vinfastauto.com/vn_vi/xe-may-dien-vinfast.html`
- Run ID: `vinfast_motorbike_listing`
- Chunk count: `16`
- Files sinh ra: `parsed.md`, `chunks.jsonl`, `manifest.json`

Detail pages được phát hiện từ clickable image/link và đã ingest:

| Run ID | URL | Chunk count |
| --- | --- | ---: |
| `vinfast_motorbike_detail_01` | `https://shop.vinfastauto.com/vn_vi/xe-may-dien-evo-grand.html` | 4 |
| `vinfast_motorbike_detail_02` | `https://shop.vinfastauto.com/vn_vi/xe-may-dien-evo-grand-lite.html` | 4 |
| `vinfast_motorbike_detail_03` | `https://shop.vinfastauto.com/vn_vi/xe-may-dien-evo-lite-neo.html` | 34 |
| `vinfast_motorbike_detail_04` | `https://shop.vinfastauto.com/vn_vi/xe-may-dien-flazz.html` | 36 |
| `vinfast_motorbike_detail_05` | `https://shop.vinfastauto.com/vn_vi/xe-may-dien-zgoo.html` | 38 |
| `vinfast_motorbike_detail_06` | `https://shop.vinfastauto.com/vn_vi/xe-may-dien-feliz.html` | 19 |
| `vinfast_motorbike_detail_07` | `https://shop.vinfastauto.com/vn_vi/xe-may-dien-verox.html` | 19 |
| `vinfast_motorbike_detail_08` | `https://shop.vinfastauto.com/vn_vi/xe-dap-dien-drgnfly.html` | 6 |
| `vinfast_motorbike_detail_09` | `https://shop.vinfastauto.com/vn_vi/xe-may-dien-evo-neo.html` discovered, but final manifest URL redirects/normalizes to listing URL | 16 |

### Đánh giá chất lượng

Điểm tốt:

- Pipeline fetch được listing page và các detail page cùng domain.
- Mỗi page đều sinh đủ `parsed.md`, `chunks.jsonl`, `manifest.json`.
- Metadata trong manifest có `input_type`, `input_source`, `input_url`, `parser`, `run_id`, `chunk_count`.
- Clickable image/link discovery hoạt động đủ tốt để tìm các trang xe máy điện chính.
- Detail pages có chunk count khác nhau, cho thấy pipeline đang đọc từng page riêng thay vì chỉ đọc listing.

Hạn chế quan sát được:

- Nội dung vẫn còn noise từ navigation, CTA, footer hoặc block thương mại lặp lại.
- Parser hiện tại mới là stdlib HTMLParser baseline, chưa dùng `trafilatura`, nên main-content extraction chưa sạch.
- Một số thông tin trên page có thể nằm trong ảnh hoặc component frontend, hiện chưa OCR/vision.
- URL `xe-may-dien-evo-neo.html` có dấu hiệu redirect/final URL về listing page, cần lưu rõ original URL và final URL nếu muốn audit chính xác.
- Chưa có token-aware chunking bằng `tiktoken`; chunking mặc định vẫn là character-based.

### Kết luận

Real-data test đạt mục tiêu baseline: URL ingestion có thể đọc listing page, phát hiện detail pages từ clickable image/link, ingest từng page, và lưu artifact để review.

Chưa nên xem output này là production-quality. Bước tiếp theo nên là:

1. Thêm `trafilatura` để extract main content/Markdown sạch hơn.
2. Lưu cả original URL và final URL trong manifest/chunk metadata.
3. Thêm asset discovery rõ hơn cho image/PDF/iframe/object.
4. Với clickable image, lưu `image_url`, `alt_text`, `target_url`.
5. Route PDF link hoặc PDF response sang PDF ingestion.
6. Thêm `tiktoken` nếu cần token-aware chunking cho embedding/generation.
