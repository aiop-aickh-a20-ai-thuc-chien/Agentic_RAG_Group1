# 📋 TODO: GraphRAG + RAG Hybrid Pipeline Implementation

> **Goal**: Build a hybrid system that combines **GraphRAG** (knowledge-graph-based retrieval-augmented generation) with **traditional RAG** (vector-similarity retrieval) for superior question answering over private data.

---

## Phase 0: Foundation & Environment Setup
- [ ] **0.1** Install Python 3.11+ and `uv` package manager
- [ ] **0.2** Clone the GraphRAG repository and install all packages:
  - `graphrag` (core), `graphrag-llm`, `graphrag-vectors`, `graphrag-chunking`, `graphrag-input`, `graphrag-storage`, `graphrag-cache`, `graphrag-common`
- [ ] **0.3** Configure API keys (OpenAI / Azure OpenAI) in environment variables
- [ ] **0.4** Run `graphrag init --root ./project` to generate default config (`settings.yaml`)
- [ ] **0.5** Prepare a test corpus of documents (≥ 5 files, mixed topics) in `input/` directory
- [ ] **0.6** Verify the base install works: `graphrag index --root ./project`

---

## Phase 1: Document Ingestion & Chunking Pipeline
- [ ] **1.1** Implement document loading (support `.txt`, `.csv`, `.pdf`)
  - See: `load_input_documents` workflow
- [ ] **1.2** Implement text chunking with configurable chunk size & overlap
  - See: `create_base_text_units` workflow → uses `graphrag-chunking` package
  - Chunk size default: ~300 tokens, overlap: ~100 tokens
- [ ] **1.3** Add metadata prepending to chunks (title, creation date)
- [ ] **1.4** Generate unique IDs for each text unit (SHA-512 hash)
- [ ] **1.5** Store text units to persistent storage (Parquet / CosmosDB)
- [ ] **1.6** Write unit tests for chunking edge cases (empty docs, very long docs)

---

## Phase 2: Knowledge Graph Construction (GraphRAG Indexing)
- [ ] **2.1** Entity & Relationship Extraction using LLM
  - See: `extract_graph` workflow
  - Prompt-based extraction → entities (name, type, description) + relationships (source, target, description, weight)
  - Support "gleanings" (multiple extraction passes per chunk)
- [ ] **2.2** Implement entity/relationship merging across chunks
  - Same entity name → merge descriptions → summarize
- [ ] **2.3** Implement description summarization for merged entities & relationships
  - See: `summarize_descriptions` operation
- [ ] **2.4** Build the final entity graph (NetworkX)
  - See: `finalize_graph` workflow
  - Compute edge combined degrees, finalize entities & relationships
- [ ] **2.5** Extract covariates/claims (optional)
  - See: `extract_covariates` workflow
- [ ] **2.6** Write unit tests for extraction (mock LLM responses)

---

## Phase 3: Community Detection & Summarization
- [ ] **3.1** Run hierarchical Leiden community detection on the entity graph
  - See: `create_communities` workflow → `cluster_graph` operation
  - Parameters: `max_cluster_size`, `use_lcc`, `seed`
- [ ] **3.2** Build community hierarchy (parent-child relationships)
- [ ] **3.3** Aggregate entity IDs, relationship IDs, text unit IDs per community
- [ ] **3.4** Generate LLM-powered community reports (summaries)
  - See: `create_community_reports` workflow
  - Build local context (nodes, edges, claims) → summarize per community level
- [ ] **3.5** Store communities and community reports
- [ ] **3.6** Write tests for community detection with known graph structures

---

## Phase 4: Embedding Generation (Shared by Graph & Vector RAG)
- [ ] **4.1** Generate text embeddings for entity descriptions
  - Embedding field: `entity_description_embedding`
- [ ] **4.2** Generate text embeddings for text unit texts
  - Embedding field: `text_unit_text_embedding`
- [ ] **4.3** Generate text embeddings for community report full content
  - Embedding field: `community_full_content_embedding`
- [ ] **4.4** Store embeddings in vector store (LanceDB / Azure AI Search / CosmosDB)
  - See: `generate_text_embeddings` workflow → `graphrag-vectors` package
- [ ] **4.5** Verify embeddings are searchable with similarity queries

---

## Phase 5: Traditional RAG Pipeline (Vector Search Branch)
- [ ] **5.1** Implement Basic Search (pure vector similarity on text units)
  - See: `BasicSearch` class + `BasicSearchContext`
  - Steps: embed query → find top-K text units → build context → LLM answer
- [ ] **5.2** Implement query embedding using the same embedding model
- [ ] **5.3** Implement context window management (token budget for text units)
- [ ] **5.4** Implement response generation with system prompt
- [ ] **5.5** Support streaming responses
- [ ] **5.6** Write integration tests for basic search

---

## Phase 6: GraphRAG Query Pipeline — Local Search
- [ ] **6.1** Implement entity extraction from query
  - See: `entity_extraction.py` context builder → maps query to graph entities via vector similarity
- [ ] **6.2** Build mixed context from multiple sources:
  - Entities (matched by embedding similarity)
  - Relationships (in-network + out-network, ranked)
  - Community reports (for matched entities' communities)
  - Text units (original source text for matched entities)
  - Covariates (if available)
  - See: `LocalSearchMixedContext`
- [ ] **6.3** Implement token budget allocation across context types
  - `text_unit_prop`, `community_prop`, remaining for entities/relationships
- [ ] **6.4** Implement conversation history support
- [ ] **6.5** Generate final answer with context-aware system prompt
- [ ] **6.6** Write tests with mock graph data

---

## Phase 7: GraphRAG Query Pipeline — Global Search
- [ ] **7.1** Implement Map phase:
  - Split community reports into batches
  - Run parallel LLM calls per batch → extract key points + scores
  - See: `GlobalSearch._map_response_single_batch()`
- [ ] **7.2** Implement Reduce phase:
  - Collect all key points, filter by score > 0
  - Sort by descending score, fit within token budget
  - Generate final comprehensive answer
  - See: `GlobalSearch._reduce_response()`
- [ ] **7.3** Support dynamic community selection (optional)
  - See: `dynamic_community_selection.py` → select relevant communities before Map
- [ ] **7.4** Support streaming for both Map and Reduce phases
- [ ] **7.5** Write tests for Map-Reduce orchestration

---

## Phase 8: GraphRAG Query Pipeline — DRIFT Search
- [ ] **8.1** Implement DRIFT Primer:
  - Build initial context from community reports
  - Generate primer response (intermediate answer + follow-up queries)
  - See: `DRIFTPrimer`
- [ ] **8.2** Implement DRIFT Action loop:
  - Rank incomplete actions by score
  - Execute follow-up queries via Local Search
  - Accumulate answers and generate new follow-ups
  - See: `DRIFTSearch._search_step()`
- [ ] **8.3** Implement query state management (DAG of actions)
  - See: `QueryState`
- [ ] **8.4** Implement final Reduce step (combine all intermediate answers)
- [ ] **8.5** Write tests for multi-hop reasoning scenarios

---

## Phase 9: Hybrid GraphRAG + RAG Fusion
- [ ] **9.1** Design the hybrid query router:
  - Classify incoming query → local/global/drift/basic/hybrid
  - Use query complexity heuristics or a lightweight classifier
- [ ] **9.2** Implement parallel execution:
  - Run GraphRAG (Local or Global) and Basic RAG concurrently
  - Merge results with relevance-weighted fusion
- [ ] **9.3** Implement context deduplication:
  - Remove overlapping text units between graph-context and vector-context
- [ ] **9.4** Implement answer synthesis:
  - Combine structured (graph) and unstructured (vector) contexts
  - Use a final LLM call to synthesize a coherent answer
- [ ] **9.5** Implement confidence scoring for hybrid results
- [ ] **9.6** Write integration tests for hybrid pipeline

---

## Phase 10: Incremental Update Pipeline
- [ ] **10.1** Implement document delta detection
  - See: `load_update_documents` workflow
- [ ] **10.2** Implement entity/relationship update merging
  - See: `update_entities_relationships` workflow
- [ ] **10.3** Implement community re-clustering
  - See: `update_communities` workflow
- [ ] **10.4** Implement community report regeneration
  - See: `update_community_reports` workflow
- [ ] **10.5** Implement embedding update (only changed items)
  - See: `update_text_embeddings` workflow
- [ ] **10.6** Test incremental indexing correctness

---

## Phase 11: API Layer & Serving
- [ ] **11.1** Build FastAPI/Flask REST API with endpoints:
  - `POST /index` — trigger indexing pipeline
  - `POST /query` — query with search method selection
  - `GET /status` — check indexing progress
  - `GET /graph` — export graph data
- [ ] **11.2** Implement WebSocket for streaming responses
- [ ] **11.3** Add authentication & rate limiting
- [ ] **11.4** Write API documentation (OpenAPI/Swagger)

---

## Phase 12: Evaluation & Optimization
- [ ] **12.1** Implement evaluation metrics:
  - Faithfulness (answer grounded in retrieved context)
  - Relevancy (answer addresses the question)
  - Context precision (retrieved context is relevant)
  - Context recall (relevant information is retrieved)
- [ ] **12.2** Benchmark: GraphRAG-only vs RAG-only vs Hybrid
- [ ] **12.3** Optimize LLM costs:
  - Cache extraction results (see `graphrag-cache` package)
  - Tune chunk sizes and embedding batch sizes
  - Use Fast indexing (`extract_graph_nlp` + `prune_graph`) for cost reduction
- [ ] **12.4** Prompt tuning for entity extraction accuracy
- [ ] **12.5** Performance profiling and bottleneck identification

---

## Phase 13: Production Readiness
- [ ] **13.1** Add comprehensive logging (structured JSON logs)
- [ ] **13.2** Implement error recovery and retry logic
- [ ] **13.3** Set up monitoring (LLM call counts, token usage, latency)
- [ ] **13.4** Write deployment guide (Docker, cloud deployment)
- [ ] **13.5** Create user-facing documentation
- [ ] **13.6** Final end-to-end integration test

---

## Key Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector Store | LanceDB (local) / Azure AI Search (cloud) | LanceDB for dev, Azure for prod scale |
| LLM Provider | OpenAI GPT-4o / Azure OpenAI | Best extraction quality, configurable |
| Embedding Model | text-embedding-3-small | Good quality/cost balance |
| Chunking Strategy | Token-based with overlap | Preserves context at boundaries |
| Community Detection | Hierarchical Leiden | Proven for knowledge graph clustering |
| Search Default | Hybrid (Local + Basic) | Best overall accuracy |

---

## File References

| Component | Key Source File |
|-----------|----------------|
| Pipeline Factory | `packages/graphrag/graphrag/index/workflows/factory.py` |
| Extract Graph | `packages/graphrag/graphrag/index/workflows/extract_graph.py` |
| Communities | `packages/graphrag/graphrag/index/workflows/create_communities.py` |
| Community Reports | `packages/graphrag/graphrag/index/workflows/create_community_reports.py` |
| Embeddings | `packages/graphrag/graphrag/index/workflows/generate_text_embeddings.py` |
| Local Search | `packages/graphrag/graphrag/query/structured_search/local_search/search.py` |
| Global Search | `packages/graphrag/graphrag/query/structured_search/global_search/search.py` |
| DRIFT Search | `packages/graphrag/graphrag/query/structured_search/drift_search/search.py` |
| Basic Search | `packages/graphrag/graphrag/query/structured_search/basic_search/` |
| Query Factory | `packages/graphrag/graphrag/query/factory.py` |
| Data Models | `packages/graphrag/graphrag/data_model/` |
| Config | `packages/graphrag/graphrag/config/` |
