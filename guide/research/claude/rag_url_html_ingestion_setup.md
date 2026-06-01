# RAG Ingestion + Chunking Setup Guide: URL & HTML

> Research compiled by Claude (Anthropic). Intended for AI assistant consumption.  
> Last updated: June 2026. All tools verified as of this date.

---

## Overview

Setting up a RAG ingestion pipeline for URLs and HTML requires 5 layers:

1. **Web Crawling** — fetch pages, follow links, render JavaScript
2. **HTML Cleaning** — strip boilerplate, extract main content
3. **Chunking** — split clean text into retrieval-ready pieces
4. **Embedding** — convert chunks to vectors
5. **Vector Store** — store and query vectors

---

## Layer 1: Web Crawling

### Option A: Self-hosted (Free)

#### Crawl4AI (Recommended)
- **What it does**: Async browser crawl, outputs clean Markdown, handles JavaScript via Playwright, multi-page depth crawl out of the box
- **Install**:
  ```bash
  pip install crawl4ai
  crawl4ai-setup        # auto-installs Playwright browser
  crawl4ai-doctor       # diagnose if errors appear
  ```
- **Cost**: Free
- **GitHub**: https://github.com/unclecode/crawl4ai (46k+ stars)
- **Best for**: Local dev, full control, Vietnamese content, privacy-sensitive data
- **Performance**: ~1.6s per simple crawl, ~4.6s with JS execution — faster than Firecrawl in benchmarks

#### Playwright (auto-installed by Crawl4AI)
- Needed for JS-rendered pages (SPAs, infinite scroll, dynamic content)
- Installed automatically via `crawl4ai-setup`

#### Trafilatura (fallback for static pages)
- **Install**: `pip install trafilatura`
- **Cost**: Free
- **Use when**: Simple static HTML, no JavaScript needed
- **Advantage**: No browser overhead, very fast, good main-content extraction

### Option B: Managed API (Paid, Production)

#### Firecrawl
- **What it does**: Managed crawl with anti-bot bypass, sitemap discovery, depth control, no server required
- **Install**: `pip install firecrawl-py`
- **Cost**: $16–$83/month (also has open-source self-hostable version)
- **Website**: https://www.firecrawl.dev
- **Best for**: JS-heavy sites, Cloudflare-protected sites, production at scale
- **Output**: LLM-ready Markdown + structured JSON on every request

#### Spider API
- **Install**: `pip install spider-client`
- **Cost**: ~$1/GB bandwidth (pay-per-success only)
- **Website**: https://spider.cloud
- **Output**: Markdown / HTML / JSON / XML
- **Best for**: High-volume crawls where predictable per-GB pricing is preferred

### Crawl Strategy Recommendation

| Scenario | Tool |
|---|---|
| Dev/learning, static sites | Crawl4AI (free) |
| JS-heavy pages, Vietnamese news sites | Crawl4AI with Playwright |
| Cloudflare / anti-bot sites | Firecrawl API |
| Production, 100k+ pages/month | Firecrawl or Spider |
| Hybrid: most pages free, hard sites paid | Crawl4AI + Firecrawl fallback |

---

## Layer 2: HTML Cleaning

All tools below are **free**.

### Install
```bash
pip install beautifulsoup4 lxml html2text
```

### BeautifulSoup4
- Parse HTML tree, remove nav/footer/header/ads/cookie banners by tag or CSS class
- Extract all links for recursive crawling:
  ```python
  from bs4 import BeautifulSoup
  soup = BeautifulSoup(html, 'lxml')
  links = [a['href'] for a in soup.find_all('a', href=True)]
  # Remove boilerplate
  for tag in soup(['nav', 'footer', 'header', 'aside', 'script', 'style']):
      tag.decompose()
  clean_text = soup.get_text(separator='\n', strip=True)
  ```

### html2text
- Convert cleaned HTML → Markdown, preserving headings (h1/h2/h3) and lists
- Better downstream chunking because heading structure is preserved
  ```python
  import html2text
  h = html2text.HTML2Text()
  h.ignore_links = False   # keep links for metadata
  h.ignore_images = True
  markdown = h.handle(cleaned_html)
  ```

### Trafilatura (alternative all-in-one)
- Heuristic + XPath cascade — strips boilerplate, extracts main content in one call
- Output: TXT, Markdown, JSON, XML
  ```python
  import trafilatura
  downloaded = trafilatura.fetch_url(url)
  text = trafilatura.extract(downloaded, output_format='markdown')
  ```

### Key things to strip from HTML before chunking
- Navigation menus (`<nav>`)
- Cookie consent banners
- Sidebar widgets
- Footer links
- JavaScript/CSS blocks
- Social share buttons
- Duplicate content (header repeated in og:tags)

---

## Layer 3: Chunking

### Install
```bash
pip install langchain-text-splitters tiktoken
pip install chonkie   # only if semantic chunking needed later
```

### Recommended combo for HTML: HTMLHeaderTextSplitter + RecursiveCharacterTextSplitter

This is the best practice for HTML/URL content:

```python
from langchain_text_splitters import HTMLHeaderTextSplitter, RecursiveCharacterTextSplitter

# Step 1: Split by HTML headers (h1, h2, h3)
# Automatically attaches the heading path as metadata to each chunk
headers_to_split_on = [
    ("h1", "Header 1"),
    ("h2", "Header 2"),
    ("h3", "Header 3"),
]
html_splitter = HTMLHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
header_splits = html_splitter.split_text_from_url(url)
# OR from string: html_splitter.split_text(html_string)

# Step 2: Apply size limit to each header-split chunk
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,       # tokens or chars — tune based on embedding model
    chunk_overlap=50,     # ~10% overlap, preserves cross-boundary context
    length_function=len,
)
chunks = text_splitter.split_documents(header_splits)

# Result: each chunk has metadata like:
# {'Header 1': 'Introduction', 'Header 2': 'Installation', source: '...'}
```

### Chunk size guidance

| Use case | chunk_size | chunk_overlap |
|---|---|---|
| Fine-grained factual QA | 256 tokens | 25–30 tokens |
| General purpose (start here) | 512 tokens | 50 tokens |
| Long-form summarization | 1024 tokens | 100 tokens |

> **Research finding (Firecrawl benchmark, 2026)**: Recursive 512-token splitting scored 69% accuracy across 50 academic papers — outperforming semantic chunking (54%) in that study. Start with 512 tokens.

> **Research finding (MDPI Bioengineering, Nov 2025)**: Adaptive/semantic chunking hit 87% accuracy vs 13% for fixed-size on clinical decision support tasks. Use semantic when your documents have clear multi-topic structure.

### Token counting (important)
```python
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")  # OpenAI models
num_tokens = len(enc.encode(chunk_text))
```

### Semantic chunking with chonkie (advanced, optional)
- Use only after verifying that standard recursive chunking underperforms for your corpus
- **Warning**: ~14× slower than token-based chunking (0.33 MB/s vs 4.82 MB/s)
  ```python
  from chonkie import SemanticChunker
  chunker = SemanticChunker(
      embedding_model="sentence-transformers/all-MiniLM-L6-v2",
      chunk_size=512,
      similarity_threshold=0.7   # tune per embedding model
  )
  chunks = chunker.chunk(text)
  ```

### Metadata to attach to every chunk

Always store these alongside the chunk text:

```python
metadata = {
    "source_url": url,
    "domain": urlparse(url).netloc,
    "crawl_date": datetime.utcnow().isoformat(),
    "language": "vi",               # or "en"
    "section_heading": "...",        # from HTMLHeaderTextSplitter
    "chunk_index": i,
    "word_count": len(chunk.split()),
    "doc_title": page_title,
}
```

---

## Layer 4: Embedding

### Option A: Local (Free)

```bash
pip install sentence-transformers
```

```python
from sentence_transformers import SentenceTransformer

# Best free multilingual model (supports Vietnamese well)
model = SentenceTransformer('BAAI/bge-m3')
# Alternative: 'intfloat/multilingual-e5-large'

embeddings = model.encode(
    [chunk.page_content for chunk in chunks],
    batch_size=32,
    show_progress_bar=True
)
```

**Recommended free models for Vietnamese + English:**
- `BAAI/bge-m3` — best multilingual, 8192 token context
- `intfloat/multilingual-e5-large` — strong on retrieval benchmarks
- `VinAI/phobert-base-v2` — Vietnamese-only, needs word segmentation first

### Option B: API (Paid)

```bash
pip install openai voyageai
```

| Provider | Model | Cost | Notes |
|---|---|---|---|
| OpenAI | text-embedding-3-small | ~$0.02/1M tokens | Good general purpose |
| OpenAI | text-embedding-3-large | ~$0.13/1M tokens | Higher quality |
| VoyageAI | voyage-3 | ~$0.06/1M tokens | Strong RAG retrieval |

```python
from openai import OpenAI
client = OpenAI()
response = client.embeddings.create(
    input=[chunk.page_content for chunk in chunks],
    model="text-embedding-3-small"
)
```

---

## Layer 5: Vector Store

### ChromaDB — start here (Free, local)

```bash
pip install chromadb
```

```python
import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("rag_docs")

collection.add(
    ids=[f"chunk_{i}" for i in range(len(chunks))],
    documents=[c.page_content for c in chunks],
    embeddings=embeddings.tolist(),
    metadatas=[c.metadata for c in chunks],
)

# Query
results = collection.query(query_embeddings=[query_embedding], n_results=5)
```

**Good for**: Dev, learning, datasets under ~100k chunks.

### Qdrant — production self-hosted (Free)

```bash
docker run -p 6333:6333 qdrant/qdrant
pip install qdrant-client
```

- Hybrid BM25 + vector search built in
- Filter by metadata (date, language, domain) at query time
- Scales to millions of vectors

### Pinecone — managed cloud

```bash
pip install pinecone
```

- **Free starter**: 1 index, 100k vectors
- **Paid**: from ~$70/month for production
- Serverless, no infrastructure management

---

## Full Minimal Pipeline (Code Skeleton)

```python
import asyncio
from crawl4ai import AsyncWebCrawler
from bs4 import BeautifulSoup
import html2text
from langchain_text_splitters import HTMLHeaderTextSplitter, RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import chromadb
from datetime import datetime
from urllib.parse import urlparse

# --- Config ---
START_URL = "https://example.com"
MAX_DEPTH = 2
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
EMBED_MODEL = "BAAI/bge-m3"

# --- Models ---
embedder = SentenceTransformer(EMBED_MODEL)
db = chromadb.PersistentClient(path="./chroma_db")
collection = db.get_or_create_collection("rag_docs")

headers_to_split = [("h1","H1"),("h2","H2"),("h3","H3")]
html_splitter = HTMLHeaderTextSplitter(headers_to_split_on=headers_to_split)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

async def ingest_url(url: str):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
    
    # Clean
    soup = BeautifulSoup(result.html, 'lxml')
    for tag in soup(['nav','footer','header','aside','script','style']):
        tag.decompose()
    clean_html = str(soup)
    title = soup.title.string if soup.title else url

    # Chunk
    header_splits = html_splitter.split_text(clean_html)
    chunks = text_splitter.split_documents(header_splits)

    # Embed + store
    texts = [c.page_content for c in chunks]
    embeddings = embedder.encode(texts, batch_size=32).tolist()

    ids, docs, metas = [], [], []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        ids.append(f"{urlparse(url).netloc}_{i}")
        docs.append(chunk.page_content)
        metas.append({
            **chunk.metadata,
            "source_url": url,
            "domain": urlparse(url).netloc,
            "doc_title": title,
            "chunk_index": i,
            "crawl_date": datetime.utcnow().isoformat(),
        })

    collection.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metas)
    print(f"Ingested {len(chunks)} chunks from {url}")

asyncio.run(ingest_url(START_URL))
```

---

## Cost Summary

| Path | Fixed cost | Variable cost | Minimum requirement |
|---|---|---|---|
| Full local (dev) | $0 | $0 | Python 3.10+, 8GB RAM |
| Local + OpenAI embed | $0 | ~$0.02/1M tokens | Python 3.10+, OpenAI key |
| Firecrawl + local embed | $16–83/month | $0 | API key |
| Full managed (Firecrawl + OpenAI + Pinecone) | ~$100–150/month | per usage | API keys only |

---

## Quick Install: All Layers at Once

```bash
# Core pipeline (free)
pip install crawl4ai beautifulsoup4 lxml html2text \
            langchain-text-splitters tiktoken \
            sentence-transformers chromadb

# Setup browser for JS rendering
crawl4ai-setup

# Optional: semantic chunking
pip install chonkie

# Optional: API embedding
pip install openai voyageai

# Optional: production vector store
pip install qdrant-client pinecone
docker run -p 6333:6333 qdrant/qdrant  # if using Qdrant
```

---

## Key Research References

| Source | Finding |
|---|---|
| Crawl4AI PyPI benchmark | Crawl4AI is 4× faster than Firecrawl for simple crawls, still faster with JS execution |
| Firecrawl vs Crawl4AI (Apify, 2026) | Firecrawl wins on setup speed + MCP support; Crawl4AI wins on cost + control |
| Firecrawl chunking benchmark (2026) | Recursive 512-token: 69% accuracy; Semantic chunking: 54% on academic papers |
| MDPI Bioengineering (Nov 2025) | Adaptive chunking: 87% accuracy vs 13% fixed-size on clinical decision support |
| Chonkie benchmarks | Semantic chunking: 0.33 MB/s vs token-based: 4.82 MB/s (~14× slower) |
| LangChain docs | HTMLHeaderTextSplitter auto-attaches heading path as metadata — best for structured HTML |
| VN-MTEB benchmark (arxiv 2507.21500) | bge-m3 and multilingual-e5-large are top models for Vietnamese retrieval |
| Anthropic Contextual Retrieval | Adding context per chunk before embedding reduces retrieval failures by up to 67% |

---

## Vietnamese-specific additions

If your corpus includes Vietnamese text, add these to Layer 1–2:

```bash
pip install underthesea vietnormalizer
```

```python
from underthesea import text_normalize, word_tokenize
import unicodedata

def clean_vietnamese(text: str) -> str:
    # 1. Unicode normalization (NFC form)
    text = unicodedata.normalize('NFC', text)
    # 2. Normalize numbers, abbreviations, loanwords
    text = text_normalize(text)
    return text

def segment_for_phobert(text: str) -> str:
    # Required if using PhoBERT embedding
    return ' '.join(word_tokenize(text, format='text'))
```

**Vietnamese embedding models (choose one):**
- `BAAI/bge-m3` — multilingual, works without segmentation (recommended)
- `intfloat/multilingual-e5-large` — strong on retrieval
- `vinai/phobert-base-v2` — Vietnamese-only, requires VnCoreNLP word segmentation first
