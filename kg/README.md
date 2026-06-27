# `kg/` — Knowledge-Graph Construction (greenfield)

Pipeline tự-chứa, **độc lập với code hiện tại** của dự án. Xây KG từ tài liệu theo
backbone **EDC (Extract → Define → Canonicalize)**: *mở trước → chuẩn hoá sau*.
Chạy được ngay không cần API (mock), và là **adapter** — không thay vector store.

```
[1] EXTRACT(open) → [2] STAGE → [3a] RESOLVE → [3b] CANONICALIZE → [3c] GATES → [4] MERGE → [5] ENRICH → [6] STORE
└──────── INGEST (per-doc, incremental) ───────┘ └─────────────── BATCH (view toàn cục, tái lập được) ───────────────┘
```

## Chạy demo

```bash
python -m kg.demo
```
Sinh ra trong `kg/output/`:
- **`architecture.html`** — sơ đồ pipeline + tích hợp + số liệu chạy thật *(mở để thấy "từng bước làm gì, ở đâu")*
- **`graph.html`** — graph tương tác (bấm node xem quan hệ + bằng chứng)
- `graph.json` — dữ liệu node-link

## Từng bước làm gì + tích hợp ở đâu

| # | File | Lane | Làm gì |
|---|---|---|---|
| **[1] Extract** | `extract.py` | INGEST | LLM trích triple **mở** mỗi chunk (predicate/type free-form) + gleanings. Giữ nguyên cách diễn đạt. |
| **[2] Stage** | `stage.py` | INGEST | Ghi triple thô append-only + provenance. Tách trích khỏi chuẩn hoá. |
| **[3a] Resolve** | `resolve.py` | BATCH | Gộp biến thể entity: blocking embedding → vùng xám LLM-judge → canonical id content-addressed. |
| **[3b] Canonicalize** | `canonicalize.py` | BATCH | EDC Define→Canonicalize predicate: gộp đồng nghĩa + hướng chuẩn. |
| **[3c] Gates** | `gates.py` | BATCH | Drop đại từ / generic-only / evidence không-substring. |
| **[4] Merge** | `merge.py` | BATCH | Map canonical, **đảo hướng** theo direction+type, gộp cạnh. |
| **[5]/[6] Store** | `store.py` | BATCH | networkx graph + query (k-hop) + community + **delete_document** (lifecycle/GDPR). |
| Orchestrate | `pipeline.py` | — | `ingest()` per-doc, `build()` batch. |

## Chạy THẬT (OpenAI + Neo4j)

LLM = **OpenAI SDK trực tiếp** (không litellm). Store = **Neo4j**.

```bash
uv pip install neo4j                 # driver (đã cài)
# .env: OPENAI_API_KEY, LLM_MODEL=gpt-4o-mini, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
docker run -p7474:7474 -p7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5   # nếu chạy local

python -m kg.run_real --check        # test kết nối OpenAI + Neo4j (ping 1 token)
python -m kg.run_real --wipe         # build bằng LLM thật → đẩy vào Neo4j
```
Thành phần thật: `OpenAILLM` / `OpenAIEmbedder` ([llm.py](llm.py)), `Neo4jStore` ([store_neo4j.py](store_neo4j.py)),
entrypoint [run_real.py](run_real.py). Env cờ: `KG_OPENAI_EMBED=1` (dùng embedding OpenAI),
`KG_USE_MOCK=1` (ép mock), `KG_GLEANINGS=1`.

> ⚠️ `run_real` đang dùng `sample_data.DOCUMENTS` — **thay bằng chunk thật** của bạn. Pipeline [1]–[4] không đổi.
> Neo4jStore có cùng interface GraphStore (`find_node`/`neighbors`/`edges_of`/`delete_document`/`to_node_link`)
> nên sẵn sàng cho bước **online retrieval** (Cypher traversal) tiếp theo.

## Cắm LLM / embedding thật (production seam)

Chỉ cần thay 2 thứ, **không sửa pipeline**:

```python
from kg.pipeline import KGPipeline
pipe = KGPipeline(llm=MyLLMClient(), embedder=MyEmbedder())  # protocol seams
```
- **`LLMClient`**: bất kỳ object có `.complete(prompt, system) -> str`. Ví dụ `LiteLLMClient` ở cuối `kg/llm.py`. (Mock chỉ dùng cho demo.)
- **`Embedder`**: bất kỳ object có `.embed(text) -> dict`. Thay `CharNGramEmbedder` bằng sentence-embedding đa ngữ thật.
- **Store**: đổi `build_graph` → Neo4j (GDS cho resolution + Cypher) khi cần quy mô.

## Quyết định thiết kế (và vì sao)

- **Mở trước, chuẩn hoá sau (EDC)** — không khoá schema từ đầu; predicate "mọc" từ dữ liệu.
- **Canonicalize BATCH, không online** — canonical là hàm của *dữ liệu*, không phải *thứ tự upload* → tái lập + A/B được (tránh order-dependence + early-poison).
- **Content-addressed id** (`hash(normalized)`) — idempotent, race-safe.
- **Gates ở merge-time** — LLM không tự lọc được rác (đại từ, phụ kiện, hallucination).
- **Đảo hướng theo predicate+type** — bị động tiếng Việt ("được sản xuất bởi") không làm lật quan hệ.
- **Provenance `doc_id`+`chunk_id` mọi cạnh** + `delete_document` — re-ingest/GDPR sạch.

## Demo chứng minh gì

Trên 13 triple thô từ 3 doc tiếng Việt: gộp `VF 8`/`VinFast VF8`, `pin LFP`/`pin lithium LFP`,
`VF 5`/`vf5`; gộp 11 predicate → 6 (made_by/has_feature/...); **loại 3 rác** (đại từ "Xe này",
phụ kiện-generic, evidence giả "Toyota"); **đảo hướng** "VinFast sản xuất VF 8" → `VF 8 —made_by→ VinFast`;
và xoá 1 doc gỡ đúng các cạnh của nó.
