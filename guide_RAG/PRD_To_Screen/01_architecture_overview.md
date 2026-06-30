# 🏗️ Architecture Overview: GraphRAG + RAG Hybrid System

## 1. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      USER QUERY                                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │    QUERY ROUTER        │
              │  (classify query type) │
              └───────┬────────────────┘
                      │
         ┌────────────┼─────────────┐
         ▼            ▼             ▼
    ┌─────────┐  ┌──────────┐  ┌──────────┐
    │ GraphRAG│  │  Basic   │  │  Hybrid  │
    │ Search  │  │   RAG    │  │  Fusion  │
    │(Local/  │  │(Vector)  │  │(Both)    │
    │Global/  │  │          │  │          │
    │DRIFT)   │  │          │  │          │
    └────┬────┘  └────┬─────┘  └────┬─────┘
         │            │             │
         └────────────┼─────────────┘
                      ▼
              ┌───────────────┐
              │  LLM ANSWER   │
              │  GENERATION   │
              └───────────────┘
```

## 2. Indexing Pipeline (Offline)

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌────────────┐
│  Input   │───▶│  Text    │───▶│   Entity &   │───▶│  Finalize  │
│Documents │    │ Chunking │    │ Relationship │    │   Graph    │
│(.txt,.csv│    │(300 tok) │    │ Extraction   │    │ (degrees)  │
│ .pdf)    │    │          │    │   (LLM)      │    │            │
└──────────┘    └──────────┘    └──────────────┘    └─────┬──────┘
                                                          │
     ┌────────────────────────────────────────────────────┘
     │
     ▼
┌──────────┐    ┌──────────────┐    ┌────────────────┐    ┌──────────┐
│Community │───▶│  Community   │───▶│   Embedding    │───▶│  Vector  │
│Detection │    │   Report     │    │  Generation    │    │  Store   │
│ (Leiden) │    │ Generation   │    │(entities,text  │    │(LanceDB) │
│          │    │   (LLM)      │    │units,reports)  │    │          │
└──────────┘    └──────────────┘    └────────────────┘    └──────────┘
```

### Standard Pipeline Workflow Order:
```python
_standard_workflows = [
    "create_base_text_units",      # Phase 1: Chunking
    "create_final_documents",      # Phase 1: Store document metadata
    "extract_graph",               # Phase 2: Entity & Relationship extraction
    "finalize_graph",              # Phase 2: Compute edge degrees
    "extract_covariates",          # Phase 2: Optional claims extraction
    "create_communities",          # Phase 3: Leiden clustering
    "create_final_text_units",     # Phase 1: Link text units to entities
    "create_community_reports",    # Phase 3: LLM community summaries
    "generate_text_embeddings",    # Phase 4: All embeddings
]
```

## 3. Data Model

```
┌─────────────┐       ┌────────────────┐       ┌───────────────┐
│  Document   │──1:N──│   TextUnit     │──M:N──│    Entity     │
│             │       │                │       │               │
│ id          │       │ id             │       │ id            │
│ title       │       │ text           │       │ title         │
│ text        │       │ document_id    │       │ type          │
│ raw_data    │       │ n_tokens       │       │ description   │
│             │       │ entity_ids     │       │ desc_embedding│
│             │       │ relationship_ids│      │ community_ids │
│             │       │                │       │ text_unit_ids │
└─────────────┘       └────────────────┘       │ rank          │
                                               └───────┬───────┘
                                                       │
                        ┌──────────────────────────────┘
                        │ M:N
                        ▼
                ┌───────────────┐       ┌──────────────────┐
                │ Relationship  │       │    Community      │
                │               │       │                   │
                │ id            │       │ id                │
                │ source        │       │ title             │
                │ target        │       │ level             │
                │ weight        │       │ parent            │
                │ description   │       │ children          │
                │ desc_embedding│       │ entity_ids        │
                │ text_unit_ids │       │ relationship_ids  │
                │ rank          │       │ text_unit_ids     │
                └───────────────┘       │ size              │
                                        └────────┬──────────┘
                                                 │ 1:1
                                                 ▼
                                        ┌──────────────────┐
                                        │ CommunityReport  │
                                        │                  │
                                        │ id               │
                                        │ community_id     │
                                        │ summary          │
                                        │ full_content     │
                                        │ rank             │
                                        │ content_embedding│
                                        └──────────────────┘
```

## 4. Query Methods Comparison

| Feature | Local Search | Global Search | DRIFT Search | Basic Search |
|---------|-------------|---------------|--------------|--------------|
| **Best for** | Specific entity questions | Broad thematic questions | Multi-hop reasoning | Simple factual lookup |
| **Context Source** | Entities + Relations + Text Units + Community Reports | Community Reports (all) | Community Reports + Local Search iteratively | Text Units only |
| **LLM Calls** | 1 | N (map) + 1 (reduce) | M (primer + iterations) | 1 |
| **Speed** | Fast | Slower (many batches) | Slowest (iterative) | Fastest |
| **Accuracy** | High for local info | High for global themes | Highest for complex queries | Baseline |
| **Cost** | Medium | High | Highest | Low |

## 5. Package Dependency Map

```
graphrag (main)
├── graphrag-llm          # LLM completion & embedding wrappers
│   ├── completion/       # ChatOpenAI, AzureOpenAI wrappers
│   ├── embedding/        # Text embedding models
│   ├── tokenizer/        # Token counting
│   └── rate_limit/       # Rate limiting & retry
├── graphrag-vectors      # Vector store abstractions
│   ├── lancedb.py        # LanceDB implementation
│   ├── azure_ai_search.py# Azure AI Search implementation
│   └── cosmosdb.py       # CosmosDB implementation
├── graphrag-chunking     # Document chunking
├── graphrag-input        # Document parsing & loading
├── graphrag-storage      # Storage backends (file, blob, cosmos)
├── graphrag-cache        # LLM response caching
└── graphrag-common       # Shared config & utilities
```

## 6. Configuration Structure (`settings.yaml`)

```yaml
# Key configuration sections:
models:
  default_chat_model:
    type: openai_chat          # or azure_openai_chat
    model: gpt-4o
    api_key: ${GRAPHRAG_API_KEY}

  default_embedding_model:
    type: openai_embedding
    model: text-embedding-3-small

chunking:
    size: 300
    overlap: 100
    encoding_model: cl100k_base

extract_graph:
    entity_types: [organization, person, location, event]
    max_gleanings: 1           # re-extraction passes

cluster_graph:
    max_cluster_size: 10
    use_lcc: true

community_reports:
    max_length: 2000
    max_input_length: 8000

embed_text:
    names: [entity_description, text_unit_text, community_full_content]
    batch_size: 16

vector_store:
    type: lancedb
    db_uri: ./lancedb

local_search:
    text_unit_prop: 0.5
    community_prop: 0.1
    top_k_entities: 10
    top_k_relationships: 10
    max_context_tokens: 12000

global_search:
    data_max_tokens: 12000
    map_max_length: 1000
    reduce_max_length: 2000
```
