"""Eval runner worker — chạy Pipeline + RAGAS song song (producer-consumer)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from agentic_rag.autodata_eval.db import get_conn, retry_on_operational_error

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 3.0
_BATCH_SIZE = 3

# Guard chống 2 worker thread cùng chạy cho 1 run_id
_running_workers: set[str] = set()
_running_workers_lock = threading.Lock()


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline_for_question(
    question_id: str,
    question: str,
    source_chunk_ids: list[str],
) -> dict[str, Any]:
    """Chạy RAG pipeline cho 1 câu hỏi, trả về kết quả + metrics."""
    try:
        from agentic_rag.agent.graph import run_agent
        from agentic_rag.core.contracts import WorkflowRunInput
        from agentic_rag.generation.evidence import source_provider_from_env

        provider = source_provider_from_env()
        result = run_agent(
            provider=provider,
            request=WorkflowRunInput(
                question=question,
                document_ids=None,  # search full corpus
            ),
        )

        bot_response = result.answer.answer
        citations    = result.answer.citations
        bot_citations = [c.model_dump() for c in citations]
        rag_context  = "\n\n".join(sr.chunk.text for sr in result.evidence_chunks)
        retrieved_ids = [sr.chunk.chunk_id for sr in result.evidence_chunks[:5]]

        ground_truth_rank = _compute_rank(source_chunk_ids, retrieved_ids)
        recall = _recall_at_k(source_chunk_ids, retrieved_ids, k=5)
        mrr    = _mrr_at_k(source_chunk_ids, retrieved_ids, k=5)
        citation_match = _citation_match(source_chunk_ids, bot_citations)
        guardrail = result.answer.status == "answered"

        return {
            "rag_context": rag_context,
            "bot_response": bot_response,
            "bot_citations": bot_citations,
            "trace_url": None,
            "retrieved_top5_ids": retrieved_ids,
            "ground_truth_rank": ground_truth_rank,
            "recall_at_5": recall,
            "mrr_at_5": mrr,
            "citation_chunk_match": citation_match,
            "guardrail_pass": guardrail,
            "eval_error": None,
        }
    except Exception as exc:
        logger.exception("Pipeline error for question %s: %s", question_id, exc)
        return {"eval_error": str(exc)}


def _compute_rank(ground_truth_ids: list[str], retrieved_ids: list[str]) -> int | None:
    for rank, rid in enumerate(retrieved_ids, start=1):
        if rid in ground_truth_ids:
            return rank
    return None


def _recall_at_k(ground_truth_ids: list[str], retrieved_ids: list[str], k: int) -> float:
    if not ground_truth_ids:
        return 0.0
    hits = len(set(retrieved_ids[:k]) & set(ground_truth_ids))
    return hits / len(ground_truth_ids)


def _mrr_at_k(ground_truth_ids: list[str], retrieved_ids: list[str], k: int) -> float:
    for rank, rid in enumerate(retrieved_ids[:k], start=1):
        if rid in ground_truth_ids:
            return 1.0 / rank
    return 0.0


def _citation_match(ground_truth_ids: list[str], citations: list[Any]) -> float:
    if not ground_truth_ids or not citations:
        return 0.0
    cited_ids = {c.get("chunk_id", "") for c in citations if isinstance(c, dict)}
    hits = len(cited_ids & set(ground_truth_ids))
    return hits / len(ground_truth_ids)


# ── DB helpers ────────────────────────────────────────────────────────────────

@retry_on_operational_error
def _write_result(run_id: str, question_id: str, payload: dict[str, Any]) -> None:
    import json
    has_error = bool(payload.get("eval_error"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO eval_results (
                  question_id, run_id,
                  rag_context, bot_response, bot_citations, trace_url,
                  retrieved_top5_ids, ground_truth_rank,
                  recall_at_5, mrr_at_5, citation_chunk_match, guardrail_pass,
                  eval_error
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (question_id, run_id) DO UPDATE SET
                  rag_context = EXCLUDED.rag_context,
                  bot_response = EXCLUDED.bot_response,
                  bot_citations = EXCLUDED.bot_citations,
                  trace_url = EXCLUDED.trace_url,
                  retrieved_top5_ids = EXCLUDED.retrieved_top5_ids,
                  ground_truth_rank = EXCLUDED.ground_truth_rank,
                  recall_at_5 = EXCLUDED.recall_at_5,
                  mrr_at_5 = EXCLUDED.mrr_at_5,
                  citation_chunk_match = EXCLUDED.citation_chunk_match,
                  guardrail_pass = EXCLUDED.guardrail_pass,
                  eval_error = EXCLUDED.eval_error,
                  ran_at = NOW()
                RETURNING (xmax = 0) AS is_new_insert
                """,
                (
                    question_id, run_id,
                    payload.get("rag_context"),
                    payload.get("bot_response"),
                    json.dumps(payload.get("bot_citations")) if payload.get("bot_citations") else None,
                    payload.get("trace_url"),
                    payload.get("retrieved_top5_ids"),
                    payload.get("ground_truth_rank"),
                    payload.get("recall_at_5"),
                    payload.get("mrr_at_5"),
                    payload.get("citation_chunk_match"),
                    payload.get("guardrail_pass"),
                    payload.get("eval_error"),
                ),
            )
            # Chỉ tăng counter khi INSERT thật (xmax=0), không tăng khi ON CONFLICT DO UPDATE
            # Tránh success/failed vượt quá total khi 2 worker chạy cùng lúc hoặc retry
            is_new = (cur.fetchone() or {}).get("is_new_insert", False)
            if is_new:
                col = "failed" if has_error else "success"
                cur.execute(
                    f"UPDATE eval_runs SET {col} = {col} + 1 WHERE id = %s", (run_id,)
                )
        conn.commit()


@retry_on_operational_error
def _next_pending_question(run_id: str) -> dict[str, Any] | None:
    """Lấy câu tiếp theo từ snapshot đóng băng lúc tạo run (frozen_question_ids).
    Dùng snapshot tránh worker đọc dataset live — câu mới add sau khi run bắt đầu
    sẽ không bị kéo vào và không gây vòng lặp vô hạn."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT q.id, q.question, q.ground_truth, q.source_chunk_ids, q.document_id
                FROM eval_runs run
                JOIN eval_questions q ON q.id = ANY(run.frozen_question_ids)
                LEFT JOIN eval_results r ON r.question_id = q.id AND r.run_id = %s
                WHERE run.id = %s
                  AND r.id IS NULL
                  AND q.deleted_at IS NULL
                LIMIT 1
                """,
                (run_id, run_id),
            )
            return cur.fetchone()


@retry_on_operational_error
def _fetch_ragas_batch(run_id: str, batch_size: int) -> list[dict[str, Any]]:
    """Lấy batch câu đã có pipeline output nhưng chưa có RAGAS score."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.question_id, q.question, q.ground_truth,
                       r.rag_context, r.bot_response
                FROM eval_results r
                JOIN eval_questions q ON q.id = r.question_id
                WHERE r.run_id = %s
                  AND r.eval_error IS NULL
                  AND r.ragas_faithfulness IS NULL
                  AND r.bot_response IS NOT NULL
                LIMIT %s
                """,
                (run_id, batch_size),
            )
            return cur.fetchall()


# ── RAGAS ─────────────────────────────────────────────────────────────────────

def _setup_ragas() -> dict[str, Any]:
    """Import RAGAS, cấu hình LLM/embeddings. Gọi 1 lần duy nhất."""
    import sys
    import types
    import os

    _lc_vertexai = "langchain_community.chat_models.vertexai"
    if _lc_vertexai not in sys.modules:
        _mod = types.ModuleType(_lc_vertexai)
        _mod.ChatVertexAI = None  # type: ignore[attr-defined]
        sys.modules[_lc_vertexai] = _mod

    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    _llm = LangchainLLMWrapper(ChatOpenAI(
        model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        api_key=os.environ.get("OPENAI_API_KEY"),
    ))
    _emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(
        model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        api_key=os.environ.get("OPENAI_API_KEY"),
    ))
    for _m in (faithfulness, answer_relevancy, context_precision, context_recall):
        _m.llm = _llm  # type: ignore[attr-defined]
    answer_relevancy.embeddings = _emb  # type: ignore[attr-defined]

    return {
        "evaluate": evaluate,
        "metrics": [faithfulness, answer_relevancy, context_precision, context_recall],
    }


def _process_ragas_batch(run_id: str, rows: list[dict[str, Any]], ctx: dict[str, Any]) -> None:
    """Chạy RAGAS cho 1 batch và ghi kết quả vào DB."""
    from datasets import Dataset as HFDataset

    evaluate = ctx["evaluate"]
    metrics  = ctx["metrics"]

    dataset = HFDataset.from_list([
        {
            "question": r["question"],
            "answer":   r["bot_response"] or "",
            "contexts": [r["rag_context"] or ""],
            "ground_truth": r["ground_truth"],
        }
        for r in rows
    ])

    scores    = evaluate(dataset, metrics=metrics)
    scores_df = scores.to_pandas()

    with get_conn() as conn:
        with conn.cursor() as cur:
            for i, row in enumerate(rows):
                s = scores_df.iloc[i]
                cur.execute(
                    """
                    UPDATE eval_results SET
                      ragas_faithfulness      = %s,
                      ragas_answer_relevancy  = %s,
                      ragas_context_precision = %s,
                      ragas_context_recall    = %s
                    WHERE id = %s
                    """,
                    (
                        float(s.get("faithfulness",       0) or 0),
                        float(s.get("answer_relevancy",   0) or 0),
                        float(s.get("context_precision",  0) or 0),
                        float(s.get("context_recall",     0) or 0),
                        row["id"],
                    ),
                )
        conn.commit()

    logger.info("RAGAS batch done: %d rows for run %s", len(rows), run_id)


def _ragas_consumer(run_id: str, pipeline_done: threading.Event) -> None:
    """
    Consumer thread: poll DB cho batch mới ngay khi pipeline produce đủ 3 câu.
    Chạy song song với pipeline loop — tiết kiệm pipeline_time so với sequential.
    """
    try:
        ctx = _setup_ragas()
    except ImportError:
        logger.error("RAGAS not installed. Run: uv pip install ragas datasets")
        return
    except Exception as exc:
        logger.exception("RAGAS setup failed: %s", exc)
        return

    logger.info("RAGAS consumer started for run %s", run_id)

    while True:
        rows = _fetch_ragas_batch(run_id, _BATCH_SIZE)

        if len(rows) == _BATCH_SIZE:
            # Full batch sẵn sàng — process ngay
            _process_ragas_batch(run_id, rows, ctx)
        elif pipeline_done.is_set():
            # Pipeline xong, xử lý nốt phần còn lại (< BATCH_SIZE)
            if rows:
                _process_ragas_batch(run_id, rows, ctx)
            break
        else:
            # Chưa đủ batch, chờ pipeline produce thêm
            time.sleep(_POLL_INTERVAL)

    logger.info("RAGAS consumer done for run %s", run_id)


@retry_on_operational_error
def _get_run_status(run_id: str) -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM eval_runs WHERE id = %s", (run_id,))
            row = cur.fetchone()
            return row["status"] if row else None


@retry_on_operational_error
def _mark_run_done(run_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_runs SET status = 'done', completed_at = NOW() WHERE id = %s",
                (run_id,),
            )
        conn.commit()


@retry_on_operational_error
def _mark_run_running(run_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE eval_runs SET status = 'running' WHERE id = %s", (run_id,))
        conn.commit()


# ── Main worker ───────────────────────────────────────────────────────────────

def run_eval_worker(run_id: str) -> None:
    """Worker chạy trong background thread cho 1 eval run."""
    with _running_workers_lock:
        if run_id in _running_workers:
            logger.warning("Worker already active for run %s — skipping duplicate start", run_id)
            return
        _running_workers.add(run_id)

    logger.info("Eval worker started for run %s", run_id)
    try:
        _mark_run_running(run_id)

        pipeline_done = threading.Event()

        ragas_thread = threading.Thread(
            target=_ragas_consumer,
            args=(run_id, pipeline_done),
            daemon=True,
        )
        ragas_thread.start()

        while True:
            if _get_run_status(run_id) == "paused":
                time.sleep(_POLL_INTERVAL)
                continue

            row = _next_pending_question(run_id)
            if row is None:
                break

            payload = run_pipeline_for_question(
                question_id=str(row["id"]),
                question=row["question"],
                source_chunk_ids=row.get("source_chunk_ids") or [],
            )
            _write_result(run_id, str(row["id"]), payload)

        logger.info("Pipeline done for run %s, waiting for RAGAS consumer", run_id)
        pipeline_done.set()
        ragas_thread.join()

        _mark_run_done(run_id)
        logger.info("Run %s marked as done", run_id)
    finally:
        with _running_workers_lock:
            _running_workers.discard(run_id)


# ── Manual RAGAS trigger (dùng cho router endpoint POST /runs/{id}/ragas) ────

def run_ragas_worker(run_id: str, question_ids: list[str] | None = None) -> None:
    """Chạy lại RAGAS cho các câu chưa có score (dùng khi trigger thủ công)."""
    try:
        ctx = _setup_ragas()
    except ImportError:
        logger.error("RAGAS not installed. Run: uv pip install ragas datasets")
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            filter_clause = "AND r.question_id = ANY(%s)" if question_ids else ""
            params: tuple = (run_id, question_ids) if question_ids else (run_id,)
            cur.execute(
                f"""
                SELECT r.id, r.question_id, q.question, q.ground_truth,
                       r.rag_context, r.bot_response
                FROM eval_results r
                JOIN eval_questions q ON q.id = r.question_id
                WHERE r.run_id = %s
                  AND r.eval_error IS NULL
                  AND r.ragas_faithfulness IS NULL
                  {filter_clause}
                """,
                params,
            )
            rows = cur.fetchall()

    if not rows:
        logger.warning("RAGAS: no rows to evaluate for run %s", run_id)
        return

    logger.info("RAGAS manual trigger: %d rows for run %s", len(rows), run_id)

    for batch_start in range(0, len(rows), _BATCH_SIZE):
        batch = rows[batch_start : batch_start + _BATCH_SIZE]
        _process_ragas_batch(run_id, batch, ctx)

    logger.info("RAGAS manual trigger done for run %s", run_id)
