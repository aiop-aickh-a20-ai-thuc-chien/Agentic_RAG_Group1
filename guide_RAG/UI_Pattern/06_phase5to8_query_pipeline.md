# 🔎 Phase 5-8 Pseudocode: Query Pipeline (All Search Methods)

## Overview
This document covers all four search methods:
- **Phase 5**: Basic Search (pure vector RAG)
- **Phase 6**: Local Search (entity-centric GraphRAG)
- **Phase 7**: Global Search (community-level Map-Reduce)
- **Phase 8**: DRIFT Search (iterative multi-hop)

---

## Phase 5: Basic Search (Traditional RAG)

```pseudo
CLASS BasicSearch:
    """
    Simplest search mode: embed query, find similar text units, generate answer.
    This is pure vector-similarity RAG with no graph involvement.
    
    Source: packages/graphrag/graphrag/query/structured_search/basic_search/search.py
    """
    
    FUNCTION __init__(model, context_builder, tokenizer, model_params):
        self.model = model                      # LLM for answer generation
        self.context_builder = context_builder   # BasicSearchContext
        self.tokenizer = tokenizer
    
    ASYNC FUNCTION search(query, conversation_history = None):
        """
        Steps:
            1. Embed the query
            2. Find top-K similar text units
            3. Build context string
            4. Generate answer with LLM
        """
        
        # Step 1-3: Context building
        context_result = self.context_builder.build_context(
            query = query,
            conversation_history = conversation_history,
            k = config.basic_search.k,                          # top-K, default: 20
            max_context_tokens = config.basic_search.max_context_tokens  # default: 12000
        )
        # context_result.context_chunks = formatted text of top-K text units
        # context_result.context_records = dataframe of matched text units
        
        # Step 4: Generate answer
        search_prompt = BASIC_SEARCH_SYSTEM_PROMPT.format(
            context_data  = context_result.context_chunks,
            response_type = self.response_type
        )
        
        response = AWAIT self.model.completion(
            messages = [
                {"role": "system", "content": search_prompt},
                {"role": "user",   "content": query}
            ],
            stream = True
        )
        
        RETURN SearchResult(
            response     = response,
            context_data = context_result.context_records
        )


CLASS BasicSearchContext:
    """
    Context builder for basic search — pure vector similarity.
    
    Source: packages/graphrag/graphrag/query/structured_search/basic_search/basic_context.py
    """
    
    FUNCTION build_context(query, k, max_context_tokens):
        # Step 1: Embed the query
        query_embedding = self.text_embedder.embed(query)
        
        # Step 2: Search vector store for similar text units
        results = self.text_unit_embeddings.search(
            query_embedding = query_embedding,
            top_k = k
        )
        # Returns: list of (text_unit_id, similarity_score)
        
        # Step 3: Retrieve full text unit data
        matched_text_units = [
            self.text_units[result.id] FOR result IN results
        ]
        
        # Step 4: Build context string within token budget
        context_text = ""
        remaining_tokens = max_context_tokens
        
        FOR EACH unit IN matched_text_units:
            unit_text = f"--- Text Unit {unit.short_id} ---\n{unit.text}\n\n"
            unit_tokens = self.tokenizer.count(unit_text)
            
            IF unit_tokens > remaining_tokens:
                BREAK
            
            context_text += unit_text
            remaining_tokens -= unit_tokens
        
        RETURN ContextResult(
            context_chunks  = context_text,
            context_records = DataFrame(matched_text_units)
        )
```

---

## Phase 6: Local Search (Entity-Centric GraphRAG)

```pseudo
CLASS LocalSearch:
    """
    Graph-enhanced local search: find relevant entities via embedding similarity,
    then build rich context from the knowledge graph neighborhood.
    
    Source: packages/graphrag/graphrag/query/structured_search/local_search/search.py
    """
    
    ASYNC FUNCTION search(query, conversation_history = None):
        """
        Steps:
            1. Extract entities from query via embedding similarity
            2. Build mixed context from graph neighborhood
            3. Generate answer with rich context
        """
        
        # Step 1-2: Build mixed context
        context_result = self.context_builder.build_context(
            query = query,
            conversation_history = conversation_history,
            text_unit_prop     = 0.5,    # 50% of token budget for text units
            community_prop     = 0.1,    # 10% for community reports
            # remaining 40% for entities + relationships
            top_k_mapped_entities = 10,
            top_k_relationships   = 10,
            max_context_tokens    = 12000
        )
        
        # Step 3: Generate answer
        search_prompt = LOCAL_SEARCH_SYSTEM_PROMPT.format(
            context_data  = context_result.context_chunks,
            response_type = self.response_type
        )
        
        response = AWAIT self.model.completion(
            messages = [
                {"role": "system", "content": search_prompt},
                {"role": "user",   "content": query}
            ],
            stream = True
        )
        
        RETURN SearchResult(
            response = response,
            context_data = context_result.context_records
        )


CLASS LocalSearchMixedContext:
    """
    Builds context from multiple graph data sources.
    
    Source: packages/graphrag/graphrag/query/structured_search/local_search/mixed_context.py
           + packages/graphrag/graphrag/query/context_builder/local_context.py
    """
    
    FUNCTION build_context(query, conversation_history, text_unit_prop, community_prop,
                           top_k_mapped_entities, top_k_relationships, max_context_tokens):
        """
        TOKEN BUDGET ALLOCATION:
            Total Budget = max_context_tokens (e.g., 12000)
            
            ├── Community Reports:    community_prop × budget  (e.g., 1200 tokens)
            ├── Text Units:           text_unit_prop × budget  (e.g., 6000 tokens)
            └── Entities + Relations: remaining budget          (e.g., 4800 tokens)
        """
        
        # ========================================
        # Step 1: ENTITY MATCHING (via embeddings)
        # ========================================
        query_embedding = self.text_embedder.embed(query)
        
        # Search entity description embeddings
        entity_matches = self.entity_text_embeddings.search(
            query_embedding = query_embedding,
            top_k = top_k_mapped_entities         # default: 10
        )
        
        selected_entities = [self.entities[match.id] FOR match IN entity_matches]
        # selected_entities: list of Entity objects with full graph data
        
        # ========================================
        # Step 2: RELATIONSHIP CONTEXT
        # ========================================
        # Priority 1: In-network relationships (between selected entities)
        in_network_rels = get_in_network_relationships(
            selected_entities = selected_entities,
            relationships     = self.relationships
        )
        # Sorted by rank (combined degree)
        
        # Priority 2: Out-of-network relationships (between selected and other entities)
        out_network_rels = get_out_network_relationships(
            selected_entities = selected_entities,
            relationships     = self.relationships
        )
        # Sorted by: (# mutual links with selected entities, then by rank)
        
        # Combine: in-network first, then out-network up to budget
        selected_relationships = in_network_rels + out_network_rels[:top_k_relationships * len(selected_entities)]
        
        # ========================================
        # Step 3: BUILD CONTEXT SECTIONS
        # ========================================
        
        context_parts = {}
        remaining_tokens = max_context_tokens
        
        # --- Section A: Entity Context ---
        entity_context, entity_df = build_entity_context(
            selected_entities = selected_entities,
            max_context_tokens = remaining_tokens * 0.4,   # 40% for entities
            include_entity_rank = True
        )
        # Format: "|id|entity|description|# relationships|\n|1|MICROSOFT|Tech company...|25|"
        
        # --- Section B: Relationship Context ---
        rel_context, rel_df = build_relationship_context(
            selected_entities  = selected_entities,
            relationships      = selected_relationships,
            max_context_tokens = remaining_tokens * 0.4
        )
        # Format: "|id|source|target|description|\n|1|MICROSOFT|AZURE|Microsoft owns...|"
        
        # --- Section C: Community Report Context ---
        community_budget = INT(max_context_tokens * community_prop)
        community_context = build_community_context(
            selected_entities  = selected_entities,
            community_reports  = self.community_reports,
            max_context_tokens = community_budget
        )
        # Uses entities' community_ids to find relevant reports
        
        # --- Section D: Text Unit Context ---
        text_unit_budget = INT(max_context_tokens * text_unit_prop)
        text_unit_context = build_text_unit_context(
            selected_entities  = selected_entities,
            text_units         = self.text_units,
            max_context_tokens = text_unit_budget
        )
        # Retrieves original source text for matched entities
        
        # --- Section E: Covariate Context (optional) ---
        IF self.covariates:
            cov_context = build_covariates_context(
                selected_entities = selected_entities,
                covariates        = self.covariates
            )
        
        # ========================================
        # Step 4: COMBINE ALL CONTEXT
        # ========================================
        full_context = "\n\n".join([
            entity_context,
            rel_context,
            community_context,
            text_unit_context,
            cov_context   # if available
        ])
        
        RETURN ContextResult(
            context_chunks  = full_context,
            context_records = {
                "entities":      entity_df,
                "relationships": rel_df,
                "communities":   community_df,
                "text_units":    text_unit_df
            }
        )
```

---

## Phase 7: Global Search (Map-Reduce over Communities)

```pseudo
CLASS GlobalSearch:
    """
    Community-level search using Map-Reduce pattern.
    Best for broad, thematic questions like "What are the main themes?"
    
    Source: packages/graphrag/graphrag/query/structured_search/global_search/search.py
    """
    
    ASYNC FUNCTION search(query, conversation_history = None):
        """
        Two-phase process:
            MAP:    Process each community report batch → extract key points
            REDUCE: Combine all key points → generate final answer
        """
        
        # ========================================
        # BUILD CONTEXT: Split community reports into batches
        # ========================================
        context_result = AWAIT self.context_builder.build_context(
            query = query,
            conversation_history = conversation_history,
            max_context_tokens = self.max_data_tokens     # e.g., 12000
        )
        # context_result.context_chunks = list of community report batches
        # Each batch fits within max_data_tokens
        
        # ========================================
        # PHASE 1: MAP — Parallel processing of batches
        # ========================================
        map_responses = AWAIT PARALLEL [
            self._map_response_single_batch(
                context_data = batch,
                query        = query,
                max_length   = self.map_max_length    # 1000 tokens
            )
            FOR batch IN context_result.context_chunks
        ]
        
        # ========================================
        # PHASE 2: REDUCE — Combine map results
        # ========================================
        final_response = AWAIT self._reduce_response(
            map_responses = map_responses,
            query         = query
        )
        
        RETURN GlobalSearchResult(
            response         = final_response,
            map_responses    = map_responses,
            context_data     = context_result.context_records
        )
    
    
    ASYNC FUNCTION _map_response_single_batch(context_data, query, max_length):
        """
        Process a single batch of community reports.
        Extract key points relevant to the query.
        
        Output format (JSON):
        {
            "points": [
                {"description": "Key insight about...", "score": 85},
                {"description": "Another finding...", "score": 72}
            ]
        }
        """
        
        search_prompt = MAP_SYSTEM_PROMPT.format(
            context_data = context_data,
            max_length   = max_length
        )
        
        response = AWAIT self.model.completion(
            messages = [
                {"role": "system", "content": search_prompt},
                {"role": "user",   "content": query}
            ],
            response_format_json_object = True   # Force JSON output
        )
        
        # Parse JSON response → list of {answer, score}
        parsed = JSON_PARSE(response)
        points = parsed.get("points", [])
        
        RETURN SearchResult(
            response = [
                {"answer": p["description"], "score": INT(p["score"])}
                FOR p IN points
                IF "description" IN p AND "score" IN p
            ]
        )
    
    
    ASYNC FUNCTION _reduce_response(map_responses, query):
        """
        Combine all key points from map phase into a final answer.
        """
        
        # Step 1: Collect all key points
        all_key_points = []
        FOR EACH (index, response) IN ENUMERATE(map_responses):
            FOR EACH point IN response.response:
                all_key_points.APPEND({
                    "analyst":  index,
                    "answer":   point["answer"],
                    "score":    point["score"]
                })
        
        # Step 2: Filter and sort
        filtered_points = [p FOR p IN all_key_points IF p["score"] > 0]
        filtered_points = SORT(filtered_points, key = "score", descending = True)
        
        IF LENGTH(filtered_points) == 0:
            RETURN "I am sorry but I am unable to answer this question 
                    given the provided data."
        
        # Step 3: Build reduce context within token budget
        reduce_context = ""
        total_tokens = 0
        
        FOR EACH point IN filtered_points:
            point_text = f"""
                ----Analyst {point['analyst'] + 1}----
                Importance Score: {point['score']}
                {point['answer']}
            """
            point_tokens = self.tokenizer.count(point_text)
            
            IF total_tokens + point_tokens > self.max_data_tokens:
                BREAK
            
            reduce_context += point_text + "\n\n"
            total_tokens += point_tokens
        
        # Step 4: Generate final answer
        reduce_prompt = REDUCE_SYSTEM_PROMPT.format(
            report_data   = reduce_context,
            response_type = self.response_type,
            max_length    = self.reduce_max_length    # 2000 tokens
        )
        
        final_response = AWAIT self.model.completion(
            messages = [
                {"role": "system", "content": reduce_prompt},
                {"role": "user",   "content": query}
            ],
            stream = True
        )
        
        RETURN final_response


CLASS GlobalCommunityContext:
    """
    Context builder for global search.
    Optionally supports dynamic community selection.
    
    Source: packages/graphrag/graphrag/query/structured_search/global_search/community_context.py
    """
    
    ASYNC FUNCTION build_context(query, max_context_tokens):
        """
        Option A: Static — Use all community reports, shuffled and batched
        Option B: Dynamic — LLM rates which communities are relevant first
        """
        
        IF self.dynamic_community_selection:
            # Dynamic: Rate each community's relevance to the query
            relevant_communities = AWAIT rate_community_relevance(
                query = query,
                communities = self.communities,
                model = self.model
            )
            reports = [r FOR r IN self.reports IF r.community_id IN relevant_communities]
        ELSE:
            reports = self.community_reports
        
        # Sort by rank (importance), then batch by token budget
        reports = SORT(reports, key = "rank", descending = True)
        
        batches = []
        current_batch = ""
        current_tokens = 0
        
        FOR EACH report IN reports:
            report_text = format_report(report)   # title + summary/full_content
            report_tokens = self.tokenizer.count(report_text)
            
            IF current_tokens + report_tokens > max_context_tokens:
                batches.APPEND(current_batch)
                current_batch = ""
                current_tokens = 0
            
            current_batch += report_text + "\n\n"
            current_tokens += report_tokens
        
        IF current_batch:
            batches.APPEND(current_batch)
        
        RETURN ContextResult(
            context_chunks  = batches,     # list of batch strings
            context_records = reports_df
        )
```

---

## Phase 8: DRIFT Search (Dynamic Reasoning with Iterative Follow-ups)

```pseudo
CLASS DRIFTSearch:
    """
    DRIFT = Dynamic Reasoning with Iterative Follow-up Thinking
    
    Multi-hop search that:
    1. Primers with community reports for initial answer
    2. Generates follow-up queries
    3. Iteratively explores the graph via Local Search
    4. Reduces all intermediate answers to a final response
    
    Source: packages/graphrag/graphrag/query/structured_search/drift_search/search.py
    """
    
    FUNCTION __init__(model, context_builder, tokenizer):
        self.model = model
        self.context_builder = context_builder   # DRIFTSearchContextBuilder
        self.query_state = QueryState()          # DAG of actions/answers
        self.primer = DRIFTPrimer(model, context_builder.config)
        self.local_search = self._init_local_search()
    
    
    ASYNC FUNCTION search(query, reduce = True):
        """
        Main DRIFT search loop.
        """
        
        # ========================================
        # PHASE 1: PRIMER — Initial community-level answer
        # ========================================
        IF self.query_state IS EMPTY:
            
            # Build primer context: top-K relevant community reports
            primer_context, token_usage = AWAIT self.context_builder.build_context(query)
            # primer_context: list of top-K community reports by embedding similarity
            
            # Ask LLM to generate initial answer + follow-up queries
            primer_response = AWAIT self.primer.search(
                query = query,
                top_k_reports = primer_context
            )
            # primer_response.response = [
            #     {
            #         "intermediate_answer": "Based on the community data, ...",
            #         "follow_up_queries": ["What is X's relationship to Y?", ...],
            #         "score": 85
            #     }
            # ]
            
            # Package into DriftAction
            init_action = DriftAction.from_primer_response(query, primer_response)
            self.query_state.add_action(init_action)
            self.query_state.add_all_follow_ups(init_action, init_action.follow_ups)
        
        # ========================================
        # PHASE 2: ITERATIVE FOLLOW-UP LOOP
        # ========================================
        epochs = 0
        WHILE epochs < config.n_depth:    # default: 3 iterations
            
            # Get highest-priority incomplete actions
            actions = self.query_state.rank_incomplete_actions()
            IF LENGTH(actions) == 0:
                BREAK   # no more follow-ups to explore
            
            # Take top-K follow-ups
            actions = actions[:config.drift_k_followups]    # default: 3
            
            # Execute each follow-up via Local Search
            results = AWAIT PARALLEL [
                action.search(
                    search_engine = self.local_search,
                    global_query  = query,
                    k_followups   = config.drift_k_followups
                )
                FOR action IN actions
            ]
            # Each result contains:
            #   - intermediate_answer
            #   - new follow_up_queries
            #   - context_data
            
            # Update query state
            FOR EACH action_result IN results:
                self.query_state.add_action(action_result)
                self.query_state.add_all_follow_ups(action_result, action_result.follow_ups)
            
            epochs += 1
        
        # ========================================
        # PHASE 3: REDUCE — Combine all intermediate answers
        # ========================================
        response_state, context_data, context_text = self.query_state.serialize()
        # response_state: collected intermediate answers as structured data
        
        IF reduce:
            final_answer = AWAIT self._reduce_response(
                responses = response_state,
                query     = query
            )
        ELSE:
            final_answer = response_state
        
        RETURN SearchResult(
            response     = final_answer,
            context_data = context_data,
            context_text = context_text
        )
    
    
    ASYNC FUNCTION _reduce_response(responses, query):
        """
        Combine all intermediate answers into a single coherent response.
        """
        
        # Collect all intermediate answers
        IF isinstance(responses, str):
            reduce_inputs = [responses]
        ELSE:
            reduce_inputs = [
                node["answer"] FOR node IN responses.get("nodes", [])
                IF node.get("answer")
            ]
        
        reduce_prompt = DRIFT_REDUCE_SYSTEM_PROMPT.format(
            context_data  = reduce_inputs,
            response_type = self.context_builder.response_type
        )
        
        final_response = AWAIT self.model.completion(
            messages = [
                {"role": "system", "content": reduce_prompt},
                {"role": "user",   "content": query}
            ]
        )
        
        RETURN final_response


CLASS QueryState:
    """
    Maintains a DAG (directed acyclic graph) of search actions.
    Each node = one intermediate answer + its follow-up queries.
    
    Source: packages/graphrag/graphrag/query/structured_search/drift_search/state.py
    """
    
    graph: dict[str, DriftAction]   # action_id → action
    
    FUNCTION add_action(action):
        self.graph[action.id] = action
    
    FUNCTION add_all_follow_ups(parent_action, follow_ups):
        FOR EACH follow_up_query IN follow_ups:
            child_action = DriftAction(
                query  = follow_up_query,
                parent = parent_action.id,
                status = "incomplete"
            )
            self.graph[child_action.id] = child_action
    
    FUNCTION rank_incomplete_actions():
        """Return incomplete actions sorted by score (highest first)."""
        incomplete = [a FOR a IN self.graph.values() IF a.status == "incomplete"]
        RETURN SORT(incomplete, key = lambda a: a.score, descending = True)
    
    FUNCTION serialize():
        """Convert the action DAG to structured output for reduce phase."""
        nodes = [
            {"query": a.query, "answer": a.answer, "score": a.score}
            FOR a IN self.graph.values()
            IF a.status == "complete"
        ]
        RETURN ({"nodes": nodes}, context_data, context_text)
```

---

## Search Method Decision Flow

```
                    User Query
                        │
                ┌───────┴───────┐
                │  Classify     │
                │  Query Type   │
                └───────┬───────┘
                        │
          ┌─────────────┼──────────────┬──────────────┐
          ▼             ▼              ▼              ▼
    "Who is X?"   "What themes   "How does A    "Find docs
     (specific)    exist?"        relate to B    about X"
                   (broad)        through C?"    (simple)
          │             │              │              │
          ▼             ▼              ▼              ▼
     LOCAL SEARCH  GLOBAL SEARCH  DRIFT SEARCH  BASIC SEARCH
```
