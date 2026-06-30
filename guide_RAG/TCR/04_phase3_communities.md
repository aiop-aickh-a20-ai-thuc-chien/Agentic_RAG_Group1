# 🏘️ Phase 3 Pseudocode: Community Detection & Report Generation

## Overview
This phase applies hierarchical community detection (Leiden algorithm) on the 
entity graph, then uses LLM to generate summary reports for each community.
Communities group related entities — enabling the "global" view in GraphRAG.

---

## 3.1 Community Detection (create_communities)

```pseudo
FUNCTION create_communities(config, context):
    """
    Apply hierarchical Leiden clustering to the entity-relationship graph.
    Produces a tree of communities at multiple resolution levels.
    
    Source: packages/graphrag/graphrag/index/workflows/create_communities.py
    """
    
    # Step 1: Load graph data
    entities = READ_TABLE("entities")
    relationships = READ_TABLE("relationships")
    
    # Step 2: Build adjacency from relationships
    # The Leiden algorithm operates on the edge list directly
    max_cluster_size = config.cluster_graph.max_cluster_size   # default: 10
    use_lcc          = config.cluster_graph.use_lcc            # default: True
    seed             = config.cluster_graph.seed               # for reproducibility
    
    # Step 3: Run hierarchical Leiden clustering
    clusters = cluster_graph(
        relationships     = relationships,
        max_cluster_size  = max_cluster_size,
        use_lcc           = use_lcc,
        seed              = seed
    )
    # Returns: list of [level, community_id, parent_community_id, [entity_titles]]
    
    # Step 4: Build community records
    communities = []
    FOR EACH (level, community_id, parent_id, entity_titles) IN clusters:
        
        # Map entity titles → entity IDs
        entity_ids = [entities.get_id(title) FOR title IN entity_titles]
        
        # Find intra-community relationships
        relationship_ids = FIND relationships WHERE
            source IN entity_titles AND target IN entity_titles
        
        # Collect text unit IDs from those relationships
        text_unit_ids = UNIQUE(
            FLATTEN([rel.text_unit_ids FOR rel IN selected_relationships])
        )
        
        community = {
            "id":               generate_uuid(),
            "human_readable_id": community_id,
            "title":            f"Community {community_id}",
            "level":            level,
            "parent":           parent_id,
            "children":         [],           # filled below
            "entity_ids":       entity_ids,
            "relationship_ids": relationship_ids,
            "text_unit_ids":    text_unit_ids,
            "size":             LENGTH(entity_ids),
            "period":           TODAY().isoformat()
        }
        communities.APPEND(community)
    
    # Step 5: Build parent-child tree
    FOR EACH community IN communities:
        children = FIND communities WHERE parent == community.community_id
        community.children = [child.community_id FOR child IN children]
    
    STORE communities TO "communities" table
    RETURN communities


FUNCTION cluster_graph(relationships, max_cluster_size, use_lcc, seed):
    """
    Hierarchical Leiden community detection.
    
    Source: packages/graphrag/graphrag/index/operations/cluster_graph.py
    """
    
    # Step 1: Build NetworkX graph from relationships
    graph = nx.Graph()
    FOR EACH rel IN relationships:
        graph.add_edge(rel.source, rel.target, weight = rel.weight)
    
    # Step 2: Optionally restrict to Largest Connected Component
    IF use_lcc:
        largest_cc = MAX(nx.connected_components(graph), key = LENGTH)
        graph = graph.subgraph(largest_cc)
    
    # Step 3: Run Leiden algorithm at multiple resolutions
    # graspologic / igraph library handles the multi-level decomposition
    results = []
    level = 0
    current_graph = graph
    
    WHILE any community has size > max_cluster_size:
        # Apply Leiden at current level
        partition = leiden(
            current_graph,
            resolution = adaptive_resolution(level),
            seed = seed
        )
        
        FOR EACH (community_id, members) IN partition.items():
            parent_id = find_parent_community(members, level - 1)
            results.APPEND([level, community_id, parent_id, members])
        
        # Next level: re-cluster oversized communities
        level += 1
        current_graph = get_oversized_subgraphs(partition, max_cluster_size)
    
    RETURN results
```

---

## 3.2 Community Hierarchy Visualization

```
Level 0 (coarsest):    [Community 0: ALL entities]
                              |
Level 1:           [Comm 1]  [Comm 2]  [Comm 3]
                    /   \       |        / \
Level 2:       [1a] [1b]    [2a]    [3a] [3b]
               /|\   /\       |      /\    |
Level 3:     ...  ...  ...  ...   ...  ... ...
(finest)
```

Each community at level N is a subset of its parent at level N-1.
This hierarchy enables multi-granularity search.

---

## 3.3 Community Report Generation (create_community_reports)

```pseudo
FUNCTION create_community_reports(config, context):
    """
    Generate LLM-powered summary reports for each community.
    Reports describe what the community is about, key entities, 
    and key relationships.
    
    Source: packages/graphrag/graphrag/index/workflows/create_community_reports.py
    """
    
    # Step 1: Load all data
    entities      = READ_TABLE("entities")
    relationships = READ_TABLE("relationships")
    communities   = READ_TABLE("communities")
    claims        = READ_TABLE("covariates") IF enabled ELSE None
    
    # Step 2: Initialize LLM for report generation
    model = create_completion(
        config = config.community_reports.completion_model_config,
        cache  = context.cache.child("community_reports")
    )
    tokenizer = model.tokenizer
    
    # Step 3: Explode communities to get entity-level data
    # For each community, list all entities with their details
    nodes = explode_communities(communities, entities)
    #   Join: community × entity_ids → full entity records per community
    
    # Step 4: Prepare node and edge details for context building
    nodes = prep_nodes(nodes)
    #   Add NODE_DETAILS: {short_id, title, description, degree}
    edges = prep_edges(relationships)
    #   Add EDGE_DETAILS: {short_id, source, target, description, degree}
    claims_prepped = prep_claims(claims) IF claims ELSE None
    
    # Step 5: Build local context for each community
    local_contexts = build_local_context(
        nodes       = nodes,
        edges       = edges,
        claims      = claims_prepped,
        tokenizer   = tokenizer,
        max_input_length = config.community_reports.max_input_length   # 8000 tokens
    )
    # Returns: dict mapping community_id → context string
    # Context includes tables of entities, relationships, claims within the community
    
    # Step 6: Generate reports per community (bottom-up, level by level)
    reports = AWAIT summarize_communities(
        nodes          = nodes,
        communities    = communities,
        local_contexts = local_contexts,
        model          = model,
        prompt         = COMMUNITY_REPORT_PROMPT,
        max_report_length = config.community_reports.max_length   # 2000 tokens
    )
    
    STORE reports TO "community_reports" table
    RETURN reports


FUNCTION build_local_context(nodes, edges, claims, tokenizer, max_input_length):
    """
    Build context string for a community containing its entities, 
    relationships, and claims, formatted as markdown tables.
    
    Source: packages/graphrag/graphrag/index/operations/summarize_communities/
            graph_context/context_builder.py
    """
    
    contexts = {}
    
    FOR EACH community_id IN UNIQUE(nodes.community_id):
        # Get community members
        community_nodes = nodes WHERE community_id == community_id
        community_edges = edges WHERE (source IN community_nodes.title 
                                       AND target IN community_nodes.title)
        community_claims = claims WHERE subject_id IN community_nodes.title
        
        # Build context string with token budget management
        context_parts = []
        remaining_tokens = max_input_length
        
        # Part 1: Entities table
        entity_table = FORMAT_TABLE(
            headers = ["id", "entity", "description", "# relationships"],
            rows    = community_nodes
        )
        entity_tokens = tokenizer.count(entity_table)
        IF entity_tokens < remaining_tokens:
            context_parts.APPEND(entity_table)
            remaining_tokens -= entity_tokens
        
        # Part 2: Relationships table
        rel_table = FORMAT_TABLE(
            headers = ["id", "source", "target", "description"],
            rows    = community_edges
        )
        rel_tokens = tokenizer.count(rel_table)
        IF rel_tokens < remaining_tokens:
            context_parts.APPEND(rel_table)
            remaining_tokens -= rel_tokens
        
        # Part 3: Claims table (if available)
        IF community_claims IS NOT EMPTY:
            claims_table = FORMAT_TABLE(
                headers = ["id", "entity", "type", "status", "description"],
                rows    = community_claims
            )
            IF tokenizer.count(claims_table) < remaining_tokens:
                context_parts.APPEND(claims_table)
        
        contexts[community_id] = "\n\n".join(context_parts)
    
    RETURN contexts


FUNCTION summarize_communities(nodes, communities, local_contexts, model, prompt, 
                                tokenizer, max_report_length, num_threads):
    """
    Generate community reports level by level (bottom-up).
    Lower-level reports can be included as context for higher-level reports.
    
    Source: packages/graphrag/graphrag/index/operations/summarize_communities/
            summarize_communities.py
    """
    
    reports = []
    levels = SORTED(UNIQUE(communities.level), reverse = True)   # bottom-up
    
    FOR EACH level IN levels:
        level_communities = communities WHERE level == level
        
        # Process communities in parallel
        PARALLEL FOR EACH community IN level_communities (max_concurrent = num_threads):
            
            # Build the context: local data + child community reports
            context = local_contexts[community.id]
            
            # Include sub-community reports if this is a higher-level community
            IF community.children IS NOT EMPTY:
                child_reports = [reports[child_id] FOR child_id IN community.children]
                child_context = FORMAT_CHILD_REPORTS(child_reports)
                context = context + "\n\n" + child_context
            
            # Truncate if exceeds token limit
            IF tokenizer.count(context) > max_input_length:
                context = TRUNCATE(context, max_input_length)
            
            # Generate report via LLM
            report_text = AWAIT model.completion(
                messages = [
                    {"role": "system", "content": prompt.format(
                        input_text = context
                    )}
                ]
            )
            
            # Parse structured report (title, summary, full_content, rating, findings)
            parsed_report = parse_community_report(report_text)
            
            report = CommunityReport(
                id               = generate_uuid(),
                community_id     = community.id,
                title            = parsed_report.title,
                summary          = parsed_report.summary,
                full_content     = parsed_report.full_content,
                rank             = parsed_report.rating,
                size             = community.size,
                period           = community.period
            )
            reports.APPEND(report)
    
    RETURN reports
```

---

## Community Report Prompt Template (Simplified)

```
You are an AI assistant that helps a human analyst to perform 
information discovery on a knowledge graph.

# Report Structure
The report should include the following sections:
- TITLE: Community name reflecting its key entities
- SUMMARY: Executive summary of the community's overall structure
- REPORT RATING: 1-10 importance score
- RATING EXPLANATION: Why this score
- DETAILED FINDINGS: Comprehensive list of insights with citations

# Input Data Tables
{input_text}

Generate a comprehensive report about this community:
```

---

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_cluster_size` | 10 | Max entities per cluster before further splitting |
| `use_lcc` | True | Restrict to largest connected component |
| `seed` | None | Random seed for reproducible clustering |
| `max_input_length` | 8000 | Max tokens for community context |
| `max_report_length` | 2000 | Max tokens for generated report |
