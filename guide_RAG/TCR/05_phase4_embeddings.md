# 🔍 Phase 4 Pseudocode: Embedding Generation

## Overview
This phase generates vector embeddings for entity descriptions, text unit texts,
and community report content. These embeddings are stored in a vector store and
used at query time for similarity-based retrieval.

---

## 4.1 Generate Text Embeddings Workflow

```pseudo
FUNCTION generate_text_embeddings(config, context):
    """
    Generate embeddings for all configured fields and store them
    in the vector store.
    
    Source: packages/graphrag/graphrag/index/workflows/generate_text_embeddings.py
    
    Three embedding fields by default:
        1. entity_description_embedding  — for entity search
        2. text_unit_text_embedding       — for basic RAG search
        3. community_full_content_embedding — for community search
    """
    
    # Step 1: Initialize embedding model
    model = create_embedding(
        config = config.embed_text.embedding_model_config,
        cache  = context.cache.child("embed_text")
    )
    tokenizer = model.tokenizer
    
    # Step 2: Get list of fields to embed
    embedded_fields = config.embed_text.names
    # e.g., ["entity_description", "text_unit_text", "community_full_content"]
    
    # Step 3: Process each field
    FOR EACH field_name IN embedded_fields:
        
        field_config = EMBEDDING_FIELDS[field_name]
        # field_config = {
        #     name:         "entity_description",
        #     table_name:   "entities",
        #     embed_column: "title_description",    # column to embed
        #     row_transform: transform_entity_row_for_embedding  (optional)
        # }
        
        # Step 3a: Check source table exists
        IF NOT table_provider.has(field_config.table_name):
            LOG_WARNING(f"Source table {field_config.table_name} not found, skipping")
            CONTINUE
        
        # Step 3b: Initialize vector store for this field
        vector_store = create_vector_store(
            config       = config.vector_store,
            index_schema = config.vector_store.index_schema[field_config.name]
        )
        vector_store.connect()
        
        # Step 3c: Open source table for streaming read
        input_table = OPEN_TABLE(field_config.table_name,
                                 transformer = field_config.row_transform)
        
        # Step 3d: Embed in batches
        count = AWAIT embed_text(
            input_table    = input_table,
            model          = model,
            tokenizer      = tokenizer,
            embed_column   = field_config.embed_column,
            batch_size     = config.embed_text.batch_size,        # default: 16
            batch_max_tokens = config.embed_text.batch_max_tokens, # default: 8191
            num_threads    = config.concurrent_requests,
            vector_store   = vector_store
        )
        
        LOG_INFO(f"Embedded {count} rows for {field_config.name}")
    
    RETURN None
```

---

## 4.2 Batch Embedding Algorithm

```pseudo
FUNCTION embed_text(input_table, model, tokenizer, embed_column, 
                    batch_size, batch_max_tokens, num_threads, vector_store):
    """
    Read rows from input table, batch them, send to embedding model,
    and write results to vector store.
    
    Source: packages/graphrag/graphrag/index/operations/embed_text/embed_text.py
    """
    
    batch = []
    batch_tokens = 0
    total_count = 0
    
    ASYNC FOR EACH row IN input_table:
        text = row[embed_column]
        
        IF text IS EMPTY OR text IS None:
            CONTINUE
        
        text_tokens = tokenizer.count_tokens(text)
        
        # Check if adding this text would exceed batch limits
        IF (LENGTH(batch) >= batch_size) OR (batch_tokens + text_tokens > batch_max_tokens):
            # Process current batch
            AWAIT _process_batch(batch, model, vector_store)
            total_count += LENGTH(batch)
            batch = []
            batch_tokens = 0
        
        batch.APPEND({
            "id":   row["id"],
            "text": text,
            "row":  row        # keep full row for metadata
        })
        batch_tokens += text_tokens
    
    # Process remaining batch
    IF LENGTH(batch) > 0:
        AWAIT _process_batch(batch, model, vector_store)
        total_count += LENGTH(batch)
    
    RETURN total_count


FUNCTION _process_batch(batch, model, vector_store):
    """
    Send a batch of texts to the embedding model and store results.
    """
    
    texts = [item["text"] FOR item IN batch]
    
    # Call embedding API (e.g., OpenAI text-embedding-3-small)
    embeddings = AWAIT model.embed_batch(texts)
    # Returns: list of float vectors, e.g., [[0.01, -0.03, ...], ...]
    # Dimension depends on model (e.g., 1536 for text-embedding-3-small)
    
    # Write to vector store
    FOR i, item IN ENUMERATE(batch):
        vector_store.upsert(
            id        = item["id"],
            embedding = embeddings[i],
            metadata  = {
                "text": item["text"],
                # Additional fields from the row (title, type, etc.)
            }
        )
```

---

## 4.3 Entity Row Transform for Embedding

```pseudo
FUNCTION transform_entity_row_for_embedding(row):
    """
    Transform an entity row for embedding.
    Combines title and description into a single embeddable string.
    
    Source: packages/graphrag/graphrag/data_model/row_transformers.py
    """
    
    title = row.get("title", "")
    description = row.get("description", "")
    
    # Create combined text for embedding
    IF description:
        row["title_description"] = f"{title}: {description}"
    ELSE:
        row["title_description"] = title
    
    RETURN row
```

---

## 4.4 Vector Store Abstraction

```pseudo
CLASS VectorStore:
    """
    Abstract base for vector storage backends.
    
    Implementations:
        - LanceDB     (local, file-based)
        - AzureAISearch (cloud, managed)
        - CosmosDB    (cloud, multi-model)
    
    Source: packages/graphrag-vectors/graphrag_vectors/vector_store.py
    """
    
    FUNCTION connect():
        """Establish connection to the vector store."""
        pass
    
    FUNCTION upsert(id, embedding, metadata):
        """Insert or update a vector record."""
        pass
    
    FUNCTION search(query_embedding, top_k, filters = None):
        """
        Find the top-K most similar vectors.
        
        Returns: list of (id, score, metadata) tuples
                 sorted by cosine similarity descending
        """
        pass
    
    FUNCTION delete(ids):
        """Remove vectors by ID."""
        pass


# Example: LanceDB Implementation
CLASS LanceDBVectorStore(VectorStore):
    
    FUNCTION connect():
        self.db = lancedb.connect(self.config.db_uri)
        self.table = self.db.open_table(self.config.table_name)
    
    FUNCTION upsert(id, embedding, metadata):
        record = {"id": id, "vector": embedding, **metadata}
        self.table.add([record])
    
    FUNCTION search(query_embedding, top_k, filters = None):
        results = self.table.search(query_embedding)
                         .limit(top_k)
                         .to_list()
        RETURN [(r["id"], r["_distance"], r) FOR r IN results]
```

---

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `embedding_model` | text-embedding-3-small | OpenAI embedding model |
| `batch_size` | 16 | Texts per embedding API call |
| `batch_max_tokens` | 8191 | Max tokens per batch |
| `vector_store.type` | lancedb | Vector store backend |
| `vector_store.db_uri` | ./lancedb | Storage path |
| `concurrent_requests` | 25 | Parallel embedding calls |

## Embedding Fields Summary

| Field Name | Source Table | Source Column | Purpose |
|------------|-------------|---------------|---------|
| `entity_description` | entities | title + description | Local Search entity matching |
| `text_unit_text` | text_units | text | Basic Search (traditional RAG) |
| `community_full_content` | community_reports | full_content | Community-level search |
