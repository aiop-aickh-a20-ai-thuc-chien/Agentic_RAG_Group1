# GraphRAG cho dự án Agentic RAG — Nghiên cứu & Kế hoạch tích hợp

> **Phạm vi:** Nghiên cứu đầy đủ về (1) xây dựng Knowledge Graph từ tài liệu đã ingest,
> (2) Graph-based Retrieval, (3) tích hợp vào app với mode chọn được (traditional vs
> graph-enhanced). Ưu tiên hướng tiếp cận của big tech + nghiên cứu học thuật thường dùng,
> và **đánh giá độ phù hợp cụ thể** với stack hiện tại: Qdrant hybrid + Self-RAG/LangGraph +
> PDF tiếng Việt (miền xe điện VinFast).
>
> Phương pháp: tổng hợp từ deep-research web (23 nguồn → 113 claim → 24 claim đã verify
> 3-vote) **+** phân tích trực tiếp source code dự án. Nguồn trích dẫn ở cuối ([Tài liệu tham khảo](#10-tài-liệu-tham-khảo)).
> Ngày: 2026-06-21.

---

## 0. TL;DR — Khuyến nghị chính

1. **Dự án bạn đã có sẵn ~70% nền tảng cho GraphRAG.** Bạn đã trích xuất **entity** (762
   canonical, có type: `car_model`/`ebike_model`/`location`/`brand`/...), đã canonical-hoá
   (`entity_map.json`), đã lưu `metadata.entities_canonical` per-chunk trong Qdrant và **đã
   index keyword**, và `_entity_prefilter_for()` đã làm **lọc 1-hop entity→chunk**. Cái còn
   thiếu để thành KG đúng nghĩa là **EDGES (quan hệ giữa entity)** + cơ chế **traversal**.

2. **Cách big tech & học thuật xây KG = LLM-based entity/relation extraction** (LangChain
   `LLMGraphTransformer`, LlamaIndex `PropertyGraphIndex`, Microsoft GraphRAG, LightRAG) —
   **không** phải spaCy/NER. Nhưng spaCy/dependency-parser vẫn đạt **~94%** chất lượng của
   LLM với chi phí rẻ hơn nhiều → là đường "giảm chi phí" đáng pilot cho tiếng Việt.

3. **Retrieval production = HYBRID** (vector/keyword + graph traversal), chia **local
   (lân cận entity)** vs **global (tóm tắt community)**. Graph retrieval thắng RAG thường
   trên **multi-hop QA** (HippoRAG +tới 20% recall, và **rẻ hơn 10–30×, nhanh hơn 6–13×** so
   với vòng lặp agentic ở **query time**) — nhưng **chi phí lớn nằm ở khâu extraction offline**.

4. **Lộ trình phù hợp nhất với bạn (KHÔNG bê nguyên Microsoft GraphRAG):**
   - **Phase 0 — Co-occurrence graph (gần như miễn phí):** dựng đồ thị entity↔entity từ
     `entities_canonical` sẵn có (đồng xuất hiện trong cùng chunk). 0 đồng LLM, vài trăm dòng.
   - **Phase 1 — LLM relation extraction:** mở rộng stage `[L]` ([extract.py](../src/agentic_rag/ingestion/metadata/extract.py))
     để xuất thêm **triple (subject, predicate, object)**, **tái dùng `entity_map.json`** để
     canonical-hoá (đây chính là lợi thế giải quyết bài toán dedup tiếng Việt mà LightRAG
     exact-key dedup thất bại).
   - **Phase 2 — Graph-enhanced retrieval mode + toggle:** mở rộng `entity_filter` qua hàng
     xóm trong graph + fetch chunk liên-thông, **fuse RRF** với hybrid hiện có; thêm 1 switch
     vào [config/page.tsx](../frontend/app/config/page.tsx) y khuôn mẫu hiện tại.
   - **Phase 3 (tùy chọn) — Global/community** (Leiden + community summaries) cho câu hỏi
     tổng hợp toàn corpus, hoặc **HippoRAG PPR** để thay vòng lặp `transform_query` đắt đỏ.

5. **Tái dùng Qdrant cho graph embeddings: ĐƯỢC** (LlamaIndex cho truyền `vector_store=Qdrant`)
   — nhưng **bản thân cấu trúc đồ thị vẫn cần nơi lưu riêng** (NetworkX/Kuzu/Neo4j/bảng Neon).
   Qdrant **không** lưu/duyệt graph được. Với quy mô của bạn, **không cần Neo4j ngay** — bắt
   đầu bằng NetworkX in-memory hoặc bảng Postgres/Neon đã có.

---

## 1. Bối cảnh dự án hiện tại (điểm xuất phát)

| Thành phần | Hiện trạng | Liên quan GraphRAG |
|---|---|---|
| **Vector store** | Qdrant hybrid: named vectors `dense` + `sparse`, RRF fusion (`_query_qdrant_points` dùng `Prefetch` + `FusionQuery(RRF)`) | Tái dùng làm "vector path" trong hybrid graph+vector |
| **Entity (NODES)** | `entity_map.json`: 762 canonical, có `type`; `entities_canonical` per-chunk; **đã index keyword** trong Qdrant | ✅ **Nodes đã có** — chỉ thiếu edges |
| **Entity detect** | `detect_in_query()`, `_entity_prefilter_for()` → lọc `MatchAny` tại chokepoint Qdrant | ✅ Đây là **local retrieval 1-hop sơ khai** |
| **Chunk metadata `[L]`** | LLM xuất `summary/keywords/questions/entities/document_type/quality_score` ([extract.py](../src/agentic_rag/ingestion/metadata/extract.py)) | 🔧 Điểm cắm rẻ nhất để thêm **relation extraction** |
| **Agent** | Self-RAG/LangGraph: preprocess→clarify→retrieve(song song)→rerank(per-query-group)→generate→check→transform_query(loop) | 🔧 `transform_query` loop có thể thay bằng graph traversal (HippoRAG) |
| **Injection point** | `SourceEvidenceProvider.retrieve()` (agent gọi), `qdrant_hybrid_search()` | 🔧 Nơi cắm "graph-enhanced mode" sạch nhất |
| **Mode toggle hạ tầng** | `RetrievalConfig` + `GET/POST /config/retrieval` (ghi ENV live + lưu `.env`) + `TOGGLES` ở [config/page.tsx](../frontend/app/config/page.tsx) | ✅ **Task 3 gần như miễn phí** — thêm 1 field + 1 switch |
| **Fusion sẵn có** | `rrf_fusion`, `rrf_fusion_nway` (đã dùng cho question-index như "đường thứ 3") | ✅ Tái dùng để fuse graph path |

> **Kết luận mục 1:** Bạn không bắt đầu từ số 0. Bạn đang ở vị trí lý tưởng để thêm GraphRAG
> *tăng dần* mà không phá kiến trúc — vì nodes, canonicalization, hybrid fusion, và hạ tầng
> toggle đều đã có.

---

## 2. Phần 1 — Knowledge Graph Construction

### 2.1 KG gồm gì
- **Nodes (entity):** sản phẩm/model, tổ chức, địa điểm, chính sách, linh kiện... → **bạn đã có**.
- **Edges (relation):** quan hệ có hướng + nhãn giữa node, ví dụ
  `VF 8 —[sử dụng]→ pin LFP`, `Klara S —[sản xuất bởi]→ VinFast`,
  `bộ sạc 7,4kW —[tương thích]→ VF 5`, `chính sách thuê pin —[áp dụng cho]→ ô tô điện`.
- (Tùy chọn) **Claims/attributes:** thuộc tính + mệnh đề (Microsoft GraphRAG trích cả "factual claims").
- (Tùy chọn) **Communities:** cụm node liên kết chặt (phát hiện bằng Leiden) + **summary** mỗi cụm.

### 2.2 Các kỹ thuật trích xuất edges — bảng so sánh

| Hướng | Công cụ tiêu biểu | Chất lượng | Chi phí | Tiếng Việt | Ghi chú |
|---|---|---|---|---|---|
| **LLM structured extraction** *(dominant)* | LangChain `LLMGraphTransformer` (function-calling), LlamaIndex `SchemaLLMPathExtractor`/`SimpleLLMPathExtractor`, Microsoft GraphRAG, LightRAG | ⭐⭐⭐⭐ cao nhất | 💰💰💰 token-heavy (mỗi chunk 1 call) | ✅ tốt nếu LLM đa ngữ (cùng LLM bạn đang dùng cho `[L]`) | **Khớp nhất** với pipeline `[L]` hiện tại |
| **spaCy / dependency parser** | spaCy + relationship rules | ⭐⭐⭐ (~**94%** của LLM) | 💰 rẻ, nhanh, offline | ⚠️ cần model tiếng Việt (`vi_core_news`, underthesea) | Đường giảm chi phí; nên pilot |
| **Zero-shot NER** | **GLiNER** (`urchade/GLiNER`) | ⭐⭐⭐ (chỉ entity, không relation) | 💰 nhẹ, chạy CPU | ⚠️ đa ngữ một phần | Bổ sung/thay NER; **không** cho relation |
| **Relation extraction model** | **REBEL** (seq2seq triple) | ⭐⭐⭐ | 💰💰 trung bình | ❌ chủ yếu tiếng Anh | Hợp với LlamaIndex; yếu cho tiếng Việt |
| **Open IE** | Stanford OpenIE | ⭐⭐ ồn, generic | 💰 rẻ | ❌ | Triple thô, cần lọc mạnh |
| **Co-occurrence (thống kê)** | tự code từ `entities_canonical` | ⭐⭐ (không có nhãn quan hệ, chỉ "liên quan") | **0 đồng** | ✅ ngôn ngữ-độc lập | **MVP rẻ nhất — tái dùng metadata sẵn có** |

**Nhận định cho bạn:**
- **Big tech làm LLM-based**, nhưng họ cũng hỗ trợ spaCy (~94% chất lượng) như đường rẻ.
- **GLiNER/REBEL/OpenIE** chủ yếu mạnh tiếng Anh → rủi ro với tiếng Việt; **không** nên là
  lựa chọn đầu cho relation tiếng Việt.
- **Đường tối ưu chi phí/độ phù hợp cho bạn:** **co-occurrence trước (Phase 0)** → rồi
  **LLM relation extraction trong stage `[L]`** (Phase 1), vì:
  - Tái dùng đúng LLM + đúng prompt-infra `[L]` đang chạy.
  - **Tái dùng `entity_map.json` để canonical-hoá head/tail** → giải quyết bài toán dedup
    tiếng Việt (biến thể dấu/cách viết "VF8" vs "VF 8" vs "VinFast VF 8") mà **LightRAG
    exact-key dedup sẽ làm vỡ graph**.

### 2.3 Chi phí extraction (số liệu thực tế)
- Neo4j (Tomaz Bratanic, 2024): **~13k entity + ~16k relation từ 2.000 bài báo** mất
  **~35 (±5) phút và ~$30 với GPT-4o** [^neo4j-global]. Đây là **chi phí một lần, offline**,
  tỉ lệ với **tổng token corpus** — và là yếu tố chi phí chính khi áp lên corpus PDF tiếng Việt.
- GPT-4o nay đã rẻ hơn → $30 là **cận trên**. Với model rẻ/đa ngữ (vd Haiku-class) chi phí
  còn thấp hơn.
- ⚠️ Claim "global GraphRAG cần ~29.000 LLM call cho graph 13k node" đã bị **bác bỏ (0-3)** —
  **đừng** xem community summarization là đắt khủng khiếp ở quy mô nhỏ.

### 2.4 Xử lý tiếng Việt — tái dùng tài sản sẵn có
- **Canonicalization/coreference là rủi ro #1** cho KG tiếng Việt (biến thể dấu, viết tắt,
  "TP.HCM" vs "Thành phố Hồ Chí Minh"). Không nguồn nào trong tập verify đo trực tiếp chất
  lượng extraction tiếng Việt → **cần pilot thực nghiệm**.
- ✅ **Lợi thế của bạn:** `entity_map.json` + `entity_normalization_report.md` +
  `entity_map_groups.md` **đã là lớp canonical/merge**. Dùng nó làm **lớp dedup node** cho KG
  → tránh đúng cái bẫy LightRAG.

### 2.5 Visualize graph
| Công cụ | Khi nào dùng | Ghi chú |
|---|---|---|
| **pyvis** (`pyvis.network`) | Nhúng HTML tương tác, nhanh | Hợp xuất 1 file `.html` xem nhanh (giống `docs/slide-tuan.html` bạn đang có) |
| **NetworkX + matplotlib** | Ảnh tĩnh, debug | Đi kèm nếu Phase 0 dùng NetworkX |
| **Gephi** | Phân tích layout/community quy mô lớn, offline | Export GEXF/GraphML |
| **Neo4j Bloom / yFiles** | Nếu dùng Neo4j | Đẹp nhưng kéo theo Neo4j |
| **Frontend (react-force-graph / Cytoscape.js)** | Nhúng vào app Next.js của bạn | Hợp nếu muốn người dùng xem subgraph dùng để trả lời |

> Khuyến nghị: **pyvis** cho khâu nghiên cứu/hiểu cấu trúc; nếu muốn show trong app thì
> **react-force-graph** ở Next.js (render subgraph mà câu trả lời dựa vào → tăng tính giải thích).

---

## 3. Phần 2 — Graph-based Retrieval

### 3.1 Local retrieval (lân cận entity) — *building block trực tiếp dùng được*
Cơ chế (Neo4j/AWS): **phát hiện entity trong câu hỏi → duyệt graph lấy lân cận các node liên
quan** [^neo4j-acc][^aws]. Độ sâu duyệt (`traversal_depth`) là tham số cấu hình:
- LlamaIndex `KnowledgeGraphRAGRetriever` mặc định **2 hop**; ví dụ AWS Neptune dùng **3 hop**
  ("càng cao càng nhiều ngữ cảnh KG").

> **Đối với bạn đây gần như là mở rộng của `_entity_prefilter_for`:** thay vì chỉ lọc chunk
> theo entity phát hiện, **bung thêm các entity hàng xóm (1–2 hop)** rồi gộp chunk của chúng.

### 3.2 Global retrieval (community summaries) — cho câu hỏi tổng hợp
- Microsoft "From Local to Global" (arXiv 2404.16130) [^msgraphrag]:
  - Dựng **phân cấp community** bằng **Hierarchical Leiden** (đệ quy tới ngưỡng kích thước,
    `max_cluster_size` mặc định 10) [^ms-community].
  - **Sinh summary mỗi community** (LLM).
  - **Global search** dùng các community report theo **map-reduce** (map: từng report → câu
    trả lời bộ phận; reduce: gộp → câu trả lời cuối) — hợp câu hỏi "toàn corpus/tổng hợp".
- **LightRAG** phản chiếu bằng **dual-level**: low-level (entity cụ thể) vs high-level (chủ
  đề/khái quát) [^lightrag].

> ⚠️ Global mode **tốn token** (LightRAG tự báo GraphRAG global ~**610k token/query**, vs
> LightRAG **<100 token + 1 call**) — nhưng đây là **số tự báo của tác giả LightRAG**, so với
> **đường global đắt nhất** của GraphRAG, **không** phải local. Xem là minh hoạ cận trên, không
> phải đối đầu công bằng (độ tin cậy: **trung bình**) [^lightrag].

### 3.3 Subgraph extraction nâng cao
- **G-Retriever** (NeurIPS 2024) [^gretriever]: RAG đầu tiên cho textual graph tổng quát; trích
  subgraph bằng **Prize-Collecting Steiner Tree (PCST)** (tối đa "prize" node, tối thiểu "cost"
  cạnh). **Cần thành phần GNN** → **nặng để tích hợp**, để dành nghiên cứu sau.

### 3.4 HippoRAG — thay vòng lặp agentic bằng 1 bước duyệt graph
- HippoRAG (NeurIPS 2024) [^hipporag]: LLM + KG + **Personalized PageRank**, cảm hứng từ lý
  thuyết hippocampal indexing. **Vượt SOTA retrieval tới +20%** trên multi-hop QA (R@5 **89.1%**
  vs ColBERTv2 **68.2%** trên 2WikiMultiHopQA); **single-step ngang/hơn IRCoT** mà **rẻ 10–30×,
  nhanh 6–13×** ở **online retrieval** (chưa tính chi phí index offline).

> **Cực kỳ liên quan với bạn:** Self-RAG của bạn có vòng `transform_query → retrieve` lặp lại
> (đắt). Một bước **PPR trên graph** có thể thay phần lớn vòng lặp đó cho câu hỏi multi-hop.

### 3.5 Hybrid graph + vector = best practice production
- Đồng thuận (Neo4j/LlamaIndex + học thuật): **kết hợp** vector/keyword (unstructured) **với**
  graph traversal (structured), **không** chọn một [^neo4j-acc][^llamaindex]. Tìm kiếm phản
  biện cho ra **đồng thuận ngược lại**: HybridRAG (NVIDIA/BlackRock, arXiv 2408.04948) cho thấy
  fuse KG + vector **thắng cả hai** trên Q&A tài chính; "Towards Practical GraphRAG" (arXiv
  2507.03226) dùng **RRF fusion** vector + graph.
- Lưu ý tinh tế: **chèn graph CÓ CHỌN LỌC** ở nơi vector search hụt (multi-hop, quan hệ, tổng
  hợp), không thay thế hoàn toàn.

> ✅ Bạn **đã có `rrf_fusion_nway`** (đang fuse hybrid + question-index). Thêm graph path thành
> "đường thứ N" là **đúng pattern bạn đang dùng**.

### 3.6 So sánh GraphRAG vs RAG truyền thống

| Tiêu chí | RAG truyền thống (vector/hybrid) | GraphRAG |
|---|---|---|
| **Single-fact / lookup** | ✅ Tốt, rẻ | ⚪ Ngang, thừa |
| **Multi-hop / quan hệ** | ❌ Yếu (thiếu liên kết) | ✅ **+tới 20% recall** (HippoRAG) |
| **Câu hỏi tổng hợp toàn corpus** | ❌ Kém (chỉ top-k chunk rời) | ✅ Global/community summary |
| **Chi phí index (offline)** | 💰 Chỉ embedding | 💰💰💰 **+LLM extraction** (~$30/13k entity ref) |
| **Chi phí/độ trễ query** | 💰 Thấp | 💰 Local thấp; **Global cao**; HippoRAG **rẻ/nhanh hơn vòng lặp agentic** |
| **Giải thích (explainability)** | ⚪ Chunk | ✅ Đường đi graph (entity→relation→entity) |
| **Bảo trì khi thêm tài liệu** | ✅ Upsert chunk | ⚠️ Cần cập nhật graph (LightRAG: **union incremental**, không rebuild) [^lightrag] |
| **Rủi ro tiếng Việt** | ⚪ Đã chạy ổn | ⚠️ Canonicalization/coreference (giảm thiểu bằng `entity_map.json`) |

> **Kết luận mục 3:** GraphRAG **không thay** RAG thường — nó **bù** đúng các điểm yếu
> (multi-hop, quan hệ, tổng hợp). Vì vậy **mode chọn được (traditional vs graph-enhanced) là
> đúng đắn**, và mặc định nên là hybrid có chọn lọc.

---

## 4. Phần 3 — Khảo sát Big Tech & Academic

| Framework / Hệ | Phe | KG construction | Retrieval | Storage | Phù hợp với bạn |
|---|---|---|---|---|---|
| **Microsoft GraphRAG** | Big tech | LLM trích entity+relation+claim, summary theo node/edge/community | Local + **Global** (Leiden community, map-reduce) | graspologic (Python) + parquet/lancedb | ⚪ Mạnh nhưng nặng & token-heavy; tham khảo **global** |
| **Neo4j + LangChain** | Big tech | `LLMGraphTransformer` (function-calling) | `structured_retriever` (Cypher neighborhood) + vector | **Neo4j** | ⚪ Tốt nếu chấp nhận Neo4j |
| **LlamaIndex `PropertyGraphIndex`** | Big tech | Composable extractors (`SchemaLLMPathExtractor`...) | `LLMSynonymRetriever` + `VectorContextRetriever` + `Cypher/TextToCypher` + custom; depth chỉnh được | Graph store (Neo4j/Kuzu/memory) **+ `vector_store` rời** | ⭐ **Khớp nhất**: **cho truyền Qdrant làm `vector_store`** (xem 5.2) |
| **LangChain `LLMGraphTransformer`** | Big tech | LLM structured (fallback `json_repair`) | (ghép tay) | tùy | 🔧 Có thể chỉ mượn **bộ trích** cho Phase 1 |
| **Amazon Bedrock + Neptune** | Big tech | LLM (LlamaIndex orchestrate) | `graph_traversal_depth` (vd 3 hop) | **Neptune** | ⚪ Pattern "graph DB riêng + vector riêng" |
| **NebulaGraph** | Big tech (OSS) | (qua LlamaIndex/LangChain) | Cypher/nGQL traversal | NebulaGraph | ⚪ Nếu cần graph DB phân tán |
| **LightRAG** | Academic/OSS | LLM trích + **profiling key-value** + dedup; **incremental union** | **Dual-level** (low/high) | KV/graph store gọn | ⭐ Hợp **bài toán corpus đã ingest** (cập nhật tăng dần); ⚠️ exact-key dedup yếu tiếng Việt |
| **HippoRAG** | Academic | LLM + KG | **Personalized PageRank** 1 bước | KG + embeddings | ⭐ Thay **vòng lặp Self-RAG** đắt đỏ |
| **G-Retriever** | Academic | (trên graph có sẵn) | **PCST subgraph** + GNN | — | ⚪ Nặng (cần GNN), để sau |
| **GraphReader** | Academic | KG/notes | Agent "đọc" graph theo node, ghi chú | — | ⚪ Ý tưởng agent-traversal, tham khảo |

---

## 5. Phần 4 — Đánh giá độ phù hợp & quyết định kiến trúc

### 5.1 Có cần graph DB riêng không?
- **Qdrant KHÔNG lưu/duyệt graph** được → cấu trúc đồ thị **phải** ở nơi khác.
- Pattern chuẩn big tech: **graph DB riêng (Neo4j/Neptune) + vector store riêng**.
- **Nhưng với quy mô của bạn (corpus tài liệu 1 hãng), KHÔNG cần Neo4j ngay.** Lựa chọn lưu graph:

| Lựa chọn lưu graph | Ưu | Nhược | Khi nào |
|---|---|---|---|
| **NetworkX (in-memory, serialize JSON/pickle)** | 0 hạ tầng, đơn giản, đủ cho vài chục nghìn node | Mất khi restart (load lại), không scale rất lớn | ⭐ **Phase 0–2** |
| **Bảng Postgres/Neon (edges table)** | **Bạn đã có Neon** (autodata_eval); bền, query SQL | Traversal sâu phải tự viết recursive CTE | ⭐ Khi cần bền/đa tiến trình |
| **Kuzu (embedded graph DB)** | Nhúng như SQLite, Cypher, nhẹ | Thêm dependency | Khi traversal phức tạp mà chưa muốn Neo4j |
| **Neo4j / Memgraph** | Cypher mạnh, hệ sinh thái GraphRAG | Thêm service để vận hành | Khi lên production graph nghiêm túc |

### 5.2 Tái dùng Qdrant cho graph node embeddings?
✅ **ĐƯỢC** — LlamaIndex `PropertyGraphIndex` tách **graph store** khỏi **embedding store** và
nhận tham số `vector_store` ngoài (`embed_kg_nodes=True` mặc định). Tài liệu chính thức có ví dụ
**Neo4j (graph) + Qdrant (vector)** [^llamaindex][^qdrant-neo4j]. Nghĩa là: node embeddings có
thể nằm trong **Qdrant của bạn**, còn cấu trúc graph nằm ở graph store. **Tóm lại:** tái dùng
Qdrant cho *embeddings* được; nhưng vẫn cần *graph store* cho *cấu trúc*.

### 5.3 Chi phí extraction tiếng Việt
- Một lần, offline, tỉ lệ token corpus. Tham chiếu ~$30/13k entity (GPT-4o, đã rẻ hơn) [^neo4j-global].
- **Giảm chi phí:** (a) chỉ trích relation cho chunk `quality_score` cao; (b) pilot **spaCy
  ~94%**; (c) **incremental union** kiểu LightRAG để không rebuild khi thêm PDF [^lightrag].

---

## 6. Phần 5 — Kế hoạch tích hợp cụ thể (theo code của bạn)

### 6.1 Bốn hướng kiến trúc (xếp theo công sức tăng dần)

- **Hướng A — Co-occurrence + NetworkX (nhẹ nhất):** edge = entity đồng xuất hiện trong chunk
  (trọng số = số chunk chung / PMI). 0 đồng LLM. Cho retrieval **2-hop entity expansion**.
- **Hướng B — LlamaIndex `PropertyGraphIndex` + (Neo4j/Kuzu) + Qdrant `vector_store`:** đúng
  bài bản big tech, nhưng **song song** với pipeline hiện tại (trùng lặp), hợp làm nhánh thí nghiệm.
- **Hướng C — LightRAG:** dual-level + incremental update, hợp corpus đã ingest; nhưng cần lắp
  lớp dedup tiếng Việt bằng `entity_map.json`.
- **Hướng D — HippoRAG PPR:** thay vòng `transform_query`; mạnh multi-hop, rẻ/nhanh ở query time.

> **Khuyến nghị: đi A → (LLM relation) → toggle, rồi cân nhắc D.** Tránh bê nguyên Microsoft
> GraphRAG/Neo4j ngay vì trùng lặp hạ tầng và token-heavy.

### 6.2 Điểm cắm chính xác trong repo

1. **Ingestion / KG build**
   - **Phase 0:** script `scripts/build_graph.py` — scroll Qdrant, đọc `metadata.entities_canonical`,
     dựng co-occurrence graph (NetworkX), lưu `data/graph/cooccur.gpickle` (+ pyvis HTML).
   - **Phase 1:** mở rộng [extract.py](../src/agentic_rag/ingestion/metadata/extract.py) `LLMExtractedMetadata`
     thêm field `relations: list[Triple]`; prompt LLM xuất `(head, relation, tail)`; canonical-hoá
     head/tail bằng `normalize_all()` ([entity_normalizer.py](../src/agentic_rag/ingestion/metadata/entity_normalizer.py)).
     Lưu edges (NetworkX hoặc bảng Neon `kg_edges`).
2. **Retrieval (graph-enhanced mode)**
   - Thêm `graph_search()` trong [retrieval/](../src/agentic_rag/retrieval/): nhận entity phát
     hiện (`detect_in_query`) → lấy hàng xóm k-hop → mở rộng `entity_filter` và/hoặc trả chunk
     liên-thông → **fuse RRF** với `qdrant_hybrid_search` qua `rrf_fusion_nway`.
   - Cắm tại `SourceEvidenceProvider.retrieve()` (đường agent) — đối xứng với cách question-index
     đang cắm trong `qdrant_hybrid_search`.
3. **Mode toggle (Task 3) — đúng khuôn mẫu hiện có**
   - Backend: thêm field vào `RetrievalConfig` ([api.py](../src/agentic_rag/api.py)), ví dụ
     `graph_retrieval_enabled: bool` (+ `graph_hops: int`), map sang ENV `RETRIEVAL_GRAPH_ENABLED` /
     `RETRIEVAL_GRAPH_HOPS` trong `get/set_retrieval_config`.
   - Gate runtime: hàm `_graph_retrieval_enabled()` đọc `os.getenv(...)` (giống `_question_index_enabled()`).
   - Frontend: thêm 1 mục vào mảng `TOGGLES` ở [config/page.tsx](../frontend/app/config/page.tsx)
     (`{ key: "graph_retrieval_enabled", label: "Graph-enhanced retrieval", hint: "..." }`) — tự
     động hiện switch, lưu `.env`, áp ngay cho `/answer`.
   - `.env.example`: thêm `RETRIEVAL_GRAPH_ENABLED=false` (mặc định OFF = baseline) + `RETRIEVAL_GRAPH_HOPS=2`.

### 6.3 Lộ trình theo phase (kèm tiêu chí done)

| Phase | Việc | Công cụ | Chi phí | Done khi |
|---|---|---|---|---|
| **0** | Co-occurrence graph + visualize | NetworkX, pyvis | ~0 | Có graph + HTML xem được; thống kê node/edge |
| **1** | LLM relation extraction ở `[L]`, canonical hoá | LLM `[L]` + `entity_map.json` | 💰 1 lần | Edges có nhãn, dedup theo canonical |
| **2** | Graph-enhanced retrieval mode + toggle + RRF fuse | code nội bộ + `rrf_fusion_nway` | ~0 | A/B eval graph ON/OFF trên benchmark (đã có hạ tầng eval) |
| **3a** | (Tùy chọn) Global/community | Leiden (`igraph`/`graspologic`) + summary | 💰 | Trả lời tốt câu hỏi tổng hợp |
| **3b** | (Tùy chọn) HippoRAG PPR thay `transform_query` | PPR (NetworkX `pagerank`) | ~0 query | Giảm số vòng lặp/độ trễ multi-hop |

> Bạn đã có **hạ tầng eval** (`autodata_eval`, benchmark, RunEvalModal) → Phase 2 nên gắn
> thẳng vào A/B `RETRIEVAL_GRAPH_ENABLED` true/false như cách bạn đang A/B question-index/BM25-augment.

---

## 7. Tradeoffs & best practices production

- **Chi phí dồn ở offline extraction**, không phải query → tách rõ "index cost" (1 lần) vs
  "query cost" (lặp lại). Đừng để global-mode token-heavy thành mặc định.
- **Hybrid mặc định, graph có chọn lọc** — route câu hỏi: lookup → vector; multi-hop/quan
  hệ/tổng hợp → graph. **Có thể để chính Self-RAG grading tự route** thay vì bắt user chọn (xem Open Questions).
- **Incremental update** (LightRAG union) để thêm PDF không phải rebuild.
- **Canonicalization là sống còn** cho graph tiếng Việt → tái dùng `entity_map.json`; **không**
  dựa vào exact-key dedup.
- **Explainability**: lưu lại đường đi graph dùng để trả lời → hiển thị (tăng tin cậy, hợp demo).
- **Đo lường**: gắn vào eval hiện có; theo dõi recall multi-hop, token/query, độ trễ ON vs OFF.

---

## 8. Caveats (độ tin cậy & giới hạn nguồn)

- **Số HippoRAG (+20% / 10–30× / 6–13×)** là **best-case 1 benchmark, giữa 2024**; "SOTA" nay đã
  cũ (đã có HippoRAG 2, HopRAG, IndexRAG). Lợi thế rẻ/nhanh **chỉ ở online retrieval**, **không**
  gồm chi phí index offline.
- **LightRAG ~610k vs <100 token**: **single-source, tự báo**, nhằm vào **global** (đường đắt
  nhất) của GraphRAG → minh hoạ cận trên, **không** phải đối đầu công bằng (độ tin cậy trung bình).
- **Nguồn Neo4j** có **động cơ vendor** (bán graph DB) — nhưng khuyến nghị "hybrid" lại ngược
  với pitch "pure graph", và được học thuật trung lập xác nhận.
- **Khoảng trống tiếng Việt:** **không** nguồn nào đo trực tiếp chất lượng extraction/normalization
  tiếng Việt → **bắt buộc pilot thực nghiệm** trên corpus của bạn.
- **"Big tech = LLM, không spaCy/NER"** là **khái quát hơi quá** — họ vẫn hỗ trợ spaCy (~94%).
- Claim "29k LLM call cho graph 13k node" **đã bị bác bỏ** — không dùng làm lý do sợ community summary.

---

## 9. Open Questions (cần thực nghiệm để chốt)

1. Chi phí/độ trễ/chất lượng extraction **thực tế trên corpus PDF tiếng Việt** của bạn là bao
   nhiêu? So **LLM vs spaCy/GLiNER** cho tiếng Việt.
2. Dedup/coreference tiếng Việt chịu được tới đâu? `entity_map.json` có đủ làm lớp merge cho KG?
3. Với stack Qdrant + Self-RAG này, nên (a) LlamaIndex+Neo4j+Qdrant, (b) LightRAG, hay (c)
   HippoRAG PPR thay vòng lặp? — cần benchmark nội bộ.
4. Khi nào route local vs global, và **có nên để Self-RAG grading tự route** thay vì user chọn?
   Token global-mode có chấp nhận được ở quy mô corpus của bạn không?

---

## 10. Tài liệu tham khảo

Nguồn đã qua xác minh đối kháng (3-vote) trong nghiên cứu này:

[^neo4j-global]: Neo4j — *Implementing 'From Local to Global' GraphRAG with Neo4j and LangChain* (chi phí ~$30/35′, ~13k entity/16k relation). https://neo4j.com/blog/developer/global-graphrag-neo4j-langchain/
[^neo4j-acc]: Neo4j — *Enhancing the Accuracy of RAG Applications With Knowledge Graphs* (structured_retriever, hybrid). https://medium.com/neo4j/enhancing-the-accuracy-of-rag-applications-with-knowledge-graphs-ad5e2ffab663
[^llamaindex]: LlamaIndex — *Introducing the Property Graph Index* (composable extractors, `vector_store` rời, `embed_kg_nodes`). https://www.llamaindex.ai/blog/introducing-the-property-graph-index-a-powerful-new-way-to-build-knowledge-graphs-with-llms
[^msgraphrag]: Microsoft Research — *From Local to Global: A Graph RAG Approach* (Leiden, global map-reduce). https://arxiv.org/abs/2404.16130
[^ms-community]: Microsoft GraphRAG docs — *Community detection* (Hierarchical Leiden, `max_cluster_size`). https://microsoft.github.io/graphrag/ (concepts/community-detection)
[^hipporag]: HippoRAG — *Neurobiologically Inspired Long-Term Memory for LLMs* (PPR, +20%, 10–30× rẻ). https://arxiv.org/abs/2405.14831
[^lightrag]: LightRAG — *Simple and Fast Retrieval-Augmented Generation* (dual-level, incremental union, token comparison). https://arxiv.org/abs/2410.05779
[^gretriever]: G-Retriever — *RAG for Textual Graph Understanding & QA* (PCST subgraph + GNN). https://arxiv.org/abs/2402.07630
[^aws]: AWS — *Using Knowledge Graphs to build GraphRAG with Bedrock & Neptune* (`graph_traversal_depth`). https://aws.amazon.com/blogs/database/using-knowledge-graphs-to-build-graphrag-applications-with-amazon-bedrock-and-amazon-neptune/
[^qdrant-neo4j]: Qdrant docs — *GraphRAG with Qdrant & Neo4j* (Qdrant vector + Neo4j graph). https://qdrant.tech/documentation/examples/graphrag-qdrant-neo4j/

Nguồn bổ trợ: LlamaIndex LPG guide (developers.llamaindex.ai/.../lpg_index_guide), GLiNER
(github.com/urchade/GLiNER), REBEL + LlamaIndex (medium @sauravjoshi23), LLMGraphTransformer
(medium data-science), HybridRAG (arXiv 2408.04948), Towards Practical GraphRAG (arXiv 2507.03226).

> *Lưu ý: một số số liệu là snapshot tại thời điểm công bố (2024); lĩnh vực này thay đổi nhanh.
> Trước khi cam kết kiến trúc, hãy chạy pilot extraction trên corpus tiếng Việt của bạn (Open Question #1).*
