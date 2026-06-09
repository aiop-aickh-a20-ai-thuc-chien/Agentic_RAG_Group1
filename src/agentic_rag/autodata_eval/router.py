"""FastAPI router cho AutoData + Eval pipeline."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException
from psycopg.rows import dict_row

from agentic_rag.autodata_eval.db import get_conn
from agentic_rag.autodata_eval.models import (
    ApproveRequest,
    Dataset,
    DatasetCreate,
    EvalResult,
    EvalRun,
    GenerateJob,
    GenerateRequest,
    Question,
    QuestionCreate,
    QuestionWithStatus,
    RunCreate,
    RunProgress,
    RunSummary,
)
from agentic_rag.autodata_eval.worker import run_eval_worker, run_ragas_worker

logger = logging.getLogger(__name__)
router = APIRouter(tags=["autodata-eval"])


# ── Datasets ──────────────────────────────────────────────────────────────────

@router.get("/datasets", response_model=list[Dataset])
def list_datasets() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM eval_datasets ORDER BY created_at DESC")
            return cur.fetchall()


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: UUID) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM eval_datasets WHERE id = %s", (str(dataset_id),))
        conn.commit()


@router.post("/datasets", response_model=Dataset)
def create_dataset(body: DatasetCreate) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO eval_datasets (name, description, is_benchmark)
                VALUES (%s, %s, %s) RETURNING *
                """,
                (body.name, body.description, body.is_benchmark),
            )
            row = cur.fetchone()
        conn.commit()
    return row


# ── Questions ─────────────────────────────────────────────────────────────────

@router.get("/datasets/{dataset_id}/questions", response_model=list[QuestionWithStatus])
def list_questions(dataset_id: UUID, include_deleted: bool = False) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            deleted_filter = "" if include_deleted else "AND q.deleted_at IS NULL"
            cur.execute(
                f"""
                SELECT q.*,
                  a.id IS NOT NULL   AS is_approved,
                  a.reviewed_by,
                  a.reviewed_at,
                  EXISTS(
                    SELECT 1 FROM eval_results er
                    JOIN eval_runs r ON er.run_id = r.id
                    WHERE er.question_id = q.id AND r.dataset_id = q.dataset_id
                  ) AS has_results
                FROM eval_questions q
                LEFT JOIN eval_questions_approved a ON a.question_id = q.id
                WHERE q.dataset_id = %s {deleted_filter}
                ORDER BY q.created_at DESC
                """,
                (str(dataset_id),),
            )
            return cur.fetchall()


def _parse_chunk_ids(raw: Any) -> list[str]:
    if not raw:
        return []
    return [c.strip() for c in str(raw).split(",") if c.strip()]


def _doc_id_from_chunks(chunk_ids: list[str]) -> str:
    if not chunk_ids:
        return "unknown"
    parts = chunk_ids[0].split("_")
    return f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else chunk_ids[0]


def _parse_excel_row(row: tuple, col: dict[str, int]) -> dict | None:
    """Return a question dict for pending rows, or None to skip."""
    status = row[col["review_status"]] if "review_status" in col else None
    if status == "approved":
        return None
    q_text = row[col["question"]] if "question" in col else None
    gt     = row[col["expected_answer"]] if "expected_answer" in col else None
    if not q_text or not gt:
        return None
    chunk_ids = _parse_chunk_ids(row[col["ground_truth_chunk_ids"]] if "ground_truth_chunk_ids" in col else None)
    section   = row[col["section_name"]] if "section_name" in col else None
    return {
        "question":     str(q_text).strip(),
        "ground_truth": str(gt).strip(),
        "section":      str(section) if section else None,
        "chunk_ids":    chunk_ids,
        "doc_id":       _doc_id_from_chunks(chunk_ids),
    }


def _load_excel_pending(col: dict[str, int], rows: list[tuple], existing: set) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    result = []
    for row in rows:
        parsed = _parse_excel_row(row, col)
        if parsed is None:
            continue
        key = (parsed["question"], parsed["ground_truth"])
        if key in existing or key in seen:
            continue
        seen.add(key)
        result.append(parsed)
    return result


@router.post("/datasets/{dataset_id}/import-excel")
def import_pending_from_excel(dataset_id: UUID) -> dict:
    """Import câu hỏi pending/None từ result.xlsx vào dataset dưới dạng Draft."""
    import openpyxl
    from pathlib import Path

    excel_path = Path("guide/reports/result.xlsx")
    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="guide/reports/result.xlsx not found")

    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    col = {h: i for i, h in enumerate(all_rows[1]) if h is not None}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT question, ground_truth FROM eval_questions WHERE dataset_id = %s",
                (str(dataset_id),),
            )
            existing = {(r["question"].strip(), r["ground_truth"].strip()) for r in cur.fetchall()}

    to_import = _load_excel_pending(col, all_rows[2:], existing)

    if not to_import:
        return {"imported": 0, "skipped_existing": len(existing)}

    with get_conn() as conn:
        with conn.cursor() as cur:
            for q in to_import:
                cur.execute(
                    """
                    INSERT INTO eval_questions
                      (dataset_id, document_id, section, question, ground_truth, source_chunk_ids)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (str(dataset_id), q["doc_id"], q["section"],
                     q["question"], q["ground_truth"], q["chunk_ids"]),
                )
        conn.commit()

    return {"imported": len(to_import), "skipped_existing": len(existing)}


@router.post("/questions/batch", response_model=list[Question])
def create_questions_batch(questions: list[QuestionCreate]) -> list[dict]:
    if not questions:
        return []
    with get_conn() as conn:
        with conn.cursor() as cur:
            rows = []
            for q in questions:
                cur.execute(
                    """
                    INSERT INTO eval_questions
                      (dataset_id, document_id, section, question, ground_truth, source_chunk_ids)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
                    """,
                    (
                        str(q.dataset_id), q.document_id, q.section,
                        q.question, q.ground_truth, q.source_chunk_ids,
                    ),
                )
                rows.append(cur.fetchone())
        conn.commit()
    return rows


@router.post("/questions/approve")
def approve_questions(body: ApproveRequest) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            for qid in body.question_ids:
                cur.execute(
                    """
                    INSERT INTO eval_questions_approved (question_id, dataset_id, reviewed_by)
                    SELECT %s, dataset_id, %s FROM eval_questions WHERE id = %s
                    ON CONFLICT (question_id) DO UPDATE SET
                      reviewed_by = EXCLUDED.reviewed_by,
                      reviewed_at = NOW()
                    """,
                    (str(qid), body.reviewed_by, str(qid)),
                )
        conn.commit()
    return {"approved": len(body.question_ids)}


@router.post("/questions/archive")
def archive_questions(question_ids: list[UUID]) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_questions SET deleted_at = NOW() WHERE id = ANY(%s)",
                ([str(q) for q in question_ids],),
            )
        conn.commit()
    return {"archived": len(question_ids)}


@router.post("/questions/restore")
def restore_questions(question_ids: list[UUID]) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_questions SET deleted_at = NULL WHERE id = ANY(%s)",
                ([str(q) for q in question_ids],),
            )
        conn.commit()
    return {"restored": len(question_ids)}


@router.get("/datasets/{dataset_id}/doc-question-counts")
def doc_question_counts(dataset_id: UUID) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_id, COUNT(*) AS cnt
                FROM eval_questions
                WHERE dataset_id = %s AND deleted_at IS NULL
                GROUP BY document_id
                """,
                (str(dataset_id),),
            )
            return {r["document_id"]: r["cnt"] for r in cur.fetchall()}


@router.get("/chunks/{chunk_id}")
def get_chunk_content(chunk_id: str) -> dict:
    """Lấy nội dung text của 1 chunk theo chunk_id."""
    try:
        from agentic_rag.generation.evidence import source_provider_from_env
        from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider

        provider = source_provider_from_env()
        if not isinstance(provider, LocalPdfEvidenceProvider):
            raise HTTPException(status_code=404, detail="Not a LocalPdf provider")
        parts = chunk_id.split("_")
        doc_id = f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else chunk_id
        doc_chunks = provider.document_chunks(document_id=doc_id)
        for chunk in doc_chunks.chunks:
            if chunk.chunk_id == chunk_id:
                return {
                    "chunk_id": chunk_id,
                    "document_id": doc_id,
                    "text": chunk.text,
                    "metadata": dict(chunk.metadata),
                }
        raise HTTPException(status_code=404, detail="Chunk not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/datasets/{dataset_id}/sections")
def list_sections(dataset_id: str, document_id: str) -> list[dict]:
    """Trả về danh sách section + số chunk của 1 document trong store."""
    try:
        from agentic_rag.generation.evidence import source_provider_from_env
        from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider

        provider = source_provider_from_env()
        if not isinstance(provider, LocalPdfEvidenceProvider):
            return []
        doc_chunks = provider.document_chunks(document_id=document_id)
        sections: dict[str, int] = {}
        for chunk in doc_chunks.chunks:
            section = str(chunk.metadata.get("section") or chunk.metadata.get("title") or "Không có section")
            sections[section] = sections.get(section, 0) + 1
        return [{"section": s, "chunk_count": c} for s, c in sorted(sections.items())]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── AutoData Generate ─────────────────────────────────────────────────────────

_generate_jobs: dict[str, str] = {}


@router.post("/autodata/generate", response_model=GenerateJob)
def generate_questions(body: GenerateRequest, background: BackgroundTasks) -> dict:
    job_id = str(uuid.uuid4())
    _generate_jobs[job_id] = "running"
    background.add_task(_run_generate, job_id, body)
    return {"job_id": job_id, "status": "running", "message": "Đang sinh câu hỏi..."}


@router.get("/autodata/jobs/{job_id}", response_model=GenerateJob)
def get_generate_job(job_id: str) -> dict:
    status = _generate_jobs.get(job_id, "not_found")
    messages = {
        "running": "Đang sinh câu hỏi...",
        "done": "Hoàn thành",
        "failed": "Thất bại",
        "not_found": "Không tìm thấy job",
    }
    return {"job_id": job_id, "status": status, "message": messages.get(status, "")}


def _run_generate(job_id: str, body: GenerateRequest) -> None:
    try:
        from agentic_rag.integrations.local_pdf.providers import get_source_provider

        provider = get_source_provider()
        chunks = provider.storage.read_chunks(body.document_id)

        if body.section_filters:
            chunks = [
                c for c in chunks
                if (c.metadata.get("section") or c.metadata.get("title", "")) in body.section_filters
            ]

        section_chunks: dict[str, list] = {}
        for chunk in chunks:
            section = chunk.metadata.get("section") or chunk.metadata.get("title") or "General"
            section_chunks.setdefault(section, []).append(chunk)

        questions: list[QuestionCreate] = []
        for section, sec_chunks in section_chunks.items():
            context = "\n\n".join(c.text for c in sec_chunks[:10])
            generated = _call_llm_generate(context, body.questions_per_section, section)
            for item in generated:
                questions.append(QuestionCreate(
                    dataset_id=body.dataset_id,
                    document_id=body.document_id,
                    section=section,
                    question=item["question"],
                    ground_truth=item["answer"],
                    source_chunk_ids=[c.chunk_id for c in sec_chunks[:5]],
                ))

        if questions:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    for q in questions:
                        cur.execute(
                            """
                            INSERT INTO eval_questions
                              (dataset_id, document_id, section, question, ground_truth, source_chunk_ids)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (str(q.dataset_id), q.document_id, q.section,
                             q.question, q.ground_truth, q.source_chunk_ids),
                        )
                conn.commit()

        _generate_jobs[job_id] = "done"
    except Exception as exc:
        logger.error("Generate job %s failed: %s", job_id, exc)
        _generate_jobs[job_id] = "failed"


def _call_llm_generate(context: str, n: int, section: str) -> list[dict[str, str]]:
    import litellm
    import os

    prompt = f"""Dựa vào đoạn văn bản sau, hãy tạo ra {n} câu hỏi và câu trả lời ngắn gọn.
Section: {section}

Văn bản:
{context[:3000]}

Trả về JSON array với format:
[{{"question": "...", "answer": "..."}}]
Chỉ trả về JSON, không thêm gì khác."""

    response = litellm.completion(
        model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "[]"
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = parsed.get("questions", parsed.get("items", list(parsed.values())[0] if parsed else []))
        return [q for q in parsed if isinstance(q, dict) and "question" in q and "answer" in q][:n]
    except Exception:
        return []


# ── Eval Runs ─────────────────────────────────────────────────────────────────

@router.get("/runs", response_model=list[EvalRun])
def list_runs(dataset_id: UUID | None = None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if dataset_id:
                cur.execute(
                    "SELECT * FROM eval_runs WHERE dataset_id = %s ORDER BY created_at DESC",
                    (str(dataset_id),),
                )
            else:
                cur.execute("SELECT * FROM eval_runs ORDER BY created_at DESC")
            return cur.fetchall()


@router.post("/runs", response_model=EvalRun)
def create_run(body: RunCreate, background: BackgroundTasks) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS cnt FROM eval_questions_approved a
                JOIN eval_questions q ON q.id = a.question_id
                WHERE a.dataset_id = %s AND q.deleted_at IS NULL
                """,
                (str(body.dataset_id),),
            )
            total = (cur.fetchone() or {}).get("cnt", 0)

            cur.execute(
                """
                INSERT INTO eval_runs (dataset_id, name, description, config, status, total)
                VALUES (%s, %s, %s, %s, 'queued', %s) RETURNING *
                """,
                (str(body.dataset_id), body.name, body.description,
                 json.dumps(body.config), total),
            )
            run = cur.fetchone()
        conn.commit()

    background.add_task(run_eval_worker, str(run["id"]))
    return run


@router.get("/runs/{run_id}/progress", response_model=RunProgress)
def get_run_progress(run_id: UUID) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.status, r.total, r.success, r.failed,
                  (r.total - r.success - r.failed) AS not_started
                FROM eval_runs r WHERE r.id = %s
                """,
                (str(run_id),),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Run không tồn tại")
    return {"run_id": run_id, **row}


@router.post("/runs/{run_id}/pause")
def pause_run(run_id: UUID) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_runs SET status = 'paused' WHERE id = %s AND status = 'running'",
                (str(run_id),),
            )
        conn.commit()
    return {"status": "paused"}


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: UUID, background: BackgroundTasks) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_runs SET status = 'running' WHERE id = %s AND status = 'paused'",
                (str(run_id),),
            )
        conn.commit()
    background.add_task(run_eval_worker, str(run_id))
    return {"status": "running"}


@router.post("/runs/{run_id}/ragas")
def run_ragas(run_id: UUID, question_ids: list[UUID] | None = None, background: BackgroundTasks = None) -> dict:
    ids = [str(q) for q in question_ids] if question_ids else None
    background.add_task(run_ragas_worker, str(run_id), ids)
    return {"status": "started", "message": "RAGAS đang chạy ngầm..."}


# ── Results ───────────────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/results", response_model=list[EvalResult])
def list_results(run_id: UUID) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM eval_results WHERE run_id = %s ORDER BY ran_at",
                (str(run_id),),
            )
            return cur.fetchall()


# ── Compare ───────────────────────────────────────────────────────────────────

@router.get("/compare", response_model=list[RunSummary])
def compare_runs(dataset_id: UUID) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  r.id          AS run_id,
                  r.name,
                  r.config,
                  COUNT(res.id)                                      AS total_questions,
                  AVG(res.recall_at_5)                               AS avg_recall,
                  AVG(res.mrr_at_5)                                  AS avg_mrr,
                  AVG(res.citation_chunk_match)                      AS avg_citation,
                  AVG(CASE WHEN res.guardrail_pass THEN 1.0 ELSE 0.0 END) AS guardrail_rate,
                  BOOL_OR(res.ragas_faithfulness IS NOT NULL)        AS has_ragas,
                  AVG(res.ragas_faithfulness)                        AS avg_ragas_faithfulness,
                  AVG(res.ragas_answer_relevancy)                    AS avg_ragas_relevancy
                FROM eval_runs r
                LEFT JOIN eval_results res ON res.run_id = r.id
                WHERE r.dataset_id = %s
                GROUP BY r.id
                ORDER BY r.created_at DESC
                """,
                (str(dataset_id),),
            )
            return cur.fetchall()
