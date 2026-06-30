# VinFast RAG Pipeline — Upgrade TODO
> Stack: Playwright + VLM (GPT-4o Vision) + Instructor — không phụ thuộc vendor ngoài

---

## Nguyên tắc Fallback

Vì ZenRows / Bright Data không thấy được trang chính, toàn bộ pipeline này dùng:
- **Playwright** để điều khiển browser thật (không headless khi cần thiết)
- **GPT-4o Vision (VLM)** để đọc UI khi DOM bị obfuscate hoặc dữ liệu nằm trong ảnh
- **Instructor + GPT-4o** để ép output thành Pydantic schema chuẩn
- **Không cần proxy vendor** — thay bằng kỹ thuật stealth thủ công

---

## 1. Vượt Anti-bot Không Cần Vendor

### 1a. Stealth Browser Setup
- [ ] Cài `playwright-extra` + plugin `puppeteer-extra-plugin-stealth` (port cho Python)
- [ ] Chạy Playwright với **`channel="chrome"`** thay vì Chromium mặc định — dùng Chrome thật đã cài trên máy
- [ ] Tắt flag `--enable-automation` và `--disable-blink-features=AutomationControlled`
- [ ] Set `user_agent` thực từ browser thật, không dùng default Playwright UA
- [ ] Set `viewport` ngẫu nhiên trong khoảng thực tế (1280–1920 x 800–1080)

```python
browser = await p.chromium.launch(
    channel="chrome",          # Dùng Chrome thật trên máy
    headless=False,            # Bật headful nếu bị block headless
    args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
    ]
)
context = await browser.new_context(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
    viewport={"width": 1440, "height": 900},
    locale="vi-VN",
    timezone_id="Asia/Ho_Chi_Minh",
)
```

### 1b. Human-like Behavior
- [ ] Thêm delay ngẫu nhiên giữa mỗi action: `await asyncio.sleep(random.uniform(1.5, 4.0))`
- [ ] Dùng `page.mouse.move()` để di chuyển chuột trước khi click
- [ ] Scroll trang từ từ trước khi tương tác: `page.evaluate("window.scrollBy(0, 300)")`
- [ ] Đừng click ngay khi element xuất hiện — đợi thêm 0.5–1.5s sau khi locator ready

### 1c. Fallback Cuối Cùng: VLM thay DOM
- [ ] Nếu DOM bị obfuscate hoàn toàn (class name ngẫu nhiên, React hydration lạ) → **không cần đọc DOM**
- [ ] Chụp screenshot toàn trang bằng `page.screenshot(full_page=True)`
- [ ] Gửi ảnh lên **GPT-4o Vision** với prompt trích xuất có cấu trúc (xem Mục 4)
- [ ] VLM đọc giá, thông số, tên biến thể trực tiếp từ ảnh → bypass toàn bộ vấn đề DOM

---

## 2. Error Recovery & Retry Logic

- [ ] Wrap mỗi scraping action trong `try/except` riêng biệt — không để 1 lỗi sập cả pipeline
- [ ] Implement retry với exponential backoff:

```python
import asyncio

async def retry(fn, retries=3, base_delay=2.0):
    for attempt in range(retries):
        try:
            return await fn()
        except Exception as e:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt))
```

- [ ] Nếu `wait_for_selector` timeout → fallback sang chụp screenshot + VLM thay vì crash
- [ ] Nếu network intercept bỏ lỡ response (race condition) → fallback đọc DOM text → fallback VLM
- [ ] Log mọi failed URL + lý do thất bại vào `failed_urls.jsonl`
- [ ] Thay selector cứng `has-text('VF 9 Plus')` bằng selector theo `aria-label` hoặc `data-testid`

### Fallback Chain (theo thứ tự)
```
1. Network intercept JSON  (nhanh nhất, sạch nhất)
        ↓ nếu không bắt được
2. Đọc DOM text qua Playwright locator
        ↓ nếu DOM obfuscate / class ngẫu nhiên
3. Chụp screenshot → GPT-4o Vision
        ↓ nếu page bị block hoàn toàn
4. Log URL vào failed_urls.jsonl → retry sau 24h
```

---

## 3. Change Detection & Scheduling (Tự xây)

Không dùng Browse.ai — tự implement bằng Python thuần:

- [ ] Sau mỗi lần crawl, hash toàn bộ JSON output:
```python
import hashlib, json

def content_hash(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
```
- [ ] Lưu hash vào file `hashes.json` — so sánh trước khi re-ingest
- [ ] Chỉ đẩy vào Vector DB khi hash thay đổi → tránh duplicate
- [ ] Dùng **APScheduler** hoặc cron để chạy pipeline mỗi 24h:
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
scheduler = AsyncIOScheduler()
scheduler.add_job(run_pipeline, "cron", hour=2)  # Chạy lúc 2AM mỗi ngày
scheduler.start()
```
- [ ] Lưu versioned snapshot: `output/vf9_plus_2026-06-20.json`

---

## 4. VLM Integration — GPT-4o Vision

Dùng VLM như một **fallback thông minh**, không phải bước chính:

### Khi nào trigger VLM
- [ ] DOM bị obfuscate / không đọc được locator
- [ ] Dữ liệu nằm trong ảnh (bảng so sánh, nội thất, màu sắc)
- [ ] Network intercept không bắt được JSON pricing

### Prompt chuẩn cho VLM
```python
import base64
from openai import OpenAI

async def extract_via_vlm(screenshot_path: str) -> dict:
    client = OpenAI()
    with open(screenshot_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                },
                {
                    "type": "text",
                    "text": """Trích xuất thông tin sản phẩm VinFast từ ảnh này.
Trả về JSON với các field sau:
- model_name: tên xe (VD: VF 9, VF 3)
- variant: phiên bản (Eco / Plus / null)
- base_price_vnd: giá bằng số nguyên VND (bỏ dấu chấm/phẩy)
- battery_subscription: true nếu là thuê pin, false nếu mua pin
- promotions: danh sách string các khuyến mãi đang hiện
- specs: object chứa range_km, charging_time_min, horsepower nếu có
Chỉ trả về JSON thuần, không có markdown hay giải thích."""
                }
            ]
        }]
    )
    return json.loads(response.choices[0].message.content)
```

- [ ] Reconcile rule: nếu VLM output mâu thuẫn API data → **ưu tiên API data**
- [ ] Validate output VLM bằng Pydantic trước khi dùng — reject nếu thiếu field bắt buộc

---

## 5. Schema — Hoàn thiện với Instructor

- [ ] Cài `instructor`: `pip install instructor`
- [ ] Wrap GPT-4o bằng Instructor để đảm bảo output luôn đúng Pydantic schema:

```python
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class VinFastProduct(BaseModel):
    product_type: str          # 'Real Car' | 'Scale Model'
    model_name: str
    variant: Optional[str]     # Eco, Plus
    base_price_vnd: int
    battery_subscription: bool
    scale_ratio: Optional[str] # '1:24' — chỉ cho mô hình
    specs: dict                # range_km, charging_time_min, horsepower
    promotions: List[str]
    source_url: str            # URL nguồn
    scraped_at: datetime       # timestamp crawl
    chunk_id: str              # hash(model+variant+battery_option) — dùng để upsert

client = instructor.from_openai(OpenAI())

def parse_to_schema(raw_text: str, source_url: str) -> VinFastProduct:
    return client.chat.completions.create(
        model="gpt-4o",
        response_model=VinFastProduct,
        messages=[{
            "role": "user",
            "content": f"Chuyển dữ liệu sau thành schema VinFastProduct:\n\n{raw_text}\n\nsource_url: {source_url}"
        }]
    )
```

- [ ] `chunk_id` phải deterministic: `hashlib.md5(f"{model_name}-{variant}-{battery_subscription}".encode()).hexdigest()`
- [ ] Validate bắt buộc `scraped_at` và `chunk_id` — reject nếu thiếu 2 field này

---

## 6. Chunking Strategy cho RAG

- [ ] Tách mỗi biến thể thành Document độc lập trước khi ingest
- [ ] Chunk thông số theo danh mục ngữ nghĩa:

| Chunk | Nội dung |
|---|---|
| `range_charging` | range_km, charging_time, battery capacity |
| `safety` | tính năng an toàn, ADAS, airbag |
| `dimensions` | kích thước, trọng lượng, khoang chứa đồ |
| `interior` | nội thất, màn hình, tiện nghi |
| `pricing` | giá, tùy chọn pin, khuyến mãi |

- [ ] Mỗi chunk đính kèm metadata đầy đủ:
```json
{
  "model": "VF9",
  "variant": "Plus",
  "battery_option": "Mua pin",
  "category": "range_charging",
  "scraped_at": "2026-06-20T02:00:00",
  "chunk_id": "abc123"
}
```
- [ ] Test retrieval precision trước/sau chunking mới

---

## 7. Stack Tổng Thể (Không Vendor)

| Vấn đề | Giải pháp |
|---|---|
| Anti-bot | Playwright + Chrome thật + stealth flags + human delay |
| DOM obfuscate | Fallback sang GPT-4o Vision screenshot |
| Tương tác động | Playwright (click, wait, scroll) |
| Change detection | Hash JSON + APScheduler tự xây |
| Clean output | GPT-4o text extraction + Instructor |
| Structured schema | Pydantic + Instructor |
| Scheduling | APScheduler hoặc cron |

---

## Priority Order

| # | Mục | Độ ưu tiên | Lý do |
|---|---|---|---|
| 1 | Stealth browser setup (1a + 1b) | 🔴 Cao | Không vào được trang → không có gì để làm |
| 2 | Fallback chain + VLM (1c + 4) | 🔴 Cao | Đây là "lưới an toàn" khi DOM fail |
| 3 | Hoàn thiện Schema + Instructor (5) | 🔴 Cao | Thiếu `chunk_id` gây duplicate trong Vector DB |
| 4 | Error recovery (2) | 🟡 Trung | Cần trước khi chạy production |
| 5 | Chunking strategy (6) | 🟡 Trung | Ảnh hưởng trực tiếp retrieval quality |
| 6 | Change detection tự xây (3) | 🟢 Thấp | Tối ưu cost, không bắt buộc ngay |
