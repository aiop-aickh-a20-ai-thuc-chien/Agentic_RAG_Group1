# 📄 Phase 1 Pseudocode: Document Ingestion & Text Chunking

## Overview
This phase handles loading raw documents, splitting them into manageable text chunks
(called "text units"), and storing them for downstream processing.

---

## 1.1 Document Loading

```pseudo
FUNCTION load_input_documents(config, context):
    """
    Load raw documents from the configured input directory.
    Supports: .txt, .csv, .pdf (via graphrag-input package)
    """
    
    # Step 1: Read input configuration
    input_storage = create_storage(config.input_storage)
    
    # Step 2: Discover all document files
    file_list = input_storage.list_files(
        pattern = config.input.file_pattern,  # e.g., "*.txt"
        base_dir = config.input.base_dir
    )
    
    # Step 3: Parse each file into a TextDocument
    documents = []
    FOR each file IN file_list:
        raw_text = input_storage.read(file.path)
        
        doc = TextDocument(
            id     = generate_uuid(),
            title  = extract_title(file.name),
            text   = raw_text,
            creation_date = file.metadata.created_at,
            raw_data = file.raw_bytes   # keep original for reference
        )
        documents.APPEND(doc)
    
    # Step 4: Write documents table to output storage
    documents_df = convert_to_dataframe(documents)
    STORE documents_df TO "documents" table
    
    RETURN documents_df
```

---

## 1.2 Text Chunking (create_base_text_units)

```pseudo
FUNCTION create_base_text_units(config, context):
    """
    Split documents into text chunks (text units) with configurable
    size, overlap, and optional metadata prepending.
    
    Key Parameters:
        chunk_size   = 300 tokens (default)
        overlap      = 100 tokens (default)
        encoding     = "cl100k_base" (tiktoken)
    """
    
    # Step 1: Initialize tokenizer and chunker
    tokenizer = get_tokenizer(encoding_model = config.chunking.encoding_model)
    chunker   = create_chunker(
        config    = config.chunking,
        encode_fn = tokenizer.encode,
        decode_fn = tokenizer.decode
    )
    
    # Step 2: Open document table for streaming read
    documents_table = OPEN_TABLE("documents")
    text_units_table = OPEN_TABLE("text_units")
    
    # Step 3: Process each document
    FOR EACH doc IN documents_table:
        
        # Step 3a: Optional metadata prepending
        IF config.chunking.prepend_metadata IS NOT EMPTY:
            # Collects specified fields (title, date, etc.) and prepends them
            metadata = doc.collect(config.chunking.prepend_metadata)
            transformer = add_metadata(metadata, line_delimiter = ".\n")
        ELSE:
            transformer = None
        
        # Step 3b: Chunk the document text
        chunks = chunker.chunk(doc.text, transform = transformer)
        # chunker internally:
        #   1. Encodes text to tokens
        #   2. Splits at chunk_size boundaries
        #   3. Adds overlap from previous chunk
        #   4. Decodes back to text
        
        # Step 3c: Create text unit records
        FOR EACH chunk IN chunks:
            IF chunk.text IS EMPTY:
                CONTINUE
            
            text_unit = {
                "id":          SHA512_HASH(chunk.text),    # deterministic ID
                "document_id": doc.id,
                "text":        chunk.text,
                "n_tokens":    tokenizer.count_tokens(chunk.text)
            }
            
            WRITE text_unit TO text_units_table
    
    RETURN text_units_table


# ====== CHUNKING ALGORITHM DETAIL ======

FUNCTION token_chunker(text, chunk_size, overlap, encode, decode):
    """
    The actual chunking logic (from graphrag-chunking package).
    """
    tokens = encode(text)           # e.g., [1234, 5678, 9012, ...]
    total_tokens = LENGTH(tokens)
    
    chunks = []
    start = 0
    
    WHILE start < total_tokens:
        end = MIN(start + chunk_size, total_tokens)
        chunk_tokens = tokens[start:end]
        chunk_text = decode(chunk_tokens)
        
        chunks.APPEND(TextChunk(
            text     = chunk_text,
            n_tokens = LENGTH(chunk_tokens)
        ))
        
        # Move forward by (chunk_size - overlap) to create overlap
        start = start + chunk_size - overlap
    
    RETURN chunks
```

---

## 1.3 Final Documents (create_final_documents)

```pseudo
FUNCTION create_final_documents(config, context):
    """
    Enrich document records with text unit references.
    After chunking, we know which text units belong to which document.
    """
    
    documents = READ_TABLE("documents")
    text_units = READ_TABLE("text_units")
    
    # Group text units by document_id
    doc_text_units = GROUP_BY(text_units, key = "document_id")
    
    FOR EACH doc IN documents:
        # Attach text unit IDs
        doc.text_unit_ids = [tu.id FOR tu IN doc_text_units[doc.id]]
        doc.text_unit_count = LENGTH(doc.text_unit_ids)
    
    STORE documents TO "final_documents" table
    RETURN documents
```

---

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Chunk Size | 300 tokens | Balanced between context and granularity |
| Overlap | 100 tokens | Prevents information loss at boundaries |
| ID Generation | SHA-512 of text | Deterministic, deduplication-friendly |
| Tokenizer | cl100k_base (tiktoken) | Matches GPT-4 tokenization exactly |
| Streaming | Row-by-row processing | Memory efficient for large corpora |
| Metadata Prepend | Optional title/date | Helps LLM understand chunk context |
