# Hướng dẫn chạy Demo Đánh giá Dynamic Ingestion & Prompts (Manual)

Tài liệu này hướng dẫn cách chạy script demo đánh giá khả năng trích xuất dữ liệu động/cấu trúc phức tạp (như lựa chọn màu sắc ngoại thất, lựa chọn phiên bản xe, tích chọn ưu đãi VinClub, bảng thông số kỹ thuật ẩn...) từ các trang web của VinFast.

---

## 1. Yêu cầu hệ thống & Tiền đề (Prerequisites)

*   **Python 3.11+** và công cụ quản lý package **uv** (đã được cấu hình trong dự án).
*   **File môi trường `.env`**: Đảm bảo các cấu hình LLM đã được điền đầy đủ để phục vụ đánh giá (script sẽ tự động phân giải model role `evaluation` hoặc `ingestion`/`default` từ file `.env`).
    *   Ví dụ: các biến `LLM_PROVIDER=openai` và `LLM_API_KEY=sk-proj-...` phải khả dụng.

---

## 2. Cách chạy Demo

Chạy lệnh sau tại thư mục gốc của dự án (`e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1`):

```bash
uv run python guide_2/demo/demo_dynamic_eval.py
```

### Quá trình hoạt động của Demo:
1.  **Đọc cấu trúc prompts**: Tự động tải các block prompt đánh giá từ [guide_2/test_prompts.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_2/test_prompts.md).
2.  **Đọc dữ liệu kiểm thử**: 
    *   **Ground Truth** (dữ liệu mẫu lý tưởng): [vf9_ground_truth.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_2/ground_truth/https-shop-vinfastauto-com-vn-vi-dat-coc-o-to-dien-vinfast-html-modelid-products-car-VF9/vf9_ground_truth.md)
    *   **Actual Output** (dữ liệu cào thực tế từ pipeline): [actual_output.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_2/demo/verify_ingestion/offline_self_check/actual_output.md)
3.  **Thực thi LLM Evaluations**: Gọi API LLM để chấm điểm và phân tích theo 3 khía cạnh:
    *   *Kiểm tra tính toàn vẹn của cấu trúc & bảng dữ liệu* (Structural & Formatting Integrity).
    *   *Kiểm tra độ đầy đủ của danh sách thông số ẩn* (Hidden List & Accordion Completeness).
    *   *Kiểm tra độ chính xác của trạng thái thay đổi giá* (State-Aware Dynamic Pricing - màu sắc, pin, ưu đãi thành viên VinClub).
4.  **Xuất báo cáo**: Ghi kết quả ra file định dạng Markdown và HTML trực quan.

---

## 3. Các File Kết quả đầu ra (Output Files)

Sau khi chạy xong, kết quả đánh giá sẽ được ghi nhận tại thư mục `guide_2/demo/output/`:

1.  **Báo cáo Markdown**: [dynamic_eval_report.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_2/demo/output/dynamic_eval_report.md) - Xem nhanh trực tiếp trong IDE.
2.  **Báo cáo HTML trực quan**: [dynamic_eval_report.html](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_2/demo/output/dynamic_eval_report.html) - Mở file này trên trình duyệt (Chrome, Edge, Firefox) để xem giao diện báo cáo chuyên nghiệp có định dạng màu sắc rõ ràng và so sánh trực quan giữa dữ liệu Ingest thực tế và Ground Truth.

---

## 4. Xử lý sự cố thường gặp (Troubleshooting)

*   **Lỗi Encoding (`UnicodeEncodeError`)**:
    *   Script đã được cấu hình tự động reconfigure stdout sang UTF-8 và ghi báo cáo thẳng vào file UTF-8. Nếu gặp lỗi hiển thị ký tự Việt có dấu trên PowerShell cũ, hãy dùng Windows Terminal hiện đại hoặc xem trực tiếp các file output đã lưu.
*   **Lỗi phân giải LLM Client (`ModelRuntimeConfigurationError` hoặc tương tự)**:
    *   Đảm bảo bạn đã điền đúng `LLM_API_KEY` trong file `.env` ở thư mục gốc và có kết nối mạng ổn định đến provider (OpenAI).
