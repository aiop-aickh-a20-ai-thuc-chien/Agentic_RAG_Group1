# URL ground truth chunk review

Demo này đọc `ground_truth_manifest.json`, chuyển từng golden JSON thành Markdown có cấu trúc, rồi dùng URL Markdown chunker hiện tại để kiểm tra chunk.

Mục tiêu chính:

- Kiểm tra JSON ground truth có thể dựng thành Markdown đọc được cho LLM.
- Xem mỗi chunk có giữ được mẫu xe, giá, lựa chọn, màu, ưu đãi, `modelId` hay không.
- Tạo dữ liệu review trước khi đưa URL ingestion thật vào judge prompt.

Chạy từ root repo:

```powershell
uv run python guide/demo/url-ground-truth-chunk-review/run_ground_truth_chunk_review.py
```

Output mặc định nằm tại:

```text
guide/demo/url-ground-truth-chunk-review/output/
```

Mỗi dataset có các file:

- `ground_truth.md`: Markdown dựng từ JSON/state.
- `chunks.jsonl`: danh sách `Chunk` theo contract hiện tại.
- `entity_chunks.jsonl`: chunk review theo entity/section nhỏ như phiên bản, mẫu xe, lựa chọn, pricing.
- `chunks_readable.md`: bảng review và nội dung từng chunk.
- `entity_chunks_readable.md`: bản đọc nhanh để xem “mỗi chunk là một model/choices/pricing”.
- `chunks_readable.html`: bản xem nhanh trong trình duyệt.
- `manifest.json`: metadata, diagnostics, missing values.

Tùy chỉnh kích thước chunk:

```powershell
uv run python guide/demo/url-ground-truth-chunk-review/run_ground_truth_chunk_review.py --max-chars 900
```
