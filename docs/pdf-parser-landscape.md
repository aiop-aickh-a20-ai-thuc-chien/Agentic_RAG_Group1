# Landscape parser PDF cho RAG

Tài liệu này tóm tắt các hướng parser PDF phổ biến và SOTA để nhóm có cái nhìn
tổng quan trước khi quyết định tối ưu pipeline ingestion. Pipeline hiện tại vẫn
giữ `docling` làm mặc định vì đánh giá dữ liệu thật kết luận baseline "Keep but
tune": text và asset export đủ dùng, nhưng page metadata và mapping asset-chunk
còn yếu.

## Cách đọc nhanh

| Nhóm | Công cụ đại diện | Mục tiêu chính | Khi nên dùng |
| --- | --- | --- | --- |
| Text-only baseline | `pypdf` | Lấy text nhanh, ít dependency | Control baseline, PDF text đơn giản |
| Table/layout inspection | `pdfplumber` | Text, bảng, object layout cấp thấp | PDF có bảng/form cần kiểm tra thủ công |
| Markdown/RAG-oriented | `docling`, `pymupdf4llm` | Convert PDF sang Markdown cho LLM/RAG | Pipeline cần Markdown/chunking ngay |
| OCR/model-heavy local | Unstructured, Marker, MinerU | Layout phức tạp, scan, bảng, công thức | Khi baseline miss nội dung quan trọng |
| Cloud/VLM parser | LlamaParse, VLM tự quản | Chất lượng cao hoặc parsing theo instruction | Khi chấp nhận API key, chi phí, latency |

## Parser đã implement trong repo

### Docling

- Vai trò: parser mặc định.
- Điểm mạnh: Markdown khá tốt cho tài liệu tiếng Việt, export được bảng/hình
  qua helper multimodal, phù hợp baseline end-to-end.
- Điểm yếu hiện tại: `Chunk.metadata["page"]` vẫn là `None`; asset đang gắn vào
  chunk đầu tiên trong helper multimodal v1; một số mục lục/form có spacing
  noise.
- Dùng khi: cần pipeline ổn định, không muốn thay behavior mặc định.

### pypdf

- Vai trò: control baseline text-only.
- Điểm mạnh: nhẹ, dễ cài, API đơn giản để extract text từng page.
- Điểm yếu: không phải parser layout/RAG chuyên dụng; bảng, heading, reading
  order phức tạp thường kém hơn layout-aware parser.
- Dùng khi: muốn biết "plain text extraction" đạt được mức nào trước khi dùng
  parser nặng hơn.

### pdfplumber

- Vai trò: baseline kiểm tra text và bảng.
- Điểm mạnh: có API extract text, table, và object layout cấp thấp; hữu ích khi
  review PDF form/table-heavy.
- Điểm yếu: không tự sinh Markdown semantic hoàn chỉnh; cần adapter để chuyển
  table sang Markdown và vẫn cần chunking riêng.
- Dùng khi: cần so sánh table/form extraction với Docling.

### PyMuPDF4LLM

- Vai trò: Markdown/RAG-oriented alternative.
- Điểm mạnh: API `to_markdown()` nhắm trực tiếp tới output Markdown cho LLM/RAG,
  có nhiều option về page chunks, image/table handling và OCR.
- Điểm yếu: phụ thuộc PyMuPDF; cần chú ý license AGPL/commercial trước khi dùng
  trong sản phẩm thương mại.
- Dùng khi: muốn so sánh Markdown output nhanh với Docling trên cùng PDF.

## Parser khảo sát, chưa implement ở v1

### Unstructured

Unstructured phù hợp khi cần chiến lược partition đa dạng cho PDF, bao gồm các
mode OCR/layout nặng hơn. Đây là candidate tốt cho scan PDF hoặc tài liệu nhiều
layout, nhưng kéo theo dependency/runtime lớn hơn nên nên để optional hook sau.

### Marker

Marker là hướng model-heavy local, convert document sang Markdown/JSON/chunks và
có khả năng xử lý bảng, forms, equations, images. Nó mạnh cho tài liệu phức tạp
nhưng phụ thuộc PyTorch/model weights và có ràng buộc license, nên chưa nên đưa
vào default CI/runtime.

### MinerU

MinerU tập trung biến PDF/document phức tạp thành Markdown/JSON sẵn cho LLM. Đây
là candidate SOTA/open-source đáng khảo sát cho tài liệu nhiều layout, nhưng chi
phí cài đặt và runtime cao hơn nhóm parser nhẹ.

### LlamaParse

LlamaParse là cloud parser, phù hợp khi cần parser chất lượng cao, instruction
parsing, hoặc không muốn tự vận hành model layout/OCR. Tradeoff là API key, chi
phí, network dependency, và governance dữ liệu.

### VLM/cloud parser tự quản

VLM parser có thể xử lý hình ảnh, form, chart, bảng phức tạp bằng cách render
page sang image rồi gọi model. Đây là hướng mạnh nhất cho tài liệu scan hoặc
visual-heavy, nhưng cũng đắt nhất về latency, chi phí và kiểm soát hallucination.

## Quy tắc triển khai trong repo

- Public contract vẫn là `Chunk`; không thêm model framework-specific vào
  `agentic_rag.core`.
- Parser mới phải đi qua registry PDF-local và lazy import dependency.
- `load_pdf_chunks(path)` vẫn mặc định dùng Docling.
- Parser khác dùng `load_pdf_chunks(path, parser_name="pypdf")` hoặc
  `LOCAL_PDF_PARSER=pypdf`.
- Chunker mặc định là `docling-hybrid`. Dùng
  `load_pdf_chunks(path, chunker_name="deterministic")` hoặc
  `LOCAL_PDF_CHUNKER=deterministic` khi cần fallback/baseline deterministic.
- `save_pdf_ingestion_artifacts(..., parser_name=...)` dùng để xuất artifact so
  sánh Markdown/chunk.
- `save_pdf_multimodal_artifacts()` tạm thời Docling-only vì đang phụ thuộc
  document object của Docling để export assets.
- Generated files trong `.data/` không được commit.

## Tài liệu tham khảo chính

- Docling: https://docling-project.github.io/docling/
- PyMuPDF4LLM API: https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html
- pdfplumber: https://github.com/jsvine/pdfplumber
- pypdf text extraction: https://pypdf.readthedocs.io/en/stable/user/extract-text.html
- Unstructured partitioning: https://docs.unstructured.io/open-source/core-functionality/partitioning
- Marker: https://github.com/datalab-to/marker
- MinerU: https://github.com/opendatalab/MinerU
- LlamaParse: https://developers.llamaindex.ai/llamaparse/parse/
