## Báo cáo tóm tắt URL benchmarking hiện tại

Mình đã kiểm tra phần benchmarking trong:

- `src/agentic_rag/ingestion/url/benchmarking/custom_benchmark.py`
- `src/agentic_rag/ingestion/url/benchmarking/cli.py`
- `src/agentic_rag/ingestion/url/tests/benchmarking`

### Kết quả kiểm tra

Benchmarking hiện tại OK cho baseline Sprint 1.

Đã chạy:

```text
uv run pytest src/agentic_rag/ingestion/url/tests/benchmarking -q
5 passed in 0.40s
```

Benchmark CLI hiện trả:

```text
parser: builtin-html-parser
average_score: 1.0
cases:
- article_with_navigation_noise: score 1.0
- docs_page_with_code_noise: score 1.0
```

### Benchmark hiện đang dùng gì?

Hiện tại chỉ benchmark một parser:

- `builtin-html-parser`
- dùng Python stdlib `html.parser.HTMLParser`
- loại bỏ noise tags cơ bản: `script`, `style`, `nav`, `footer`, `header`, `aside`
- nhận diện section từ heading: `h1`, `h2`, `h3`

Benchmark case hiện có 2 fixture HTML local:

1. `article_with_navigation_noise`
   - kiểm tra loại bỏ `nav/footer`
   - kiểm tra giữ lại nội dung article
   - kiểm tra detect section từ `h1`

2. `docs_page_with_code_noise`
   - kiểm tra loại bỏ `header/script`
   - kiểm tra giữ lại nội dung docs
   - kiểm tra detect section từ `h1/h2`

### Cách chấm điểm

Mỗi case so sánh:

- expected terms có xuất hiện trong extracted text không
- expected sections có detect được không
- số ký tự extract được
- missing terms nếu có

Score hiện tại:

```text
score = term_score * 0.8 + section_score * 0.2
```

Tức là 80% điểm cho matched terms, 20% điểm cho detected sections.

### `custom_benchmark.py` custom từ benchmark/algorithm online nào?

Không phải copy hoặc custom trực tiếp từ benchmark online chính thức nào.

`custom_benchmark.py` là benchmark tự thiết kế cho project này. Nó là smoke/regression benchmark nhẹ, deterministic, chạy local, không cần network và không cần paid service.

Ý tưởng của nó dựa trên pattern đánh giá extraction phổ biến:

- tạo HTML fixture cố định
- định nghĩa expected key terms
- định nghĩa expected headings/sections
- chạy parser
- so sánh extracted text + detected sections
- tính weighted score

Vì vậy nó không tương đương các benchmark chính thức như OmniDocBench, BEIR, MTEB, RAGAS, hay benchmark crawling/public dataset. Nó nên được hiểu là baseline regression benchmark để so sánh parser sau này.

### Có cần update không?

Chưa bắt buộc update trước khi merge baseline URL ingestion.

Nhưng mình đề xuất update ở iteration tiếp theo:

1. Thêm fixture HTML tiếng Việt.
2. Thêm case malformed HTML.
3. Thêm case có repeated navigation/footer/CTA.
4. Thêm case product/spec table.
5. Thêm parser candidates:
   - stdlib baseline hiện tại
   - `trafilatura`
   - BeautifulSoup/readability fallback
6. Thêm metrics cho:
   - encoding correctness
   - boilerplate leakage
   - section quality
   - Markdown suitability
   - runtime

### Kết luận

Giữ benchmark hiện tại làm lightweight baseline là hợp lý. Khi thêm `trafilatura` hoặc parser adapter khác, lúc đó nên mở rộng benchmark để so sánh parser theo cùng fixture và metric.
