# Lưu trữ Metadata Chunk vào PostgreSQL (Neon) + Qdrant

> **Branch:** `feat/metadata-store`  
> **Người thực hiện:** Hoang

---

## Bối cảnh

Hệ thống RAG cần lưu trữ metadata của từng chunk để phục vụ tìm kiếm, lọc, và đánh giá chất lượng. Trước đây metadata chỉ được lưu cục bộ (JSONL) hoặc trong S3 — không ai trong team có thể truy cập chung được.

Branch này giải quyết vấn đề đó bằng cách thêm **PostgreSQL (Neon)** làm nơi lưu metadata chunk có cấu trúc, đồng thời đảm bảo **Qdrant** cũng nhận đầy đủ metadata `[P]` + `[L]` trong payload để phục vụ vector search có filter. Pipeline ingestion được tích hợp thêm giai đoạn trích xuất metadata bằng LLM.

---

## Kiến trúc tổng thể

```
Pipeline Ingestion
│
├─ 1. Parse / Fetch tài liệu
│
├─ 2. Gán metadata [P] (rule-based)
│     _chunks_with_local_metadata()
│     annotate_chunks_with_quality()
│
├─ 3. Phát hiện trùng lặp (Dedup)
│     _apply_dedup_to_new_chunks()
│
├─ 4. Ghi lần 1 vào S3 + Neon + Qdrant
│     _write_indexes()
│       ├─ S3     → file gốc + markdown (blob)
│       ├─ Neon   → document + chunks với metadata [P] (chưa có [L])
│       └─ Qdrant → dense vectors + payload với metadata [P]
│
└─ 5. Làm giàu metadata [L] bằng LLM → ghi lần 2
      _enrich_chunks_with_llm()
        ├─ extract_chunk_metadata()         ← code của teammate
        ├─ apply_extracted_metadata()       ← code của teammate
        ├─ _replace_document_chunks()       → cập nhật Neon với [P] + [L]
        └─ _upsert_dense_embeddings_safely() → cập nhật Qdrant payload với [P] + [L]
```

### Ba nhóm metadata trên mỗi chunk

| Ký hiệu | Nguồn | Các trường |
|---------|-------|-----------|
| `[P]` | Rule-based (parser) | `title`, `section`, `section_path`, `chunk_index`, `quality_score`, v.v. |
| `[L]` | LLM extraction | `summary`, `keywords`, `questions`, `entities`, `document_type`, `language` |
| `[S]` | Storage layer | `document_id`, `chunk_id`, `ingested_at` |

---

## Các thay đổi trong branch này

### 1. Thêm `HybridLocalSourceStore` — `storage.py`

Trước đây chỉ có hai lựa chọn: lưu toàn bộ vào S3 hoặc toàn bộ vào Postgres. Branch này thêm class `HybridLocalSourceStore`:

- **S3** → nhận file gốc (PDF, raw) và markdown (blob-only, không lưu chunks)
- **Postgres (Neon)** → nhận metadata document và toàn bộ chunks (source of truth)

```
LOCAL_SOURCE_STORE=hybrid
LOCAL_SOURCE_POSTGRES_CONNECTION=<neon connection string>
LOCAL_SOURCE_POSTGRES_TABLE_PREFIX=local_rag
```

Schema Postgres được tự động tạo khi kết nối lần đầu (`_ensure_schema()`), bao gồm hai bảng:

- `local_rag_documents` — thông tin document (id, name, source\_type, metadata)
- `local_rag_chunks` — toàn bộ chunks kèm metadata đầy đủ

Và các index:
- `chunk_id` — tra cứu nhanh theo chunk
- `to_tsvector('english', text)` — full-text search
- `source_type` — lọc theo loại tài liệu

### 2. Thêm dependency — `pyproject.toml`

```toml
"psycopg[binary]>=3.1,<4",
"psycopg-pool>=3.1,<4",
```

PostgreSQL driver cần thiết để kết nối Neon.

### 3. Tích hợp LLM enrichment — `providers.py`

Thêm import:

```python
from agentic_rag.ingestion.metadata import (
    apply_extracted_metadata,
    extract_chunk_metadata,
)
```

Thêm helper method `_enrich_chunks_with_llm()`: sau khi chunk được ghi vào Neon + Qdrant với metadata `[P]`, helper này gọi LLM để trích xuất metadata `[L]` cho từng chunk, rồi cập nhật lại **cả Neon lẫn Qdrant** với metadata đầy đủ. Nếu không có LLM nào được cấu hình hoặc tất cả extraction đều thất bại, bước này tự động bỏ qua (no-op) — không có write thừa nào xảy ra.

Helper này được gọi ở cả ba entry point ingestion:
- `upload_document()` — PDF
- `upload_url()` — URL
- `upload_text()` — văn bản thô

---

## Cấu hình môi trường cần thiết

### Bật Neon + S3 + Qdrant (hybrid — mặc định cho branch này)

```dotenv
LOCAL_SOURCE_STORE=hybrid
LOCAL_SOURCE_POSTGRES_CONNECTION=postgresql+psycopg://<user>:<password>@<host>/<db>?sslmode=require
LOCAL_SOURCE_POSTGRES_TABLE_PREFIX=local_rag
```

> Connection string lấy từ Neon project của team leader (cùng project đã dùng cho eval data, khác table prefix).

### Tắt Neon, chỉ dùng S3 + Qdrant

```dotenv
LOCAL_SOURCE_STORE=s3
```

Qdrant luôn chạy độc lập và không bị ảnh hưởng bởi switch này. Teammate làm việc trên Qdrant approach dùng mode này.

### Bật LLM enrichment `[L]`

```dotenv
INGESTION_LLM_MODEL=<model>
INGESTION_LLM_API_KEY=<key>
```

Nếu không set, pipeline vẫn chạy bình thường — các trường `[L]` sẽ là `None`.

---

## Luồng dữ liệu khi upload một tài liệu

1. Tài liệu được parse → tạo ra danh sách chunks với metadata `[P]`
2. Dedup detection chạy — đánh dấu chunks trùng lặp nếu có
3. `_write_indexes()` ghi lần 1:
   - File gốc + markdown → S3
   - Document record + chunks (với `[P]`) → Neon
   - Dense vectors + payload (với `[P]`) → Qdrant
4. `_enrich_chunks_with_llm()` gọi LLM cho từng chunk:
   - Nếu LLM trả về kết quả → `apply_extracted_metadata()` ghi `[L]` vào chunk
   - Nếu ít nhất một chunk được làm giàu → ghi lần 2:
     - `_replace_document_chunks()` → cập nhật Neon với `[P]` + `[L]`
     - `_upsert_dense_embeddings_safely()` → cập nhật Qdrant payload với `[P]` + `[L]`
5. Kết quả trả về cho caller với đầy đủ metadata `[P]` + `[L]` + `[S]`

---

## Các file liên quan

| File | Thay đổi |
|------|---------|
| `src/agentic_rag/integrations/local_pdf/storage.py` | Thêm `HybridLocalSourceStore`, thêm indexes vào `_ensure_schema()` |
| `src/agentic_rag/integrations/local_pdf/providers.py` | Import extraction functions, thêm `_enrich_chunks_with_llm()` (cập nhật cả Neon lẫn Qdrant), gọi ở 3 upload methods |
| `pyproject.toml` | Thêm `psycopg[binary]` và `psycopg-pool` |
| `src/agentic_rag/ingestion/metadata/extract.py` | Code của teammate — không thay đổi, chỉ tích hợp vào pipeline |

---

## Ghi chú cho teammate làm Qdrant

Qdrant đã nhận đầy đủ metadata `[P]` + `[L]` trong payload sau khi LLM enrichment chạy. Các field hiện được index trong Qdrant (`QDRANT_INDEX_FIELDS` trong `schema.py`):

```
document_id, source_type, document_type, product_model, language, topic_tags
```

Nếu cần filter theo `entities` hoặc `keywords` trong vector search, cần thêm vào `QDRANT_INDEX_FIELDS`:

```python
"metadata.entities",
"metadata.keywords",
```
