# Module Contracts

Codebase được thiết kế trung lập về tech stack. Thành viên có thể chọn thư viện
riêng bên trong module của mình, nhưng phần tích hợp giữa các module phải dùng
Pydantic v2 contracts dưới đây.

## Shared Models

Tất cả module nên import shared models từ `agentic_rag.core.contracts`. Dùng
generic type built-in của Python 3.12 như `list[Chunk]`, không dùng
legacy `typing.List`.

### `Chunk`

Đoạn tài liệu đã được normalize, sinh ra từ ingestion.

Required fields:

- `chunk_id: str`
- `text: str`
- `metadata: dict[str, Any]`

Các metadata key dùng chung:

- `source`
- `source_type`
- `file_name`
- `url`
- `page`
- `section`

Top-level extra fields sẽ bị reject. Field mở rộng theo từng nguồn dữ liệu nên
đặt trong `metadata`.

### `SearchResult`

Kết quả retrieval đã được rank, truyền từ retrieval sang fusion/generation.

Required fields:

- `chunk: Chunk`
- `score: float`
- `rank: int`
- `retriever: str`

Giá trị `retriever` khuyến nghị:

- `bm25`
- `dense`
- `hybrid`
- `rerank`

### `Citation`

Tham chiếu nguồn được tạo từ metadata của evidence.

Required fields:

- `source: str`
- `chunk_id: str`

Optional fields:

- `page`
- `section`
- `url`

### `Answer`

Kết quả generation trả về cho UI hoặc evaluation layer.

Required fields:

- `answer: str`
- `citations: list[Citation]`
- `status: "answered" | "not_found"`

Default fields:

- `citations: list[Citation] = []`

Pydantic chấp nhận nested dictionaries khớp với `Citation` và validate thành
instance của `Citation`.

## Các phần implementation

| Phần | Boundary kỳ vọng |
| --- | --- |
| PDF ingestion + chunking | `agentic_rag.ingestion.pdf.load_pdf_chunks(path: str) -> list[Chunk]` |
| URL ingestion + chunking | `agentic_rag.ingestion.url.load_url_chunks(url: str) -> list[Chunk]` |
| Query + BM25/dense retrieval | `agentic_rag.retrieval.search.preprocess_query(...)`, `bm25_search(...)`, `dense_search(...)` |
| Hybrid fusion + evidence context | `agentic_rag.retrieval.fusion.rrf_fusion(...)`, `rerank(...)`, `build_evidence_context(...)` |
| Generation + citations + UI | `agentic_rag.generation.answering.generate_answer(...)`, `validate_answer_with_citations(...)`, `agentic_rag.app.run_app()` |
| Evaluation report | `agentic_rag.evaluation.metrics.recall_at_k(...)`, `mrr_at_k(...)` |

Protocol definitions nằm trong `agentic_rag.core.ports`.

## Package Layout

```text
agentic_rag/
  core/          Shared Pydantic contracts và protocols
  ingestion/     PDF và URL ingestion packages
  retrieval/     Query preprocessing, BM25, dense retrieval, fusion, reranking
  generation/    Grounded answer và citation boundaries
  evaluation/    Recall@k và MRR@k boundaries
  app.py         UI-framework-neutral app boundary
```

## Quy tắc tích hợp

- Ingestion modules chỉ cần sinh ra `Chunk` objects.
- Retrieval modules nên nhận chunks từ ingestion module hoặc fixtures.
- Fusion không phụ thuộc private BM25 hoặc dense index object; fusion consume
  `list[SearchResult]`.
- Generation không được tạo citation giả. Citation chỉ được trỏ tới retrieved
  evidence chunks.
- UI code nên gọi module boundaries, không import private internals của module.
- Public boundaries có thể truyền Pydantic model instances hoặc dictionaries mà
  Pydantic validate được thành models tương ứng.

## Fixtures

Dùng `agentic_rag.testing.fixtures` cho phát triển độc lập:

- `sample_chunks()`
- `sample_search_results()`
- `sample_answer()`
