# Review bộ hỗ trợ benchmark URL ingestion

## Bối cảnh

Issue này dùng để review các helper benchmark hiện tại cho URL ingestion tại:

```text
src/agentic_rag/ingestion/url/benchmarking
```

Các file hiện tại:

```text
benchmarking/
  __init__.py
  cli.py
  custom_benchmark.py
```

Test liên quan:

```text
src/agentic_rag/ingestion/url/tests/benchmarking
```

## Mục đích hiện tại

Các helper benchmark này chạy local, deterministic và nhẹ dependency. Mục tiêu là giúp nhóm so sánh hành vi parser URL/HTML trước khi thêm dependency nặng hơn hoặc dùng dịch vụ benchmark/live crawling.

Hiện tại hỗ trợ:

- chạy các custom HTML benchmark case có sẵn
- parse một file HTML local thành JSON dễ dùng cho benchmark
- báo cáo parser score, matched terms, missing terms, detected sections và extracted character count
- chạy không cần network access, API key, external vector store hoặc dịch vụ trả phí

## CLI hiện tại

Chạy các custom local benchmark case:

```bash
uv run python -m agentic_rag.ingestion.url.benchmarking.custom_benchmark
```

Hoặc chạy qua benchmark CLI:

```bash
uv run python -m agentic_rag.ingestion.url.benchmarking.cli custom
```

Parse một file HTML local:

```bash
uv run python -m agentic_rag.ingestion.url.benchmarking.cli parse-html --html-file path/to/page.html
```

## Câu hỏi cần review

Mọi người comment giúp nếu có phần nào cần đổi trước khi dùng phần này làm baseline chung của nhóm.

Các điểm cần review:

- Tên folder `benchmarking` đã ổn chưa?
- Tên file `custom_benchmark.py` đã rõ nghĩa chưa?
- CLI command nên là `custom`, `local`, `html`, hay tên khác?
- Output benchmark hiện tại đã đủ cho Sprint 1 chưa?
- Benchmark case có nên thêm sample HTML tiếng Việt không?
- Sau này có nên benchmark nhiều parser adapter không, ví dụ stdlib parser vs Trafilatura vs BeautifulSoup?
- Kết quả benchmark nên lưu vào folder chuẩn nào, ví dụ `guide/results` hoặc `artifacts/benchmarking`?

## Đề xuất hiện tại

Sprint 1 nên giữ implementation local và deterministic:

```text
custom_benchmark.py -> các parser benchmark case nhỏ, cố định
cli.py              -> wrapper cho lệnh benchmark và parse HTML local
tests/benchmarking -> test deterministic cho CLI và benchmark output
```

Chỉ nên thêm so sánh parser nặng hơn sau khi URL ingestion baseline đã ổn định.
