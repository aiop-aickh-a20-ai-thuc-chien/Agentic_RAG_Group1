# 🚀 Phase 11-13 Pseudocode: API, Evaluation & Production

## Phase 11: API Layer & Serving

### 11.1 FastAPI REST API

```pseudo
# ====== main.py ======

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel

app = FastAPI(title = "GraphRAG + RAG Hybrid API")


# -------- Data Models --------

CLASS IndexRequest(BaseModel):
    input_dir: str                                # path to documents
    method: str = "standard"                      # standard | fast | standard-update | fast-update
    config_overrides: dict = {}                    # override settings.yaml values

CLASS QueryRequest(BaseModel):
    query: str
    search_method: str = "hybrid"                 # local | global | drift | basic | hybrid
    conversation_id: str | None = None            # for multi-turn conversations
    response_type: str = "multiple paragraphs"
    stream: bool = False

CLASS QueryResponse(BaseModel):
    response: str
    search_method: str
    context_data: dict                            # entities, relationships, text units used
    confidence: float
    completion_time: float
    token_usage: dict                             # llm_calls, prompt_tokens, output_tokens


# -------- Endpoints --------

@app.post("/index")
ASYNC FUNCTION trigger_indexing(request: IndexRequest):
    """
    Trigger the indexing pipeline (async background task).
    Returns a job ID for status polling.
    """
    
    # Load config
    config = load_config(request.input_dir)
    config.apply_overrides(request.config_overrides)
    
    # Determine pipeline type
    method = IndexingMethod(request.method)
    pipeline = PipelineFactory.create_pipeline(config, method)
    
    # Launch as background task
    job_id = generate_uuid()
    background_tasks.add_task(
        run_indexing_job,
        job_id   = job_id,
        pipeline = pipeline,
        config   = config
    )
    
    RETURN {"job_id": job_id, "status": "started", "method": method}


@app.post("/query", response_model = QueryResponse)
ASYNC FUNCTION query(request: QueryRequest):
    """
    Query the indexed knowledge base.
    """
    
    # Load indexed data
    config = load_config()
    data = load_indexed_data(config)
    # data = { entities, relationships, communities, reports, text_units, vector_stores }
    
    # Get conversation history
    history = None
    IF request.conversation_id:
        history = conversation_store.get(request.conversation_id)
    
    # Execute search
    IF request.search_method == "hybrid":
        engine = HybridSearch(config, data)
    ELIF request.search_method == "local":
        engine = get_local_search_engine(config, data)
    ELIF request.search_method == "global":
        engine = get_global_search_engine(config, data)
    ELIF request.search_method == "drift":
        engine = get_drift_search_engine(config, data)
    ELIF request.search_method == "basic":
        engine = get_basic_search_engine(config, data)
    
    result = AWAIT engine.search(
        query = request.query,
        conversation_history = history
    )
    
    # Update conversation history
    IF request.conversation_id:
        conversation_store.append(request.conversation_id, request.query, result.response)
    
    RETURN QueryResponse(
        response        = result.response,
        search_method   = request.search_method,
        context_data    = result.context_data,
        confidence      = result.confidence IF hasattr ELSE 0.0,
        completion_time = result.completion_time,
        token_usage     = {
            "llm_calls":     result.llm_calls,
            "prompt_tokens": result.prompt_tokens,
            "output_tokens": result.output_tokens
        }
    )


@app.websocket("/ws/query")
ASYNC FUNCTION websocket_query(websocket: WebSocket):
    """
    WebSocket endpoint for streaming responses.
    """
    AWAIT websocket.accept()
    
    WHILE True:
        data = AWAIT websocket.receive_json()
        query = data["query"]
        method = data.get("search_method", "hybrid")
        
        engine = get_search_engine(method, config)
        
        ASYNC FOR chunk IN engine.stream_search(query):
            AWAIT websocket.send_json({
                "type": "chunk",
                "content": chunk
            })
        
        AWAIT websocket.send_json({"type": "done"})


@app.get("/status/{job_id}")
ASYNC FUNCTION get_job_status(job_id: str):
    """Check indexing job progress."""
    
    job = job_store.get(job_id)
    RETURN {
        "job_id":     job_id,
        "status":     job.status,       # running | completed | failed
        "progress":   job.progress,     # 0.0 - 1.0
        "current_workflow": job.current_workflow,
        "elapsed_time":     job.elapsed_time,
        "error":      job.error IF job.status == "failed" ELSE None
    }


@app.get("/graph")
ASYNC FUNCTION export_graph(format: str = "json"):
    """Export the knowledge graph."""
    
    entities = load_table("entities")
    relationships = load_table("relationships")
    communities = load_table("communities")
    
    IF format == "json":
        RETURN {
            "nodes": entities.to_dict("records"),
            "edges": relationships.to_dict("records"),
            "communities": communities.to_dict("records")
        }
    ELIF format == "graphml":
        graph = build_networkx_graph(entities, relationships)
        RETURN nx.generate_graphml(graph)
```

---

## Phase 12: Evaluation & Optimization

### 12.1 Evaluation Metrics

```pseudo
CLASS RAGEvaluator:
    """
    Evaluation framework for GraphRAG + RAG hybrid system.
    Measures: Faithfulness, Relevancy, Context Precision, Context Recall.
    """
    
    FUNCTION __init__(eval_model):
        self.model = eval_model   # LLM for evaluation (can be same or different)
    
    
    ASYNC FUNCTION evaluate(query, response, context, ground_truth = None):
        """
        Run all evaluation metrics on a single query-response pair.
        """
        
        scores = {}
        
        # Metric 1: Faithfulness — is the answer grounded in the context?
        scores["faithfulness"] = AWAIT self._evaluate_faithfulness(
            response = response,
            context  = context
        )
        
        # Metric 2: Relevancy — does the answer address the question?
        scores["relevancy"] = AWAIT self._evaluate_relevancy(
            query    = query,
            response = response
        )
        
        # Metric 3: Context Precision — is the retrieved context relevant?
        scores["context_precision"] = AWAIT self._evaluate_context_precision(
            query   = query,
            context = context
        )
        
        # Metric 4: Context Recall — is all relevant info retrieved?
        IF ground_truth:
            scores["context_recall"] = AWAIT self._evaluate_context_recall(
                context      = context,
                ground_truth = ground_truth
            )
        
        RETURN scores
    
    
    ASYNC FUNCTION _evaluate_faithfulness(response, context):
        """
        Check: Can every claim in the response be traced to the context?
        
        Steps:
            1. Extract claims from the response
            2. For each claim, verify if context supports it
            3. Faithfulness = # supported claims / # total claims
        """
        
        # Step 1: Extract claims
        claims = AWAIT self.model.completion(
            prompt = f"List all factual claims in this response:\n{response}"
        )
        claim_list = parse_claims(claims)
        
        # Step 2: Verify each claim
        supported = 0
        FOR EACH claim IN claim_list:
            verdict = AWAIT self.model.completion(
                prompt = f"""
                    Context: {context}
                    Claim: {claim}
                    Is this claim supported by the context? (yes/no)
                """
            )
            IF verdict.lower().startswith("yes"):
                supported += 1
        
        RETURN supported / LENGTH(claim_list) IF LENGTH(claim_list) > 0 ELSE 1.0
    
    
    ASYNC FUNCTION _evaluate_relevancy(query, response):
        """
        Check: Does the response actually answer the question?
        
        Score 0-1 via LLM judgment.
        """
        
        score = AWAIT self.model.completion(
            prompt = f"""
                Question: {query}
                Answer: {response}
                Rate how well the answer addresses the question (0.0 to 1.0):
            """
        )
        
        RETURN FLOAT(score)
    
    
    ASYNC FUNCTION _evaluate_context_precision(query, context):
        """
        Check: How much of the retrieved context is actually relevant?
        
        Precision = # relevant context items / # total context items
        """
        
        # For each context item, judge relevance
        relevant_count = 0
        total_count = 0
        
        FOR EACH item IN context:
            is_relevant = AWAIT self.model.completion(
                prompt = f"""
                    Query: {query}
                    Context Item: {item}
                    Is this context item relevant to the query? (yes/no)
                """
            )
            total_count += 1
            IF is_relevant.lower().startswith("yes"):
                relevant_count += 1
        
        RETURN relevant_count / total_count IF total_count > 0 ELSE 0.0


FUNCTION benchmark_search_methods(queries, ground_truths, config):
    """
    Compare all search methods on a test dataset.
    """
    
    methods = ["local", "global", "drift", "basic", "hybrid"]
    results = {}
    
    FOR EACH method IN methods:
        engine = get_search_engine(method, config)
        evaluator = RAGEvaluator(eval_model)
        
        method_scores = []
        FOR EACH (query, truth) IN ZIP(queries, ground_truths):
            result = AWAIT engine.search(query)
            scores = AWAIT evaluator.evaluate(
                query        = query,
                response     = result.response,
                context      = result.context_data,
                ground_truth = truth
            )
            scores["completion_time"] = result.completion_time
            scores["llm_calls"]      = result.llm_calls
            scores["token_usage"]    = result.prompt_tokens + result.output_tokens
            method_scores.APPEND(scores)
        
        results[method] = {
            "avg_faithfulness":      MEAN([s["faithfulness"] FOR s IN method_scores]),
            "avg_relevancy":         MEAN([s["relevancy"] FOR s IN method_scores]),
            "avg_context_precision": MEAN([s["context_precision"] FOR s IN method_scores]),
            "avg_completion_time":   MEAN([s["completion_time"] FOR s IN method_scores]),
            "total_llm_calls":       SUM([s["llm_calls"] FOR s IN method_scores]),
            "total_tokens":          SUM([s["token_usage"] FOR s IN method_scores])
        }
    
    RETURN results
```

### 12.2 Cost Optimization Strategies

```pseudo
# Strategy 1: Use Fast Indexing (NLP-based, no LLM for extraction)
config.indexing_method = IndexingMethod.Fast
# Uses extract_graph_nlp instead of extract_graph
# Much cheaper but less accurate

# Strategy 2: Cache LLM responses
config.cache.type = "file"
config.cache.base_dir = "./cache"
# Subsequent runs reuse cached extraction/summarization results

# Strategy 3: Tune chunk sizes
config.chunking.size = 500          # larger chunks = fewer LLM calls
config.chunking.overlap = 50        # smaller overlap = fewer chunks

# Strategy 4: Reduce gleanings
config.extract_graph.max_gleanings = 0   # no re-extraction passes

# Strategy 5: Limit embedding fields
config.embed_text.names = ["entity_description"]   # only embed entities
# Skip text_unit and community_report embeddings if not using basic search
```

---

## Phase 13: Production Readiness

### 13.1 Deployment Architecture

```pseudo
# Docker Compose for production deployment

services:
    api:
        build: ./api
        ports: ["8000:8000"]
        environment:
            GRAPHRAG_API_KEY: ${API_KEY}
            GRAPHRAG_STORAGE: "cosmosdb"
            GRAPHRAG_VECTOR_STORE: "azure_ai_search"
        volumes:
            - ./data:/app/data
    
    worker:
        build: ./worker
        # Background indexing worker
        environment:
            GRAPHRAG_API_KEY: ${API_KEY}
        command: ["python", "-m", "celery", "worker"]
    
    redis:
        image: redis:7
        # Task queue for background indexing
    
    monitoring:
        image: grafana/grafana
        ports: ["3000:3000"]
        # Dashboard for LLM usage monitoring


# Health check endpoint
@app.get("/health")
FUNCTION health_check():
    RETURN {
        "status": "healthy",
        "version": "1.0.0",
        "index_status": check_index_exists(),
        "vector_store": check_vector_store_connection(),
        "llm_provider": check_llm_availability()
    }


# Monitoring middleware
CLASS MonitoringMiddleware:
    
    FUNCTION track_query(query, method, result):
        metrics.record({
            "query_length":     LENGTH(query),
            "search_method":    method,
            "llm_calls":        result.llm_calls,
            "prompt_tokens":    result.prompt_tokens,
            "output_tokens":    result.output_tokens,
            "completion_time":  result.completion_time,
            "estimated_cost":   calculate_cost(result),
            "timestamp":        NOW()
        })
    
    FUNCTION calculate_cost(result):
        # GPT-4o pricing (example):
        input_cost  = result.prompt_tokens * 2.50 / 1_000_000
        output_cost = result.output_tokens * 10.0 / 1_000_000
        RETURN input_cost + output_cost
```

### 13.2 Error Recovery

```pseudo
CLASS ResilientPipeline:
    """
    Wrapper that adds retry logic and checkpoint recovery to the pipeline.
    """
    
    ASYNC FUNCTION run_with_recovery(pipeline, config):
        """
        Run pipeline with automatic retry on failure.
        Resumes from last successful workflow.
        """
        
        checkpoint = load_checkpoint()
        start_from = checkpoint.last_completed_workflow IF checkpoint ELSE 0
        
        FOR i, (name, workflow_fn) IN ENUMERATE(pipeline.run()):
            IF i < start_from:
                CONTINUE   # skip already completed workflows
            
            retries = 0
            max_retries = 3
            
            WHILE retries < max_retries:
                TRY:
                    result = AWAIT workflow_fn(config, context)
                    save_checkpoint(workflow_index = i, name = name)
                    BREAK
                EXCEPT RateLimitError:
                    retries += 1
                    wait_time = 2 ** retries * 30   # exponential backoff
                    LOG_WARNING(f"Rate limited. Retrying in {wait_time}s...")
                    AWAIT sleep(wait_time)
                EXCEPT Exception AS e:
                    LOG_ERROR(f"Workflow {name} failed: {e}")
                    IF retries >= max_retries - 1:
                        save_checkpoint(workflow_index = i, name = name, error = str(e))
                        RAISE
                    retries += 1
```

---

## Quick Reference: Full Pipeline Execution Order

```
┌─────────────────────────────────────────────────────────────┐
│                    INDEXING PIPELINE                         │
├─────────────────────────────────────────────────────────────┤
│ 1. load_input_documents    │ Parse raw files              │
│ 2. create_base_text_units  │ Chunk documents              │
│ 3. create_final_documents  │ Store doc metadata           │
│ 4. extract_graph           │ LLM entity extraction        │
│ 5. finalize_graph          │ Compute graph metrics        │
│ 6. extract_covariates      │ Optional claims extraction   │
│ 7. create_communities      │ Leiden clustering            │
│ 8. create_final_text_units │ Link text units to entities  │
│ 9. create_community_reports│ LLM community summaries      │
│ 10. generate_text_embeddings│ Vector embeddings           │
├─────────────────────────────────────────────────────────────┤
│                    QUERY PIPELINE                           │
├─────────────────────────────────────────────────────────────┤
│ 1. Query Router            │ Classify query type          │
│ 2. Context Building        │ Retrieve relevant data       │
│ 3. LLM Generation          │ Generate answer              │
│ 4. (Hybrid) Fusion         │ Merge multi-source results   │
└─────────────────────────────────────────────────────────────┘
```
