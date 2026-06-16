# PDF Ingestion Subproject

Thư mục này là boundary riêng cho PDF ingestion. Những phần chỉ phục vụ PDF
ingestion, bao gồm parser baseline, PDF parser registry và benchmark parser,
được giữ trong thư mục này để không làm rò rỉ trách nhiệm sang module khác.
Các primitive chunking dùng chung nằm ở `agentic_rag.ingestion.chunking` để PDF
và URL/text ingestion có thể dùng cùng một nền tảng tách nội dung.

## Mục tiêu hiện tại

Phase hiện tại ưu tiên tạo baseline end-to-end để unblock các phase tiếp theo
của RAG pipeline. Parser mặc định là Docling: module PDF dùng Docling để chuyển
PDF cục bộ sang Markdown, sau đó tách Markdown thành `Chunk` objects theo
contract dùng chung. Pipeline mặc định là `ocr/docling`; chunker mặc định là
`deterministic` để giữ output ổn định và dễ debug. Docling HybridChunker vẫn
có thể bật rõ ràng để so sánh chất lượng chunking native. Kiến trúc mới giữ
parser và chunker là hai strategy riêng: parser chịu trách nhiệm tạo
Markdown/file-backed assets/native document, còn chunker chịu trách nhiệm tách
output parser thành chunk candidate.

Benchmark workflow với OmniDocBench vẫn được giữ để so sánh và tối ưu parser ở
các vòng sau. Nói cách khác: triển khai Docling trước để có pipeline chạy được,
rồi dùng benchmark và review thủ công để quyết định thay thế hoặc tinh chỉnh
parser sau. Tổng quan các parser phổ biến/SOTA nằm ở
`docs/pdf-parser-landscape.md`.

## Kiến trúc parser/chunker

PDF parser trong repo là Markdown-first, asset-aware và chunker-independent:

- `PdfMarkdownParser`: adapter chuyển một PDF thành `PdfParseResult`.
- `PdfParseResult`: chứa full Markdown, tên parser, source path, warnings,
  metadata và danh sách `PdfAssetRef`.
- `PdfAssetRef`: reference tới asset đã ghi ra file, dùng cho hậu xử lý bảng,
  hình ảnh hoặc chart; không nhúng binary/object vào shared `Chunk`.
- `PdfChunkingInput`: compatibility subclass của shared `ChunkingInput`, gồm
  Markdown và optional parser-native document.
- `MarkdownChunker`: PDF compatibility protocol cho shared chunking boundary,
  tách input đã normalize thành chunk candidate.
- `load_pdf_chunks()`: facade ghép parser + chunker + mapper để trả về
  `list[Chunk]` theo contract chung.

Parser comparison nên so sánh Markdown và artifact parser trước. Chunking
comparison là tầng riêng: giữ parser output cố định rồi thay chunker. Agentic
orchestration, nếu dùng sau này, nên nằm phía trên các tool deterministic này để
chọn parser, chạy fallback và ghi trace; agent không thay thế parser core.
PDF chunker strategy dùng `agentic_rag.ingestion.chunking` làm shared source of
truth; module `agentic_rag.ingestion.pdf.chunking` chỉ là compatibility export
cho các import cũ.

## Chạy PDF ingestion baseline

Từ root repository:

```bash
uv sync
uv run python -c "from agentic_rag.ingestion.pdf import load_pdf_chunks; print(load_pdf_chunks('path/to/file.pdf'))"
```

Để test parser cục bộ bằng command line và một file path cụ thể, dùng CLI
PDF-local. CLI đọc mặc định từ `.env`, nhưng vẫn cho phép override bằng argument:

```bash
uv run python -m agentic_rag.ingestion.pdf.cli parse path/to/file.pdf \
  --pipeline ocr \
  --strategy docling \
  --chunker deterministic \
  --output-json
```

Nếu đã cấu hình `.env`, có thể chạy ngắn hơn:

```bash
uv run python -m agentic_rag.ingestion.pdf.cli parse path/to/file.pdf --output-json
```

Ghi artifact debug theo layout chuẩn của PDF ingestion:

```bash
uv run python -m agentic_rag.ingestion.pdf.cli parse path/to/file.pdf \
  --pipeline ocr \
  --strategy docling \
  --chunker docling-page-aware \
  --write-artifacts \
  --output-root storage/local_pdf/parser-artifacts \
  --run-id manual-check
```

Lệnh này tạo `parsed.md`, `chunks.jsonl`, `chunks.md` và `manifest.json` trong
thư mục run tương ứng.

Ví dụ smoke test với PDF thật đã có trong repo:

```bash
uv run python -m agentic_rag.ingestion.pdf.cli parse \
  src/agentic_rag/ingestion/pdf/.data/VF3-ERG_VN_V4.pdf \
  --pipeline ocr \
  --strategy docling \
  --chunker docling-page-aware \
  --write-artifacts \
  --output-root tmp/pdf-cli-artifacts \
  --run-id vf3-local-test
```

Kiểm tra output:

```bash
RUN_DIR="tmp/pdf-cli-artifacts/vf3_erg_vn_v4/vf3_local_test"

cat "$RUN_DIR/manifest.json"
sed -n '1,120p' "$RUN_DIR/parsed.md"
sed -n '1,120p' "$RUN_DIR/chunks.md"
head -n 3 "$RUN_DIR/chunks.jsonl"
```

Một số dòng log như `RapidOCR returned empty result!` hoặc warning OCR không có
text có thể xuất hiện với vùng/page không OCR được. Nếu command vẫn in
`Wrote parser artifacts to ...` thì artifact đã được ghi thành công.

Public API của module vẫn là:

```python
from agentic_rag.ingestion.pdf import load_pdf_chunks

chunks = load_pdf_chunks("path/to/file.pdf")
```

Chọn parser hoặc chunker khác khi registry đã có adapter tương ứng:

```python
chunks = load_pdf_chunks(
    "path/to/file.pdf",
    pipeline_name="ocr",
    strategy_name="docling",
    chunker_name="deterministic",
)
```

Parser pipeline registry hiện có:

- `ocr/docling`: mặc định, baseline OCR/layout/text hiện tại.
- `vlm/mineru`: seam cho VLM parser; hiện fail rõ ràng cho tới khi dependency
  và execution mode của MinerU được wire trong bước riêng.

Chunker registry hiện có:

- `deterministic`: mặc định, tách Markdown/text ổn định bằng shared
  ingestion chunking.
- `docling-page-aware`: dùng Docling native document provenance để tách nội dung
  theo trang trước khi áp dụng deterministic chunking; phù hợp khi cần citation
  PDF có `page`/`page_range`.
- `docling-hybrid`: opt-in, dùng `Docling HybridChunker` trên Docling native
  document để giữ ngữ cảnh/heading tốt hơn cho PDF.

Trong app local, có thể đổi parser hoặc chunker PDF bằng biến môi trường:

```text
LOCAL_PDF_PIPELINE=ocr
LOCAL_PDF_STRATEGY=docling
# Legacy alias for LOCAL_PDF_STRATEGY during transition:
LOCAL_PDF_PARSER=docling
LOCAL_PDF_CHUNKER=deterministic
```

Khi cần so sánh với chunker native của Docling:

```text
LOCAL_PDF_CHUNKER=docling-hybrid
```

Khi cần ưu tiên citation theo trang từ Docling provenance:

```text
LOCAL_PDF_CHUNKER=docling-page-aware
```

`load_pdf_chunks()` chỉ trả về `Chunk` trong memory và không tự ghi file debug.
Nếu cần lưu output để kiểm tra parser hoặc đánh giá chunking, dùng helper riêng
được mô tả ở phần bên dưới.

Mỗi `Chunk` trả về có metadata chính:

- `source`: đường dẫn PDF đầu vào.
- `source_type`: luôn là `pdf`.
- `file_name`: tên file PDF.
- `page`: hiện là `None` trong baseline Markdown chunking.
- `pages`: có khi dùng `docling-page-aware`; lưu danh sách trang provenance đầy
  đủ nếu item gốc trải trên nhiều trang.
- `page_range`: có khi dùng `docling-page-aware` và parser cung cấp page
  provenance.
- `section`: heading path dạng chuỗi nếu parser/chunker cung cấp.
- `section_path`: danh sách heading đầy đủ nếu dùng Docling HybridChunker.
- `raw_text`: nội dung gốc của Docling chunk trước khi contextualize, nếu dùng
  Docling HybridChunker.
- `parser`: parser được chọn, mặc định là `docling`.
- `chunking_method`: chunker được chọn, mặc định là `deterministic`.
- `chunk_index`: thứ tự chunk bắt đầu từ 1.
- `page_number`: shared-schema alias for `page`; `None` when no page provenance.
- `heading`: shared-schema alias for `section`.
- `breadcrumb`: shared-schema alias for `section_path` or `[section]`.
- `token_count`: approximate token/word count for the chunk.
- `updated_date`: required shared-schema timestamp from the PDF load start time.
- `updated_date_source`: currently `ingestion_start`.

Shared metadata rule:

- `source_type` is required and must be `pdf` for PDF ingestion.
- `updated_date` is required and must be non-empty. In this project it means the
  time this system started loading the PDF.
- `created_date` is optional. Add it only when a PDF parser extracts trusted
  source modified metadata from inside the PDF. Do not derive it from filesystem
  ctime/mtime.
- `language` is optional. Add it only when the parser or enrichment step can
  identify it.
- `document_type` is optional. PDF ingestion should only add it when a parser or
  enrichment step can prove the document type.

## Lưu artifact để debug và đánh giá

Khi cần quan sát Markdown sau parser và danh sách chunk sau chunking, chạy helper
rõ ràng thay vì thêm side effect vào loader chính:

```bash
uv run python -c "from agentic_rag.ingestion.pdf import save_pdf_ingestion_artifacts; print(save_pdf_ingestion_artifacts('path/to/file.pdf').model_dump())"
```

Khi muốn xuất artifact bằng parser khác đã được đăng ký:

```bash
uv run python -c "from agentic_rag.ingestion.pdf import save_pdf_ingestion_artifacts; print(save_pdf_ingestion_artifacts('path/to/file.pdf', parser_name='docling').model_dump())"
```

Hoặc dùng CLI PDF-local từ root repository:

```bash
uv run python -m agentic_rag.ingestion.pdf.cli parse path/to/file.pdf \
  --pipeline ocr \
  --strategy docling \
  --chunker docling-page-aware \
  --write-artifacts \
  --output-root src/agentic_rag/ingestion/pdf/.data/parser-comparison \
  --run-id docling-baseline
```

Mặc định helper ghi vào thư mục đã được ignore:

```text
src/agentic_rag/ingestion/pdf/.data/artifacts/<pdf-stem>/<run-id>/
  parsed.md
  chunks.jsonl
  chunks.md
  manifest.json
```

Ý nghĩa các file:

- `parsed.md`: Markdown do parser được chọn export từ PDF gốc.
- `chunks.jsonl`: mỗi dòng là một shared `Chunk` sau bước chunking.
- `chunks.md`: companion file dễ đọc để debug chunk bằng mắt; `chunks.jsonl`
  vẫn là artifact canonical cho máy đọc/replay.
- `manifest.json`: metadata của lần chạy, gồm input path, parser, run id, đường
  dẫn artifact và số lượng chunk.

Không commit nội dung trong `.data/`; đây chỉ là dữ liệu phục vụ debug và
evaluation cục bộ.

## Lưu artifact đa phương thức

Khi cần giữ lại bảng, hình ảnh hoặc chart candidate để hậu xử lý, dùng helper
rõ ràng thay vì thêm side effect vào `load_pdf_chunks()`. Với CLI PDF-local:

```bash
uv run python -m agentic_rag.ingestion.pdf.cli parse path/to/file.pdf \
  --write-multimodal-artifacts \
  --output-root src/agentic_rag/ingestion/pdf/.data/parser-comparison \
  --run-id docling-multimodal
```

Ví dụ với PDF thật:

```bash
uv run python -m agentic_rag.ingestion.pdf.cli parse \
  src/agentic_rag/ingestion/pdf/.data/VF3-ERG_VN_V4.pdf \
  --write-multimodal-artifacts \
  --output-root tmp/pdf-multimodal-artifacts \
  --run-id vf3-image-test
```

Kiểm tra output multimodal:

```bash
RUN_DIR="tmp/pdf-multimodal-artifacts/vf3_erg_vn_v4/vf3_image_test"

sed -n '1,120p' "$RUN_DIR/parsed.md"
sed -n '1,20p' "$RUN_DIR/elements.jsonl"
find "$RUN_DIR/assets" -maxdepth 3 -type f | sort
```

Nếu cần gọi bằng Python thay vì CLI, dùng helper tương ứng:

```bash
uv run python -c "from agentic_rag.ingestion.pdf import save_pdf_multimodal_artifacts; print(save_pdf_multimodal_artifacts('path/to/file.pdf').model_dump())"
```

Helper này vẫn không thay đổi `load_pdf_chunks()`. Output mặc định nằm trong
`.data/`:

```text
src/agentic_rag/ingestion/pdf/.data/artifacts/<pdf-stem>/<run-id>/
  parsed.md
  chunks.jsonl
  chunks.md
  manifest.json
  elements.jsonl
  assets/
    images/
    tables/
    charts/
```

Ý nghĩa phần mở rộng:

- `parsed.md`: Markdown được export với image references khi Docling cung cấp
  image data; các link ảnh trỏ tới file trong `assets/images/`.
- `elements.jsonl`: mỗi dòng mô tả một asset bằng `element_id`, loại asset,
  `page`, có thể kèm `pages`/`page_range` nếu provenance trải trên nhiều trang,
  đường dẫn file asset và các `chunk_id` liên quan. Khi chunk có page metadata,
  asset được gắn vào mọi chunk có giao với `pages` hoặc `page_range` của asset;
  nếu không có chunk phù hợp, `chunk_ids` để rỗng thay vì gắn mặc định vào
  chunk đầu tiên.
- `assets/images/`: raw image được Docling trích ra từ PDF.
- `assets/tables/`: bảng được lưu ở Markdown, CSV và PNG nếu parser cung cấp.
- `assets/charts/`: chart candidate được lưu như raw image khi Docling gắn label
  phù hợp.

`Chunk.metadata` chỉ lưu reference như `asset_ids`, `has_image`, `has_table`,
`has_chart`; không nhúng binary image, DataFrame hoặc table object vào `Chunk`.
Mapping asset hiện là page/page-range based, chưa dùng coordinate/proximity
trong cùng một trang. Với text hoặc asset trải nhiều trang, chunk vẫn giữ text
nguyên vẹn và chỉ annotate bằng `page`, `pages`, `page_range`. V1 chỉ lưu raw
assets và table Markdown/CSV. Captioning hình ảnh và chart extraction bằng
model nặng sẽ được xử lý ở phase tối ưu sau.

## Benchmark tự động

OmniDocBench là nguồn benchmark lập trình được cho phase tối ưu parser. Repo này
không vendor benchmark dataset hoặc mã nguồn OmniDocBench; developer cần cung
cấp ground-truth JSON, thư mục Markdown parser output và môi trường Docker hoặc
checkout OmniDocBench cục bộ.

Nếu cần tải benchmark dataset phục vụ kiểm tra local, dùng script PDF-local:

```bash
uv --directory src/agentic_rag/ingestion/pdf run python download_benchmark_datasets.py
```

Script này dùng `huggingface-hub` để tải:

- ParseBench vào `src/agentic_rag/ingestion/pdf/.data/parsebench_dataset/`.
- MDPBench vào `src/agentic_rag/ingestion/pdf/.data/mdpbench_dataset/`.

Chạy bằng `uv --directory src/agentic_rag/ingestion/pdf` để `./.data` resolve
về thư mục `.data/` của PDF subproject, vốn đã được ignore. Không chạy script từ
root repo nếu không truyền output path riêng, vì root-level `.data/` không phải
layout artifact chuẩn của module PDF.

Wrapper hỗ trợ hai backend:

- `docker`: dựng command Docker và mount ground truth, predictions, config và
  result directory vào container OmniDocBench.
- `local`: chạy `python pdf_validation.py --config <config>` từ checkout
  OmniDocBench cục bộ.

Ví dụ dry-run từ PDF subproject:

```bash
uv --directory src/agentic_rag/ingestion/pdf run python -m benchmarking.cli run-omnidocbench \
  --backend docker \
  --ground-truth /path/to/OmniDocBench.json \
  --predictions /path/to/parser_markdown_outputs \
  --output-dir src/agentic_rag/ingestion/pdf/.data/omnidocbench/results \
  --config-output src/agentic_rag/ingestion/pdf/.data/omnidocbench/config.yaml \
  --dry-run
```

CI chỉ kiểm tra wrapper, config generation và dry-run behavior. CI không tải
dataset, không gọi Docker, không yêu cầu network và không yêu cầu checkout
OmniDocBench.

## Đánh giá thủ công

Human evaluation không được encode thành Pydantic scoring model. Reviewer sẽ tự
đối chiếu PDF gốc hoặc ground truth chính thức với output Markdown của parser,
rồi ghi nhận judgement thủ công. Mục tiêu là giữ phần benchmark tự động dựa trên
benchmark hợp lệ, còn phần human review vẫn là quá trình kiểm tra trực quan hoặc
cross-reference do reviewer thực hiện.

Các file trong `.data/` không được commit.

RAGFlow chỉ dùng làm benchmark/reference, không phải dependency hay main
platform của repo trong phase này.

## Chạy như subproject

PDF ingestion có `pyproject.toml` riêng để thành viên có thể chạy kiểm tra cục
bộ mà không cần thao tác ở root project.

Từ root repository:

```bash
uv --directory src/agentic_rag/ingestion/pdf sync
uv --directory src/agentic_rag/ingestion/pdf run ruff format --check .
uv --directory src/agentic_rag/ingestion/pdf run ruff check .
uv --directory src/agentic_rag/ingestion/pdf run mypy
uv --directory src/agentic_rag/ingestion/pdf run pytest -q
```

Root CI vẫn chạy toàn bộ test của repo, bao gồm `tests/` của PDF subproject.
