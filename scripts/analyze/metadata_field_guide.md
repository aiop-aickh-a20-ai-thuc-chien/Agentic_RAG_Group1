# Hướng dẫn sử dụng Metadata trong RAG Pipeline

> **Corpus:** VinFast EV — 1,488 chunks / 308 tài liệu (tiếng Việt)  
> **Cập nhật:** 2026-06-17

---

## Metadata có những trường gì?

Metadata chia thành 2 nhóm: **[P]** trích xuất tự động khi parse, **[L]** do LLM generate lúc ingestion.

### Nhóm [P] — Rule-based, luôn có

| Trường | Ý nghĩa |
|--------|---------|
| `chunk_id` | ID duy nhất của chunk |
| `document_id` | ID tài liệu gốc |
| `source_url` | URL nguồn |
| `source_type` | Loại nguồn (`url`) |
| `language` | Ngôn ngữ (`vi`) |
| `document_type` | Loại tài liệu (rule-based) |
| `chunk_index` | Vị trí chunk trong tài liệu |
| `total_chunks` | Tổng số chunk của tài liệu |
| `char_count` | Số ký tự |

### Nhóm [L] — LLM-extracted, cần cấu hình `INGESTION_LLM_*`

| Trường | Ý nghĩa |
|--------|---------|
| `summary` | Tóm tắt nội dung chunk (1–2 câu) |
| `keywords` | Danh sách từ khóa (~8/chunk) |
| `questions` | Câu hỏi mà chunk có thể trả lời (~4/chunk) |
| `entities` | Thực thể có tên: xe, địa điểm, thương hiệu (~3/chunk) |
| `document_type` | Loại tài liệu (LLM classify, chính xác hơn [P]) |
| `language` | Ngôn ngữ (LLM detect) |

---

## Trường nào dùng được, ở đâu, làm gì?

### ✅ entities — Pre-filter trong Qdrant

**Dùng khi:** Query của user nhắc đến tên xe hoặc địa điểm cụ thể.

**Cách hoạt động:**
```
Query: "pin VF 8 bao nhiêu kWh?"
  → extract entity: "VF 8"
  → Qdrant filter: entities CONTAINS "VF 8"
  → search chỉ trong ~175 chunk thay vì 1,488 chunk
```

**Lưu ý quan trọng:** LLM không nhất quán khi viết tên xe — cần normalize trước khi filter:

```
"VF 8" | "VinFast VF 8" | "VF8" | "VF 8 Plus"  →  đều cần về "VF 8"
```

Entities đáng tin cậy để filter: tên model VF (VF 3–9, VF e34), tên dòng xe máy điện (Theon S, Klara S…), thành phố (Hà Nội, Đà Nẵng…).

**Không nên filter:** "VinFast" (75% chunk — quá rộng), entities chỉ xuất hiện 1–2 lần.

---

### ✅ questions — Q→Q Retrieval (hiệu quả nhất)

**Vấn đề cần giải quyết:** Query của user (ngắn, thông dụng) rất khác chunk text (dài, kỹ thuật) → similarity thấp, lấy nhầm chunk.

**Giải pháp Q→Q:**

```
Thay vì:  embed(query) → so sánh với embed(chunk_text)   ← semantic gap lớn

Dùng:     embed(query) → so sánh với embed(question)     ← cùng dạng câu hỏi
                                    ↓
                              lấy chunk_id của question đó
```

**Cách setup:**
1. Lấy toàn bộ ~5,800 câu hỏi từ tất cả chunks
2. Embed từng câu hỏi → lưu vào Qdrant collection `questions` (payload gồm `chunk_id`)
3. Khi có query: search collection `questions` → lấy top chunk_ids → retrieve chunks đó

**Ví dụ thực tế:**
```
Query:    "VF 8 đầy bình chạy được bao xa?"
Question: "VF 8 chạy được bao nhiêu km một lần sạc?"  ← match cao
  → chunk về quãng đường VF 8 được trả về đúng
```

---

### ✅ keywords — BM25 Augmentation (offline)

**Dùng khi:** Index vào sparse retrieval (BM25) để tăng recall từ khóa.

**Cách hoạt động:**

```
Chunk text gốc:  "Hệ thống Immobilizer ngăn chặn việc khởi động trái phép..."
Keywords LLM:    ["chống trộm", "chìa khóa", "bảo vệ", "khởi động"]

→ Nối keywords vào text trước khi index BM25:
   "...khởi động trái phép... chống trộm chìa khóa bảo vệ"

Query: "VF e34 có chống trộm không?"
→ BM25 match được "chống trộm" dù chunk text không dùng từ đó
```

**Lưu ý:** Keywords chủ yếu là synonym / từ thông dụng hơn so với chunk text. Không dùng keywords để filter — quá generic.

---

### ✅ document_type — Boost khi Re-rank

**Dùng khi:** Re-rank kết quả retrieval dựa vào loại tài liệu phù hợp với intent của query.

| Loại query | document_type ưu tiên |
|------------|----------------------|
| "thông số kỹ thuật...", "dung lượng pin...", "công suất..." | `spec_sheet` |
| "làm thế nào...", "hướng dẫn...", "cách..." | `faq`, `manual` |
| "chính sách...", "điều khoản...", "bảo hành..." | `policy` |
| Tin tức, tổng quan | `article` |

---

### ✅ summary — Re-rank & Hiển thị

**2 cách dùng:**

1. **Re-rank rẻ hơn:** So sánh query với summary (~100 ký tự) thay vì full chunk (~800 ký tự) → tiết kiệm token 8x khi gọi LLM re-ranker.

2. **Hiển thị snippet:** Dùng summary làm đoạn mô tả ngắn trong UI kết quả, thay vì cắt thô chunk text.

---

### ✅ chunk_index + total_chunks — Context Expansion

**Dùng khi:** Chunk tìm được nằm giữa tài liệu và nội dung bị cắt đứt → lấy thêm chunk liền kề để có context đầy đủ hơn.

```
chunk_index=2, total_chunks=6
→ có thể lấy thêm chunk_index=1 và chunk_index=3 để mở rộng context
```

---

### ✅ source_url — Citation

Hiển thị URL nguồn trong câu trả lời để user có thể kiểm chứng. Không dùng để filter (toàn bộ đều là `vinfastauto.com`).

---

### ❌ language, source_type — Không dùng được

- `language`: 100% `vi` → không phân biệt được gì
- `source_type`: 100% `url` → không phân biệt được gì

---

## Tóm tắt — Bảng tổng hợp

| Metadata | Dùng ở giai đoạn | Làm gì | Ưu tiên |
|----------|-----------------|--------|---------|
| `questions` [L] | Retrieval (online) | Q→Q collection riêng trong Qdrant | 🔴 Cao nhất |
| `entities` [L] | Query processing (online) | Pre-filter Qdrant theo model/địa điểm | 🔴 Cao |
| `keywords` [L] | Index (offline, 1 lần) | Nối vào text để tăng BM25 recall | 🟡 Trung bình |
| `document_type` [L] | Re-ranking (online) | Boost score theo loại tài liệu | 🟡 Trung bình |
| `summary` [L] | Re-ranking / UI (online) | Re-rank rẻ hơn, hiển thị snippet | 🟡 Trung bình |
| `chunk_index` [P] | Post-retrieval (online) | Mở rộng context lấy chunk liền kề | 🟢 Nhỏ |
| `source_url` [P] | Response (online) | Hiển thị citation cho user | 🟢 Nhỏ |
| `language` [P/L] | — | Không dùng | ❌ |
| `source_type` [P] | — | Không dùng | ❌ |

---

## Pipeline đề xuất

```
User Query
    │
    ▼
[1] Extract entities (regex) + detect intent
    │
    ├──────────────────┬──────────────────┐
    ▼                  ▼                  ▼
[2a] Hybrid Search  [2b] Q→Q Search   [2c] Entity Pre-filter
    dense + sparse      questions           Qdrant filter
    (BM25 augmented     collection          entities ∋ "VF 8"
     với keywords)      → chunk_ids
    │                  │                  │
    └──────────────────┴──────────────────┘
                       │
                       ▼
[3] RRF Fusion — gộp kết quả từ 2a + 2b + 2c
                       │
                       ▼
[4] Re-rank — boost theo document_type + summary comparison
                       │
                       ▼
[5] Top-5 chunks → LLM generate answer
    + source_url citation + summary snippet
```
