# Agentic RAG — Tài liệu bàn giao

## Tổng quan

Pipeline Agentic RAG được implement theo kiến trúc Self-RAG, dùng LangGraph làm orchestrator.
Bật/tắt qua env var `AGENT_MODE=true/false` — giữ nguyên linear pipeline khi tắt.

---

## Cấu trúc module

```
src/agentic_rag/agent/
├── __init__.py          exports: AgentState, build_agent, run_agent
├── state.py             AgentState TypedDict — toàn bộ state qua các nodes
├── grading.py           preprocess_query, grade_hallucination, transform_query
├── nodes.py             tất cả LangGraph node functions + routing functions
└── graph.py             build_agent(), run_agent(), WorkflowRunInput/WorkflowRunOutput
```

---

## Pipeline flow

```
question + history
      ↓
[preprocess_node]
  • Heuristic check (free): có history? multi-intent?
  • Nếu không → pass-through (0 LLM calls)
  • Nếu có → preprocess-llm: resolve pronouns / decompose
      ↓
[retrieve_node]          BM25 + dense + RRF (provider nội bộ)
      ↓
[rerank_node]            cross-encoder với original question, top-N
      ↓
route_after_rerank
  ├── có docs → [generate_node]
  └── không có, step < max → [transform_query_node]
                                    ↓
                             expand / requery → retrieve lại
[generate_node]          build_evidence_context + LLM generate
      ↓
[grade_hallucination_node]  LLM: mọi claim có trong evidence không?
      ├── grounded → [check_answer_node]
      └── bịa + attempts < max → [generate_node] (regen)
[check_answer_node]      rule-based: override → not_found nếu hallucinated max lần
      ↓
route_after_check
  ├── answered → END
  └── not_found + step < max → [transform_query_node] → retrieve lại
```

---

## LLM calls

| Scenario | Calls |
|---|---|
| Happy path, query rõ | generate + hallucination = **2** |
| Có history / multi-intent | + preprocess = **3** |
| + 1 lần transform | + transform + hallucination = **+2** |
| Hallucinate 1 lần | + generate + hallucination = **+2** |

---

## Env vars (agent-specific)

```bash
AGENT_MODE=true                   # bật Self-RAG pipeline
AGENT_MAX_STEPS=3                 # max retrieval+transform loops
AGENT_RERANK_TOP_N=20             # top-N docs vào rerank
AGENT_MAX_GENERATE_ATTEMPTS=2     # max regen khi hallucinate
```

---

## Files thay đổi ngoài agent/

| File | Thay đổi |
|---|---|
| `api.py` | `AnswerRequest.history` dùng `ConversationMessage`; gọi `run_agent` với `WorkflowRunInput` |
| `integrations/local_pdf/providers.py` | Dense dùng original query (có dấu); bỏ provider-rerank; thêm `@traceable` |
| `retrieval/search.py` | Embedding configurable (openai/huggingface) |
| `generation/answering.py` | Thêm `@traceable` cho llm-call, answer-parse |
| `observability/trace.py` | Thêm `LANGSMITH_TRACE_MODE=langgraph\|custom` |

---

## Key design decisions

1. **Rerank trước grade** — cross-encoder chạy 1 lần sau retrieve (không trong generate), dùng original question (có dấu tiếng Việt) để score chất lượng cao hơn.

2. **preprocess chỉ chạy khi cần** — heuristic check trước: có history/multi-intent signal thì mới gọi LLM, tránh tốn API call cho query đơn giản.

3. **grade_answer bị bỏ** — thay bằng `check_answer_node` rule-based. Nếu answer grounded + answered → đủ, không cần LLM phán "useful không".

4. **transform chỉ trigger khi stuck** — không có chunk hoặc answer = not_found. Không trigger khi answer "answered but off-topic" (đã bỏ grade_answer).

5. **Chống loop vô hạn** — `AGENT_MAX_STEPS` cho transform loop; `AGENT_MAX_GENERATE_ATTEMPTS` cho regen loop; transform skip detect qua trace.

---

## LangSmith trace

```
LANGSMITH_TRACE_MODE=langgraph    # dùng native LangGraph trace (khuyến nghị)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<same as LANGSMITH_API_KEY>
LANGCHAIN_PROJECT=agentic-rag-group1
```

Trace tree:
```
preprocess   → preprocess-llm (nếu cần)
retrieve     → retrieve-query → query-normalize / bm25 / dense / threshold / rrf
rerank       → rerank (cross-encoder)
generate     → generate-answer → llm-call + answer-parse
hallucination→ grade-hallucination-llm
transform    → transform-query-llm (nếu stuck)
check_answer → (rule-based, không trace LLM)
```

---

## Cách chạy

```bash
# Backend
uv run uvicorn agentic_rag.api:api --reload --port 8000

# Frontend
cd frontend && npm run dev
```

## API — gửi history

```json
POST /answer/stream
{
  "question": "Còn pin VF9 thì sao?",
  "history": [
    {"role": "user", "content": "Pin VF8 bảo hành bao lâu?"},
    {"role": "assistant", "content": "Pin VF8 bảo hành 8 năm hoặc 160,000 km."}
  ]
}
```
