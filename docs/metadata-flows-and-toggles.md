# Metadata: nhiệm vụ từng trường, các luồng sử dụng & công tắc ENV

> Tài liệu này gom (1) nhiệm vụ của từng trường metadata, (2) các luồng dùng metadata —
> **hard filter**, **soft boosting**, và các **retriever mở rộng mới code**, (3) **toàn bộ
> công tắc ENV** (cũ + mới thêm), và (4) **health-check**: luồng nào *thực sự* chạy ở config nào.
>
> Trạng thái nhánh tại thời điểm viết: các cờ `RETRIEVAL_BM25_AUGMENT_KEYWORDS`,
> `RETRIEVAL_QUESTION_INDEX_ENABLED`, `QUESTION_MIN_SCORE`, và việc sinh `quality_score`
> **chưa merge `develop`** (nằm trên các feature branch — xem cột "Trạng thái").

---

## 1. Nhiệm vụ từng trường metadata

Ký hiệu giai đoạn: `[P]` rule-based parser · `[L]` LLM Extract · `[S]` storage.

| Trường | Giai đoạn | Nhiệm vụ | Sinh bởi | Được TIÊU THỤ ở | Trạng thái |
|---|---|---|---|---|---|
| `entities` | `[L]` | nguồn để tính `entities_canonical` | LLM Extract | (gián tiếp) hard filter | ✅ dùng |
| `entities_canonical` | backfill | **hard pre-filter** (Qdrant MatchAny) | `scripts/backfill_entity_canonical.py` | retrieval (Qdrant) | ✅ dùng (có điều kiện) |
| `document_type` | `[L]` | **soft boosting** (ma trận query-aware) | LLM Extract | `boosting.py` | ✅ dùng (agent path) |
| `fetched_at` | `[S]` | boosting recency decay | storage | `boosting.py` | ✅ dùng (agent path) |
| `deduplication` | dedup | boosting penalty + loại layer trùng | dedup stage | `boosting.py` + filter `exclude_dedup_layers` | ✅ dùng |
| `keywords` | `[L]` | (mới) bơm vào BM25 sparse | LLM Extract | BM25 augmentation | ⚙️ off mặc định, chưa merge |
| `questions` | `[L]` | (mới) retriever câu hỏi↔câu hỏi | LLM Extract | question-index | ⚙️ off mặc định, chưa merge |
| `quality_score` | `[L]` | (mới) tín hiệu chất lượng | LLM Extract | **chưa có consumer** | ⚠️ sinh+lưu, chưa dùng |
| `summary` | `[L]` | tóm tắt (chỉ hợp answer-side) | LLM Extract | **chưa có consumer** | ⚠️ sinh+lưu, chưa dùng |
| `topic_tags` | `[L]` | (khai báo) tag chủ đề filter | — (không stage nào sinh) | **không** | ❌ field chết |
| `language` | `[L]` | lọc theo ngôn ngữ | LLM Extract | trong `QDRANT_INDEX_FIELDS`, **không có code filter** | ⚠️ index-trên-giấy |
| `source_type`, `product_model` | `[P]` | lọc nguồn / model | parser | trong `QDRANT_INDEX_FIELDS`, chưa có code filter | ⚠️ index-trên-giấy |
| `page_type` (classify_page) | `[P]` | điều tiết dọn markdown + lưu | rule-based URL | cleanup ingest; **không** ở retrieval | ⚠️ lưu, không filter |
| `infer_page_type/price_type/vehicle_model` | runtime | nhãn vào evidence prompt | `evidence_metadata.py` lúc trả lời | prompt LLM | ✅ luôn chạy |

---

## 2. Công tắc ENV (đầy đủ — cũ + mới)

| ENV | Default | Tác dụng | Luồng | Trạng thái |
|---|---|---|---|---|
| `METADATA_BOOSTING_ENABLED` | `true` | bật/tắt **soft boosting** (document_type × recency × dedup) | agent path | develop |
| `ENTITY_PREFILTER_ENABLED` | `true` | bật/tắt **hard filter** entity | retrieval (Qdrant) | develop |
| `ENTITY_PREFILTER_LLM` | `false` | LLM map query→canonical khi từ điển không bắt được | preprocess | develop |
| `VECTOR_STORE_PROVIDER` | `turbovec` | **phải = `qdrant`** thì hard filter mới áp | retrieval | develop |
| `AGENT_MODE` | `false` | **phải = `true`** thì boosting mới chạy | pipeline | develop |
| `FUSION_METHOD` | `rrf` | question-index chỉ fuse khi `=rrf` | fusion | develop |
| `RETRIEVAL_BM25_AUGMENT_KEYWORDS` | `false` | (MỚI) nối `keywords` vào text BM25 index | sparse | ⚙️ `feature/bm25-metadata-augmentation` |
| `RETRIEVAL_QUESTION_INDEX_ENABLED` | `false` | (MỚI) bật retriever câu hỏi (đường thứ 3 RRF) | retrieval (Store) | ⚙️ `feature/question-index-retrieval` |
| `QUESTION_MIN_SCORE` | `0.5` | (MỚI) sàn cosine giữ question match; rỗng = tắt lọc | question-index | ⚙️ `feature/question-index-retrieval` |

> Ngưỡng retrieval chung (không riêng metadata, để tham khảo): `BM25_MIN_SCORE`,
> `DENSE_MIN_SCORE`, `BM25_MIN_NORM_SCORE`, `DENSE_MIN_NORM_SCORE`, `FUSION_MIN_SCORE`,
> `RERANK_MIN_SCORE`, `MIN_EVIDENCE_COUNT` — đều default rỗng/0.

---

## 3. Chi tiết các luồng dùng metadata

### 3.1 HARD FILTER — entity pre-filter (`entities_canonical`)
- **Kiến trúc 3 phase:** (1) offline LLM dựng `entity_map.json` (1036 surface forms) +
  `entity_filter_allowlist.json` (33 canonical coverage-gated) → (2) runtime pure-lookup
  (`entity_normalizer.py`, KHÔNG LLM) → (3) **backfill** (`scripts/backfill_entity_canonical.py`)
  tính `normalize_filterable(entities)` → ghi `entities_canonical` vào Neon + Qdrant payload
  (`set_payload`, không re-embed) + tạo keyword index.
- **Chỉ loại filterable:** `car_model / ebike_model / location` (bỏ brand/generic).
- **Query:** `detect_in_query()` (word-boundary, ≥3 ký tự, allowlist) → `filter_entities` →
  Qdrant `MatchAny(any=[canonicals])` trên `metadata.entities_canonical` (union/OR).
- **Fallback:** filter ra 0 kết quả → tìm lại KHÔNG filter (không bao giờ làm trống đáp án).
- **Điều kiện active:** `ENTITY_PREFILTER_ENABLED=true` **AND** `VECTOR_STORE_PROVIDER=qdrant`
  **AND** đã chạy backfill. Thiếu bất kỳ điều nào → không lọc.

### 3.2 SOFT BOOSTING (`boosting.py`, PR90)
- Áp **sau fusion, trước rerank** (per-query). 3 hệ số nhân, clamp `[0.7, 1.4]`:
  `document_type` (ma trận query-aware) × `fetched_at` (recency half-life 90 ngày) ×
  `deduplication` (duplicate_candidate ×0.8).
- **Điều kiện active:** `METADATA_BOOSTING_ENABLED=true` **AND** `AGENT_MODE=true`
  (gọi tại `agent/nodes.py:_retrieve_query` — **không** chạy ở linear path).
- Chunk `document_type=None/unknown` chỉ ăn hệ số default → boosting yếu.

### 3.3 BM25 keyword augmentation (MỚI — `feature/bm25-metadata-augmentation`)
- Nối `keywords` vào **CUỐI** text mà sparse index bao phủ (BM25Okapi in-memory + Qdrant
  sparse vector). **Không** đụng dense embedding, **không** đụng text gốc trong kho.
- **Điều kiện active:** `RETRIEVAL_BM25_AUGMENT_KEYWORDS=true`. BM25 in-memory nhận ngay;
  Qdrant sparse cần re-upsert (sparse-only) để có hiệu lực.

### 3.4 Question-index retriever (MỚI — `feature/question-index-retrieval`)
- "Dense search thứ 2": index là **các câu hỏi** của chunk; query↔question matching →
  trả **chunk cha** → fuse làm **đường thứ 3** trong RRF. In-memory, không re-embed kho chính.
- Dedup nhiều câu hỏi→1 chunk (max score); cắt `QUESTION_MIN_SCORE`.
- **Điều kiện active:** `RETRIEVAL_QUESTION_INDEX_ENABLED=true` **AND** `FUSION_METHOD=rrf`
  **AND** linear path (provider `_fuse_results`). **Chưa** wire cho nhánh Qdrant lẫn agent.

### 3.5 quality_score (MỚI — `feature/metadata-topic-quality`)
- LLM Extract sinh 0.0–1.0 + clamp. `apply_extracted_metadata` ghi vào chunk.
- **Chưa có consumer** — mới chỉ sinh + lưu.

---

## 4. ⚠️ HEALTH-CHECK — luồng nào THỰC SỰ chạy?

Điểm cốt lõi: **các luồng metadata nằm rải ở những code path khác nhau**, và config
**MẶC ĐỊNH** (`AGENT_MODE=false`, `VECTOR_STORE_PROVIDER=turbovec`, các cờ mới off) khiến
phần lớn **không active**.

| Luồng | Cờ riêng | Bị chặn bởi | Active ở config MẶC ĐỊNH? |
|---|---|---|---|
| Entity hard-filter | `ENTITY_PREFILTER_ENABLED=true` | cần `qdrant` + đã backfill | ❌ (default `turbovec`) |
| Soft boosting | `METADATA_BOOSTING_ENABLED=true` | cần `AGENT_MODE=true` | ❌ (default `false`) |
| BM25 keyword aug | off | toggle off + chưa merge | ❌ |
| Question-index | off | toggle off + chưa merge | ❌ |
| quality_score | (sinh nếu có LLM ingest) | không consumer | ❌ (chưa ai đọc) |
| Answer-side page/price/model | luôn | — | ✅ (vào evidence prompt) |

**Kết luận:**
1. Ở **config mặc định**, gần như **không có feature metadata nào tác động retrieval** —
   chỉ nhãn answer-side (`evidence_metadata.py`) chạy mọi lúc.
2. Hai feature "đã có sẵn trên develop" (entity-filter, boosting) **bật cờ riêng nhưng vẫn
   bị chặn**: entity cần `qdrant`, boosting cần `AGENT_MODE=true`. ⇒ Muốn chúng chạy phải
   set đúng **cả 2 lớp** (cờ riêng *và* điều kiện hệ).
3. Triển khai thực tế của nhóm (nếu chạy **Qdrant + AGENT_MODE=true + đã backfill**) thì
   entity-filter và boosting mới thực sự hoạt động — lúc đó hạ tầng đã sẵn sàng
   (map 1036 forms, allowlist 33 canonical).

### Lỗi tương tác cần biết (chưa active nhưng sẽ cắn khi bật)
- **Question-index ↔ agent path:** agent (`_search_via_provider`) tách kết quả fused theo
  `retriever == "bm25"/"dense"` rồi fuse lại. Kết quả tag `retriever="question"` **rơi rụng**
  ở bước tách này. ⇒ Question-index hiện chỉ đúng ở **linear path**; muốn dùng ở agent path
  phải sửa bước tách (đưa "question" vào danh sách giữ lại). Hiện vô hại vì cả 2 cờ đều off.

---

## 5. Khuyến nghị
- **Trước khi đo eval:** chốt rõ deployment chạy `turbovec` hay `qdrant`, và `AGENT_MODE`.
  Nếu mặc định → boosting + entity-filter đang **không chạy** dù cờ bật.
- **Dọn rác schema:** `topic_tags` (field chết) còn trong `QDRANT_INDEX_FIELDS` trong khi code
  index thực tế là `entities_canonical` (không nằm trong list đó) → nên đồng bộ lại.
- **Nối consumer:** `quality_score`/`summary`/`language` mới chỉ "sinh+lưu" — cần wire vào
  boosting / answer-prompt / filter nếu muốn có tác dụng.
