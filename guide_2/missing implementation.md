# Missing implementation — VinFast pipeline

File này ghi các hạng mục trong `vinfast_pipeline_todo.md` chưa thể xác nhận hoàn tất
chỉ bằng implementation và test offline hiện tại.

## Chưa nối vào production entry point

- `VinFastExtractionPipeline` đã thực thi đúng chuỗi ưu tiên network -> DOM -> VLM,
  retry và log lỗi, nhưng chưa có entry point production ghép trực tiếp network response,
  DOM locator và screenshot từ một phiên Playwright duy nhất. URL integration hiện tại vẫn
  cần truyền các extractor adapter cụ thể.
- `ChangeStore.record()` trả về `False` khi nội dung không đổi, nhưng nơi upsert Vector DB
  hiện tại chưa gọi API này để bỏ qua re-ingest. Cần chọn rõ source provider/collection trước
  khi nối để không làm thay đổi hành vi ingestion chung.
- `daily_scheduler()` tạo APScheduler job chạy 02:00 mỗi ngày nhưng không tự `start()` trong
  application process. Deployment owner cần quyết định chạy scheduler trong API process,
  worker riêng hay cron của hạ tầng để tránh chạy trùng khi có nhiều replica.

## Cần môi trường hoặc credential thật để nghiệm thu

- Chưa chạy Chrome channel `chrome` trên trang VinFast live để xác nhận profile, random
  viewport, mouse movement, scroll và các selector `aria-label`/`data-testid` hoạt động với
  UI hiện tại.
- Chưa chạy GPT-4o Vision/Instructor thật vì môi trường không cung cấp API credential.
  Code adapter và Pydantic validation đã có, nhưng độ chính xác trên screenshot thật chưa được
  đo.
- Chưa kiểm tra full-page screenshot khi `wait_for_selector` timeout trong một phiên browser
  thật. Đây là một phần của production adapter còn thiếu ở mục trên.
- Chưa chạy APScheduler liên tục 24 giờ hoặc xác nhận timezone trên môi trường deployment.
- Chưa đo retrieval precision trước/sau semantic chunking trên bộ câu hỏi đánh giá VinFast.
  `product_chunks()` đã tạo chunk theo category nhưng cần benchmark có ground truth để kết luận
  chất lượng.

## Khác biệt dependency stealth

TODO đề xuất `playwright-extra` + `puppeteer-extra-plugin-stealth` “port cho Python”, nhưng hai
package được nêu là hệ Node/Puppeteer và không phải dependency Python chuẩn của repo. Phần đã
implement dùng Playwright Python với Chrome thật, bỏ `--enable-automation`, đặt
`AutomationControlled`, user agent rõ ràng và init script cho `navigator.webdriver`. Chưa thêm
một stealth package không rõ contract vào runtime. Nếu nhóm chọn một Python port cụ thể, cần
review package/security/license rồi mới pin version.

## Trạng thái dependency local

Extra `vinfast-pipeline` đã khai báo `instructor`, `openai` và `apscheduler`. `uv` không thể
download dependency trong phiên làm việc này do network sandbox chặn PyPI, nên chưa xác nhận
`uv sync --extra vinfast-pipeline` trên môi trường sạch.

## Điều kiện để đóng file này

1. Thêm production Playwright adapter tạo network, DOM và VLM extractors từ cùng một page.
2. Nối `ChangeStore` trước Vector DB upsert và test hành vi unchanged/changed.
3. Chọn một scheduler owner duy nhất và chạy smoke test deployment.
4. Chạy live smoke test Chrome + GPT-4o Vision với artifact đã redacted.
5. Chạy retrieval benchmark trước/sau và lưu report có ground truth.
