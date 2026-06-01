# URL / HTML Ingestion + Chunking Setup for RAG Sprint 1

> Goal: ingest URLs and raw HTML, extract clean text/Markdown, chunk with metadata, and index into BM25 + dense vector retrieval.

---

## 1. What You Need to Set Up

### Core pipeline

```text
URL / HTML input
   ↓
Fetch page or read HTML file
   ↓
Extract clean content
   ↓
Convert to Markdown / normalized text
   ↓
Split into chunks
   ↓
Attach metadata
   ↓
Store documents + chunks
   ↓
Index chunks into BM25 + vector DB
```

For Sprint 1, keep the pipeline boring and reliable. Avoid building a full crawler first. Start with a list of allowed URLs and ingest them one by one.

---

## 2. Recommended Stack

### Best fast-to-build stack

| Layer | Recommended tool | Why |
|---|---|---|
| Static URL fetching | `httpx` | Fast async HTTP client |
| Clean article extraction | `trafilatura` | Extracts main text, metadata, Markdown/text output |
| HTML parsing fallback | `beautifulsoup4` + `lxml` | Useful for custom cleanup and section extraction |
| JS-rendered pages | `crawl4ai` or `playwright` | Handles dynamic pages when plain HTTP fails |
| Markdown normalization | `markdownify` / Crawl4AI built-in Markdown | Makes chunks readable and citation-friendly |
| Chunking | custom heading-aware chunker | Better metadata than blind token splitting |
| Token counting | `tiktoken` or simple char-based fallback | Helps control chunk size |
| BM25 | `rank-bm25` or `bm25s` | Simple keyword retrieval |
| Dense embeddings | `sentence-transformers` | Local embeddings, cheap for demo |
| Vector DB | `ChromaDB` | Easy local persistence |
| Metadata store | SQLite / JSONL / PostgreSQL | Depends on app complexity |
| UI | Streamlit | Fastest demo UI |

---

## 3. What to Install

### Minimal install

```bash
pip install httpx trafilatura beautifulsoup4 lxml markdownify tiktoken
pip install sentence-transformers chromadb rank-bm25 streamlit
```

### If you need JavaScript-rendered pages

Option A: Playwright

```bash
pip install playwright
playwright install chromium
```

Option B: Crawl4AI

```bash
pip install crawl4ai
crawl4ai-setup
```

Use Playwright/Crawl4AI only when simple fetching fails. Browser crawling is slower and heavier.

---

## 4. What You Need to Buy

### For a student/intern demo: probably nothing

You can run the first demo locally with:

- Free Python libraries
- Local ChromaDB
- Local BM25
- Local embedding model
- Streamlit UI
- Manually curated URL list

### Optional paid services

| Need | Paid option | When to buy |
|---|---|---|
| Hosted LLM | OpenAI / Gemini / Claude API | If local LLM quality is not enough |
| Hosted embeddings | OpenAI / Voyage / Cohere | If local embedding quality/speed is weak |
| Proxy / anti-bot access | ScrapingBee / Bright Data / Firecrawl Cloud | Only if target sites block you |
| Hosted vector DB | Pinecone / Weaviate Cloud / Qdrant Cloud | Only if deployment needs scale |
| Cloud server | Render / Railway / Fly.io / VPS | Needed for public demo deployment |

Do **not** buy proxies or hosted scraping tools for Sprint 1 unless your target websites actively block normal crawling.

---

## 5. Suggested Project Structure

```text
rag_app/
  backend/
    main.py
    config.py
    ingestion/
      url_loader.py
      html_loader.py
      cleaner.py
      markdown_normalizer.py
      chunker.py
      metadata.py
    retrieval/
      bm25_index.py
      vector_index.py
      rrf.py
    generation/
      answer_service.py
      citation_guard.py
    storage/
      documents.jsonl
      chunks.jsonl
      chroma/
    eval/
      questions.json
      metrics.py
  frontend/
    app.py              # Streamlit UI
  data/
    urls.txt
    raw_html/
  requirements.txt
  README.md
```

---

## 6. Metadata Schema

Every chunk should carry enough metadata to support citations.

```json
{
  "chunk_id": "url_0001_chunk_0003",
  "document_id": "url_0001",
  "source_type": "url",
  "source": "https://example.com/admissions",
  "title": "Admissions Requirements",
  "section": "Scholarships",
  "page": null,
  "url": "https://example.com/admissions",
  "published_date": "2026-05-12",
  "fetched_at": "2026-06-01T08:00:00+07:00",
  "content_hash": "sha256_hash_here",
  "chunk_index": 3,
  "text": "...chunk text..."
}
```

For raw HTML files, use:

```json
{
  "source_type": "html",
  "source": "data/raw_html/admissions.html",
  "url": null
}
```

---

## 7. Chunking Strategy

### Recommended default

Use heading-aware chunking:

1. Convert HTML to Markdown.
2. Split by headings: `#`, `##`, `###`.
3. Merge tiny sections.
4. Split long sections into overlapping chunks.
5. Preserve heading path in metadata.

### Default chunk settings

```text
chunk_size: 700–1,000 tokens
chunk_overlap: 100–150 tokens
minimum_chunk_size: 150 tokens
```

For Vietnamese content, avoid tiny chunks because Vietnamese context can be fragmented quickly. A 700–1,000 token range is safer for answer grounding.

---

## 8. URL Ingestion Rules

### Keep it safe and demo-friendly

- Only ingest URLs from an allowlist.
- Respect `robots.txt` where applicable.
- Do not crawl login/private pages without permission.
- Store `fetched_at` for freshness.
- Store `content_hash` to avoid duplicate re-indexing.
- Keep original URL for citation.
- Use a polite delay if crawling multiple pages.

### URL input format

`data/urls.txt`

```text
https://example.edu/admissions
https://example.edu/scholarships
https://example.edu/programs/computer-science
```

---

## 9. Basic Implementation Plan

### Step 1: Fetch URL

Use `httpx` first.

```python
import httpx

async def fetch_url(url: str) -> str:
    headers = {"User-Agent": "StudentRAGBot/0.1"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text
```

### Step 2: Extract clean text / Markdown

Use Trafilatura for static pages.

```python
import trafilatura


def extract_markdown(html: str, url: str | None = None) -> str:
    result = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        favor_recall=True,
    )
    return result or ""
```

### Step 3: Fallback HTML cleanup

Use BeautifulSoup if Trafilatura returns empty content.

```python
from bs4 import BeautifulSoup


def fallback_extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    return soup.get_text("\n", strip=True)
```

### Step 4: Chunk with section metadata

```python
def chunk_text(text: str, chunk_size: int = 3500, overlap: int = 500) -> list[str]:
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(end - overlap, end)

    return chunks
```

For Sprint 1, character-based chunking is acceptable. Later, replace this with token-aware and heading-aware chunking.

---

## 10. Indexing Plan

### BM25

- Store all chunk texts in memory or JSONL.
- Tokenize text.
- Use `rank-bm25` for keyword search.

### Dense vector

- Use `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` for Vietnamese + English.
- Store embeddings in ChromaDB.

```bash
pip install sentence-transformers chromadb
```

Recommended embedding model for demo:

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

Better but heavier multilingual option:

```text
intfloat/multilingual-e5-base
```

---

## 11. RRF Fusion

Use Reciprocal Rank Fusion to combine BM25 and dense retrieval.

```python
def reciprocal_rank_fusion(result_lists, k: int = 60):
    scores = {}

    for results in result_lists:
        for rank, chunk_id in enumerate(results, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

---

## 12. Citation Format

Every answer should cite chunks like this:

```text
[Source: Admissions Requirements | Section: Scholarships | Chunk: url_0001_chunk_0003]
```

For URL sources:

```text
[https://example.edu/admissions | Scholarships | chunk_0003]
```

If evidence is missing, answer:

```text
not found in the provided documents
```

---

## 13. Sprint 1 MVP Checklist

- [ ] Create `urls.txt`
- [ ] Build URL loader with `httpx`
- [ ] Build HTML file loader
- [ ] Extract clean Markdown with Trafilatura
- [ ] Add BeautifulSoup fallback
- [ ] Store raw document records in JSONL
- [ ] Chunk extracted Markdown/text
- [ ] Add metadata to every chunk
- [ ] Save chunks to JSONL
- [ ] Build BM25 index
- [ ] Build Chroma vector index
- [ ] Implement RRF fusion
- [ ] Generate grounded answers using top chunks only
- [ ] Add citation guard
- [ ] Build Streamlit upload/input UI
- [ ] Prepare 10+ benchmark questions
- [ ] Report Recall@5 and MRR@5

---

## 14. Recommended First Demo Scope

Use only:

```text
PDF + URL ingestion
Trafilatura for URL extraction
Character/heading-aware chunking
BM25 + Chroma dense retrieval
RRF fusion
Streamlit UI
JSONL metadata storage
```

Avoid for Sprint 1:

```text
Full recursive crawler
Login crawling
Anti-bot bypass
GraphRAG
Complex reranker
Agentic ingestion planner
Automatic infinite sitemap discovery
```

---

## 15. Final Recommendation

For fastest reliable setup:

```text
httpx + trafilatura + BeautifulSoup fallback
→ Markdown/text normalization
→ heading-aware chunks with metadata
→ rank-bm25 + ChromaDB
→ RRF fusion
→ Streamlit demo
```

Buy nothing at first. Spend money only if:

1. target websites block crawling,
2. local embeddings are too weak,
3. you need public deployment,
4. hosted LLM/API quality is required for the demo.
