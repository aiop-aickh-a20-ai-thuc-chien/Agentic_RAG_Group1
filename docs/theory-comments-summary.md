# Tổng hợp comment theory RAG

Ngày tổng hợp: 31/05/2026

Tài liệu này gom các nội dung theory đã được comment trên GitHub Issues, sắp xếp lại theo thứ tự luồng RAG để cả nhóm dễ ôn tập, thuyết trình và đối chiếu khi làm phần code.

## Nguồn issue

| Thứ tự | Issue | Chủ đề | Trạng thái |
| --- | --- | --- | --- |
| 1 | [#135](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/135) | Ingestion Pipeline + Chunking | Done |
| 2 | [#142](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/142) | Research ingestion pipeline, metadata, chunking Q&A | Done |
| 3 | [#143](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/143) | Chunking cho từng loại file sau ingestion | Done |
| 4 | [#144](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/144) | Chunking sau khi normalize thành Markdown | Done |
| 5 | [#137](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/137) | Indexing, Retrieval, Generation | Done |
| 6 | [#140](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/140) | Indexing, Query, Sparse/Dense Retrieval | Done |
| 7 | [#141](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/141) | Hybrid Search, Reranker, Evidence Context, Citation | Done |
| 8 | [#139](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/139) | Evaluation + Guardrails | Done |

## 1. Ingestion Pipeline + Chunking

### 1.1. Tổng quan từ issue #135

Phần theory đầu tiên tập trung vào cách hệ thống RAG tiếp nhận tài liệu đầu vào, xử lý nội dung thô, làm sạch văn bản, gắn metadata và chia tài liệu thành chunk trước khi indexing/retrieval.

Flow cần nắm:

```text
PDF / URL / HTML / Text
-> Parse / Extract
-> Clean text
-> Attach metadata
-> Chunking
-> Clean chunks ready for indexing
```

Comment trạng thái:

- `NAT23042004`: "Dạ em đang xem ạ"
- `hotrandinhnguyen`: "Đã chia ra các subtask và hoàn thành"

### 1.2. Ingestion pipeline là gì

Ingestion pipeline là chuỗi xử lý giúp đưa tài liệu thô vào hệ thống RAG và biến nó thành dữ liệu có cấu trúc, có metadata, có thể chunk, index, retrieve và trích dẫn nguồn.

Nếu ingestion không tốt, hệ thống dễ gặp các lỗi:

- Parse sai nội dung tài liệu.
- Lấy cả menu, footer, quảng cáo hoặc noise vào chunk.
- Mất nguồn gốc trang, section hoặc file.
- Chunk bị đứt nghĩa hoặc quá dài.
- Retrieval trả về chunk kém liên quan.
- Citation không rõ ràng hoặc sai nguồn.

### 1.3. Các loại dữ liệu đầu vào

| Nguồn | Cách xử lý chính | Rủi ro cần chú ý |
| --- | --- | --- |
| PDF native | Extract text trực tiếp theo page/layout | Mất cột, mất bảng, text bị trộn |
| PDF scan | OCR từ ảnh | OCR sai dấu, sai ký tự, đứt dòng |
| PDF phức tạp | Layout-aware parsing, table extractor hoặc VLM | Bỏ sót bảng, figure, chart |
| URL/HTML | Fetch/render, parse DOM, extract main content | Lấy nhầm nav, footer, ads, script |
| Plain text | Normalize Unicode, clean whitespace, tách section | Thiếu cấu trúc, dễ chunk kém |

Với URL/HTML, điểm khó không chỉ là lấy được HTML mà là lấy đúng nội dung chính. Nếu giữ lại menu, footer, quảng cáo hoặc cookie banner, retrieval sẽ bị nhiễu.

### 1.4. Text cleaning

Các bước cleaning được comment trong issue #142:

- Normalize Unicode, ưu tiên NFC.
- Xóa zero-width characters, BOM và ký tự lỗi.
- Chuẩn hóa khoảng trắng.
- Sửa từ bị tách dòng.
- Sửa lỗi OCR phổ biến.
- Bỏ header/footer lặp lại.
- Decode HTML entities như `&amp;`, `&lt;`.
- Phát hiện ngôn ngữ nếu cần chọn tokenizer hoặc embedding model phù hợp.

Với tiếng Việt, cleaning quan trọng vì lỗi dấu thanh, từ ghép và encoding có thể làm sai nghĩa câu.

### 1.5. Metadata và source tracking

Metadata giúp hệ thống biết chunk đến từ đâu, nằm ở đâu trong tài liệu và dùng để citation.

Metadata tối thiểu nên có:

| Field | Ý nghĩa |
| --- | --- |
| `document_id` | Định danh tài liệu gốc |
| `chunk_id` | Định danh chunk |
| `source` | Nguồn hoặc tên tài liệu |
| `source_type` | `pdf`, `url`, `html`, `text`, `md`, ... |
| `file_name` | Tên file nếu có |
| `url` | Link gốc nếu đến từ web |
| `page` | Số trang nếu là PDF |
| `section` | Mục hoặc heading chứa chunk |
| `chunk_index` | Vị trí chunk trong tài liệu |
| `lang` | Ngôn ngữ |

Metadata dùng để filter retrieval, ưu tiên nguồn, debug, lấy neighbor chunks và tạo citation chính xác. Nếu thiếu metadata, hệ thống có thể tìm đúng nội dung nhưng không chứng minh được nguồn.

### 1.6. Chunking là gì

Chunking là quá trình chia tài liệu thành các đoạn nhỏ để embedding, indexing và retrieval hoạt động tốt hơn.

Mục tiêu của chunking:

- Đủ nhỏ để truy hồi chính xác.
- Đủ lớn để giữ ngữ nghĩa.
- Không cắt ngang ý quan trọng.
- Luôn giữ được metadata để citation.

Các chiến lược chunking:

| Chiến lược | Khi dùng | Rủi ro |
| --- | --- | --- |
| Fixed-size | Baseline, dễ làm, dễ benchmark | Dễ cắt đứt ý nghĩa |
| Sliding window | Văn bản liên tục, cần tránh mất ý ở biên | Tăng số chunk và chi phí |
| Semantic chunking | Tài liệu có đoạn/câu/heading rõ | Implementation khó hơn |
| Structure-aware | Manual, policy, technical docs, FAQ | Cần parser tốt |
| Table-aware | Bảng dài hoặc bảng nhiều header | Không được cắt mất header |
| Page-aware | PDF cần citation theo trang | Có thể đứt mạch giữa hai trang |

### 1.7. Chunk size và overlap

| Yếu tố | Quá nhỏ | Quá lớn |
| --- | --- | --- |
| Chunk size | Retrieval sắc hơn nhưng thiếu context | Giữ context nhưng dễ loãng và khó rank |
| Overlap | Ít trùng lặp, rẻ hơn | Giảm mất ngữ cảnh nhưng tăng noise và chi phí |

Không có chunk size đúng cho mọi bài toán. Cần chọn theo loại tài liệu, mục tiêu retrieval, embedding model, ngôn ngữ và độ chi tiết citation.

### 1.8. Chunking theo loại file sau ingestion

Từ issue #143, sau khi tài liệu đã được parse/extract/clean và có metadata, mỗi loại file nên có rule chunking riêng:

| Source type | Strategy | Ghi chú |
| --- | --- | --- |
| URL/HTML sạch | Heading/article-section aware | Tránh menu, footer, ads còn sót |
| TXT/plain text | Recursive paragraph/sentence fallback | Ít cấu trúc nên cần fallback |
| Markdown | Markdown-aware chunking | Giữ heading, list, table, code block |
| DOCX | Style/heading-aware chunking | Dựa vào Heading 1/2/3, list, table |
| Native PDF | Layout/structure-aware chunking | Giữ page, heading, table guard |
| OCR PDF | OCR-dependent + recursive/semantic | Cần quality flags và page boundary |
| PDF bảng phức tạp | Table-aware hoặc VLM/page chunking | Không cắt bảng tùy tiện |

Comment chia việc trong issue #143 đề xuất các nhóm: chunk schema chung, URL/HTML + TXT, DOCX/Markdown, native PDF, OCR PDF + bảng phức tạp, evaluation/Q&A.

### 1.9. Chunking sau khi normalize thành Markdown

Từ issue #144, giả định tất cả file sau ingestion được normalize thành Markdown nhưng metadata vẫn phải giữ nguồn gốc như `url`, `pdf_native`, `scan_pdf`, `docx`, `txt`.

Flow cần thống nhất:

```text
Load Markdown + metadata
-> Parse Markdown blocks
-> Group by heading/page
-> Protect table/code/image blocks
-> Recursive split long sections
-> Emit chunks with metadata
```

Quy tắc chính:

- Markdown-aware chunking tận dụng `#`, `##`, paragraph, list, table, code block.
- Metadata-aware chunking phải giữ `source_type`, `source_path`, `url`, `page_start`, `page_end`, `heading_path`, `section_id`, `parser_used`, `ocr`, `quality_flags`.
- Bảng Markdown không nên bị cắt mất header. Nếu bảng quá dài, split theo nhóm dòng và lặp lại header.
- Code block ngắn nên giữ nguyên.
- Image/caption/VLM summary nên đi cùng metadata ảnh hoặc page.
- Recursive fallback dùng khi section Markdown quá dài.

Kết luận quan trọng: normalize thành Markdown giúp chunking thống nhất hơn, nhưng không được xóa khác biệt nguồn. Khác biệt nguồn phải nằm trong metadata để phục vụ retrieval, filter, citation và debug.

## 2. Indexing, Retrieval, Generation

### 2.1. Tổng quan từ issue #137

Flow theory cần nắm:

```text
Clean chunks
-> BM25 index + Vector index

User question
-> Query processing
-> BM25 search + Dense search
-> RRF fusion
-> Evidence context
-> LLM generation
-> Answer with citation
```

Comment trạng thái:

- `hotrandinhnguyen`: "Đã chia ra thành các subtask và hoàn thành."

### 2.2. Keyword vs embedding

Từ issue #140, các điểm chính:

- BoW biểu diễn tài liệu bằng số lần xuất hiện của từ trong bộ từ vựng.
- TF-IDF giảm trọng số của từ quá phổ biến và tăng trọng số của từ đặc trưng.
- BM25 là bản nâng cấp của TF-IDF, dùng inverted index và có cơ chế bão hòa term frequency, phạt độ dài tài liệu.
- Embedding chuyển text thành dense vector để nắm ngữ nghĩa, giúp tìm được nội dung tương đồng dù không trùng keyword.
- Sparse retrieval mạnh với từ khóa chính xác, mã lỗi, tên hàm, thuật ngữ cụ thể.
- Dense retrieval mạnh với đồng nghĩa, diễn đạt tự nhiên, đa ngôn ngữ và ý nghĩa ngầm.

### 2.3. Indexing

Indexing là kỹ thuật cấu trúc lại dữ liệu để tối ưu tìm kiếm, sắp xếp và lọc. Trong RAG, có hai nhóm index chính:

| Index | Dùng cho | Cách hoạt động |
| --- | --- | --- |
| BM25/Inverted index | Keyword search | Lưu từ khóa -> danh sách document/chunk chứa từ đó |
| Vector index | Dense retrieval | Lưu embedding vector, tìm nearest neighbors bằng cosine/distance |

Vector index có thể dùng HNSW, IVF hoặc các cấu trúc ANN khác để tránh duyệt tuyến tính toàn bộ vector.

### 2.4. Query processing

Các kỹ thuật query transformation được comment:

- Query expansion: sinh thêm từ đồng nghĩa, khái niệm liên quan hoặc cách diễn đạt khác để tăng recall.
- Query decomposition: tách câu hỏi phức tạp thành nhiều sub-query nhỏ.
- Step-back prompting: sinh câu hỏi tổng quát hơn để lấy nền tảng kiến thức.
- HyDE: LLM tạo hypothetical document, embed đoạn giả định đó rồi dùng để tìm tài liệu thật.

HyDE giúp giảm khoảng cách giữa query ngắn và document dài, nhưng tài liệu giả định không được dùng làm evidence cuối cùng.

### 2.5. Hybrid search

Từ issue #141:

```text
User Query
-> BM25 Search -> Top-K BM25
-> Dense Vector Search -> Top-K Dense
-> Deduplication
-> RRF Fusion
-> Candidate Chunks
```

Hybrid search kết hợp:

- BM25 để không bỏ sót keyword, mã lỗi, điều khoản, tên riêng.
- Dense vector để bắt được ngữ nghĩa, đồng nghĩa và cách diễn đạt khác.

Mục tiêu của retrieval trong RAG là không bỏ sót evidence thật sự chứa câu trả lời.

### 2.6. RRF Fusion

RRF giải quyết vấn đề BM25 score và vector score khác thang đo, không thể cộng trực tiếp.

Công thức:

```text
RRF(d) = sum(1 / (k + rank_m(d)))
```

Trong đó:

- `d`: document/chunk.
- `m`: từng retriever, ví dụ BM25 và dense.
- `rank_m(d)`: thứ hạng của chunk trong retriever đó.
- `k`: hằng số làm mượt, thường khoảng 60.

RRF ưu tiên chunk được nhiều retriever xếp hạng cao, thay vì phụ thuộc score tuyệt đối.

### 2.7. Reranker

Reranker là tầng lọc thứ hai:

```text
Candidate chunks
-> Reranker
-> Sorted chunks
-> Top evidence chunks
```

So sánh:

| Thành phần | Mục tiêu | Đặc điểm |
| --- | --- | --- |
| Retriever | High recall | Rẻ, nhanh, quét toàn bộ corpus |
| Reranker | High precision | Đọc kỹ candidates, chậm hơn nhưng chính xác hơn |

Bi-Encoder mã hóa query và document độc lập, nhanh, có thể precompute document embedding. Cross-Encoder đưa query và document vào cùng model, chính xác hơn nhưng không scale cho toàn bộ corpus nên dùng làm reranker.

### 2.8. Evidence context

Evidence context là dữ liệu có cấu trúc được đóng gói từ top evidence chunks để đưa vào prompt LLM.

Một evidence nên có:

- `chunk_id`
- source/file/url
- page hoặc section
- score hoặc rank
- text evidence

Evidence context là ranh giới thông tin duy nhất mà LLM được phép dùng để trả lời, giúp giảm hallucination.

### 2.9. Citation và grounded generation

Citation là cơ chế gắn nguồn vào các claim trong câu trả lời. Có thể ở mức:

- Document-level: `[policy.pdf]`
- Page-level: `[policy.pdf, page 12]`
- Chunk-level: `[policy.pdf, chunk_045]`

Grounded generation nghĩa là LLM phải trả lời hoàn toàn dựa trên evidence context, không dùng tri thức ngoài tài liệu để bịa thêm. Nếu không đủ evidence, hệ thống phải trả lời không tìm thấy trong tài liệu và không tạo citation giả.

## 3. Evaluation + Guardrails

### 3.1. Tổng quan từ issue #139

Phần này do `hotrandinhnguyen` phụ trách. Mục tiêu là đánh giá cả pipeline RAG sau khi chạy: retrieval, generation, citation và guardrails.

Flow evaluation:

```text
User question
-> Retrieval lấy top-k chunks
-> LLM sinh câu trả lời
-> Trả lời kèm citation
-> Evaluation kiểm tra đúng/sai
```

Các điểm cần đánh giá:

- Retrieval có tìm đúng evidence không.
- Evidence đúng có nằm trong top 5 không.
- Evidence đúng nằm ở rank mấy.
- LLM có trả lời đúng dựa trên evidence không.
- Citation có trỏ đúng nguồn không.
- Câu hỏi ngoài tài liệu có được xử lý đúng không.

### 3.2. Test questions và ground truth evidence

Cần chuẩn bị ít nhất 10 câu hỏi test trên bộ tài liệu đã ingest, gồm:

- Câu hỏi có đáp án trực tiếp trong tài liệu.
- Câu hỏi cần hiểu một đoạn dài.
- Câu hỏi cần nhiều chunk để trả lời.
- Câu hỏi dễ gây nhầm.
- Câu hỏi ngoài scope để test guardrails.

Ground truth evidence là chunk/page/section chuẩn chứa câu trả lời đúng. Nó dùng để kiểm tra retrieval có tìm đúng evidence hay không.

### 3.3. Recall@5

Recall@5 đo xem trong 5 chunk đầu tiên có chứa evidence đúng không.

```text
Recall@5 = số câu retrieve được evidence đúng trong top 5 / tổng số câu hỏi in-scope
```

Recall@5 trả lời câu hỏi: trong 5 chunk đầu tiên, hệ thống có tìm thấy đoạn tài liệu đúng không?

### 3.4. MRR@5

MRR@5 đo evidence đúng nằm ở vị trí thứ mấy trong top 5.

```text
Reciprocal Rank = 1 / rank của evidence đúng đầu tiên
```

Nếu evidence đúng ở rank 1 thì điểm là 1.0. Nếu ở rank 5 thì điểm là 0.2. Nếu không nằm trong top 5 thì điểm là 0.

Recall@5 đo "có tìm thấy không". MRR@5 đo "tìm thấy ở vị trí cao hay thấp".

### 3.5. Failure analysis

Các nhóm lỗi chính:

| Error type | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| Retrieval error | Top 5 không có ground truth evidence | Kiểm tra parsing, chunking, BM25, embedding |
| Ranking error | Có evidence đúng nhưng rank thấp | Cải thiện fusion hoặc reranker |
| Generation error | Retrieval đúng nhưng answer sai | Cải thiện prompt, grounded generation |
| Citation error | Answer đúng nhưng citation sai | Kiểm tra metadata và citation mapping |
| Guardrail error | Out-of-scope nhưng vẫn trả lời | Thêm threshold, not_found rule |
| Ingestion/chunking error | Text sai, chunk đứt, metadata thiếu | Sửa pipeline đầu nguồn |

### 3.6. Guardrails

Guardrails cần đảm bảo:

- Chỉ trả lời dựa trên evidence.
- Nếu không có evidence đủ mạnh, trả lời "Không có trong tài liệu được cung cấp."
- Không tạo citation giả.
- Không trả lời ngoài scope tài liệu.
- Câu hỏi out-of-scope dùng để test guardrails, không tính Recall@5/MRR@5 như câu hỏi in-scope.

### 3.7. Metric mở rộng

Ngoài Recall@5 và MRR@5, có thể mở rộng:

- Faithfulness/Groundedness: claim trong answer có được evidence support không.
- Answer relevance: answer có trả lời đúng trọng tâm câu hỏi không.
- Context recall: retrieved context có bao phủ đủ evidence cần thiết không.
- Context precision: top-k context có bị nhiễu không.
- Hallucination rate: số claim không được support trên tổng số claim.
- RAGAS hoặc DeepEval nếu muốn đánh giá tự động sâu hơn.

### 3.8. Bảng evaluation nên chuẩn bị

| ID | Question | Expected Answer | Ground Truth Evidence | Retrieved Top 5 | Rank đúng | Recall@5 | MRR@5 | Answer | Citation | Error Type |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Q1 | Pin bảo hành bao lâu? | 8 năm hoặc 160.000 km | chunk_045 | 045,020,030,011,009 | 1 | 1 | 1.0 | Đúng | Đúng | None |
| Q2 | Điều kiện bảo hành? | Còn hạn, giấy tờ hợp lệ | chunk_021 | 010,021,022,030,044 | 2 | 1 | 0.5 | Đúng | Đúng | None |
| Q3 | Mất hóa đơn có bảo hành không? | Theo điều kiện tài liệu | chunk_033 | 011,020,030,040,050 | - | 0 | 0 | Sai | Sai | Retrieval error |
| Q4 | Giá cổ phiếu hôm nay? | Không có trong tài liệu | None | Không có evidence phù hợp | - | - | - | Đúng nếu từ chối | - | Guardrail test |

## 4. Tóm tắt luồng RAG end-to-end

```text
Raw documents
-> Ingestion
-> Clean text
-> Metadata
-> Chunking
-> BM25 index + Vector index
-> User question
-> Query processing
-> BM25 retrieval + Dense retrieval
-> RRF fusion
-> Optional rerank
-> Evidence context
-> Grounded LLM generation
-> Answer with citations
-> Evaluation + guardrails check
```

## 5. Các comment Done từ GitHub

- #139: `hotrandinhnguyen` comment đã họp và thuyết trình cho các thành viên trong nhóm.
- #140: `hotrandinhnguyen` comment đã thuyết trình phần indexing/query/sparse-dense retrieval, mọi người đã thảo luận và bổ sung chi tiết.
- #141: `hotrandinhnguyen` comment đã thuyết trình, thảo luận và bổ sung những phần cần thêm.
- #142: `hotrandinhnguyen` comment đã thuyết trình, thảo luận, review lại với nhau và thêm phần đầy đủ.
- #143: `hotrandinhnguyen` comment đã thuyết trình và bổ sung thêm nội dung sau thuyết trình.

