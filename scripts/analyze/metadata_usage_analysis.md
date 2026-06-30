# Phân tích Metadata & Đề xuất sử dụng trong RAG Pipeline

> **Ngày:** 2026-06-17  
> **Corpus:** 1,488 chunks / 308 documents — domain VinFast EV (tiếng Việt)  
> **Mục đích:** Phân tích các trường metadata đang có, đánh giá khả năng sử dụng và đề xuất tích hợp vào retrieval pipeline.

---

## 1. Tổng quan các trường metadata

Metadata được chia thành 2 nhóm theo nguồn trích xuất:

### [P] Rule-based — luôn có, trích xuất khi parse

| Field | Mô tả | Ví dụ |
|-------|-------|-------|
| `chunk_id` | ID duy nhất của chunk | `url_8fe358bb_c001` |
| `document_id` | ID tài liệu gốc | `url_8fe358bb` |
| `source_url` | URL nguồn | `https://vinfastauto.com/...` |
| `source_type` | Loại nguồn | `url` |
| `language` | Ngôn ngữ | `vi` |
| `document_type` | Loại tài liệu (rule-based) | `article`, `faq`, `policy`, `manual`, `spec_sheet` |
| `chunk_index` | Vị trí chunk trong tài liệu | `0`, `1`, `2`... |
| `total_chunks` | Tổng số chunk của tài liệu | `5` |
| `char_count` | Số ký tự của chunk | `842` |

### [L] LLM-extracted — chỉ có nếu `INGESTION_LLM_*` được cấu hình

| Field | Mô tả | Ví dụ |
|-------|-------|-------|
| `summary` | Tóm tắt nội dung chunk (1-2 câu) | `"VF 8 có pin LFP dung lượng 87.7 kWh..."` |
| `keywords` | Danh sách từ khóa (~8/chunk) | `["VF 8", "pin LFP", "sạc nhanh", ...]` |
| `questions` | Câu hỏi mà chunk có thể trả lời (~3.9/chunk) | `["Pin VF 8 bao nhiêu kWh?", ...]` |
| `entities` | Thực thể có tên (~3.3/chunk) | `["VinFast", "VF 8", "Hà Nội"]` |
| `document_type` | Loại tài liệu (LLM classify) | `spec_sheet` |
| `language` | Ngôn ngữ (LLM detect) | `vi` |

---

## 2. Phân tích từng trường

### 2.1 Entities

**Thống kê corpus:**
- 1,433/1,488 chunks có entities (96.3%)
- 4,958 lần xuất hiện tổng cộng, avg **3.33 entities/chunk**
- **1,036 distinct entity strings** — nhưng phân bố rất lệch:
  - 558 strings chỉ xuất hiện **1 lần** (53.9% — noise)
  - 365 strings xuất hiện 2–5 lần
  - **113 strings xuất hiện 6+ lần** → đây là phần có thể tin cậy

**Entities phổ biến nhất:**

| Entity | Số chunk | % corpus |
|--------|----------|----------|
| VinFast | 1,116 | 75.0% |
| VF 8 | 175 | 11.8% |
| VF 9 | 115 | 7.7% |
| VF e34 | 108 | 7.3% |
| xe máy điện | 98 | 6.6% |
| Hà Nội | 74 | 5.0% |
| VF 7 | 62 | 4.2% |
| VF 6 | 51 | 3.4% |
| VF 5 | 50 | 3.4% |
| VF 3 | 49 | 3.3% |

**Vấn đề: Entities không nhất quán**

LLM trích xuất cùng một thực thể nhưng viết khác nhau:

```
VF 8  →  "VF 8" ×175  |  "VinFast VF 8" ×22  |  "VF8" ×1  |  "VF 8 Plus" ×5
VF 3  →  "VF 3" ×49   |  "VinFast VF 3" ×15  |  "xe VF 3" ×1  |  "Bọc Ghế Da VF 3" ×3
```

→ **Filter exact match sẽ miss ~15% chunk đúng** nếu không normalize.

**Giải pháp:** Regex normalize về dạng chuẩn khi lưu VÀ khi extract từ query:

```python
# "VinFast VF 8" → "VF 8" | "VF8" → "VF 8" | "Thảm Cốp 3D VF 8" → "VF 8"
_VF_PATTERN = re.compile(r'\bVF[\s\-]?(e?3[45]?|[3-9]|Wild|DrgnFly)\b', re.IGNORECASE)
```

**Kết luận entities:** Dùng được cho pre-filter, nhưng **bắt buộc normalize trước**. Chỉ tin cậy với entities xuất hiện ≥ 6 lần.

---

### 2.2 Keywords

**Thống kê corpus:**
- 1,470/1,488 chunks có keywords (98.8%)
- 11,480 lần xuất hiện tổng cộng, avg **7.72 keywords/chunk**
- 87.9% chunk có đúng 8 keywords (LLM được prompt cố định 8)
- **2,326 distinct keywords**:
  - 1,185 keywords chỉ xuất hiện 1 lần (50.9% — long tail)
  - 770 keywords xuất hiện 2–5 lần
  - 371 keywords xuất hiện 6+ lần (ổn định)

**Phát hiện quan trọng — Overlap với chunk text:**

```
Total keyword occurrences  : 11,480
Đã có trong chunk text     : 10,085  (87.8%)
Thông tin MỚI (chưa có)   :  1,395  (12.2%)
```

→ 87.8% keywords đã nằm trong text gốc → BM25 không được lợi thêm  
→ Chỉ 12.2% keywords thực sự bổ sung thông tin mới (synonyms, abstractions)

**Top keywords thêm thông tin mới:**

| Keyword | Lần thêm mới |
|---------|-------------|
| xe điện | 159 |
| vinfast | 60 |
| giá | 34 |
| xe máy điện | 27 |
| khuyến mãi | 17 |
| bảo hành 24 tháng | 16 |

**Kết luận keywords:**
- **Không dùng để filter** — top keywords quá generic (vinfast 68.5%, xe điện 19.3%)
- **Dùng cho BM25 augmentation** — nối keywords vào text khi index sparse, đặc biệt có lợi khi chunk dùng từ kỹ thuật/trang trọng còn user gõ từ thông dụng

---

### 2.3 Questions

**Thống kê:**
- avg ~3.9 questions/chunk
- 1,488 × 3.9 ≈ **~5,800 câu hỏi** toàn corpus

**Ví dụ thực tế:**
```
Chunk: "Pin VF 8 dung lượng 87.7 kWh, công suất sạc DC tối đa 150 kW..."
Questions:
  - "Pin VF 8 bao nhiêu kWh?"
  - "VF 8 sạc nhanh mất bao lâu?"
  - "Thời gian sạc đầy của VF 8 là bao nhiêu?"
```

**Tại sao questions quan trọng — Semantic gap:**

```
Query user: "VF 8 đầy bình chạy được bao xa?"
                    ↕ similarity thấp (abstract vs detail)
Chunk text: "VF 8 có quãng đường di chuyển lên tới 420 km theo chu trình WLTP..."
                    ↕ similarity cao (câu hỏi ↔ câu hỏi)
Question:   "VF 8 chạy được bao nhiêu km một lần sạc?"
```

→ Q→Q matching hiệu quả hơn Query→Chunk matching vì cùng format câu hỏi.

**Kết luận questions:** Trường có tiềm năng cao nhất — embed toàn bộ ~5,800 câu hỏi vào Qdrant collection riêng, dùng cho dual-retrieval.

---

### 2.4 Document Type

**Phân bố:**

| document_type | Chunks | % |
|---------------|--------|---|
| article | 748 | 50.3% |
| faq | 224 | 15.1% |
| policy | 194 | 13.0% |
| unknown | 136 | 9.1% |
| manual | 134 | 9.0% |
| spec_sheet | 34 | 2.3% |
| None | 18 | 1.2% |

**Ứng dụng:** Boost score khi re-rank dựa vào loại query:
- Query kỹ thuật ("thông số VF 8") → boost `spec_sheet`
- Query câu hỏi ("làm thế nào để...") → boost `faq` / `manual`
- Query chính sách ("điều kiện bảo hành") → boost `policy`

---

### 2.5 Summary

**Ứng dụng:**
1. **Re-rank rẻ hơn** — so sánh query với summary (ngắn ~100 char) thay vì full chunk (~800 char) → token cost thấp hơn 8x
2. **Hiển thị cho user** — snippet ngắn trong UI kết quả trước khi mở full chunk

---

### 2.6 Các trường KHÔNG dùng được

| Field | Lý do |
|-------|-------|
| `language` | 100% `vi` → không discriminate |
| `source_type` | 100% `url` → không discriminate |
| `source_url` | Chỉ dùng để hiển thị citation, không filter |

---

## 3. Đề xuất tích hợp vào Pipeline

### Sơ đồ tổng thể

```
User Query
    │
    ▼
┌─────────────────────────────────────────────┐
│  Query Processing                            │
│  - Extract VF model/location (regex)         │
│  - Detect intent → document_type hint        │
└─────────────────────────────────────────────┘
    │
    ├──────────────────────┬─────────────────────────────┐
    ▼                      ▼                             ▼
[Hybrid Search]      [Q→Q Search]              [Entity Pre-filter]
dense + sparse       embed query →             Qdrant filter:
(BM25 augmented      questions_collection      entities CONTAINS
 với keywords)       → top-20 chunks            "VF 8" (normalized)
    │                      │                             │
    └──────────────────────┴─────────────────────────────┘
                           │
                           ▼
                    ┌─────────────────┐
                    │   RRF Fusion    │
                    │  + doc_type     │
                    │    boost        │
                    └─────────────────┘
                           │
                           ▼
                    Top-5 chunks
                    + summary display
                    + source_url citation
```

---

## 4. Thứ tự ưu tiên implement

| # | Việc | Metadata dùng | Gain | Độ khó | Ghi chú |
|---|------|---------------|------|--------|---------|
| 1 | **BM25 augment với keywords** | `keywords` | Trung bình | Dễ | Offline, 1 lần re-index |
| 2 | **Q→Q collection trong Qdrant** | `questions` | **Cao nhất** | Trung bình | Index ~5,800 vectors 1 lần |
| 3 | **Entity pre-filter** | `entities` | Cao | Trung bình | Cần normalize regex trước |
| 4 | **document_type boost** | `document_type` | Nhỏ | Dễ | Thêm vào re-ranking score |
| 5 | **Summary re-rank** | `summary` | Trung bình | Dễ | Nếu đã có LLM re-ranker |
| 6 | **Context expansion** | `chunk_index`, `total_chunks` | Nhỏ-trung bình | Dễ | Lấy chunk liền kề khi cần |

---

## 5. Lưu ý kỹ thuật quan trọng

### Entity normalization — bắt buộc trước khi filter

Áp dụng normalize **cả 2 đầu**: lúc lưu vào store VÀ lúc extract từ query user.

```python
import re

_VF_CANONICAL = {
    "vf3": "VF 3", "vf 3": "VF 3",
    "vf5": "VF 5", "vf 5": "VF 5",
    "vf6": "VF 6", "vf 6": "VF 6",
    "vf7": "VF 7", "vf 7": "VF 7",
    "vf8": "VF 8", "vf 8": "VF 8",
    "vf9": "VF 9", "vf 9": "VF 9",
    "vf e34": "VF e34", "vfe34": "VF e34",
    "vf wild": "VF Wild",
    "vf drgnfly": "VF DrgnFly",
}

_VF_PATTERN = re.compile(r'\bVF[\s\-]?(e?3[45]?|[3-9]|Wild|DrgnFly)\b', re.IGNORECASE)

def normalize_vf_entity(raw: str) -> str | None:
    """Extract và normalize tên model VF từ chuỗi bất kỳ."""
    key = raw.lower().replace("-", " ").strip()
    if key in _VF_CANONICAL:
        return _VF_CANONICAL[key]
    m = _VF_PATTERN.search(raw)
    if m:
        return f"VF {m.group(1).strip()}"
    return None  # không phải model VF
```

### Chỉ filter với entities đáng tin cậy

```python
# Chỉ dùng entity để filter khi:
# 1. Là tên model VF (sau normalize) — luôn reliable
# 2. Hoặc entity xuất hiện >= 6 lần trong corpus (113 strings)
# 3. Bỏ qua entity xuất hiện < 6 lần (558 strings — noise)
```

### Keywords cho BM25 — tránh inflate quá nhiều

```python
# Khi index, nối keywords vào cuối text (không lặp nếu đã có trong text)
def augment_text_with_keywords(text: str, keywords: list[str]) -> str:
    text_lower = text.lower()
    new_kws = [k for k in keywords if k.lower() not in text_lower]
    if not new_kws:
        return text
    return text + "\n" + " ".join(new_kws)
```

---

## 6. Scripts phân tích

Các script chi tiết có trong `scripts/analyze/`:

| File | Nội dung |
|------|---------|
| [`entity_analysis.py`](entity_analysis.py) | Frequency, clustering, VF model variants, free-form entities |
| [`entity_analysis_report.md`](entity_analysis_report.md) | Output đầy đủ của entity analysis |
| [`keyword_analysis.py`](keyword_analysis.py) | Frequency, overlap với text, by document_type, unique keywords |
| [`keyword_analysis_report.md`](keyword_analysis_report.md) | Output đầy đủ của keyword analysis |

---

*Tài liệu này tổng hợp kết quả phân tích thực tế trên corpus 1,488 chunks. Các con số là từ dữ liệu thật, không phải ước tính.*
