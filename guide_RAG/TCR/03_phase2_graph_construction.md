# 🔗 Phase 2 Pseudocode: Knowledge Graph Construction

## Overview
This phase extracts entities and relationships from text units using an LLM,
merges duplicate entities, summarizes descriptions, and builds the final
knowledge graph.

---

## 2.1 Entity & Relationship Extraction (extract_graph)

```pseudo
FUNCTION extract_graph_workflow(config, context):
    """
    Main workflow: extract entities and relationships from all text units.
    
    Source: packages/graphrag/graphrag/index/workflows/extract_graph.py
    """
    
    # Step 1: Load text units from previous phase
    text_units = READ_TABLE("text_units")
    
    # Step 2: Initialize extraction LLM
    extraction_model = create_completion(
        config = config.extract_graph.completion_model_config,
        cache  = context.cache.child("extract_graph")    # cache LLM responses
    )
    extraction_prompt = config.extract_graph.resolved_prompts().extraction_prompt
    entity_types = config.extract_graph.entity_types
    # e.g., ["organization", "person", "location", "event"]
    
    # Step 3: Initialize summarization LLM
    summarization_model = create_completion(
        config = config.summarize_descriptions.completion_model_config,
        cache  = context.cache.child("summarize_descriptions")
    )
    
    # Step 4: Extract entities and relationships
    raw_entities, raw_relationships = AWAIT extract_graph(
        text_units          = text_units,
        extraction_model    = extraction_model,
        extraction_prompt   = extraction_prompt,
        entity_types        = entity_types,
        max_gleanings       = config.extract_graph.max_gleanings,   # default: 1
        num_threads         = config.concurrent_requests             # parallel
    )
    
    # Step 5: Summarize descriptions (merge duplicates)
    entities, relationships = AWAIT summarize_descriptions(
        raw_entities        = raw_entities,
        raw_relationships   = raw_relationships,
        summarization_model = summarization_model,
        max_summary_length  = config.summarize_descriptions.max_length
    )
    
    STORE entities TO "entities" table
    STORE relationships TO "relationships" table
    
    RETURN (entities, relationships)
```

---

## 2.2 Core Extraction Algorithm

```pseudo
FUNCTION extract_graph(text_units, model, prompt, entity_types, max_gleanings, num_threads):
    """
    For each text unit, use LLM to extract entities and relationships.
    
    Source: packages/graphrag/graphrag/index/operations/extract_graph/extract_graph.py
    """
    
    all_entities = []
    all_relationships = []
    
    # Process text units in parallel (with semaphore for rate limiting)
    PARALLEL FOR EACH text_unit IN text_units (max_concurrent = num_threads):
        
        # --- Initial extraction ---
        extraction_result = AWAIT llm_extract(
            model         = model,
            prompt        = prompt,
            text          = text_unit.text,
            entity_types  = entity_types,
            text_unit_id  = text_unit.id
        )
        
        entities, relationships = parse_extraction_result(extraction_result)
        
        # --- Gleaning passes (re-extraction for completeness) ---
        FOR gleaning_round = 1 TO max_gleanings:
            gleaning_result = AWAIT llm_extract(
                model         = model,
                prompt        = GLEANING_PROMPT,   # "Did you miss any entities?"
                text          = text_unit.text,
                entity_types  = entity_types,
                text_unit_id  = text_unit.id,
                previous_extraction = extraction_result
            )
            
            new_entities, new_relationships = parse_extraction_result(gleaning_result)
            entities.EXTEND(new_entities)
            relationships.EXTEND(new_relationships)
        
        all_entities.EXTEND(entities)
        all_relationships.EXTEND(relationships)
    
    # Convert to DataFrames
    entities_df = DataFrame(all_entities)      # columns: [title, type, description, text_unit_ids]
    relationships_df = DataFrame(all_relationships)  # columns: [source, target, description, weight, text_unit_ids]
    
    RETURN (entities_df, relationships_df)


FUNCTION llm_extract(model, prompt, text, entity_types, text_unit_id):
    """
    Make a single LLM call to extract entities and relationships from text.
    
    The prompt template instructs the LLM to output in a structured format:
    ("entity"<|>ENTITY_NAME<|>ENTITY_TYPE<|>ENTITY_DESCRIPTION)
    ("relationship"<|>SOURCE<|>TARGET<|>DESCRIPTION<|>WEIGHT)
    """
    
    formatted_prompt = prompt.format(
        input_text   = text,
        entity_types = ", ".join(entity_types),
        tuple_delimiter  = "<|>",
        record_delimiter = "##",
        completion_delimiter = "<|COMPLETE|>"
    )
    
    response = AWAIT model.completion(
        messages = [
            {"role": "system", "content": formatted_prompt},
            {"role": "user",   "content": text}
        ]
    )
    
    RETURN response.content


FUNCTION parse_extraction_result(result_text):
    """
    Parse the LLM output into structured entity and relationship records.
    
    Expected format:
        ("entity"<|>MICROSOFT<|>ORGANIZATION<|>Microsoft is a technology company...)
        ("relationship"<|>MICROSOFT<|>AZURE<|>Microsoft owns Azure cloud...<|>9)
    """
    
    entities = []
    relationships = []
    
    records = result_text.split("##")    # split by record delimiter
    
    FOR EACH record IN records:
        fields = record.strip("()").split("<|>")
        
        IF fields[0] == "entity":
            entities.APPEND({
                "title":       UPPERCASE(fields[1].strip()),
                "type":        fields[2].strip(),
                "description": fields[3].strip(),
                "text_unit_ids": [current_text_unit_id]
            })
        
        ELIF fields[0] == "relationship":
            relationships.APPEND({
                "source":      UPPERCASE(fields[1].strip()),
                "target":      UPPERCASE(fields[2].strip()),
                "description": fields[3].strip(),
                "weight":      FLOAT(fields[4].strip()) IF LENGTH(fields) > 4 ELSE 1.0,
                "text_unit_ids": [current_text_unit_id]
            })
    
    RETURN (entities, relationships)
```

---

## 2.3 Description Summarization (Merge Duplicates)

```pseudo
FUNCTION summarize_descriptions(entities_df, relationships_df, model, max_summary_length, max_input_tokens, prompt):
    """
    When the same entity/relationship appears in multiple text units,
    their descriptions are merged and summarized by the LLM.
    
    Source: packages/graphrag/graphrag/index/operations/summarize_descriptions/
    """
    
    # --- Entity Summarization ---
    # Group entities by title (case-insensitive match)
    entity_groups = GROUP_BY(entities_df, key = "title")
    
    entity_summaries = []
    FOR EACH (entity_name, descriptions) IN entity_groups:
        IF LENGTH(descriptions) == 1:
            # Only one description, use as-is
            summary = descriptions[0]
        ELSE:
            # Multiple descriptions from different text units
            # Concatenate and ask LLM to summarize
            combined_text = "\n".join(descriptions)
            
            IF token_count(combined_text) > max_input_tokens:
                # Truncate or batch if too long
                combined_text = TRUNCATE(combined_text, max_input_tokens)
            
            summary = AWAIT model.completion(
                messages = [
                    {"role": "system", "content": prompt.format(
                        entity_name = entity_name,
                        description_list = combined_text,
                        max_length = max_summary_length
                    )}
                ]
            )
        
        entity_summaries.APPEND({
            "title":       entity_name,
            "description": summary
        })
    
    # --- Relationship Summarization ---
    # Group relationships by (source, target) pair
    rel_groups = GROUP_BY(relationships_df, key = ["source", "target"])
    
    rel_summaries = []
    FOR EACH ((source, target), descriptions) IN rel_groups:
        IF LENGTH(descriptions) == 1:
            summary = descriptions[0]
        ELSE:
            combined_text = "\n".join(descriptions)
            summary = AWAIT model.completion(...)  # same pattern as entities
        
        rel_summaries.APPEND({
            "source":      source,
            "target":      target,
            "description": summary
        })
    
    # Merge summaries back into the original DataFrames
    entities_final = entities_df.drop("description").merge(
        entity_summaries, on = "title", how = "left"
    )
    relationships_final = relationships_df.drop("description").merge(
        rel_summaries, on = ["source", "target"], how = "left"
    )
    
    RETURN (entities_final, relationships_final)
```

---

## 2.4 Finalize Graph

```pseudo
FUNCTION finalize_graph(config, context):
    """
    Compute graph metrics (degree centrality, edge weights)
    and finalize entity/relationship records.
    
    Source: packages/graphrag/graphrag/index/workflows/finalize_graph.py
    """
    
    entities = READ_TABLE("entities")
    relationships = READ_TABLE("relationships")
    
    # Step 1: Compute edge combined degree
    # For each relationship, degree = degree(source) + degree(target)
    FOR EACH rel IN relationships:
        source_degree = COUNT(relationships WHERE source == rel.source OR target == rel.source)
        target_degree = COUNT(relationships WHERE source == rel.target OR target == rel.target)
        rel.combined_degree = source_degree + target_degree
    
    # Step 2: Finalize entities
    FOR EACH entity IN entities:
        entity.degree = COUNT(relationships WHERE source == entity.title OR target == entity.title)
        entity.rank = entity.degree     # rank by number of connections
        entity.human_readable_id = auto_increment_id
    
    # Step 3: Finalize relationships
    FOR EACH rel IN relationships:
        rel.rank = rel.combined_degree
        rel.human_readable_id = auto_increment_id
    
    STORE entities TO "entities" table (overwrite)
    STORE relationships TO "relationships" table (overwrite)
    
    RETURN (entities, relationships)
```

---

## 2.5 Extract Covariates (Optional)

```pseudo
FUNCTION extract_covariates(config, context):
    """
    Optional: Extract claims/covariates from text units.
    Claims are assertions about entities (e.g., "Company X violated regulation Y").
    
    Source: packages/graphrag/graphrag/index/workflows/extract_covariates.py
    """
    
    IF NOT config.extract_claims.enabled:
        RETURN SKIP
    
    text_units = READ_TABLE("text_units")
    
    covariates = []
    FOR EACH text_unit IN text_units:
        claims = AWAIT model.completion(
            prompt = CLAIMS_EXTRACTION_PROMPT.format(
                text = text_unit.text
            )
        )
        
        FOR EACH claim IN parse_claims(claims):
            covariates.APPEND(Covariate(
                id          = generate_uuid(),
                subject_id  = claim.subject_entity,    # entity name
                type        = claim.claim_type,
                status      = claim.status,             # TRUE/FALSE/SUSPECTED
                description = claim.description,
                text_unit_id = text_unit.id
            ))
    
    STORE covariates TO "covariates" table
    RETURN covariates
```

---

## Extraction Prompt Template (Simplified)

```
-Goal-
Given a text document, identify all entities and relationships.

-Entity Types-
{entity_types}

-Steps-
1. Identify all entities. For each entity, extract:
   - entity_name: Name of the entity (CAPITALIZED)
   - entity_type: One of [{entity_types}]
   - entity_description: Comprehensive description

2. Identify all relationships between identified entities. For each:
   - source_entity: Name of source entity
   - target_entity: Name of target entity
   - relationship_description: Explanation of how they relate
   - relationship_strength: Integer score 1-10

-Output Format-
("entity"{tuple_delimiter}ENTITY_NAME{tuple_delimiter}ENTITY_TYPE{tuple_delimiter}DESCRIPTION)
{record_delimiter}
("relationship"{tuple_delimiter}SOURCE{tuple_delimiter}TARGET{tuple_delimiter}DESCRIPTION{tuple_delimiter}STRENGTH)

-Real Data-
Text: {input_text}
Output:
```
