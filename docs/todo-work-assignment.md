# Phân chia công việc todo

Ngày tổng hợp: 31/05/2026

Tài liệu này tổng hợp các issue đang ở trạng thái `Ready` trong GitHub Project, ghi rõ người phụ trách, phạm vi công việc, output cần trả ra và phần việc của `hotrandinhnguyen`.

## Quy định chung cho các task code

Các task #145 đến #149 đều có cùng yêu cầu chung:

- RAGFlow không thay thế nhiệm vụ chính của từng người.
- RAGFlow chỉ dùng để bổ sung tạm phần chưa có để không bị block.
- RAGFlow có thể dùng làm baseline so sánh sau khi pipeline nhóm hoàn thiện.
- Sau này có thể so sánh pipeline tự build với RAGFlow theo retrieval, answer quality, citation, tốc độ và UX demo flow.

Mỗi người cần comment vào task của mình trước khi code:

- Tech/tool/framework dự định dùng.
- Lý do chọn.
- Tech nào còn đang nghiên cứu.
- Input/output của phần mình.
- Nếu dùng RAGFlow để bổ sung tạm thì ghi rõ dùng cho phần nào.

## Bảng phân chia tổng quan

| Thứ tự | Issue | Người phụ trách | Phạm vi | Output chính |
| --- | --- | --- | --- | --- |
| 1 | [#145](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/145) | NAT - `NAT23042004` | PDF ingestion + PDF chunking | `load_pdf_chunks(path: str) -> list[Chunk]` |
| 2 | [#146](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/146) | Dũng - `dung1308` | URL/Text ingestion + chunking | `load_url_chunks(...)`, `load_text_chunks(...)` |
| 3 | [#147](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/147) | Vinh - `ngthvinhrai` | Query + BM25/Dense indexing & retrieval | `preprocess_query`, `bm25_search`, `dense_search` |
| 4 | [#148](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/148) | TesWy - `TesWy` | Hybrid fusion + rerank + evidence context | `rrf_fusion`, `rerank`, `build_evidence_context` |
| 5 | [#149](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/149) | Nguyên - `hotrandinhnguyen` | Generation + citation + guardrails + UI | `generate_answer`, `validate_answer_with_citations`, app UI |

## Thứ tự tích hợp

```text
#145 PDF chunks
        \
         -> #147 BM25/Dense retrieval -> #148 Fusion/Rerank/Evidence -> #149 Generation/UI
        /
#146 URL/Text chunks
```

Phần #149 của `hotrandinhnguyen` phụ thuộc vào output evidence từ #148, nhưng vẫn có thể làm độc lập trước bằng mock `SearchResult` và mock `evidence_context`.

## Chi tiết từng phần

### Phần 1 - PDF ingestion + PDF chunking

Issue: [#145](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/145)

Người phụ trách: NAT - `NAT23042004`

Yêu cầu:

- Đọc PDF.
- Extract text theo page.
- Clean text cơ bản.
- Gắn metadata: `source`, `source_type`, `file_name`, `page`.
- Chunk nội dung PDF.
- Trả ra `list[Chunk]` theo schema chung.

Output:

```python
load_pdf_chunks(path: str) -> list[Chunk]
```

Tech cần comment:

- Parse PDF bằng `pypdf`, `PyMuPDF`, `pdfplumber` hoặc lựa chọn khác.
- Nếu PDF scan thì xử lý OCR hoặc fallback thế nào.
- Chunking dùng LangChain splitter, LlamaIndex splitter hoặc tự code.
- Cách giữ metadata page/source.

### Phần 2 - URL/Text ingestion + URL/Text chunking

Issue: [#146](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/146)

Người phụ trách: Dũng - `dung1308`

Yêu cầu:

- Nhập URL hoặc plain text.
- Fetch HTML.
- Parse HTML.
- Extract main content.
- Loại bỏ `script`, `style`, menu, footer, noise.
- Clean text.
- Gắn metadata: `source`, `source_type`, `url`, `section`.
- Chunk nội dung URL/text.
- Trả ra `list[Chunk]` theo schema chung.

Output:

```python
load_url_chunks(url: str) -> list[Chunk]
load_text_chunks(text: str, source: str) -> list[Chunk]
```

Tech cần comment:

- Fetch URL bằng `requests` hoặc `httpx`.
- HTML parsing bằng `BeautifulSoup`.
- Main content extraction bằng `trafilatura`, `readability-lxml`, `newspaper3k` hoặc lựa chọn khác.
- Chunking dùng splitter nào.
- Metadata URL/section lưu thế nào.

### Phần 3 - Query + BM25/Dense indexing & retrieval

Issue: [#147](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/147)

Người phụ trách: Vinh - `ngthvinhrai`

Input:

- Nhận `chunks` từ phần #145/#146.
- Có thể dùng `mock_chunks.json` để làm độc lập trước.

Yêu cầu:

- Query preprocessing.
- BM25 indexing.
- BM25 retrieval.
- Embedding chunks.
- Vector indexing.
- Dense retrieval.
- Trả ra BM25 top-k và Dense top-k theo `SearchResult` schema.

Output:

```python
preprocess_query(query: str) -> dict

build_bm25_index(chunks: list[Chunk])
bm25_search(query: str, top_k: int = 10) -> list[SearchResult]

build_vector_index(chunks: list[Chunk])
dense_search(query: str, top_k: int = 10) -> list[SearchResult]
```

Tech cần comment:

- BM25 library: `rank-bm25`, Elasticsearch/OpenSearch BM25 hoặc Whoosh.
- Embedding model: Gemini, OpenAI hoặc HuggingFace `sentence-transformers`.
- Vector index: FAISS, Qdrant, Chroma hoặc Elasticsearch dense vector.
- Query preprocessing: lowercase, normalize Unicode, remove extra spaces, Vietnamese tokenization nếu cần.

### Phần 4 - Hybrid fusion + rerank + evidence context

Issue: [#148](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/148)

Người phụ trách: TesWy - `TesWy`

Input:

- Nhận BM25 top-k và dense top-k từ phần #147.
- Có thể dùng mock để làm độc lập trước.

Yêu cầu:

- RRF fusion.
- Deduplicate chunks.
- Normalize/final rank.
- Optional rerank.
- Chọn final top-k evidence chunks.
- Build evidence context đưa sang LLM.

Output:

```python
rrf_fusion(
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
    top_k: int = 10,
) -> list[SearchResult]

rerank(
    query: str,
    candidates: list[SearchResult],
    top_k: int = 5,
) -> list[SearchResult]

build_evidence_context(
    evidence_chunks: list[SearchResult],
) -> str
```

Tech cần comment:

- Cách implement RRF.
- Có làm rerank không, nếu có dùng tech nào.
- Nếu chưa làm rerank thật thì fallback là gì.
- Evidence context format ra sao.
- Final top-k chọn bao nhiêu chunk.

### Phần 5 - Generation + citation + guardrails + UI

Issue: [#149](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/149)

Người phụ trách: Nguyên - `hotrandinhnguyen`

Đây là phần của bạn.

Input:

- Nhận final evidence chunks/evidence context từ phần #148.
- Có thể dùng mock evidence để làm độc lập khi #148 chưa xong.

Yêu cầu:

- Prompt LLM.
- Sinh câu trả lời dựa trên evidence context.
- Citation từ metadata.
- Guardrails:
  - Nếu không đủ evidence thì trả lời "Không có trong tài liệu được cung cấp."
  - Không tạo citation giả.
  - Không trả lời ngoài scope tài liệu.
- UI integration:
  - Upload PDF.
  - Nhập URL/text.
  - Hỏi đáp.
  - Hiển thị answer + citations.

Output:

```python
generate_answer(
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> dict

validate_answer_with_citations(
    answer: str,
    citations: list[dict],
    evidence_chunks: list[SearchResult],
) -> bool
```

Output khi trả lời được:

```python
{
    "answer": "Pin VF8 được bảo hành 8 năm hoặc 160.000 km.",
    "citations": [
        {
            "source": "vinfast_warranty.pdf",
            "page": 12,
            "chunk_id": "pdf_001_p12_c01",
        }
    ],
    "status": "answered",
}
```

Output khi không đủ evidence:

```python
{
    "answer": "Không có trong tài liệu được cung cấp.",
    "citations": [],
    "status": "not_found",
}
```

## Todo rõ cho `hotrandinhnguyen`

### 1. Comment tech vào issue #149 trước khi code

Nội dung cần comment:

- LLM dự định dùng: Gemini Flash/Pro, OpenAI hoặc local LLM.
- Lý do chọn LLM đó.
- Prompt format để answer bám evidence.
- Citation format.
- Guardrails kiểm tra bằng cách nào.
- UI dùng Streamlit, Gradio hoặc web app.
- Input/output nhận từ #148.
- Nếu dùng RAGFlow để bổ sung tạm thì dùng cho phần nào.

### 2. Làm generation boundary

Implement hoặc chuẩn bị module theo contract:

```python
generate_answer(
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> dict
```

Logic cần có:

- Nếu `evidence_chunks` rỗng hoặc evidence score không đủ, trả `status = "not_found"`.
- Prompt phải yêu cầu LLM chỉ dùng evidence context.
- Không cho phép answer có citation không nằm trong `evidence_chunks`.
- Không trả lời bằng kiến thức ngoài tài liệu.

### 3. Làm citation validation

Implement hoặc chuẩn bị:

```python
validate_answer_with_citations(
    answer: str,
    citations: list[dict],
    evidence_chunks: list[SearchResult],
) -> bool
```

Validation cần kiểm tra:

- Mỗi citation có `chunk_id` tồn tại trong evidence chunks.
- `source`, `page`, `section`, `url` lấy từ metadata thật.
- Không có citation giả.
- Nếu `status = "not_found"` thì `citations` phải rỗng.

### 4. Làm UI integration

UI cần có các workflow:

- Upload PDF.
- Nhập URL hoặc plain text.
- Trigger ingestion/retrieval/generation.
- Nhập câu hỏi.
- Hiển thị câu trả lời.
- Hiển thị citations rõ nguồn, page/section/chunk_id.
- Hiển thị trạng thái `answered` hoặc `not_found`.

### 5. Làm mock để không bị block

Nếu #145-#148 chưa hoàn thiện, dùng mock data:

- Mock `SearchResult`.
- Mock `evidence_context`.
- Mock `citations`.
- Mock UI flow với sample question.

Khi các phần trước xong, thay mock bằng output thật từ pipeline.

### 6. Checklist Done cho #149

- [ ] Có tech comment trên issue #149.
- [ ] `generate_answer(...)` chạy được với mock evidence.
- [ ] `validate_answer_with_citations(...)` phát hiện citation giả.
- [ ] Case đủ evidence trả `status = "answered"` và có citation.
- [ ] Case thiếu evidence trả `status = "not_found"` và không có citation.
- [ ] UI hỏi đáp được.
- [ ] UI hiển thị citation.
- [ ] Không trả lời ngoài scope tài liệu.
- [ ] Có README hoặc hướng dẫn chạy phần UI nếu thêm command mới.

## Dependency giữa các thành viên

| Người | Cần cung cấp cho người sau | Người phụ thuộc |
| --- | --- | --- |
| NAT | `list[Chunk]` từ PDF, metadata page/source | Vinh, Nguyên |
| Dũng | `list[Chunk]` từ URL/text, metadata url/section | Vinh, Nguyên |
| Vinh | BM25 top-k, dense top-k theo `SearchResult` | TesWy |
| TesWy | Final evidence chunks + evidence context | Nguyên |
| Nguyên | Answer + citations + UI demo | Cả nhóm demo |

## Gợi ý nhịp làm việc

1. Mỗi người comment tech choice vào issue của mình.
2. #145 và #146 làm song song ingestion.
3. #147 làm retrieval bằng mock trước, sau đó thay bằng chunks thật.
4. #148 làm RRF/evidence bằng mock trước, sau đó thay bằng retrieval thật.
5. #149 làm generation/UI bằng mock trước, sau đó nối pipeline thật.
6. Cả nhóm chạy end-to-end: upload/ingest -> retrieve -> answer -> citation.
7. Chuẩn bị câu hỏi demo và case out-of-scope để test guardrails.

