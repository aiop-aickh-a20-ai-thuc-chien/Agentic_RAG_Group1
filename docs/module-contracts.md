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

### `ConversationMessage`

Một tin nhắn hội thoại truyền vào Workflow boundary.

Required fields:

- `role: str`
- `content: str`

### `WorkflowRunInput`

Input chuẩn hóa cho một lượt chạy Workflow.

Required fields:

- `question: str`

Default fields:

- `history: list[ConversationMessage] = []`
- `document_ids: list[str] | None = None`

### `WorkflowRunOutput`

Output chuẩn hóa cho một lượt chạy Workflow.

Required fields:

- `answer: Answer`

Default fields:

- `evidence_chunks: list[SearchResult] = []`
- `queries_tried: list[str] = []`
- `steps: list[dict[str, Any]] = []`

## Workflow node contracts

`AgentState` vẫn là `TypedDict` nội bộ vì LangGraph dùng state schema này cho
channels và reducers. Mỗi node trong `agentic_rag.agent.nodes` phải trả về
strict, frozen Pydantic model được định nghĩa trong
`agentic_rag.agent.node_contracts`.

Các node output là partial state updates. Field không áp dụng cho một nhánh phải
để unset thay vì trả về giá trị mặc định, để LangGraph không ghi đè state hiện
có. Trace entries và metadata linh hoạt vẫn giữ dạng `dict[str, Any]` bên trong
Pydantic node output; chúng không phải shared cross-module contracts.

### `RetrievalInput`

Input chuẩn hóa cho provider retrieval.

Required fields:

- `question: str`

Default fields:

- `document_ids: list[str] | None = None`
- `page_size: int | None = None`

### `RetrievalOutput`

Output chuẩn hóa từ source evidence provider.

Default fields:

- `results: list[SearchResult] = []`

### `EvidenceResolutionInput`

Input chuẩn hóa cho bước resolve evidence trước generation.

Required fields:

- `question: str`

Optional and default fields:

- `evidence_context: str | None = None`
- `evidence_chunks: list[SearchResult] | None = None`
- `provider: str | None = None`
- `document_ids: list[str] | None = None`
- `use_mock_evidence: bool = False`

### `EvidenceResolutionOutput`

Output chuẩn hóa của bước resolve evidence.

Required fields:

- `context: str`

Default fields:

- `chunks: list[SearchResult] = []`

### `SourceDocumentUpload`

Kết quả trả về sau khi source document được provider nhận để index.

Required fields:

- `document_id: str`
- `name: str`
- `dataset_id: str`
- `parse_started: bool`

Optional fields:

- `trace: dict[str, object] | None`

### `SourceDocumentChunks`

Danh sách chunk của một source document kèm tổng số chunk trước pagination.

Required fields:

- `chunks: list[Chunk]`
- `total_chunks: int`

## Các phần implementation

| Phần | Boundary kỳ vọng |
| --- | --- |
| PDF ingestion + chunking | `agentic_rag.ingestion.pdf.load_pdf_chunks(path: str) -> list[Chunk]` |
| URL ingestion + chunking | `agentic_rag.ingestion.url.load_url_chunks(url: str) -> list[Chunk]` |
| Workflow run | `run_agent(provider, request: WorkflowRunInput) -> WorkflowRunOutput` |
| Source retrieval | `SourceEvidenceProvider.retrieve(request: RetrievalInput) -> RetrievalOutput` |
| Evidence resolution | `evidence_for_question(request: EvidenceResolutionInput) -> EvidenceResolutionOutput` |
| Query + BM25/dense retrieval | `agentic_rag.retrieval.search.preprocess_query(...)`, `bm25_search(...)`, `dense_search(...)` |
| Hybrid fusion + evidence context | `agentic_rag.retrieval.fusion.rrf_fusion(...)`, `rerank(...)`, `build_evidence_context(...)` |
| Generation + citations + UI | `agentic_rag.generation.answering.generate_answer(...)`, `validate_answer_with_citations(...)`, `agentic_rag.app.run_app()` |
| Evaluation report | `agentic_rag.evaluation.metrics.recall_at_k(...)`, `mrr_at_k(...)` |

Protocol definitions nằm trong `agentic_rag.core.ports`.

## Shared ingestion chunking

PDF và URL/text parser không tự tách chunk trực tiếp. Parser nên normalize nội
dung về Markdown/text, sau đó truyền qua boundary dùng chung trong
`agentic_rag.ingestion.chunking`.

Các primitive dùng chung:

- `ChunkingInput`: input đã normalize trước khi chunking.
- `ChunkCandidate`: text chunk candidate trước khi map sang shared `Chunk`.
- `Chunker`: protocol tối thiểu với `chunk(input) -> list[ChunkCandidate]`.

PDF và URL/text loader vẫn chịu trách nhiệm map `ChunkCandidate` sang `Chunk`
với metadata riêng của từng source. Không đưa metadata đặc thù PDF/URL vào
top-level contract mới nếu chỉ một source dùng.

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
- `sample_knowledge_quality_chunks()`
- `sample_search_results()`
- `sample_answer()`
