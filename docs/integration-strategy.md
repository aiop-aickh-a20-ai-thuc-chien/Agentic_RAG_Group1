# Hướng dẫn ghép module, mock và RAGFlow

Ngày tạo: 31/05/2026

Tài liệu này hướng dẫn cách mỗi thành viên làm độc lập phần của mình, dùng mock hoặc RAGFlow khi phần trước chưa xong, nhưng vẫn giữ pipeline chính sạch và dễ ghép.

## Nguyên tắc chung

Mọi module chỉ trao đổi dữ liệu qua contract chung:

- `Chunk`
- `SearchResult`
- `Citation`
- `Answer`

Không module nào nên phụ thuộc trực tiếp vào format riêng của người khác hoặc format raw của RAGFlow. Nếu dữ liệu đến từ RAGFlow, phải đi qua adapter trong `agentic_rag.integrations.ragflow` trước.

## Vị trí thư mục

```text
src/agentic_rag/
  core/                     # contract chung
  ingestion/                # PDF, URL, text ingestion chính của nhóm
  retrieval/                # BM25/dense, fusion, rerank
  generation/               # answer, citation, guardrails
  integrations/
    ragflow/                # adapter/fallback cho RAGFlow
  testing/
    fixtures.py             # mock dùng chung
  app.py                    # UI/orchestrator
```

RAGFlow không đặt trong `src/agentic_rag/ingestion`, `retrieval` hoặc `generation` vì đó là pipeline tự build của nhóm. RAGFlow chỉ là baseline, fallback hoặc nguồn dữ liệu tạm.

## Pattern làm việc

```text
Nếu phần trước chưa xong
-> dùng fixture hoặc RAGFlow adapter
-> code phần của mình theo contract chung
-> khi phần trước xong thì thay input tạm bằng output thật
```

Điểm quan trọng: interface không đổi khi chuyển từ mock/RAGFlow sang module thật.

## Dùng fixture khi bị block

Fixture nằm ở:

```text
src/agentic_rag/testing/fixtures.py
```

Các mock hiện có:

- `sample_chunks()`
- `sample_search_results()`
- `sample_answer()`
- `sample_ragflow_chunk_payload()`
- `sample_ragflow_hit_payload()`
- `sample_ragflow_answer_payload()`

Ví dụ người làm retrieval có thể dùng:

```python
from agentic_rag.testing.fixtures import sample_chunks

chunks = sample_chunks()
```

Ví dụ người làm generation có thể dùng:

```python
from agentic_rag.testing.fixtures import sample_search_results

evidence_chunks = sample_search_results()
```

## Dùng RAGFlow adapter

Adapter nằm ở:

```text
src/agentic_rag/integrations/ragflow/adapters.py
```

Các hàm chính:

```python
chunk_from_ragflow_payload(payload) -> Chunk
search_result_from_ragflow_hit(payload) -> SearchResult
citations_from_search_results(evidence_chunks) -> list[Citation]
answer_from_ragflow_payload(payload, evidence_chunks=...) -> Answer
```

Ví dụ đổi retrieval hit từ RAGFlow sang `SearchResult`:

```python
from agentic_rag.integrations.ragflow import search_result_from_ragflow_hit

result = search_result_from_ragflow_hit(raw_hit)
```

Ví dụ đổi answer từ RAGFlow sang `Answer`:

```python
from agentic_rag.integrations.ragflow import answer_from_ragflow_payload

answer = answer_from_ragflow_payload(raw_answer, evidence_chunks=evidence_chunks)
```

## Cách từng người dùng

### NAT - phần #145

NAT ít phụ thuộc phần trước. Output cần trả là:

```python
load_pdf_chunks(path: str) -> list[Chunk]
```

Nếu muốn so sánh với RAGFlow, có thể dùng adapter để đổi chunk/export từ RAGFlow thành `Chunk`, nhưng code chính vẫn phải sinh `Chunk` từ PDF parser của nhóm.

### Dũng - phần #146

Dũng cũng ít phụ thuộc phần trước. Output cần trả là:

```python
load_url_chunks(url: str) -> list[Chunk]
load_text_chunks(text: str, source: str) -> list[Chunk]
```

Nếu dùng RAGFlow để kiểm tra baseline, chỉ dùng ở tầng adapter, không đưa raw payload vào ingestion chính.

### Vinh - phần #147

Nếu #145/#146 chưa xong, Vinh dùng:

```python
from agentic_rag.testing.fixtures import sample_chunks
```

Khi cần thử RAGFlow:

```python
from agentic_rag.integrations.ragflow import chunk_from_ragflow_payload
```

Sau đó build BM25/vector index trên `list[Chunk]` như bình thường.

### TesWy - phần #148

Nếu #147 chưa xong, TesWy dùng:

```python
from agentic_rag.testing.fixtures import sample_search_results
```

Hoặc đổi RAGFlow retrieval hit thành `SearchResult`:

```python
from agentic_rag.integrations.ragflow import search_result_from_ragflow_hit
```

Sau đó code `rrf_fusion`, `rerank`, `build_evidence_context` trên `list[SearchResult]`.

### Nguyên - phần #149

Nếu #148 chưa xong, Nguyên dùng:

```python
from agentic_rag.testing.fixtures import sample_search_results
```

Hoặc dùng RAGFlow adapter:

```python
from agentic_rag.generation.evidence import evidence_for_question
```

Phần generation/UI vẫn phải nhận:

```python
generate_answer(question, evidence_context, evidence_chunks)
```

Không viết UI phụ thuộc trực tiếp vào raw output của RAGFlow.

Nếu cần dùng RAGFlow trước khi #145-#148 hoàn thành:

```text
RAGFlow upload/list chunks/retrieve
-> agentic_rag.integrations.ragflow.providers
-> list[Chunk] hoặc list[SearchResult]
-> generation của project
```

Các file chính:

```text
src/agentic_rag/integrations/ragflow/client.py
src/agentic_rag/integrations/ragflow/providers.py
src/agentic_rag/generation/evidence.py
src/agentic_rag/observability/trace.py
```

## Khi ghép end-to-end

Thứ tự ghép:

```text
PDF/URL/Text -> list[Chunk]
list[Chunk] -> BM25/Dense SearchResult
SearchResult -> fused/reranked evidence
evidence -> Answer + Citation
Answer -> UI
```

Nếu một phần chưa xong, thay phần đó bằng fixture hoặc RAGFlow adapter nhưng vẫn giữ cùng contract.

## Checklist cho Pull Request

- [ ] Module chỉ import contract từ `agentic_rag.core.contracts`.
- [ ] Không truyền raw RAGFlow payload qua module chính.
- [ ] Nếu dùng RAGFlow, đã convert qua `agentic_rag.integrations.ragflow`.
- [ ] Có test cho case mock hoặc adapter.
- [ ] Không thay đổi `Chunk`, `SearchResult`, `Citation`, `Answer` nếu chưa thống nhất nhóm.
- [ ] Quality gate pass: `ruff`, `mypy`, `pytest`.

