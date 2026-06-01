1. RAGFlow đã và đang dùng gì cho phần này?
Để hiểu cách RAGFlow xử lý và có baseline so sánh sòng phẳng, hãy nhìn vào "bếp sau" của họ (dựa trên source code của Infiniflow RAGFlow):

HTML Parsing & Main Content Extraction: RAGFlow sử dụng trafilatura và html2text làm nòng cốt để cào dữ liệu từ URL và chuyển đổi HTML về dạng text sạch, loại bỏ các thành phần thừa (boilerplate) như menu, footer, quảng cáo rất hiệu quả.

Deep Document Parsing (Phần nâng cao): Đối với các tài liệu phức tạp, họ tự build một engine riêng gọi là DeepDoCTeK (sử dụng các mô hình Vision-Language để nhận diện layout, bảng biểu, công thức) chứ không chỉ dùng heuristic rule thông thường.

Chunking Strategy: RAGFlow không chunk "mù" theo số lượng ký tự (CharacterTextSplitter). Họ chunk dựa trên Layout & Semantics (ví dụ: nhận diện thẻ tiêu đề <h1>, <h2>, cấu trúc bảng). Đối với URL/Web, họ cố gắng giữ nguyên cấu trúc Markdown sau khi parse để chunk không bị mất context của section.

2. Gợi ý Tech Stack & Cài đặt (Requirements)
Để đáp ứng trọn vẹn yêu cầu code của bạn (Fetch -> Parse -> Clean -> Metadata -> Chunk), đây là bộ thư viện tối ưu nhất:

# Fetching & Network
httpx>=0.27.0        # Thay thế requests, hỗ trợ async cực tốt nếu sau này cần scale
# HTML/Text Extraction (Trọng tâm)
trafilatura>=1.8.0   # Vừa fetch, vừa tự động trích xuất main content, bỏ noise (RAGFlow dùng)
beautifulsoup4>=4.12.3 # Dùng để fine-tune, bóc tách các thẻ meta hoặc cấu trúc section sâu hơn
# Chunking & RAG Utilities
langchain-text-splitters>=0.2.0  # Dùng RecursiveCharacterTextSplitter hoặc MarkdownHeaderTextSplitter
pydantic>=2.7.0      # Định nghĩa schema cho Chunk và Metadata để đảm bảo tính nhất quán dữ liệu


Ứng dụng cấp API truy cập (Nếu cần nâng cấp hoặc bypass)
Nếu gặp phải các trang web sử dụng Single Page Application (SPA) như React, Vue (dùng httpx hay trafilatura chỉ cào được vỏ HTML trống), bạn sẽ cần đến:

Playwright / Selenium (Self-hosted): Chạy headless browser để render Javascript trước khi parse.

Jina Reader API (https://r.jina.ai/<URL>): Một API cực kỳ mạnh mẽ của bên thứ ba. Bạn chỉ cần gửi URL qua API của nó, nó sẽ trả về Markdown sạch 100%, đã loại bỏ hoàn toàn noise, menu, footer. Rất đáng cân nhắc để làm baseline nhanh.

3. Bản Draft "Tech Comment" cho Task của Dũng (dung1308)
Bạn có thể sử dụng hoặc chỉnh sửa format này để comment trực tiếp vào task quản lý của nhóm:

### Tech/tool/framework dự định dùng & Lý do chọn:
1. Fetch URL & Extract Content: Dùng `trafilatura` kết hợp `httpx`.
   - Lý do: `trafilatura` là thư viện mà chính RAGFlow đang sử dụng. Nó có thuật toán heuristic nhận diện "Main Content" rất xuất sắc, tự động loại bỏ menu, footer, script, style mà không cần viết bằng tay từng rule css/xpath. `httpx` dùng làm fallback hoặc khi cần xử lý async requests.
2. HTML Chunking: Dùng `MarkdownHeaderTextSplitter` kết hợp `RecursiveCharacterTextSplitter` từ LangChain.
   - Lý do: Khi `trafilatura` parse HTML ra Markdown, việc chunk theo Header (`#`, `##`) giúp chúng ta giữ được thông tin `section` cho Metadata một cách tự động và chính xác nhất, không bị mất ngữ cảnh của đoạn văn.

### Tech nào còn đang nghiên cứu:
- Xử lý các trang Web dạng SPA (Dynamic Render bằng Javascript). Đang nghiên cứu tích hợp `Playwright` dạng headless hoặc call qua `Jina Reader API` để xử lý các case khó này mà không làm nghẽn pipeline chính.

### Input/Output của phần mình:
- Input: URL (str) hoặc Plain Text (str) + source (str).
- Output: `list[Chunk]` chuẩn hóa theo cấu trúc Pydantic Schema của team (bao gồm chunk_id tự sinh bằng hash, text sạch, và metadata dict: source, source_type, url, section, file_name, page).

### Cách loại bỏ noise HTML & Lưu Metadata URL/Section:
- Noise được lọc tự động qua tầng `trafilatura.extract()`.
- Metadata `section`: Trong quá trình băm nhỏ text bằng `MarkdownHeaderTextSplitter`, tên của Header gần nhất (ví dụ: "Phần 2 — URL/Text Ingestion") sẽ được extract và gán trực tiếp vào trường `section` của chunk đó.

### Sử dụng RAGFlow bổ sung tạm:
- Trong giai đoạn đầu khi pipeline tự build chưa hoàn thiện phần Embeddings/Retrieval, mình sẽ setup một bot RAGFlow chạy Docker local, sử dụng tính năng "Web Website" dataset của RAGFlow để nạp tài liệu tạm thời, cấp API cứu cánh cho các thành viên làm phần Prompt/LLM phía sau không bị block.

4. Gợi ý cấu trúc code mẫu cho hàm của bạn
Để bạn dễ hình dung cách map từ Tech Stack ra đúng cái Output Schema mà team yêu cầu:

from typing import List, Optional
from pydantic import BaseModel, Field
import httpx
import trafilatura
from langchain_text_splitters import RecursiveCharacterTextSplitter

class ChunkMetadata(BaseModel):
    source: str
    source_type: str
    file_name: Optional[str] = None
    url: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None

class Chunk(BaseModel):
    chunk_id: str
    text: str
    metadata: ChunkMetadata

def load_url_chunks(url: str) -> List[dict]:
    # 1. Fetch và Extract main content (Sạch noise hoàn toàn)
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        # Fallback bằng httpx nếu trafilatura fetch lỗi
        response = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"})
        downloaded = response.text
        
    main_text = trafilatura.extract(downloaded, include_links=False, output_format='txt') # Hoặc 'markdown'
    
    # 2. Chunking
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = text_splitter.split_text(main_text)
    
    # 3. Ép về Schema team yêu cầu
    chunks = []
    for i, doc_text in enumerate(docs):
        chunk_obj = Chunk(
            chunk_id=f"url_{hash(url)}_{i}",
            text=doc_text,
            metadata=ChunkMetadata(
                source=url,
                source_type="url",
                url=url,
                section="main" # Có thể tối ưu bóc tách theo tầng header sau
            )
        )
        chunks.append(chunk_obj.model_dump())
    return chunks

Cơ bản các bước chuẩn bị như vậy là đã rất "vừa vặn" với yêu cầu bài toán và khớp hoàn toàn với tư duy thiết kế của RAGFlow. Bạn có cần điều chỉnh sâu hơn ở phần thuật toán tách Section hay xử lý các URL chặn crawler không?