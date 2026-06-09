"""Eval runner worker — chạy Pipeline + Metrics, RAGAS riêng."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any
from uuid import UUID

from agentic_rag.autodata_eval.db import get_conn

logger = logging.getLogger(__name__)

_PIPELINE_WORKERS = 5
_POLL_INTERVAL = 3.0


# ── Pipeline + Auto Metrics ───────────────────────────────────────────────────

def run_pipeline_for_question(
    question_id: str,
    question: str,
    ground_truth: str,
    source_chunk_ids: list[str],
    run_id: str,
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Chạy RAG pipeline cho 1 câu hỏi, trả về kết quả + metrics."""
    try:
        from agentic_rag.agent.graph import run_agent
        from agentic_rag.core.contracts import Question as AgentQuestion

        result = run_agent(
            AgentQuestion(question=question, document_ids=document_ids or []),
        )

        bot_response = result.get("answer", "")
        bot_citations = result.get("citations", [])
        rag_context = result.get("context", "")
        trace_url = result.get("trace_url")
        retrieved_chunks = result.get("retrieved_chunks", [])

        retrieved_ids = [c.get("chunk_id", "") for c in retrieved_chunks[:5]]
        ground_truth_rank = _compute_rank(source_chunk_ids, retrieved_ids)
        recall = _recall_at_k(source_chunk_ids, retrieved_ids, k=5)
        mrr = _mrr_at_k(source_chunk_ids, retrieved_ids, k=5)
        citation_match = _citation_match(source_chunk_ids, bot_citations)
        guardrail = result.get("guardrail_pass", True)

        return {
            "rag_context": rag_context,
            "bot_response": bot_response,
            "bot_citations": bot_citations,
            "trace_url": trace_url,
            "retrieved_top5_ids": retrieved_ids,
            "ground_truth_rank": ground_truth_rank,
            "recall_at_5": recall,
            "mrr_at_5": mrr,
            "citation_chunk_match": citation_match,
            "guardrail_pass": guardrail,
            "eval_error": None,
        }
    except Exception as exc:
        logger.error("Pipeline error for question %s: %s", question_id, exc)
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


# ── Worker loop ───────────────────────────────────────────────────────────────

def _write_result(run_id: str, question_id: str, payload: dict[str, Any]) -> None:
    import json
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
            has_error = bool(payload.get("eval_error"))
            col = "failed" if has_error else "success"
            cur.execute(
                f"UPDATE eval_runs SET {col} = {col} + 1 WHERE id = %s", (run_id,)
            )
        conn.commit()


def _next_pending_question(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT q.id, q.question, q.ground_truth, q.source_chunk_ids, q.document_id
                FROM eval_questions_approved a
                JOIN eval_questions q ON q.id = a.question_id
                LEFT JOIN eval_results r ON r.question_id = q.id AND r.run_id = %s
                JOIN eval_runs run ON run.id = %s
                WHERE a.dataset_id = run.dataset_id
                  AND r.id IS NULL
                  AND q.deleted_at IS NULL
                LIMIT 1
                """,
                (run_id, run_id),
            )
            return cur.fetchone()


def run_eval_worker(run_id: str) -> None:
    """Worker chạy trong background thread cho 1 eval run."""
    logger.info("Eval worker started for run %s", run_id)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_runs SET status = 'running' WHERE id = %s", (run_id,)
            )
        conn.commit()

    sem = threading.Semaphore(_PIPELINE_WORKERS)
    threads: list[threading.Thread] = []

    def process(row: dict[str, Any]) -> None:
        with sem:
            payload = run_pipeline_for_question(
                question_id=str(row["id"]),
                question=row["question"],
                ground_truth=row["ground_truth"],
                source_chunk_ids=row.get("source_chunk_ids") or [],
                run_id=run_id,
                document_ids=[row["document_id"]] if row.get("document_id") else None,
            )
            _write_result(run_id, str(row["id"]), payload)

    while True:
        row = _next_pending_question(run_id)
        if row is None:
            break

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM eval_runs WHERE id = %s", (run_id,))
                run = cur.fetchone()
        if run and run["status"] == "paused":
            time.sleep(_POLL_INTERVAL)
            continue

        t = threading.Thread(target=process, args=(row,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE eval_runs
                SET status = 'done', completed_at = NOW()
                WHERE id = %s
                """,
                (run_id,),
            )
        conn.commit()

    logger.info("Eval worker finished for run %s", run_id)


# ── RAGAS worker ──────────────────────────────────────────────────────────────

def run_ragas_worker(run_id: str, question_ids: list[str] | None = None) -> None:
    """Chạy RAGAS riêng sau khi Pipeline đã xong."""
    try:
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
        from datasets import Dataset as HFDataset
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
        return

    dataset = HFDataset.from_list([
        {
            "question": r["question"],
            "answer": r["bot_response"] or "",
            "contexts": [r["rag_context"] or ""],
            "ground_truth": r["ground_truth"],
        }
        for r in rows
    ])

    scores = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision, context_recall])
    scores_df = scores.to_pandas()

    with get_conn() as conn:
        with conn.cursor() as cur:
            for i, row in enumerate(rows):
                row_score = scores_df.iloc[i]
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
                        float(row_score.get("faithfulness", 0) or 0),
                        float(row_score.get("answer_relevancy", 0) or 0),
                        float(row_score.get("context_precision", 0) or 0),
                        float(row_score.get("context_recall", 0) or 0),
                        row["id"],
                    ),
                )
        conn.commit()

    logger.info("RAGAS done for run %s, %d questions", run_id, len(rows))
