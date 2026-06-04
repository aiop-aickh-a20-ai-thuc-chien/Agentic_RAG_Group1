# Hướng dẫn sử dụng Auto Data Tool (Sinh QA tự động)

Tool này được thiết kế để tự động hoá quá trình nạp dữ liệu (URLs, PDFs), bóc tách (chunking) và sinh ra các cặp câu hỏi - câu trả lời (QA) dùng cho việc đánh giá (Evaluation Dataset) hệ thống Agentic RAG.

## Cơ chế hoạt động

- **Giao diện (Frontend)**: Được xây dựng bằng HTML/CSS/JS thuần, giúp bạn dễ dàng theo dõi, kiểm duyệt và sinh QA hàng loạt.
- **Máy chủ (Backend Node.js)**: Đóng vai trò cầu nối, gọi tới API của LLM (để sinh QA) và lưu kết quả xuống file Excel `guide/reports/result.xlsx`.
- **Trạm trung chuyển Python (`python_parser.py`)**: ĐÂY LÀ ĐIỂM QUAN TRỌNG. Tool **không** tự bóc tách văn bản. Thay vào đó, nó nhúng trực tiếp môi trường ảo `.venv` của Repo và gọi thẳng vào 2 hàm gốc của hệ thống RAG:
  - `agentic_rag.ingestion.url.loader.load_url_chunks`
  - `agentic_rag.ingestion.pdf.loader.load_pdf_chunks`
  
Điều này đảm bảo 100% thuật toán chia đoạn (chunking logic), tiền xử lý (preprocessing) và mã băm (Chunk ID) được sinh ra từ Tool sẽ KHỚP HOÀN TOÀN với những gì hệ thống RAG thực tế đang chạy.

## Hướng dẫn cài đặt và chạy Tool

### 1. Cài đặt thư viện Node.js
Đảm bảo bạn đã cài đặt Node.js trên máy. Sau đó mở Terminal, di chuyển vào thư mục này và cài đặt các gói cần thiết:

```bash
cd guide/reports/auto_data_tool
npm install
```

### 2. Cấu hình môi trường (Không bắt buộc)
Bạn có thể thiết lập file `.env` (đặt cùng cấp với file `server.js`) nếu cần cấu hình các tham số bảo mật.
Ví dụ:
```env
PORT=3000
```

### 3. Khởi động máy chủ
Từ Terminal trong thư mục `auto_data_tool`, chạy lệnh sau:

```bash
node server.js
```

Sau khi Terminal báo `Server running on http://localhost:3000`, hãy mở trình duyệt và truy cập vào đường link trên để sử dụng Tool.

## Hướng dẫn sử dụng trên Giao diện Web

1. **Nạp dữ liệu**: 
   - Điền đường dẫn tuyệt đối hoặc tương đối tới file `*.txt` chứa danh sách các URL.
   - Điền đường dẫn tới thư mục chứa các file PDF (nếu có).
   - Nhấn **+ Nạp Document Chunk**. Tool sẽ kết nối với Python để bóc tách dữ liệu và hiển thị lên bảng.

2. **Gán nhãn & Sinh QA**:
   - Chọn một Chunk bất kỳ trong danh sách.
   - (Tuỳ chọn) Bạn có thể cấu hình tên model và URL của LLM Gateway ở cột bên trái.
   - Nhấn **Tự Động Sinh QA Cặp**.
   - Chỉnh sửa câu hỏi/câu trả lời nếu cần thiết.
   - Nhấn **Lưu Excel** để lưu trực tiếp vào file `result.xlsx`.

3. **Chạy hàng loạt (Batch Autopilot)**:
   - Nhấn nút **Auto (Batch) QA** ở góc dưới bên trái, Tool sẽ tự động duyệt qua các Chunk chưa được gán nhãn và sinh QA mà không cần bạn làm thủ công từng cái một.

> [!NOTE]
> File kết quả Excel (`result.xlsx`) sẽ được đặt ngay bên ngoài thư mục này (trong `guide/reports`). Các cột trong file Excel đã được căn lỉnh chuẩn format của Evaluation Pipeline.
