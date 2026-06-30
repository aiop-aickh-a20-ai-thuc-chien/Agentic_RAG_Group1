# 🔀 Phase 9 Pseudocode: Hybrid GraphRAG + RAG Fusion

## Overview
This phase designs and implements the **hybrid pipeline** that combines
GraphRAG (structured graph knowledge) with traditional RAG (vector similarity)
to get the best of both worlds.

---

## 9.1 Hybrid Query Router

```pseudo
CLASS HybridQueryRouter:
    """
    Classifies incoming queries to determine the best search strategy.
    Can route to a single method or trigger hybrid (parallel) search.
    """
    
    FUNCTION classify_query(query):
        """
        Classify query into categories:
            - "specific_entity"   → Local Search
            - "broad_thematic"    → Global Search
            - "multi_hop"         → DRIFT Search
            - "factual_lookup"    → Basic Search
            - "hybrid"            → Local + Basic in parallel
        
        Implementation Options:
            Option A: Rule-based heuristics
            Option B: LLM-based classification
            Option C: Embedding-based clustering
        """
        
        # ====== OPTION A: Rule-Based Heuristics ======
        query_lower = query.lower()
        
        # Check for entity-specific patterns
        IF contains_named_entity(query):
            IF contains_relationship_words(query):   # "how", "relate", "connect"
                RETURN "multi_hop"
            RETURN "specific_entity"
        
        # Check for broad/thematic patterns
        IF starts_with(query_lower, ["what are the main", "summarize", "overview", 
                                      "what themes", "describe the landscape"]):
            RETURN "broad_thematic"
        
        # Check for simple factual patterns
        IF starts_with(query_lower, ["what is", "when did", "where is", "how many"]):
            RETURN "factual_lookup"
        
        # Default: hybrid search for complex queries
        RETURN "hybrid"
        
        # ====== OPTION B: LLM-Based Classification ======
        classification = AWAIT llm.completion(
            messages = [{
                "role": "system",
                "content": """Classify this query into one of:
                    - specific_entity: About a specific entity or person
                    - broad_thematic: Asking about themes, trends, or overviews
                    - multi_hop: Requires following chains of relationships
                    - factual_lookup: Simple fact retrieval
                    - hybrid: Complex question benefiting from multiple sources
                """
            }, {
                "role": "user",
                "content": query
            }]
        )
        RETURN classification
    
    
    FUNCTION route_query(query):
        """
        Route query to appropriate search engine(s).
        """
        
        query_type = self.classify_query(query)
        
        MATCH query_type:
            CASE "specific_entity":
                RETURN {"engines": ["local"], "fusion": False}
            CASE "broad_thematic":
                RETURN {"engines": ["global"], "fusion": False}
            CASE "multi_hop":
                RETURN {"engines": ["drift"], "fusion": False}
            CASE "factual_lookup":
                RETURN {"engines": ["basic"], "fusion": False}
            CASE "hybrid":
                RETURN {"engines": ["local", "basic"], "fusion": True}
```

---

## 9.2 Hybrid Search Engine

```pseudo
CLASS HybridSearch:
    """
    Combines GraphRAG and traditional RAG results.
    
    Strategy:
        1. Run Local Search (graph-enhanced) and Basic Search (vector) in parallel
        2. Merge and deduplicate contexts
        3. Use a final LLM call to synthesize a coherent answer
    """
    
    FUNCTION __init__(config):
        self.local_search  = get_local_search_engine(config, ...)
        self.basic_search  = get_basic_search_engine(config, ...)
        self.router        = HybridQueryRouter()
        self.fusion_model  = create_completion(config.hybrid_search.completion_model)
    
    
    ASYNC FUNCTION search(query, conversation_history = None):
        """
        Main hybrid search pipeline.
        """
        
        # Step 1: Route query
        routing = self.router.route_query(query)
        
        IF NOT routing["fusion"]:
            # Single engine — no fusion needed
            engine = self._get_engine(routing["engines"][0])
            RETURN AWAIT engine.search(query, conversation_history)
        
        # Step 2: Parallel execution
        results = AWAIT PARALLEL {
            "graph":  self.local_search.search(query, conversation_history),
            "vector": self.basic_search.search(query, conversation_history)
        }
        
        graph_result  = results["graph"]
        vector_result = results["vector"]
        
        # Step 3: Context deduplication
        merged_context = self._merge_contexts(
            graph_context  = graph_result.context_data,
            vector_context = vector_result.context_data
        )
        
        # Step 4: Confidence scoring
        graph_confidence  = self._score_confidence(graph_result)
        vector_confidence = self._score_confidence(vector_result)
        
        # Step 5: Answer synthesis
        final_answer = AWAIT self._synthesize_answer(
            query = query,
            graph_answer     = graph_result.response,
            vector_answer    = vector_result.response,
            merged_context   = merged_context,
            graph_confidence  = graph_confidence,
            vector_confidence = vector_confidence
        )
        
        RETURN HybridSearchResult(
            response          = final_answer,
            graph_result      = graph_result,
            vector_result     = vector_result,
            merged_context    = merged_context,
            graph_confidence  = graph_confidence,
            vector_confidence = vector_confidence
        )
    
    
    FUNCTION _merge_contexts(graph_context, vector_context):
        """
        Merge contexts from graph and vector search, removing duplicates.
        """
        
        merged = {
            "entities":      graph_context.get("entities", DataFrame()),
            "relationships": graph_context.get("relationships", DataFrame()),
            "communities":   graph_context.get("communities", DataFrame()),
            "text_units":    DataFrame()   # merged below
        }
        
        # Text unit deduplication
        graph_text_units = graph_context.get("text_units", DataFrame())
        vector_text_units = vector_context   # BasicSearch returns text units
        
        IF BOTH ARE NOT EMPTY:
            # Concatenate and remove duplicates by text unit ID
            all_text_units = CONCAT(graph_text_units, vector_text_units)
            merged["text_units"] = all_text_units.drop_duplicates(subset = "id")
        ELIF graph_text_units IS NOT EMPTY:
            merged["text_units"] = graph_text_units
        ELSE:
            merged["text_units"] = vector_text_units
        
        RETURN merged
    
    
    FUNCTION _score_confidence(search_result):
        """
        Score the confidence of a search result.
        
        Heuristics:
            - More context records = potentially more reliable
            - Response length relative to context = less hallucination risk
            - Presence of graph structure (entities/relationships) = higher confidence
        """
        
        context_size = LENGTH(search_result.context_data)
        response_length = LENGTH(search_result.response)
        has_graph_data = "entities" IN search_result.context_data
        
        # Simple scoring (can be replaced with a trained model)
        score = 0.0
        
        IF context_size > 0:
            score += 0.3   # has relevant context
        IF context_size > 5:
            score += 0.2   # rich context
        IF response_length > 100:
            score += 0.2   # non-trivial response
        IF has_graph_data:
            score += 0.3   # graph-enhanced (usually more reliable)
        
        RETURN MIN(score, 1.0)
    
    
    ASYNC FUNCTION _synthesize_answer(query, graph_answer, vector_answer,
                                       merged_context, graph_confidence, vector_confidence):
        """
        Use LLM to synthesize a final answer from both search results.
        """
        
        synthesis_prompt = f"""
You are a research assistant synthesizing information from two search approaches.

## Graph-Enhanced Search Result (Confidence: {graph_confidence:.0%})
{graph_answer}

## Vector Similarity Search Result (Confidence: {vector_confidence:.0%})
{vector_answer}

## Additional Context
{format_merged_context(merged_context)}

## Instructions
- Combine insights from both sources into a comprehensive answer
- Prefer graph-based information for relationship and structural questions  
- Prefer vector-based information for specific factual details
- Note any contradictions between sources
- Cite source types when possible (e.g., "[from graph analysis]" or "[from source documents]")
"""
        
        final_answer = AWAIT self.fusion_model.completion(
            messages = [
                {"role": "system", "content": synthesis_prompt},
                {"role": "user",   "content": query}
            ],
            stream = True
        )
        
        RETURN final_answer
```

---

## 9.3 Reciprocal Rank Fusion (Alternative Merging Strategy)

```pseudo
FUNCTION reciprocal_rank_fusion(graph_results, vector_results, k = 60):
    """
    Alternative to LLM synthesis: merge ranked result lists using RRF.
    
    RRF Score(doc) = Σ  1 / (k + rank(doc, list_i))
    
    This gives a unified ranking across both retrieval methods.
    """
    
    # Build unified score map
    scores = defaultdict(float)
    
    # Score graph results
    FOR rank, result IN ENUMERATE(graph_results):
        scores[result.id] += 1.0 / (k + rank + 1)
    
    # Score vector results  
    FOR rank, result IN ENUMERATE(vector_results):
        scores[result.id] += 1.0 / (k + rank + 1)
    
    # Sort by combined score
    merged = SORT(scores.items(), key = lambda x: x[1], descending = True)
    
    RETURN merged
```

---

## 9.4 Hybrid Pipeline Visualization

```
                    User Query: "What is Microsoft's role in AI safety?"
                              │
                              ▼
                    ┌─────────────────┐
                    │  Query Router   │
                    │  → "hybrid"     │
                    └────────┬────────┘
                             │
                ┌────────────┴────────────┐
                ▼                         ▼
    ┌─────────────────────┐    ┌─────────────────────┐
    │   LOCAL SEARCH      │    │   BASIC SEARCH      │
    │                     │    │                     │
    │ 1. Find "MICROSOFT" │    │ 1. Embed query      │
    │    entity by embed  │    │ 2. Top-K text units │
    │ 2. Get relations:   │    │    by cosine sim    │
    │    MICROSOFT→AI     │    │ 3. Return chunks    │
    │    MICROSOFT→SAFETY │    │    about MS + AI    │
    │ 3. Community reports│    │                     │
    │ 4. Source text units │    │                     │
    │ 5. LLM Answer       │    │ 4. LLM Answer       │
    └──────────┬──────────┘    └──────────┬──────────┘
               │                          │
               └────────────┬─────────────┘
                            ▼
                ┌─────────────────────┐
                │  CONTEXT MERGE      │
                │  + DEDUPLICATION    │
                │  + CONFIDENCE SCORE │
                └──────────┬──────────┘
                           ▼
                ┌─────────────────────┐
                │  ANSWER SYNTHESIS   │
                │  (Final LLM Call)   │
                │                     │
                │  Combines graph     │
                │  structure insights │
                │  with source doc    │
                │  details            │
                └──────────┬──────────┘
                           ▼
                   Final Answer
```

---

## Key Design Decisions for Hybrid Pipeline

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Default fusion strategy | LLM synthesis | Most flexible, handles contradictions |
| Parallel vs sequential | Parallel | Minimizes latency |
| Deduplication | By text unit ID | Prevents redundant LLM context |
| Confidence scoring | Heuristic-based | Simple, fast; can upgrade to learned |
| Query routing | Rule-based + fallback hybrid | Low overhead, good coverage |
| Fusion LLM | Same as search LLM | Consistency, simpler config |
