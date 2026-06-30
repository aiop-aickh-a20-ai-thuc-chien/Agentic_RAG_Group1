# 📖 GUIDELINE — GraphRAG + RAG Hybrid System

> Tài liệu hướng dẫn tổng hợp cho hệ thống **GraphRAG + RAG Hybrid Pipeline** và **VinFast Crawler**.
> Tất cả tài liệu kỹ thuật chi tiết được tổ chức trong thư mục [`guide_RAG/`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG).

---

## 📁 Cấu trúc thư mục `guide_RAG/`

```
guide_RAG/
├── Crawler_Specs/        # Đặc tả kỹ thuật crawler chi tiết theo URL mục tiêu
├── PRD_To_Screen/        # Từ yêu cầu sản phẩm → triển khai thực tế
├── TCR/                  # Technical Core Reference — pipeline lõi
└── UI_Pattern/           # Mẫu truy vấn & tương tác hệ thống
```

---

## 1. 📋 PRD_To_Screen — Product → Implementation

> **Mục đích**: Chứa tài liệu kiến trúc tổng quan, roadmap triển khai, và các phase liên quan đến API, đánh giá, production.

| File | Mô tả | Đọc khi |
|------|--------|---------|
| [`01_architecture_overview.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/PRD_To_Screen/01_architecture_overview.md) | Kiến trúc tổng quan hệ thống: pipeline diagram, data model, query methods comparison, config structure | Bắt đầu dự án, onboarding thành viên mới |
| [`TODO.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/PRD_To_Screen/TODO.md) | Roadmap triển khai 13 phase: từ setup → ingestion → graph → query → API → production | Lập kế hoạch sprint, tracking tiến độ |
| [`09_phase11to13_api_eval_prod.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/PRD_To_Screen/09_phase11to13_api_eval_prod.md) | FastAPI REST API, WebSocket streaming, evaluation metrics (faithfulness, relevancy, context precision), deployment architecture, error recovery | Xây dựng API layer, đánh giá chất lượng, triển khai production |

### Nội dung chính:
- **Architecture Overview**: High-level system diagram, indexing pipeline, data model (Document → TextUnit → Entity → Relationship → Community → CommunityReport), query methods comparison
- **TODO Roadmap**: 13 phases chi tiết với checklist tasks, key architecture decisions, file references
- **API & Production**: REST endpoints (`/index`, `/query`, `/status`, `/graph`), WebSocket streaming, RAGEvaluator (4 metrics), cost optimization strategies, Docker Compose deployment, monitoring middleware

---

## 2. 🔧 TCR — Technical Core Reference

> **Mục đích**: Pseudocode chi tiết cho **indexing pipeline** — từ document ingestion đến embedding generation. Đây là phần core xử lý offline.

| File | Phase | Mô tả | Đọc khi |
|------|-------|--------|---------|
| [`02_phase1_ingestion_chunking.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/TCR/02_phase1_ingestion_chunking.md) | Phase 1 | Document loading, text chunking (token-based, 300 tokens + 100 overlap), metadata prepending, SHA-512 ID generation | Implement ingestion module |
| [`03_phase2_graph_construction.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/TCR/03_phase2_graph_construction.md) | Phase 2 | LLM-based entity & relationship extraction, gleaning passes, description summarization, graph finalization, covariates extraction | Implement knowledge graph builder |
| [`04_phase3_communities.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/TCR/04_phase3_communities.md) | Phase 3 | Hierarchical Leiden community detection, community hierarchy, LLM community report generation (bottom-up), context building | Implement community detection & reports |
| [`05_phase4_embeddings.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/TCR/05_phase4_embeddings.md) | Phase 4 | Embedding generation (entity descriptions, text units, community reports), batch processing, vector store abstraction (LanceDB, Azure AI Search, CosmosDB) | Implement embedding & vector store |

### Luồng xử lý (Indexing Pipeline):
```
Documents → [Phase 1] Text Chunking → [Phase 2] Entity/Relationship Extraction
         → [Phase 2] Graph Finalization → [Phase 3] Community Detection
         → [Phase 3] Community Reports → [Phase 4] Embeddings → Vector Store
```

### Key Parameters:

| Parameter | Giá trị mặc định | Thuộc Phase |
|-----------|-------------------|-------------|
| `chunk_size` | 300 tokens | Phase 1 |
| `chunk_overlap` | 100 tokens | Phase 1 |
| `encoding_model` | cl100k_base | Phase 1 |
| `entity_types` | organization, person, location, event | Phase 2 |
| `max_gleanings` | 1 | Phase 2 |
| `max_cluster_size` | 10 | Phase 3 |
| `max_input_length` | 8000 tokens | Phase 3 |
| `max_report_length` | 2000 tokens | Phase 3 |
| `embedding_model` | text-embedding-3-small | Phase 4 |
| `batch_size` | 16 | Phase 4 |

---

## 3. 🎯 UI_Pattern — Query & Interaction Patterns

> **Mục đích**: Pseudocode chi tiết cho **query pipeline** — các phương thức tìm kiếm, hybrid fusion, và incremental update. Đây là phần xử lý online/runtime.

| File | Phase | Mô tả | Đọc khi |
|------|-------|--------|---------|
| [`06_phase5to8_query_pipeline.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/UI_Pattern/06_phase5to8_query_pipeline.md) | Phase 5-8 | 4 search methods: Basic Search (vector RAG), Local Search (entity-centric GraphRAG), Global Search (Map-Reduce over communities), DRIFT Search (iterative multi-hop) | Implement query engines |
| [`07_phase9_hybrid_fusion.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/UI_Pattern/07_phase9_hybrid_fusion.md) | Phase 9 | Hybrid query router, parallel Local+Basic execution, context deduplication, confidence scoring, answer synthesis, Reciprocal Rank Fusion | Implement hybrid search |
| [`08_phase10_incremental_update.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/UI_Pattern/08_phase10_incremental_update.md) | Phase 10 | Delta detection, entity/relationship merge, community re-clustering, report regeneration (changed-only), embedding update (delta-only) | Implement incremental indexing |

### So sánh Search Methods:

| Method | Best for | Speed | Cost | LLM Calls |
|--------|----------|-------|------|-----------|
| **Basic Search** | Simple factual lookup | ⚡ Fastest | 💰 Low | 1 |
| **Local Search** | Specific entity questions | ⚡ Fast | 💰💰 Medium | 1 |
| **Global Search** | Broad thematic questions | 🐢 Slower | 💰💰💰 High | N+1 (map-reduce) |
| **DRIFT Search** | Multi-hop reasoning | 🐌 Slowest | 💰💰💰💰 Highest | M (iterative) |
| **Hybrid** | Complex queries | ⚡ Fast (parallel) | 💰💰 Medium | 2+1 (fusion) |

### Query Routing Decision Flow:
```
User Query
    │
    ├── "Who is X?" (specific)        → LOCAL SEARCH
    ├── "What themes exist?" (broad)  → GLOBAL SEARCH
    ├── "How does A relate to B       → DRIFT SEARCH
    │    through C?" (multi-hop)
    ├── "Find docs about X" (simple)  → BASIC SEARCH
    └── Complex / ambiguous           → HYBRID (Local + Basic)
```

---

## 4. 📸 PixelRAG — Visual Retrieval-Augmented Generation

> **Mục đích**: Tài liệu tham khảo về phương pháp Visual RAG từ dự án [PixelRAG](file:///E:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/PixelRAG) (Berkeley SkyLab). Thay vì parse HTML/PDF thành text, PixelRAG **render tài liệu thành ảnh chụp màn hình** và truy vấn trực tiếp trên ảnh — giữ nguyên bảng, biểu đồ, layout mà text parser thường làm mất.

### Tổng quan Pipeline

PixelRAG chia pipeline thành 4 stage rõ ràng:

```
Source Documents (URL/PDF/HTML/Image)
    │
    ▼
[Stage 1] RENDER ──── pixelshot (Chromium CDP / Playwright / PDF poppler)
    │                  URL → full-page screenshot → tiled JPEG images
    │                  PDF → page images (DPI=200) → tiles
    ▼
[Stage 2] CHUNK  ──── pixelrag_embed.chunk
    │                  Mỗi tile (~8192px cao) → chia thành grid 1024px strips
    │                  Discard tiny tails < 28px (1 Qwen3-VL patch)
    │                  Output: chunks.json manifest + chunk_XXXX_YY.png files
    ▼
[Stage 3] EMBED  ──── pixelrag_embed.embed / embed_cpu
    │                  Qwen3-VL-Embedding-2B (LoRA fine-tuned trên screenshot data)
    │                  Device: auto (CUDA / MPS / CPU)
    │                  Output: shard_XXX.npz (embeddings + article_id + tile/chunk index)
    ▼
[Stage 4] INDEX  ──── pixelrag_embed.index
    │                  FAISS IVF index (nlist = min(4096, n_vectors/40))
    │                  Output: searchable FAISS index directory
    ▼
[SERVE]          ──── pixelrag serve (FastAPI search API)
                       Search by text query OR image query
```

### Key Parameters

| Parameter | Giá trị mặc định | Ghi chú |
|-----------|-------------------|---------|
| `tile_height` | 8192 px | Chiều cao tối đa mỗi tile trước khi chunk |
| `viewport_width` | 875 px | Chiều rộng viewport browser khi render |
| `chunk_height` | 1024 px | Chiều cao tối đa mỗi chunk ảnh (model input size) |
| `min_chunk_height` | 28 px | Ngưỡng tối thiểu (1 Qwen3-VL patch) — nhỏ hơn sẽ bỏ |
| `embedding_model` | `Qwen/Qwen3-VL-Embedding-2B` | Vision-Language model cho embedding |
| `quality` (JPEG) | 85 | Chất lượng ảnh output |
| `dpi` (PDF) | 200 | Độ phân giải khi render PDF (~1650×2200 cho A4) |
| `nlist` (FAISS) | `min(4096, n_vectors/40)` | Số IVF clusters, tự điều chỉnh theo data |

### So sánh: Text-based RAG vs Visual RAG (PixelRAG)

| Tiêu chí | Text-based RAG (hiện tại) | Visual RAG (PixelRAG) |
|----------|---------------------------|------------------------|
| **Input processing** | Parse HTML/PDF → extract text → markdown | Render → screenshot tiles → image chunks |
| **Bảng & biểu đồ** | ❌ Thường bị mất structure | ✅ Giữ nguyên visual layout |
| **Embedding model** | `sentence-transformers` (text-only) | `Qwen3-VL-Embedding-2B` (vision-language) |
| **Storage** | Text chunks (~KB mỗi chunk) | Image chunks (~100KB+ mỗi chunk) |
| **Speed** | ⚡ Nhanh (text processing) | 🐢 Chậm hơn (render + vision model inference) |
| **GPU requirement** | Tùy chọn (CPU cũng chạy được) | Khuyến nghị GPU cho embedding |
| **Tìm kiếm** | Text similarity (BM25 + dense) | Visual similarity (FAISS) |
| **Best for** | Nội dung text-heavy, structured | Trang có bảng, layout phức tạp, infographics |

### Điểm tích hợp với Agentic RAG hiện tại

Có 3 hướng tích hợp tiềm năng:

1. **Visual Fallback**: Khi text extraction quality thấp (low signal markdown, bảng bị vỡ), fallback sang render screenshot và dùng VLM để trích xuất thông tin. Xem TODO trong `src/agentic_rag/ingestion/url/loader.py`.

2. **PDF Visual Chunking**: Song song với text chunking, render mỗi trang PDF thành ảnh và tạo visual chunks. Hữu ích cho brochure/catalog với nhiều hình ảnh. Xem TODO trong `src/agentic_rag/ingestion/pdf/loader.py`.

3. **Hybrid Text + Visual Scoring**: Kết hợp text retrieval score với visual retrieval score bằng Reciprocal Rank Fusion (tương tự Phase 9 Hybrid Fusion). Cần thêm visual index song song.

> **Lưu ý**: PixelRAG là tài liệu tham khảo. Các TODO pseudocode đã được thêm trong `src/agentic_rag/ingestion/` để đánh dấu điểm tích hợp, nhưng chưa implement.

---

## 5. 🕷️ VinFast Crawler — Dynamic Crawling & Entity Extraction

> **Mục đích**: Tài liệu kiến trúc và quy trình thu thập dữ liệu tự động từ các trang web của VinFast Auto. Để xử lý tốt các cấu trúc giao diện động và các kịch bản khác nhau, các tài liệu hướng dẫn được chia tách chi tiết theo từng URL mục tiêu.

### Các tài liệu đặc tả theo trang (Target-Specific Specs):

| Mục tiêu (Target URL) | Tài liệu đặc tả | Mô tả nội dung trích xuất |
|-----------------------|-----------------|---------------------------|
| `https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html` | [`car_booking.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/Crawler_Specs/car_booking.md) | **Đặt cọc ô tô điện**: Duyệt cấu trúc dòng xe (Vehicle), phiên bản (Variant), màu sắc (Color), bảng tính chi phí lăn bánh động theo tỉnh thành, và các kịch bản trả góp. |
| `https://vinfastauto.com/vn_vi` | [`homepage_portal.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/Crawler_Specs/homepage_portal.md) | **Trang chủ & Cổng thông tin**: Menu điều hướng, tin tức bài viết (News), danh sách showroom/đại lý và hệ thống các trạm sạc trên toàn quốc. |
| `https://shop.vinfastauto.com/vn_vi/xe-may-dien-vinfast.html` | [`bike_booking.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/Crawler_Specs/bike_booking.md) | **Đặt cọc xe máy điện**: Các mẫu xe máy, tùy chọn pin (thuê pin vs mua pin), phiên bản, màu sắc và cấu trúc giá động tương ứng. |

---

### Nguyên tắc thiết kế chung (General Design Principles)

#### 1. Entity First
Không coi trang web là một tài liệu tĩnh (document). Hãy coi đó là một đồ thị của các thực thể (Vehicle, Variant, Color, Price, Promotion, Specification, Image, Modal, Rolling Cost, Installment).

#### 2. State-Based Crawling
Mỗi tương tác của người dùng tạo ra một trạng thái mới (ví dụ: `VF8 -> Plus -> White -> Hà Nội -> 50% Down Payment -> 60 Months`). Crawler phải duyệt qua các trạng thái này để thu thập đầy đủ dữ liệu.

#### 3. API First
Ưu tiên chặn và trích xuất dữ liệu từ các phản hồi mạng (XHR, Fetch, GraphQL, JSON APIs) trước khi sử dụng DOM scraping để đảm bảo tính chính xác và hiệu năng cao.

---

### Kiến trúc Hệ thống Crawler (System Architecture)
```text
Playwright
    │
    ▼
Interaction Discovery (Tìm kiếm các nút bấm, swatches, tabs)
    │
    ▼
State Enumeration (Duyệt cây trạng thái cấu hình xe/pin/địa điểm)
    │
    ▼
Network Capture & Interception (Chặn bắt API phản hồi)
    │
    ▼
HTML Snapshot Storage (Lưu trữ snapshot HTML của các trạng thái)
    │
    ▼
Entity Extraction & Normalization (Trích xuất các thực thể dạng JSON)
    │
    ▼
Markdown Generation (Sinh tài liệu markdown từ thực thể phục vụ RAG)
```

---

### Quy tắc đồng bộ & Giãn cách (Sync & Pacing Rules)

- **Không dùng sleep mù**: Tránh việc chỉ sử dụng `sleep()` hoặc `wait_for_timeout()` cố định. Thay vào đó, hãy sử dụng các cơ chế đợi động:
  1. Đợi thay đổi DOM (`wait_for_function`)
  2. Đợi phản hồi API (`expect_response`)
  3. Đợi selector hiển thị (`wait_for_selector`)
- **Tốc độ giãn cách khuyến nghị (Pacing)**:
  - Đổi xe: `0.8 - 2.0 giây`
  - Đổi phiên bản: `0.5 - 1.2 giây`
  - Mở Modal: `0.3 - 0.8 giây`
  - Tính toán tài chính: `1.0 - 3.0 giây` (đợi API tính toán debounced hoàn tất)

---

## 🔗 Liên kết nhanh

### Theo mục đích sử dụng:

| Bạn muốn... | Đọc file |
|-------------|----------|
| Hiểu tổng quan hệ thống | [01_architecture_overview.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/PRD_To_Screen/01_architecture_overview.md) |
| Xem roadmap & checklist | [TODO.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/PRD_To_Screen/TODO.md) |
| Tìm hiểu Crawler & Entity Extraction (General) | [GUIDELINE.md §5](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/GUIDELINE.md#5-vinfast-crawler--dynamic-crawling--entity-extraction) |
| Đặc tả Crawler Đặt cọc Ô tô điện | [car_booking.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/Crawler_Specs/car_booking.md) |
| Đặc tả Crawler Cổng thông tin & Tin tức | [homepage_portal.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/Crawler_Specs/homepage_portal.md) |
| Đặc tả Crawler Đặt cọc Xe máy điện | [bike_booking.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/Crawler_Specs/bike_booking.md) |
| Implement ingestion & chunking | [02_phase1_ingestion_chunking.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/TCR/02_phase1_ingestion_chunking.md) |
| Implement knowledge graph | [03_phase2_graph_construction.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/TCR/03_phase2_graph_construction.md) |
| Implement community detection | [04_phase3_communities.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/TCR/04_phase3_communities.md) |
| Implement embeddings & vector store | [05_phase4_embeddings.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/TCR/05_phase4_embeddings.md) |
| Implement search engines | [06_phase5to8_query_pipeline.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/UI_Pattern/06_phase5to8_query_pipeline.md) |
| Implement hybrid fusion | [07_phase9_hybrid_fusion.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/UI_Pattern/07_phase9_hybrid_fusion.md) |
| Implement incremental update | [08_phase10_incremental_update.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/UI_Pattern/08_phase10_incremental_update.md) |
| Build API & deploy | [09_phase11to13_api_eval_prod.md](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/PRD_To_Screen/09_phase11to13_api_eval_prod.md) |
| Tham khảo Visual RAG (PixelRAG) | [GUIDELINE.md §4](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/GUIDELINE.md#4-pixelrag--visual-retrieval-augmented-generation) + [PixelRAG README](file:///E:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/PixelRAG/README.md) |

### Theo thứ tự đọc (recommended):
1. 🕸️ 0. Crawler Specifications (Thu thập dữ liệu nguồn):
   - Tổng quan & Kiến trúc: [GUIDELINE.md §5](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/GUIDELINE.md#5-vinfast-crawler--dynamic-crawling--entity-extraction)
   - Chi tiết từng URL: [`car_booking.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/Crawler_Specs/car_booking.md) | [`homepage_portal.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/Crawler_Specs/homepage_portal.md) | [`bike_booking.md`](file:///e:/VINSMART_Future_Thuc_Tap/Agentic_RAG_Project/Agentic_RAG_Group1/guide_RAG/Crawler_Specs/bike_booking.md)
2. 🏗️ 1. Architecture Overview → hiểu bức tranh toàn cảnh
3. 📋 2. TODO Roadmap → nắm được kế hoạch triển khai
4. 📄 3. Phase 1: Ingestion → bắt đầu implement từ data pipeline
5. 🔗 4. Phase 2: Graph Construction → xây knowledge graph
6. 🏘️ 5. Phase 3: Communities → clustering & reports
7. 🔍 6. Phase 4: Embeddings → vector representations
8. 🔎 7. Phase 5-8: Query Pipeline → implement search engines
9. 🔀 8. Phase 9: Hybrid Fusion → kết hợp GraphRAG + RAG
10. 🔄 9. Phase 10: Incremental Update → cập nhật theo delta
11. 🚀 10. Phase 11-13: API, Eval & Prod → triển khai production
12. 📸 11. PixelRAG Reference → tham khảo Visual RAG approach
