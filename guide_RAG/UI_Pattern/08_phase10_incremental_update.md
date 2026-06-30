# 🔄 Phase 10 Pseudocode: Incremental Update Pipeline

## Overview
This phase handles updating the knowledge graph when new documents are added,
without requiring full re-indexing. The GraphRAG codebase already supports
incremental updates with `StandardUpdate` and `FastUpdate` pipeline modes.

---

## 10.1 Update Pipeline Overview

```pseudo
# Update pipeline is a superset of the standard pipeline:
_update_pipeline = [
    # First: re-run standard indexing on NEW documents only
    "load_update_documents",           # detect new/changed docs
    "create_base_text_units",          # chunk new docs
    "create_final_documents",          # store new doc metadata
    "extract_graph",                   # extract entities from new chunks
    "finalize_graph",                  # compute degrees
    "extract_covariates",              # optional
    "create_communities",              # re-cluster
    "create_final_text_units",         # link text units
    "create_community_reports",        # generate reports
    "generate_text_embeddings",        # embed new items
    
    # Then: merge new (delta) index with existing (previous) index
    "update_final_documents",          # merge document tables
    "update_entities_relationships",   # merge entity/relationship tables
    "update_text_units",               # merge text unit tables
    "update_covariates",               # merge covariate tables
    "update_communities",              # merge community tables
    "update_community_reports",        # merge report tables
    "update_text_embeddings",          # merge embedding tables
    "update_clean_state",              # clean up temporary files
]
```

---

## 10.2 Load Update Documents (Delta Detection)

```pseudo
FUNCTION load_update_documents(config, context):
    """
    Detect which documents are new or changed since the last index run.
    
    Source: packages/graphrag/graphrag/index/workflows/load_update_documents.py
    """
    
    # Step 1: Load current input documents
    current_docs = load_documents_from_input(config.input_storage)
    
    # Step 2: Load previously indexed documents
    previous_docs = READ_TABLE("documents", from = context.previous_table_provider)
    previous_doc_ids = SET(previous_docs["id"])
    
    # Step 3: Find delta (new + modified documents)
    delta_docs = []
    FOR EACH doc IN current_docs:
        doc_id = generate_doc_id(doc)   # based on content hash
        
        IF doc_id NOT IN previous_doc_ids:
            # New or modified document
            delta_docs.APPEND(doc)
    
    IF LENGTH(delta_docs) == 0:
        LOG_INFO("No new documents found. Skipping update.")
        RETURN WorkflowFunctionOutput(result = None, stop = True)
    
    LOG_INFO(f"Found {LENGTH(delta_docs)} new/modified documents")
    
    # Step 4: Store delta documents for downstream processing
    delta_df = convert_to_dataframe(delta_docs)
    STORE delta_df TO "documents" table (in delta storage)
    
    RETURN delta_df
```

---

## 10.3 Update Entities & Relationships

```pseudo
FUNCTION update_entities_relationships(config, context):
    """
    Merge newly extracted entities/relationships with the existing index.
    
    Source: packages/graphrag/graphrag/index/workflows/update_entities_relationships.py
    
    Strategy:
        - New entities: add directly
        - Existing entities (same title): merge descriptions, update attributes
        - New relationships: add directly
        - Existing relationships (same source+target): merge descriptions, update weight
    """
    
    # Step 1: Load previous and delta data
    previous_entities = READ_TABLE("entities", from = context.previous_table_provider)
    delta_entities    = READ_TABLE("entities", from = context.delta_table_provider)
    
    previous_relationships = READ_TABLE("relationships", from = context.previous_table_provider)
    delta_relationships    = READ_TABLE("relationships", from = context.delta_table_provider)
    
    # Step 2: Merge entities
    merged_entities = merge_dataframes(
        previous = previous_entities,
        delta    = delta_entities,
        on       = "title",           # match by entity name
        strategy = {
            "description":     "concatenate_and_resummarize",
            "text_unit_ids":   "union",
            "community_ids":   "union",
            "rank":            "max",     # keep highest rank
            "type":            "keep_latest",
            "attributes":      "deep_merge"
        }
    )
    
    # Step 3: Merge relationships
    merged_relationships = merge_dataframes(
        previous = previous_relationships,
        delta    = delta_relationships,
        on       = ["source", "target"],
        strategy = {
            "description":     "concatenate_and_resummarize",
            "text_unit_ids":   "union",
            "weight":          "sum",      # additive weight
            "rank":            "max"
        }
    )
    
    # Step 4: Store merged data to output
    STORE merged_entities TO "entities" table (output storage)
    STORE merged_relationships TO "relationships" table (output storage)
    
    RETURN (merged_entities, merged_relationships)


FUNCTION merge_dataframes(previous, delta, on, strategy):
    """
    Generic dataframe merge with configurable field strategies.
    """
    
    # Find overlapping and unique records
    overlap_mask = delta[on].isin(previous[on])
    new_records = delta[~overlap_mask]
    update_records = delta[overlap_mask]
    
    # Start with previous data
    merged = previous.copy()
    
    # Apply updates for overlapping records
    FOR EACH update_row IN update_records:
        match_idx = merged[merged[on] == update_row[on]].index
        
        IF LENGTH(match_idx) > 0:
            existing_row = merged.loc[match_idx[0]]
            
            FOR EACH (column, strat) IN strategy.items():
                IF strat == "concatenate_and_resummarize":
                    merged.at[match_idx[0], column] = (
                        str(existing_row[column]) + "\n" + str(update_row[column])
                    )
                ELIF strat == "union":
                    merged.at[match_idx[0], column] = list(
                        set(existing_row[column] or []) | set(update_row[column] or [])
                    )
                ELIF strat == "max":
                    merged.at[match_idx[0], column] = max(
                        existing_row[column] or 0, update_row[column] or 0
                    )
                ELIF strat == "sum":
                    merged.at[match_idx[0], column] = (
                        (existing_row[column] or 0) + (update_row[column] or 0)
                    )
    
    # Append truly new records
    merged = CONCAT(merged, new_records)
    
    RETURN merged
```

---

## 10.4 Update Communities

```pseudo
FUNCTION update_communities(config, context):
    """
    Re-cluster communities with merged entity/relationship data.
    
    Source: packages/graphrag/graphrag/index/workflows/update_communities.py
    """
    
    # Simply re-run community detection on the merged graph
    # (No incremental Leiden — full re-cluster is required)
    
    merged_entities = READ_TABLE("entities", from = output)
    merged_relationships = READ_TABLE("relationships", from = output)
    
    # Full re-clustering on merged graph
    new_communities = create_communities(
        entities      = merged_entities,
        relationships = merged_relationships,
        config        = config.cluster_graph
    )
    
    STORE new_communities TO "communities" table
    RETURN new_communities
```

---

## 10.5 Update Community Reports

```pseudo
FUNCTION update_community_reports(config, context):
    """
    Regenerate community reports for communities that changed.
    
    Optimization: Only regenerate reports for communities whose
    entity composition changed (new entities added, entities removed).
    """
    
    previous_communities = READ_TABLE("communities", from = context.previous_table_provider)
    new_communities = READ_TABLE("communities", from = output)
    previous_reports = READ_TABLE("community_reports", from = context.previous_table_provider)
    
    # Detect which communities changed
    changed_communities = []
    unchanged_communities = []
    
    FOR EACH new_comm IN new_communities:
        prev_match = previous_communities WHERE id == new_comm.id
        
        IF prev_match IS EMPTY:
            # New community
            changed_communities.APPEND(new_comm)
        ELIF SET(new_comm.entity_ids) != SET(prev_match.entity_ids):
            # Entity composition changed
            changed_communities.APPEND(new_comm)
        ELSE:
            # Unchanged — reuse previous report
            unchanged_communities.APPEND(new_comm)
    
    # Regenerate reports only for changed communities
    new_reports = AWAIT create_community_reports(
        communities = changed_communities,
        entities    = merged_entities,
        relationships = merged_relationships,
        model       = model
    )
    
    # Combine with unchanged reports
    unchanged_reports = [
        r FOR r IN previous_reports
        IF r.community_id IN [c.id FOR c IN unchanged_communities]
    ]
    
    all_reports = CONCAT(new_reports, unchanged_reports)
    STORE all_reports TO "community_reports" table
    
    RETURN all_reports
```

---

## 10.6 Update Embeddings

```pseudo
FUNCTION update_text_embeddings(config, context):
    """
    Generate embeddings only for new/changed items.
    
    Source: packages/graphrag/graphrag/index/workflows/update_text_embeddings.py
    """
    
    # Compare current vs previous to find what needs embedding
    current_entities = READ_TABLE("entities", from = output)
    previous_entity_ids = SET(
        READ_TABLE("entities", from = context.previous_table_provider)["id"]
    )
    
    # Only embed entities that are new or have changed descriptions
    entities_to_embed = current_entities[
        ~current_entities["id"].isin(previous_entity_ids)
    ]
    
    IF LENGTH(entities_to_embed) > 0:
        AWAIT embed_text(
            input_data   = entities_to_embed,
            model        = embedding_model,
            embed_column = "title_description",
            vector_store = entity_vector_store
        )
    
    # Same for text units and community reports
    # ... (analogous logic)
    
    RETURN None
```

---

## 10.7 Storage Layout During Update

```
output/                          ← main output storage
├── entities.parquet
├── relationships.parquet
├── communities.parquet
├── community_reports.parquet
├── text_units.parquet
└── documents.parquet

update/                          ← update working directory
└── 20240615-143022/             ← timestamped run
    ├── delta/                   ← new index (from new docs only)
    │   ├── entities.parquet
    │   ├── relationships.parquet
    │   ├── text_units.parquet
    │   └── documents.parquet
    └── previous/                ← backup of previous output
        ├── entities.parquet
        ├── relationships.parquet
        └── ...

# After update completes, output/ contains the merged data
```

---

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Pipeline mode | `standard-update` | Use `IndexingMethod.StandardUpdate` |
| Delta detection | Content hash | Detect changes by SHA hash of document content |
| Community re-cluster | Full | No incremental Leiden (re-run on merged graph) |
| Report regeneration | Changed only | Only re-generate for communities with new entities |
| Embedding update | Delta only | Only embed new/changed items |
