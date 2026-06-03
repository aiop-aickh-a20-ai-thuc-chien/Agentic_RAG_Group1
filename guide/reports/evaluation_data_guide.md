# Evaluation Data Guide — Agentic RAG Group 1

> Tài liệu này mô tả chi tiết cách thiết kế, label, và sử dụng bộ dữ liệu đánh giá (evaluation dataset) cho toàn bộ pipeline RAG.

---

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Cấu trúc file evaluation](#2-cấu-trúc-file-evaluation)
3. [Giải thích chi tiết từng cột](#3-giải-thích-chi-tiết-từng-cột)
4. [Hướng dẫn label ground truth](#4-hướng-dẫn-label-ground-truth)
5. [Dữ liệu mẫu](#5-dữ-liệu-mẫu)
6. [Cách tính metrics](#6-cách-tính-metrics)
7. [Hướng dẫn human review](#7-hướng-dẫn-human-review)
8. [Failure analysis](#8-failure-analysis)

---

## 1. Tổng quan

### Pipeline đánh giá

```
┌──────────────────────────────────────────────────────┐
│  BƯỚC 1 — HUMAN: Tạo test dataset                   │
│  Chuẩn bị câu hỏi + expected answer + ground truth  │
│  Columns: A → I (màu vàng trong xlsx)                │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────┐
│  BƯỚC 2 & 3 — CODE: Chạy RAG pipeline & tính metrics│
│  Chạy lệnh:                                          │
│  `python scripts/run_evaluation.py \`                │
│    `--input guide/reports/evaluation_dataset_v2.xlsx \`│
│    `--output guide/reports/evaluation_dataset_v2_results.xlsx`│
│                                                      │
│  Lưu ý: Bạn cần activate môi trường và có dependencies│
│  (openpyxl, agentic_rag) trước khi chạy.             │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────┐
│  BƯỚC 4 — HUMAN: Review chất lượng                  │
│  Mở file *_results.xlsx, đọc answer, check đúng/sai │
│  Columns: U → AB (màu cam trong xlsx)               │
└──────────────────────────────────────────────────────┘
```

### Tỷ lệ tự động vs thủ công

| Phần | Ai làm | Effort |
|------|--------|--------|
| Test dataset (10+ câu) | 🏷️ Human | Cao — cần đọc tài liệu |
| Pipeline output | 🤖 Code | Tự động 100% |
| Retrieval metrics | 🤖 Code | Tự động 100% |
| Answer/Citation quality | 👤 Human (hoặc LLM judge) | Trung bình |
| Error classification | 🤖 Code gợi ý + 👤 Human confirm | Thấp |

---

## 2. Cấu trúc file evaluation

File `evaluation_dataset.xlsx` gồm 28 cột, chia 4 nhóm:

### Nhóm A: Test Dataset (Human fill trước khi chạy)

| Cột | Tên | Kiểu |
|-----|-----|------|
| A | `id` | string |
| B | `section_name` | string |
| C | `question` | string |
| D | `expected_answer` | string |
| E | `ground_truth_chunk_ids` | string (comma-separated) |
| F | `ground_truth_doc` | string |
| G | `ground_truth_page` | int hoặc empty |
| H | `is_out_of_scope` | TRUE / FALSE |
| I | `custom_preconds` | string hoặc empty |

### Nhóm B: Pipeline Output (Code tự fill)

| Cột | Tên | Kiểu |
|-----|-----|------|
| J | `rag_input` | string |
| K | `rag_context` | JSON string |
| L | `bot_response` | string |
| M | `bot_citations` | JSON string |
| N | `trace_url` | URL string |

### Nhóm C: Auto Metrics (Code tự tính)

| Cột | Tên | Kiểu |
|-----|-----|------|
| O | `retrieved_top5_ids` | string (comma-separated) |
| P | `ground_truth_rank` | int hoặc -1 |
| Q | `recall_at_5` | 0.0 → 1.0 |
| R | `mrr_at_5` | float (0.0 → 1.0) |
| S | `citation_chunk_match` | TRUE / FALSE |
| T | `guardrail_pass` | TRUE / FALSE / N/A |

### Nhóm D: Human Review (Human fill sau khi chạy)

| Cột | Tên | Kiểu |
|-----|-----|------|
| U | `check_answer_correct` | ✅ PASS / ⚠️ PARTIAL / ❌ FAIL |
| V | `check_answer_reason` | string |
| W | `check_kb_used` | ✅ PASS / ⚠️ PARTIAL / ❌ FAIL |
| X | `check_kb_reason` | string |
| Y | `check_citation_correct` | ✅ PASS / ⚠️ PARTIAL / ❌ FAIL |
| Z | `check_citation_reason` | string |
| AA | `error_type` | enum string |
| AB | `overall_verdict` | ✅ PASS / ⚠️ PARTIAL / ❌ FAIL |

---

## 3. Giải thích chi tiết từng cột

### Nhóm A — Test Dataset

#### `id` (cột A)
- **Mô tả**: Mã định danh câu hỏi test
- **Format**: `Q01`, `Q02`, ..., `Q10`
- **Quy tắc**: Duy nhất, không trùng

#### `section_name` (cột B)
- **Mô tả**: Nhóm/chủ đề của câu hỏi, dùng để phân loại khi phân tích
- **Ví dụ**: "Bảo hành pin", "Chính sách bảo hành", "Out-of-scope"
- **Quy tắc**: Nên nhóm các câu hỏi liên quan vào cùng section

#### `question` (cột C)
- **Mô tả**: Câu hỏi test — đây là input chính cho pipeline
- **Quy tắc**: Viết tự nhiên như người dùng thực sẽ hỏi
- **Nên gồm các loại**:
  - Câu hỏi trực tiếp (answer nằm trong 1 chunk)
  - Câu hỏi cần hiểu đoạn dài
  - Câu hỏi cần nhiều chunk
  - Câu hỏi dễ gây nhầm
  - Câu hỏi out-of-scope (ít nhất 1-2 câu)

#### `expected_answer` (cột D)
- **Mô tả**: Đáp án mong đợi — dùng để human review so sánh với bot_response
- **Quy tắc**:
  - Viết ngắn gọn, đúng trọng tâm
  - Với câu out-of-scope: ghi "Không có trong tài liệu" hoặc tương đương
- **Ví dụ**: "Pin cao áp được bảo hành 8 năm hoặc 160.000 km"

#### `ground_truth_chunk_ids` (cột E)
- **Mô tả**: Chunk ID chứa thông tin trả lời đúng — **cột quan trọng nhất cho eval**
- **Format**: Một hoặc nhiều chunk ID, cách nhau bởi dấu phẩy
- **Ví dụ**:
  - Một chunk: `pdf_001_p12_c01`
  - Nhiều chunk: `pdf_001_p12_c01,pdf_001_p13_c02`
- **Với câu out-of-scope**: Để trống hoặc ghi `NONE`
- **Cách tìm**: Xem phần [4. Hướng dẫn label ground truth](#4-hướng-dẫn-label-ground-truth)

#### `ground_truth_doc` (cột F)
- **Mô tả**: Tên tài liệu chứa evidence
- **Ví dụ**: `vinfast_warranty.pdf`, `https://example.com/warranty`
- **Với câu out-of-scope**: Để trống

#### `ground_truth_page` (cột G)
- **Mô tả**: Trang hoặc section chứa evidence (nếu biết)
- **Ví dụ**: `12` (cho PDF), hoặc `main` (cho URL)
- **Quy tắc**: Có thể để trống nếu không xác định được

#### `is_out_of_scope` (cột H)
- **Mô tả**: Đánh dấu câu hỏi không có đáp án trong tài liệu
- **Giá trị**: `TRUE` hoặc `FALSE`
- **Quan trọng**:
  - Câu out-of-scope **KHÔNG tính** Recall@5 và MRR@5
  - Câu out-of-scope dùng để test **guardrails** (hệ thống phải từ chối trả lời)

#### `custom_preconds` (cột I)
- **Mô tả**: Điều kiện đặc biệt trước khi chạy câu hỏi này
- **Giá trị**:
  - `$RESET` = reset conversation, bắt đầu session mới
  - Để trống = tiếp tục session trước
- **Dùng khi**: Test multi-turn conversation

---

### Nhóm B — Pipeline Output

#### `rag_input` (cột J)
- **Mô tả**: Câu hỏi sau khi qua query rewrite/preprocessing
- **Fill bởi**: Code — output từ `Store.preprocess_query()`
- **Ý nghĩa**: Kiểm tra rewrite có giữ đúng ý câu hỏi gốc không

#### `rag_context` (cột K)
- **Mô tả**: JSON array chứa top-k chunks retrieved
- **Fill bởi**: Code — output từ retrieval pipeline
- **Format mẫu**:
```json
[
  {"id": "pdf_001_p12_c01", "text": "Pin cao áp...", "score": 0.92, "retriever": "hybrid"},
  {"id": "url_001_c03", "text": "Chính sách...", "score": 0.78, "retriever": "hybrid"}
]
```

#### `bot_response` (cột L)
- **Mô tả**: Câu trả lời cuối cùng từ generation module
- **Fill bởi**: Code — output từ `generate_answer_with_trace()`

#### `bot_citations` (cột M)
- **Mô tả**: Citations kèm theo answer
- **Fill bởi**: Code — trích từ `Answer.citations`
- **Format mẫu**:
```json
[
  {"source": "vinfast_warranty.pdf", "chunk_id": "pdf_001_p12_c01", "page": 12}
]
```

#### `trace_url` (cột N)
- **Mô tả**: Link đến trace chi tiết (Langfuse hoặc JSONL)
- **Fill bởi**: Code — từ observability module

---

### Nhóm C — Auto Metrics

#### `retrieved_top5_ids` (cột O)
- **Mô tả**: 5 chunk IDs đầu tiên trong `rag_context`
- **Tính bởi**: Code parse `rag_context` JSON
- **Format**: `pdf_001_p12_c01, url_001_c03, pdf_002_p05_c01, ...`

#### `ground_truth_rank` (cột P)
- **Mô tả**: Vị trí (rank) đầu tiên mà ground truth chunk xuất hiện trong top 5
- **Tính bởi**: Code so sánh `ground_truth_chunk_ids` với `retrieved_top5_ids`
- **Giá trị**:
  - `1` → ground truth ở vị trí đầu tiên (tốt nhất)
  - `2` đến `5` → có tìm thấy nhưng không phải rank 1
  - `-1` → không tìm thấy trong top 5
  - Trống → câu out-of-scope

#### `recall_at_5` (cột Q)
- **Mô tả**: Tỷ lệ ground truth evidence nằm trong top 5 retrieved chunks.
- **Tính bởi**: Code
- **Công thức**:
  ```
  recall_at_5 = số ground_truth_chunk_id nằm trong top 5 / tổng số ground_truth_chunk_id
```
- **Với câu out-of-scope**: Để trống (không tính)
- **Ví dụ**: Nếu ground truth có 2 chunks và retrieved top 5 chỉ tìm thấy 1 chunk đúng, `recall_at_5 = 0.5`.

#### `mrr_at_5` (cột R)
- **Mô tả**: Reciprocal rank — đo ground truth nằm ở vị trí cao hay thấp
- **Tính bởi**: Code
- **Công thức**:
  ```
  mrr_at_5 = 1 / ground_truth_rank   nếu rank trong [1..5]
  mrr_at_5 = 0                        nếu rank = -1 (không tìm thấy)
  ```
- **Ví dụ**:
  - Rank 1 → MRR = 1.0
  - Rank 2 → MRR = 0.5
  - Rank 3 → MRR = 0.333
  - Rank 5 → MRR = 0.2
  - Không thấy → MRR = 0

#### `citation_chunk_match` (cột S)
- **Mô tả**: Citation trong bot_response có trỏ đúng chunk ground truth không?
- **Tính bởi**: Code so sánh `bot_citations[].chunk_id` với `ground_truth_chunk_ids`
- **Giá trị**: `TRUE` / `FALSE`

#### `guardrail_pass` (cột T)
- **Mô tả**: Với câu out-of-scope, hệ thống có từ chối trả lời đúng không?
- **Tính bởi**: Code kiểm tra `bot_response` có match pattern "không tìm thấy thông tin" không
- **Giá trị**:
  - `TRUE` = hệ thống đúng (từ chối trả lời câu ngoài scope)
  - `FALSE` = hệ thống sai (trả lời bừa câu ngoài scope)
  - `N/A` = câu in-scope, không cần check guardrail

---

### Nhóm D — Human Review

#### `check_answer_correct` (cột U)
- **Mô tả**: Câu trả lời có đúng không so với expected_answer?
- **Giá trị**:
  - `✅ PASS` = trả lời đúng và đầy đủ
  - `⚠️ PARTIAL` = đúng một phần, thiếu ý hoặc thừa ý
  - `❌ FAIL` = trả lời sai hoặc hallucinate

#### `check_answer_reason` (cột V)
- **Mô tả**: Giải thích ngắn gọn tại sao đánh giá PASS/PARTIAL/FAIL
- **Ví dụ**: "Đúng thời hạn bảo hành nhưng thiếu điều kiện km"

#### `check_kb_used` (cột W)
- **Mô tả**: Answer có bám theo evidence (knowledge base) không?
- **Giá trị**: `✅ PASS` / `⚠️ PARTIAL` / `❌ FAIL`
- **PASS**: Mọi claim trong answer đều có evidence support
- **PARTIAL**: Có claim đúng lẫn claim không có evidence
- **FAIL**: Answer chứa thông tin không có trong KB (hallucination)

#### `check_kb_reason` (cột X)
- **Mô tả**: Giải thích evidence usage
- **Ví dụ**: "Claim 'bảo hành 8 năm' có trong chunk_045, nhưng 'đổi mới miễn phí' không có trong KB"

#### `check_citation_correct` (cột Y)
- **Mô tả**: Citation có trỏ đúng source support answer không?
- **Giá trị**: `✅ PASS` / `⚠️ PARTIAL` / `❌ FAIL`
- **Lưu ý**: Cột S (`citation_chunk_match`) check tự động ID match, cột này human check semantic

#### `check_citation_reason` (cột Z)
- **Mô tả**: Giải thích citation quality
- **Ví dụ**: "Citation trỏ đúng chunk_045, nội dung match với claim trong answer"

#### `error_type` (cột AA)
- **Mô tả**: Phân loại lỗi chính (nếu có)
- **Giá trị**:
  - `none` — không có lỗi
  - `retrieval_error` — top 5 không chứa ground truth
  - `ranking_error` — có ground truth nhưng rank thấp (4-5)
  - `generation_error` — retrieval đúng nhưng answer sai
  - `citation_error` — answer đúng nhưng citation sai
  - `guardrail_error` — câu ngoài scope nhưng trả lời bừa
  - `rewrite_error` — query rewrite làm mất ý
- **Quy tắc**: Code sẽ **gợi ý** dựa trên metrics, human **confirm hoặc sửa**

#### `overall_verdict` (cột AB)
- **Mô tả**: Đánh giá tổng thể case này
- **Giá trị**: `✅ PASS` / `⚠️ PARTIAL` / `❌ FAIL`

---

## 4. Hướng dẫn label ground truth

### Bước 1: Xác định câu hỏi test

Cần **ít nhất 10 câu**, phân bổ như sau:

| Loại | Số lượng tối thiểu | Ví dụ |
|------|-------------------|-------|
| Trực tiếp (1 chunk) | 3-4 câu | "Pin bảo hành bao lâu?" |
| Cần hiểu đoạn dài | 2 câu | "Điều kiện bảo hành là gì?" |
| Cần nhiều chunk | 1-2 câu | "So sánh bảo hành VF5 và VF8" |
| Dễ gây nhầm | 1-2 câu | "Mất hóa đơn có bảo hành không?" |
| Out-of-scope | 1-2 câu | "Giá cổ phiếu VinFast?" |

### Bước 2: Tìm ground truth evidence

**Cách 1 — Từ chunks đã ingest:**
1. Chạy API `/sources/{document_id}/chunks` để lấy danh sách chunks
2. Đọc từng chunk, tìm chunk chứa câu trả lời
3. Ghi lại `chunk_id`, `document_name`, `page`

**Cách 2 — Từ tài liệu gốc:**
1. Đọc tài liệu PDF/URL gốc
2. Tìm đoạn chứa câu trả lời
3. Tra ngược chunk_id tương ứng qua API hoặc log

**Cách 3 — Từ rag_context có sẵn:**
1. Nếu đã có file report xlsx cũ (Report_VSF.xlsx...)
2. Đọc cột `rag_context` → tìm chunk phù hợp nhất
3. Ghi lại chunk_id làm ground truth

### Bước 3: Validate ground truth

Kiểm tra lại:
- [ ] Chunk text có thực sự chứa thông tin trả lời câu hỏi?
- [ ] Chunk ID có tồn tại trong hệ thống?
- [ ] Với câu multi-chunk: đã liệt kê đủ các chunk cần thiết?
- [ ] Câu out-of-scope: đã đánh dấu `is_out_of_scope = TRUE`?

---

## 5. Dữ liệu mẫu

### 5.1 Test Dataset (Human fill)

| id | section_name | question | expected_answer | ground_truth_chunk_ids | ground_truth_doc | ground_truth_page | is_out_of_scope |
|----|-------------|----------|----------------|----------------------|-----------------|-------------------|-----------------|
| Q01 | Bảo hành pin | Pin xe VF8 được bảo hành bao lâu? | Pin cao áp được bảo hành 8 năm hoặc 160.000 km | pdf_001_p12_c01 | vinfast_warranty.pdf | 12 | FALSE |
| Q02 | Bảo hành pin | Điều kiện để được bảo hành pin là gì? | Còn thời hạn bảo hành, có giấy tờ hợp lệ, không thuộc trường hợp từ chối | pdf_001_p12_c01,pdf_001_p13_c02 | vinfast_warranty.pdf | 12-13 | FALSE |
| Q03 | Bảo hành xe | Trường hợp nào không được bảo hành? | Tai nạn, tự ý sửa chữa, không bảo dưỡng định kỳ | pdf_001_p15_c01 | vinfast_warranty.pdf | 15 | FALSE |
| Q04 | Bảo hành xe | Nếu mất hóa đơn thì có được bảo hành không? | Theo điều kiện trong tài liệu về giấy tờ hợp lệ | pdf_001_p13_c02 | vinfast_warranty.pdf | 13 | FALSE |
| Q05 | Bảo hành xe | Bảo hành có áp dụng cho phụ kiện không? | Tùy loại phụ kiện, xem chính sách chi tiết | pdf_001_p18_c01 | vinfast_warranty.pdf | 18 | FALSE |
| Q06 | Dịch vụ | Người dùng cần mang xe đến đâu để bảo hành? | Các trung tâm dịch vụ ủy quyền VinFast | pdf_001_p20_c01 | vinfast_warranty.pdf | 20 | FALSE |
| Q07 | Bảo hành xe | Thời gian bảo hành xe là bao lâu? | 5 năm hoặc 125.000 km tùy điều kiện nào đến trước | pdf_001_p10_c01 | vinfast_warranty.pdf | 10 | FALSE |
| Q08 | Bảo hành xe | Xe bị tai nạn có được bảo hành không? | Không, tai nạn thuộc trường hợp từ chối bảo hành | pdf_001_p15_c01 | vinfast_warranty.pdf | 15 | FALSE |
| Q09 | Chính sách | Chính sách bảo hành áp dụng từ ngày nào? | Từ ngày mua xe, theo hợp đồng | pdf_001_p08_c01 | vinfast_warranty.pdf | 8 | FALSE |
| Q10 | Out-of-scope | Giá cổ phiếu VinFast hôm nay là bao nhiêu? | Không có trong tài liệu | NONE | | | TRUE |
| Q11 | Out-of-scope | Thời tiết Hà Nội hôm nay thế nào? | Không có trong tài liệu | NONE | | | TRUE |

### 5.2 Pipeline Output + Auto Metrics (Code fill) — Ví dụ case tốt

| Cột | Giá trị (Q01) |
|-----|--------------|
| rag_input | "Pin xe VF8 bảo hành bao lâu?" |
| rag_context | `[{"id":"pdf_001_p12_c01","text":"Pin cao áp được bảo hành 8 năm hoặc 160.000 km.","score":0.92},{"id":"url_001_c03","text":"...","score":0.78}]` |
| bot_response | "Pin VF8 được bảo hành 8 năm hoặc 160.000 km. [1]" |
| bot_citations | `[{"source":"vinfast_warranty.pdf","chunk_id":"pdf_001_p12_c01","page":12}]` |
| retrieved_top5_ids | pdf_001_p12_c01, url_001_c03, pdf_002_p05_c01, pdf_001_p13_c02, url_002_c01 |
| ground_truth_rank | 1 |
| recall_at_5 | 1 |
| mrr_at_5 | 1.0 |
| citation_chunk_match | TRUE |
| guardrail_pass | N/A |

### 5.3 Pipeline Output + Auto Metrics — Ví dụ case retrieval error

| Cột | Giá trị (Q04 — retrieval sai) |
|-----|-------------------------------|
| rag_input | "Mất hóa đơn bảo hành" |
| rag_context | `[{"id":"pdf_001_p10_c01",...},{"id":"pdf_001_p20_c01",...},{"id":"url_002_c01",...}]` |
| bot_response | "Khách hàng cần mang theo hóa đơn khi bảo hành..." |
| bot_citations | `[{"source":"vinfast_warranty.pdf","chunk_id":"pdf_001_p10_c01","page":10}]` |
| retrieved_top5_ids | pdf_001_p10_c01, pdf_001_p20_c01, url_002_c01, pdf_002_p05_c01, url_001_c01 |
| ground_truth_rank | -1 |
| recall_at_5 | 0 |
| mrr_at_5 | 0 |
| citation_chunk_match | FALSE |
| guardrail_pass | N/A |

### 5.4 Ví dụ case out-of-scope (guardrail test)

| Cột | Giá trị (Q10 — out-of-scope) |
|-----|------------------------------|
| rag_input | "Giá cổ phiếu VinFast hôm nay" |
| rag_context | `[{"id":"url_001_c03","text":"...VinFast...","score":0.31}]` |
| bot_response | "Mình chưa tìm thấy thông tin này trong tài liệu được cung cấp." |
| bot_citations | `[]` |
| retrieved_top5_ids | url_001_c03, pdf_001_p01_c01, ... |
| ground_truth_rank | (trống) |
| recall_at_5 | (trống) |
| mrr_at_5 | (trống) |
| citation_chunk_match | (trống) |
| guardrail_pass | TRUE |

---

## 6. Cách tính metrics

### 6.1 Recall@5 (trung bình toàn bộ câu in-scope)

```
Recall@5 = Σ recall_at_5 của các câu in-scope / số câu in-scope

Ví dụ: 9 câu in-scope, 7 câu có recall = 1
Recall@5 = 7 / 9 = 0.778
```

### 6.2 MRR@5 (trung bình toàn bộ câu in-scope)

```
MRR@5 = Σ mrr_at_5 của các câu in-scope / số câu in-scope

Ví dụ: 9 câu in-scope, MRR lần lượt = [1.0, 0.5, 1.0, 0, 1.0, 0.33, 1.0, 1.0, 0.5]
MRR@5 = (1.0+0.5+1.0+0+1.0+0.33+1.0+1.0+0.5) / 9 = 0.592
```

### 6.3 Guardrail Accuracy

```
Guardrail accuracy = số câu out-of-scope được từ chối đúng / tổng số câu out-of-scope

Ví dụ: 2 câu out-of-scope, cả 2 đều từ chối đúng
Guardrail accuracy = 2 / 2 = 1.0
```

### 6.4 Citation Accuracy (in-scope, có answer đúng)

```
Citation accuracy = số câu có citation_chunk_match = TRUE / số câu in-scope có recall = 1
```

### 6.5 Answer Accuracy (human-evaluated)

```
Answer accuracy = số câu check_answer_correct = "✅ PASS" / tổng số câu in-scope
```

### 6.6 Bảng tổng hợp metrics (ở cuối file xlsx — sheet "Summary")

| Metric | Giá trị | Target |
|--------|---------|--------|
| Tổng câu hỏi test | 11 | ≥ 10 |
| Câu in-scope | 9 | |
| Câu out-of-scope | 2 | ≥ 1 |
| **Recall@5** | 0.778 | ≥ 0.70 |
| **MRR@5** | 0.592 | ≥ 0.50 |
| Guardrail accuracy | 1.0 | = 1.0 |
| Citation accuracy | 0.857 | ≥ 0.80 |
| Answer accuracy (human) | 0.667 | ≥ 0.60 |

---

## 7. Hướng dẫn human review

### Quy trình review từng case

1. **Đọc `question`** — hiểu câu hỏi
2. **Đọc `expected_answer`** — biết đáp án chuẩn
3. **Đọc `bot_response`** — so sánh với expected
4. **Check answer correct**:
   - PASS: Bot trả lời đúng trọng tâm, đủ ý chính
   - PARTIAL: Đúng một phần, thiếu hoặc thừa ý
   - FAIL: Sai thông tin hoặc hallucinate
5. **Check KB used**:
   - Đọc `rag_context` (evidence retrieved)
   - Bot có bám theo evidence hay nói thêm?
6. **Check citation**:
   - Citation trỏ đúng chunk chứa evidence?
   - Citation source/page có match?
7. **Xác định error_type** (xem phần 8)
8. **Ghi overall_verdict**

### Mẹo review nhanh

- Nếu `recall_at_5 = 0` → retrieval sai, khả năng cao answer cũng sai
- Nếu `0 < recall_at_5 < 1` → retrieval chỉ lấy được một phần evidence, cần human review kỹ
- Nếu `recall_at_5 = 1` nhưng answer sai → generation error
- Nếu `citation_chunk_match = FALSE` → cần check citation kỹ
- Nếu `guardrail_pass = FALSE` → guardrail error chắc chắn

---

## 8. Failure analysis

### Cây quyết định phân loại lỗi

```
Câu hỏi
├── is_out_of_scope = TRUE?
│   ├── guardrail_pass = TRUE → ✅ none
│   └── guardrail_pass = FALSE → ❌ guardrail_error
│
└── is_out_of_scope = FALSE?
    ├── recall_at_5 = 0 → ❌ retrieval_error
    │
    ├── 0 < recall_at_5 < 1 → ⚠️ partial_retrieval / human judgment
    │
    ├── recall_at_5 = 1, ground_truth_rank ≥ 4 → ⚠️ ranking_error
    │
    ├── recall_at_5 = 1, ground_truth_rank ≤ 3
    │   ├── check_answer_correct = FAIL → ❌ generation_error
    │   ├── check_answer_correct = PASS, citation_chunk_match = FALSE → ⚠️ citation_error
    │   └── check_answer_correct = PASS, citation_chunk_match = TRUE → ✅ none
    │
    └── (edge cases) → human judgment
```

### Bảng error type và hành động

| Error Type | Nguyên nhân | Hành động cải thiện |
|-----------|------------|-------------------|
| `retrieval_error` | Evidence đúng không nằm trong top 5 | Cải thiện chunking, embedding, BM25 weights |
| `ranking_error` | Evidence có nhưng rank thấp (4-5) | Tune RRF weights, thêm reranker |
| `generation_error` | Retrieval đúng nhưng LLM trả lời sai | Cải thiện prompt, temperature, guardrails |
| `citation_error` | Answer đúng nhưng citation sai | Fix citation mapping logic |
| `guardrail_error` | Câu ngoài scope nhưng trả lời bừa | Strengthen not-found detection |
| `rewrite_error` | Query rewrite làm mất ý | Cải thiện rewrite prompts |

---

## Phụ lục: File kèm theo

- `evaluation_dataset.xlsx` — File template với sample data, sẵn sàng để fill
  - **Sheet "Evaluation"** — Bảng chính 28 cột
  - **Sheet "Summary"** — Bảng tổng hợp metrics (dùng formula tự tính)
  - **Sheet "Instructions"** — Tóm tắt hướng dẫn nhanh
