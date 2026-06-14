# Metadata Extraction & Enrichment cho RAG Pipeline — Nghiên cứu & Đề xuất

> Bối cảnh: chatbot **GreenSM** (xe điện / taxi điện), tài liệu **động** (loại xe, chính sách, phụ kiện, sạc, tài xế…), taxonomy **chưa biết trước**. Mục tiêu pipeline metadata: **portable** (đổi domain vẫn dùng, không hardcode taxonomy), **không thuần rule-based/heuristic**, và **hybrid cost** (nặng offline lúc ingest / nhẹ online cho doc mới + query).
>
> Liên quan: issue #166 (Cải thiện Retrieval và Metadata-aware Search) + #169 (Metadata Extraction & Enrichment). Phần retrieval (SPLADE/ColBERT/N-way/listwise) đã làm ở PR #81.
>
> **Quy ước trong tài liệu:** ✅ = có bằng chứng (nguồn verified) · 🟡 = đề xuất/kiến trúc chưa có bằng chứng độc lập · ⚠️ = caveat/rủi ro.

---

## 0. TL;DR (tóm tắt điều hành)

1. **Có 2 hướng bổ trợ nhau, đừng nhầm lẫn:**
   - **(A) Sinh metadata semantic per-chunk bằng LLM, taxonomy CỐ ĐỊNH qua prompt** (content/technical/semantic). ✅ Có bằng chứng nâng retrieval (NDCG@10 +13.7%) nhưng **chỉ trên 1 domain English, silver ground-truth**.
   - **(B) TỰ KHÁM PHÁ taxonomy bằng cluster + LLM-đặt-tên-cụm** (trọng tâm câu hỏi). ✅ Chứng minh được **rẻ** (chi phí `O(số cụm)` thay vì `O(số chunk)`), nhưng **CHƯA có benchmark chứng minh nâng retrieval end-to-end**.
2. **Khuyến nghị cho GreenSM:** kết hợp — dùng **(B)** sinh trường `category` động (portable, rẻ), dùng **(A)** ở mức tối thiểu (summary/questions-answered) nếu eval cho thấy đáng. Tất cả **offline**; online chỉ **assign chunk mới + boost/filter lúc retrieve**.
3. ⚠️ **Mọi con số gain đều từ domain khác.** Bắt buộc tự dựng **eval set tiếng Việt GreenSM** và A/B test trước khi tin.
4. **Chunk-to vs tin-nhắn-ngắn:** category là thuộc tính **của chunk** (offline) — **không ép query vào centroid cụm**; online chỉ boost/filter chunk đã retrieve, hoặc route query qua **nhãn** (không qua centroid).

---

## 1. Phân loại metadata trong RAG (câu hỏi 1)

| Nhóm | Ví dụ field | Nguồn gốc | Đã có ở repo? |
|---|---|---|---|
| **Structural** | `page`, `section`, `section_path`, `chunk_index` | Deterministic (parser) | ✅ Có |
| **Source** | `source`, `source_type`, `url`, `domain`, `author`, `title` | Deterministic (ingest) | ✅ Có |
| **Temporal** | `published_at`, `fetched_at`, `created/updated_date` | Deterministic NẾU có; PDF thường **thiếu** | 🟡 Chỉ URL có; PDF không |
| **Semantic / topic** | `category`, `topic_tag`, `document_type` | **Cần suy luận** (cluster / LLM / classifier) | ❌ Chưa |
| **Auto-generated** | `summary`, `keywords`, `questions_answered`, `language` | **Cần suy luận** (LLM / model) | 🟡 `language`, `page_type` (URL) có |

→ **Hai nhóm cuối là phần phải làm.** Structural + source gần như free và đã có sẵn. Đây cũng là ranh giới: #169 lo "sinh ra" 2 nhóm cuối; #166 lo "dùng" chúng trong retrieval.

---

## 2. Các phương pháp trích xuất — so sánh 3 trục (câu hỏi 2)

| Phương pháp | Chất lượng | Chi phí | Portable (đổi domain) | Ghi chú |
|---|---|---|---|---|
| **Rule/structural** (filename, header, regex; Unstructured) | Tốt cho structural; **kém/không có** cho semantic | Rất rẻ | Cao cho structural | ✅ Unstructured **không** sinh topic/category — chỉ structural (filename, page, coordinates, element-type) |
| **LLM-based per-chunk** (LlamaIndex extractors) | Cao | **Đắt — `O(số chunk)`** | Cao (prompt, không hardcode) | ✅ Có sẵn extractor; ⚠️ đắt nếu chạy mọi chunk |
| **Auto-discovery cluster + LLM-label-cụm** | Trung bình–cao | **Rẻ — `O(số cụm)`** | **Rất cao** (taxonomy tự mọc) | ✅ Cơ chế rẻ đã chứng minh; 🟡 gain retrieval chưa benchmark |
| **Hybrid** (cluster cho category + LLM cho summary chọn lọc) | Cao | Trung bình | Cao | Khuyến nghị |

### 2.1 LlamaIndex metadata extractors ✅
Có sẵn, **domain-agnostic, node-level**, không hardcode taxonomy ([docs](https://docs.llamaindex.ai/en/stable/module_guides/indexing/metadata_extraction/)):
- `SummaryExtractor` → `section_summary` (+ prev/next của chunk lân cận)
- `QuestionsAnsweredExtractor` → `questions_this_excerpt_can_answer`
- `TitleExtractor` → `document_title`
- `KeywordExtractor` → `excerpt_keywords`
- Chain trong `IngestionPipeline(transformations=[...])`, chạy tuần tự, có cache theo node+transformation ([cookbook](https://docs.llamaindex.ai/en/stable/examples/cookbooks/oreilly_course_cookbooks/Module-4/Metadata_Extraction/)).

> ⚠️ **CAVEAT phân loại:** `EntityExtractor` **KHÔNG phải LLM** — nó chạy NER local **SpanMarker** (`span-marker-mbert-base-multinerd`). Khi ước tính token-cost offline chỉ tính 4 extractor LLM ở trên. Gắn nhãn "LLM-based" cho cả 5 là sai.

Rationale ("chunk dreaming"): mỗi chunk được làm giàu context cấp document để nâng cả retrieval lẫn synthesis — đây là **cơ chế nêu trong docs, không phải kết quả benchmark**.

---

## 3. ⭐ TRỌNG TÂM: Tự khám phá taxonomy chưa biết trước (câu hỏi 3)

### 3.1 Pattern chuẩn: **discover → label → assign**

```
[offline]  embed chunks ─▶ (UMAP) ─▶ cluster (HDBSCAN) ─▶ cụm = category ứng viên
                                                   │
                                                   ├─▶ LLM đặt tên CỤM (1 call/cụm, ~4 doc đại diện)
                                                   └─▶ consolidate/merge cụm trùng ─▶ registry category
[online]   doc/chunk mới ─▶ gán vào cụm gần nhất (centroid) hoặc zero-shot theo nhãn  (KHÔNG gọi LLM/chunk)
```

### 3.2 Vì sao rẻ — cơ chế cốt lõi ✅
- **BERTopic gọi LLM 1 lần / CỤM**, không phải 1 lần / document; chỉ truyền **vài keyword + ~4 document đại diện** ([docs](https://maartengr.github.io/BERTopic/getting_started/representation/llm.html)). → chi phí labeling là **`O(số cụm)`**, không phải `O(số chunk)`. (Các approach LLM end-to-end "require processing each document → prohibitive costs" — [arXiv 2509.19365](https://arxiv.org/html/2509.19365v1).)
- **Chọn document đại diện**: lấy doc có `c-TF-IDF` similarity cao nhất với biểu diễn c-TF-IDF chính của cụm; mặc định **top 4** (tunable `nr_docs`) + tập keyword → nhãn người-đọc-được.

### 3.3 HDBSCAN: không cần biết số category trước ✅
- HDBSCAN **density-based**, **không yêu cầu số topic trước**, tự xác định số cụm từ cấu trúc dữ liệu ([BERTrend, arXiv 2411.05930](https://arxiv.org/html/2411.05930v1)). Hợp đúng tình huống GreenSM taxonomy chưa biết.
- ⚠️ Thực tế: vẫn phải tune `min_cluster_size` / `min_samples`; HDBSCAN gán **~18–27% doc là outlier**; cần **UMAP** giảm chiều trước.

### 3.4 Khử cluster trùng / kiểm soát độ mịn (validate brainstorm của team) ✅
- **Vòng lặp agglomerative bằng LLM** ([arXiv 2509.19365](https://arxiv.org/html/2509.19365v1)): đưa **topic representation** (không phải raw doc) cho LLM → LLM chỉ ra **2 topic chồng lấn nhất** → merge → regenerate representation → lặp đến **số topic mục tiêu do user định**.
- → đúng pattern "discover → LLM merge/name", và **kiểm soát được granularity**. (Lưu ý: setting gốc là *reduction* trên tập topic có sẵn, không phải discovery from-scratch.)
- **Thứ tự khử nên dùng (đề xuất):** merge theo **centroid** (rẻ) → merge theo **nhãn đồng nghĩa** → 1 pass **LLM dọn taxonomy** (gom 40 nhãn → N category sạch) → giữ **registry category chuẩn** để các lần re-cluster sau **map centroid cụm mới → category cũ** (tránh taxonomy "nhảy múa").

---

## 4. Incremental / dynamic — tài liệu up động (câu hỏi 4)

| Cách | Khi dùng | Trạng thái |
|---|---|---|
| `.partial_fit()` (MiniBatchKMeans + IncrementalPCA thay HDBSCAN+UMAP) | Cập nhật theo mini-batch streaming | ✅ Có; ⚠️ maintainer cảnh báo "issues with stability" |
| `.merge_models()` | Gộp model train trên các batch | ✅ **Maintainer khuyên dùng cho production** ([#2119](https://github.com/MaartenGr/BERTopic/discussions/2119)) |
| **River DBSTREAM** wrapper | **Phát hiện CỤM MỚI** khi data mới đến (xe mới, chính sách mới) | ✅ Cơ chế; ⚠️ wrapper là **code ví dụ user-viết**, không ship sẵn |
| **BERTrend** (time slice + merge theo cosine) | Phát hiện **trend / weak signal**, phân loại topic noise/weak/strong | ✅ [arXiv 2411.05930](https://arxiv.org/html/2411.05930v1) |

⚠️ **Đánh đổi:** đổi sang MiniBatchKMeans/IncrementalPCA **mất** ưu điểm của HDBSCAN (auto số cụm, robust outlier).

**Khi nào re-cluster toàn bộ vs chỉ partial/merge?** — UIClust ([arXiv 2003.13225](https://arxiv.org/abs/2003.13225)): cập nhật centroid bằng running-average nếu `dist ≤ lambda`, ngược lại tăng outlier counter; **phân biệt temporary drift vs sustained (concept) drift**. 🟡 *Ngưỡng cụ thể (vd % chunk thành outlier, độ dịch centroid) chưa có con số chuẩn — cần tự định lượng.*

---

## 5. Kỹ thuật giảm chi phí (câu hỏi 5)

- ✅ **Chỉ gọi LLM trên đại diện cụm** + **tái dùng embedding** (đã có BGE-M3) — đây là 2 đòn bẩy chính.
- ✅ **Batching** generation offline (paper dùng GPT-4o batched, structured output).
- 🟡 **Zero-shot NLI classification**, **model nhỏ/distilled**, **caching** — hợp lý về nguyên lý nhưng **chưa có nguồn verified trong nghiên cứu này** cho bối cảnh gán nhãn cụm / tiếng Việt. Coi là đề xuất.

---

## 6. Chunk-to vs tin-nhắn-ngắn — design note (gỡ hiểu lầm)

**Category là thuộc tính của CHUNK (gán offline trên chunk to → không dính bất đối xứng).** Vấn đề chỉ phát sinh nếu muốn dùng category lúc query. Hai cách:

- **A. Không route query vào cụm (khuyến nghị):** retrieve bình thường (BM25/dense/hybrid vốn đã giỏi match query-ngắn → chunk-dài), rồi **boost/filter chunk đã retrieve theo category của chúng**. Query không bao giờ cần map vào cụm.
- **B. Nếu cần route query → category:** **ĐỪNG so query với centroid chunk** (ngắn-vs-dài → nhiễu). Thay vào đó **so query với NHÃN category** (ngắn-vs-ngắn) / **zero-shot** / **ghép vào call requery LLM sẵn có** (pipeline đang chạy 1 call Decompose/Expand → đưa thêm danh sách nhãn để nó đoán luôn category, **0 chi phí online tăng thêm**).

🟡 **Soft / multi-label** cho chunk to dễ lẫn topic: lưu **top-k category kèm trọng số** thay vì 1 nhãn cứng.

---

## 7. Metadata-aware retrieval (câu hỏi 6)

- **Fuse metadata vào EMBEDDING** (không chỉ làm field filter) ✅ nâng retrieval: **prefix-fusion** (chèn metadata làm prefix trước khi encode) hoặc **TF-IDF weighted** (kết hợp tuyến tính embedding content + vector TF-IDF metadata, tối ưu ~**90:10**) — [arXiv 2512.05411](https://arxiv.org/abs/2512.05411), [2601.11863](https://arxiv.org/abs/2601.11863).
  - ⚠️ Nhưng fuse-vào-text **không enforce hard constraint** (lọc thời gian/logic) → ràng buộc cứng vẫn nên dùng **filtering**.
- **Filter (cứng) vs Boost (mềm):** 🟡 *nghiên cứu này không có hướng dẫn định lượng filter-vs-boost cho category tự-sinh.* Đề xuất của team: **boost/penalty làm chủ đạo** (recency, authority, conflict-penalty, dedup-skip), filter cứng chỉ khi user yêu cầu rõ (source/date).
- **Chỗ cắm có sẵn:** PR #81 đã có tầng **post-fusion re-score** + per-retriever threshold → category boost/penalty cắm vào đây tự nhiên.

---

## 8. Đánh giá / A/B test (câu hỏi 7)

- **Metric retrieval:** NDCG@k, MRR, Recall@k (so content-only vs +metadata; ablation từng thành phần metadata).
- **Chất lượng metadata:** human spot-check nhãn cụm; cluster coherence; % outlier; tỉ lệ doc gán đúng category.
- ⚠️ **Bài học từ paper:** dùng **silver ground-truth** (cross-encoder) thì *chỉ so sánh tương đối mới valid, con số tuyệt đối phải thận trọng*. → GreenSM nên có **một phần human-label** để chuẩn hoá.
- 🟡 Thiết kế A/B chi tiết là đề xuất (chưa có nguồn verified); tối thiểu: cùng query set, cùng retriever (PR #81), bật/tắt metadata boost, đo NDCG/MRR + tỉ lệ trả lời đúng.

---

## 9. ⭐ Kiến trúc đề xuất — Hybrid offline-heavy / online-cheap (câu hỏi 8)

### 9.1 Sơ đồ

```
OFFLINE (lúc ingest / batch định kỳ) — chấp nhận nặng
  chunks ──embed (BGE-M3, tái dùng)──┐
                                     ├─▶ UMAP ─▶ HDBSCAN ─▶ cụm
                                     │            │
                                     │            ├─▶ LLM đặt tên cụm (1 call/cụm, ~4 doc đại diện)
                                     │            └─▶ consolidate (centroid→nhãn→LLM dọn) ─▶ REGISTRY category
                                     │
                                     └─▶ (tùy chọn) LlamaIndex SummaryExtractor / QuestionsAnswered (chọn lọc)
  ──▶ ghi vào chunk.metadata: category(+top-k weight), summary?, questions?, + structural/source sẵn có

ONLINE (doc mới + query) — phải rẻ
  doc mới   ─▶ embed ─▶ gán vào cụm gần nhất (centroid) / zero-shot theo nhãn registry  (KHÔNG LLM/chunk)
                └─▶ nếu nhiều chunk "không thuộc cụm nào" vượt ngưỡng drift ─▶ xếp hàng re-cluster offline
  query     ─▶ retrieve (PR #81 hybrid) ─▶ post-fusion: boost/filter theo category + recency + authority,
                                            dedup-skip, conflict-penalty ─▶ rerank
              (tùy chọn) requery LLM đoán luôn category của query để pre-filter — 0 chi phí thêm
```

### 9.2 Tool/model đề xuất
| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Embedding | **BGE-M3** (đã có) | Tái dùng, đa ngữ, đã dùng cho SPLADE/ColBERT |
| Giảm chiều | UMAP (offline) / IncrementalPCA (online) | Theo BERTopic |
| Cluster | HDBSCAN (offline) / MiniBatchKMeans (online) / River DBSTREAM (topic mới) | Auto số cụm offline; online-capable khi cần |
| Đặt tên cụm | LLM (GPT-4o hoặc model VI rẻ hơn — 🟡 cần thử) | 1 call/cụm |
| Gán doc mới | centroid-nearest / zero-shot NLI (🟡) | Không LLM/chunk |
| Khung extractor | BERTopic (+ LlamaIndex cho summary/questions tùy chọn) | Có sẵn, ráp nhanh |

### 9.3 Tham số cần tune
`min_cluster_size`, `min_samples` (HDBSCAN) · `n_neighbors`, `n_components` (UMAP) · `nr_docs` (số doc đại diện/cụm) · số topic mục tiêu khi merge · ngưỡng merge centroid · **ngưỡng drift để re-cluster** (% outlier, độ dịch centroid) · tỉ lệ fuse metadata↔content (~90:10) · trọng số boost (recency/authority/category) · ngưỡng zero-shot assign.

---

## 10. ⚠️ Khoảng trống, rủi ro & "đừng tin nhầm"

1. **Bằng chứng gain retrieval rất hẹp:** con số +13.7% NDCG (0.615→0.699) chỉ từ **1 paper, 1 domain (AWS S3 docs, English), silver ground-truth**. **Không có** benchmark tiếng Việt / xe điện. → **phải tự A/B test**.
2. **Hai hướng khác nhau:** paper 2512.05411 dùng **taxonomy CỐ ĐỊNH qua prompt** (đã chứng minh gain) — **KHÔNG** phải auto-discovery. Hướng auto-discovery (BERTopic/HDBSCAN) **đã chứng minh RẺ nhưng CHƯA chứng minh gain retrieval end-to-end**.
3. **Claim bị BÁC (0-3 / 1-2):** "metadata enrichment *consistently* outperforms, NDCG 0.813 là tốt nhất" → **over-generalize, đã bị bác**. "Các extractor LlamaIndex chắc chắn 1 LLM-call/node" → **không xác nhận đầy đủ**. "River là project online-clustering open-source đầu tiên" → **sai**.
4. **Online incremental có rủi ro ổn định** (`.partial_fit` kém ổn định → ưu tiên `.merge_models`).
5. **Chưa có nguồn verified** cho: LangChain/Haystack extractor cụ thể; so sánh định lượng LDA/NMF/Top2Vec; zero-shot NLI gán nhãn cụm; chi tiết filter-vs-boost; model VI rẻ thay GPT-4o cho labeling. → các mục này là **đề xuất kiến trúc**, chưa có bằng chứng độc lập.

---

## 11. Đề xuất việc tiếp theo (cho #166 + #169)

1. **Deliverable nghiên cứu** (issue Research): tài liệu này + bảng tham số + thiết kế A/B.
2. **Prototype nhỏ, đo trước:** dựng pipeline BERTopic trên corpus GreenSM hiện có → xem taxonomy tự mọc có hợp lý không (human spot-check), đo % outlier.
3. **Dựng eval set tiếng Việt GreenSM** (có một phần human-label) — *điều kiện tiên quyết* để mọi con số gain có nghĩa.
4. **Nối category vào retrieval** qua tầng post-fusion của PR #81 (boost trước, filter sau).
5. **Phần Metadata-aware (dedup-skip + conflict-penalty + recency/authority)** — đã có dữ liệu sẵn (`deduplication.*`, `conflict_store`), kéo vào in-memory + boost; xem `docs/retrieval-rerank-architecture.md`.

---

## Nguồn tham khảo (đã qua verify đối kháng)

**Primary:**
- LlamaIndex metadata extraction — https://docs.llamaindex.ai/en/stable/module_guides/indexing/metadata_extraction/
- LlamaIndex IngestionPipeline cookbook — https://docs.llamaindex.ai/en/stable/examples/cookbooks/oreilly_course_cookbooks/Module-4/Metadata_Extraction/
- Metadata-for-RAG (taxonomy 3 lớp, prefix-fusion, NDCG) — arXiv 2512.05411 · https://arxiv.org/abs/2512.05411
- "Utilizing Metadata for Better RAG" — arXiv 2601.11863
- BERTopic LLM representation (1 call/cụm, c-TF-IDF repr docs) — https://maartengr.github.io/BERTopic/getting_started/representation/llm.html
- BERTopic online/incremental (partial_fit, River) — https://maartengr.github.io/BERTopic/getting_started/online/online.html
- LLM agglomerative topic merge — arXiv 2509.19365 · https://arxiv.org/html/2509.19365v1
- BERTrend (HDBSCAN, time-slice merge, weak signals) — arXiv 2411.05930 · https://arxiv.org/html/2411.05930v1
- Incremental clustering + concept drift (UIClust) — arXiv 2003.13225 · https://arxiv.org/abs/2003.13225
- Unstructured chunking (structural-only metadata) — https://docs.unstructured.io/open-source/core-functionality/chunking
- BERTopic maintainer note (merge_models ổn định hơn) — https://github.com/MaartenGr/BERTopic/discussions/2119

**Thống kê research:** 5 góc · 23 nguồn fetch · 107 claim trích · 25 verify (3-vote đối kháng) · 22 confirmed / 3 killed · 18 sau tổng hợp.

---
*Tài liệu nghiên cứu cho issue #166 / #169. Các phần đánh ✅ có nguồn; 🟡 là đề xuất chưa có bằng chứng độc lập; ⚠️ là caveat. Mọi con số định lượng đến từ domain khác — cần A/B test trên GreenSM trước khi kết luận.*
