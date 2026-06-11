"""FastAPI router cho AutoData + Eval pipeline."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from agentic_rag.autodata_eval.config_snapshot import snapshot_pipeline_config
from agentic_rag.autodata_eval.db import get_conn
from agentic_rag.autodata_eval.models import (
    ApproveRequest,
    Dataset,
    DatasetCreate,
    EvalResult,
    EvalRun,
    GenerateBulkRequest,
    GenerateJob,
    GenerateRequest,
    Question,
    QuestionCreate,
    QuestionUpdate,
    QuestionWithStatus,
    RunCreate,
    RunProgress,
    RunSummary,
)
from agentic_rag.autodata_eval.worker import run_eval_worker, run_ragas_worker
from agentic_rag.core.contracts import Chunk
from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider

logger = logging.getLogger(__name__)
router = APIRouter(tags=["autodata-eval"])


# ── Datasets ──────────────────────────────────────────────────────────────────


@router.get("/datasets", response_model=list[Dataset])
def list_datasets() -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM eval_datasets ORDER BY created_at DESC")
        return cur.fetchall()


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: UUID) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM eval_results
                WHERE run_id IN (
                    SELECT id FROM eval_runs WHERE dataset_id = %s
                )
                """,
                (str(dataset_id),),
            )
            cur.execute("DELETE FROM eval_runs WHERE dataset_id = %s", (str(dataset_id),))
            # Detach trước khi xóa: cột legacy dataset_id trên eval_questions /
            # eval_questions_approved có FK ON DELETE CASCADE — không detach thì
            # xóa dataset sẽ hard-delete câu hỏi trong kho (mất dữ liệu).
            cur.execute(
                "UPDATE eval_questions SET dataset_id = NULL WHERE dataset_id = %s",
                (str(dataset_id),),
            )
            cur.execute(
                "UPDATE eval_questions_approved SET dataset_id = NULL WHERE dataset_id = %s",
                (str(dataset_id),),
            )
            cur.execute(
                "DELETE FROM eval_dataset_questions WHERE dataset_id = %s", (str(dataset_id),)
            )
            cur.execute("DELETE FROM eval_datasets WHERE id = %s", (str(dataset_id),))
        conn.commit()
    return {"ok": True}


@router.post("/datasets", response_model=Dataset)
def create_dataset(body: DatasetCreate) -> dict[str, Any]:
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
    if row is None:
        raise HTTPException(status_code=500, detail="Dataset was not created")
    return row


# ── Questions ─────────────────────────────────────────────────────────────────


@router.get("/questions", response_model=list[QuestionWithStatus])
def list_all_questions(include_deleted: bool = False) -> list[dict[str, Any]]:
    """Lấy tất cả câu hỏi từ mọi dataset (dùng cho Review page)."""
    with get_conn() as conn, conn.cursor() as cur:
        deleted_filter = "" if include_deleted else "WHERE q.deleted_at IS NULL"
        cur.execute(
            f"""
                WITH global_order AS (
                  SELECT id,
                    ROW_NUMBER() OVER (ORDER BY created_at DESC) AS global_seq
                  FROM eval_questions
                  WHERE deleted_at IS NULL
                )
                SELECT q.*,
                  COALESCE(go.global_seq, 0) AS global_seq,
                  a.id IS NOT NULL   AS is_approved,
                  a.reviewed_by,
                  a.reviewed_at,
                  EXISTS(
                    SELECT 1 FROM eval_results er WHERE er.question_id = q.id
                  ) AS has_results
                FROM eval_questions q
                LEFT JOIN global_order go ON go.id = q.id
                LEFT JOIN eval_questions_approved a ON a.question_id = q.id
                {deleted_filter}
                ORDER BY q.created_at DESC
                """
        )
        return cur.fetchall()


@router.get("/datasets/{dataset_id}/questions", response_model=list[QuestionWithStatus])
def list_questions(dataset_id: UUID, include_deleted: bool = False) -> list[dict[str, Any]]:
    """Lấy câu hỏi thuộc dataset (qua junction table eval_dataset_questions)."""
    with get_conn() as conn, conn.cursor() as cur:
        deleted_filter = "" if include_deleted else "AND q.deleted_at IS NULL"
        cur.execute(
            f"""
                WITH global_order AS (
                  SELECT id,
                    ROW_NUMBER() OVER (ORDER BY created_at DESC) AS global_seq
                  FROM eval_questions
                  WHERE deleted_at IS NULL
                )
                SELECT q.*,
                  COALESCE(go.global_seq, 0) AS global_seq,
                  a.id IS NOT NULL   AS is_approved,
                  a.reviewed_by,
                  a.reviewed_at,
                  EXISTS(
                    SELECT 1 FROM eval_results er
                    WHERE er.question_id = q.id AND er.run_id IN (
                      SELECT id FROM eval_runs WHERE dataset_id = %s
                    )
                  ) AS has_results
                FROM eval_dataset_questions dq
                JOIN eval_questions q ON q.id = dq.question_id
                LEFT JOIN global_order go ON go.id = q.id
                LEFT JOIN eval_questions_approved a ON a.question_id = q.id
                WHERE dq.dataset_id = %s {deleted_filter}
                ORDER BY q.created_at DESC
                """,
            (str(dataset_id), str(dataset_id)),
        )
        return cur.fetchall()


@router.patch("/questions/{question_id}", response_model=Question)
def update_question(question_id: UUID, body: QuestionUpdate) -> dict[str, Any]:
    """Cập nhật câu hỏi và/hoặc đáp án chuẩn."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Không có trường nào để cập nhật")
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE eval_questions SET {set_clause} WHERE id = %s RETURNING *",
                (*updates.values(), str(question_id)),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
    return row


def _parse_chunk_ids(raw: Any) -> list[str]:
    if not raw:
        return []
    return [c.strip() for c in str(raw).split(",") if c.strip()]


def _doc_id_from_chunks(chunk_ids: list[str]) -> str:
    if not chunk_ids:
        return "unknown"
    parts = chunk_ids[0].split("_")
    return f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else chunk_ids[0]


def _parse_excel_row(row: tuple[Any, ...], col: dict[str, int]) -> dict[str, Any] | None:
    """Return a question dict (với approved=True/False), hoặc None nếu thiếu dữ liệu."""
    q_text = row[col["question"]] if "question" in col else None
    gt = row[col["expected_answer"]] if "expected_answer" in col else None
    if not q_text or not gt:
        return None
    status = (
        str(row[col["review_status"]]).strip()
        if "review_status" in col and row[col["review_status"]]
        else ""
    )
    chunk_ids = _parse_chunk_ids(
        row[col["ground_truth_chunk_ids"]] if "ground_truth_chunk_ids" in col else None
    )
    section = row[col["section_name"]] if "section_name" in col else None
    return {
        "question": str(q_text).strip(),
        "ground_truth": str(gt).strip(),
        "section": str(section) if section else None,
        "chunk_ids": chunk_ids,
        "doc_id": _doc_id_from_chunks(chunk_ids),
        "approved": status == "approved",
    }


def _load_excel_rows(
    col: dict[str, int], rows: list[tuple[Any, ...]], existing: set[tuple[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Trả về (draft_rows, approved_rows) chưa có trong DB."""
    seen: set[tuple[str, str]] = set()
    drafts, approveds = [], []
    for row in rows:
        parsed = _parse_excel_row(row, col)
        if parsed is None:
            continue
        key = (parsed["question"], parsed["ground_truth"])
        if key in existing or key in seen:
            continue
        seen.add(key)
        if parsed["approved"]:
            approveds.append(parsed)
        else:
            drafts.append(parsed)
    return drafts, approveds


@router.post("/datasets/{dataset_id}/import-excel")
def import_pending_from_excel(dataset_id: UUID) -> dict[str, Any]:
    """Import câu hỏi từ result.xlsx: pending/None → Draft, approved → insert + approve ngay."""
    from pathlib import Path

    import openpyxl

    excel_path = Path("guide/reports/result.xlsx")
    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="guide/reports/result.xlsx not found")

    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    col = {h: i for i, h in enumerate(all_rows[1]) if h is not None}

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT question, ground_truth FROM eval_questions WHERE dataset_id = %s",
            (str(dataset_id),),
        )
        existing = {(r["question"].strip(), r["ground_truth"].strip()) for r in cur.fetchall()}

    drafts, approveds = _load_excel_rows(col, all_rows[2:], existing)

    if not drafts and not approveds:
        return {"imported_draft": 0, "imported_approved": 0, "skipped_existing": len(existing)}

    def _link_to_dataset(cur: Any, question_id: str) -> None:
        # list_questions của dataset đọc qua junction — không link thì câu import
        # chỉ thấy ở Review toàn cục, không thấy trong dataset.
        cur.execute(
            """
            INSERT INTO eval_dataset_questions (dataset_id, question_id)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
            """,
            (str(dataset_id), question_id),
        )

    with get_conn() as conn:
        with conn.cursor() as cur:
            for q in drafts:
                cur.execute(
                    """
                    INSERT INTO eval_questions
                      (dataset_id, document_id, section, question, ground_truth, source_chunk_ids)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        str(dataset_id),
                        q["doc_id"],
                        q["section"],
                        q["question"],
                        q["ground_truth"],
                        q["chunk_ids"],
                    ),
                )
                row = cur.fetchone()
                if row:
                    _link_to_dataset(cur, str(row["id"]))
            for q in approveds:
                cur.execute(
                    """
                    INSERT INTO eval_questions
                      (dataset_id, document_id, section, question, ground_truth, source_chunk_ids)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        str(dataset_id),
                        q["doc_id"],
                        q["section"],
                        q["question"],
                        q["ground_truth"],
                        q["chunk_ids"],
                    ),
                )
                row = cur.fetchone()
                if row:
                    _link_to_dataset(cur, str(row["id"]))
                    cur.execute(
                        """
                        INSERT INTO eval_questions_approved (question_id, reviewed_by)
                        VALUES (%s, 'excel-import')
                        ON CONFLICT (question_id) DO NOTHING
                        """,
                        (str(row["id"]),),
                    )
        conn.commit()

    return {
        "imported_draft": len(drafts),
        "imported_approved": len(approveds),
        "skipped_existing": len(existing),
    }


@router.post("/questions/batch", response_model=list[Question])
def create_questions_batch(questions: list[QuestionCreate]) -> list[dict[str, Any]]:
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
                        str(q.dataset_id) if q.dataset_id else None,
                        q.document_id,
                        q.section,
                        q.question,
                        q.ground_truth,
                        q.source_chunk_ids,
                    ),
                )
                row = cur.fetchone()
                if row is not None:
                    rows.append(row)
        conn.commit()
    return rows


@router.post("/questions/approve")
def approve_questions(body: ApproveRequest) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            for qid in body.question_ids:
                cur.execute(
                    """
                    INSERT INTO eval_questions_approved (question_id, reviewed_by)
                    VALUES (%s, %s)
                    ON CONFLICT (question_id) DO UPDATE SET
                      reviewed_by = EXCLUDED.reviewed_by,
                      reviewed_at = NOW()
                    """,
                    (str(qid), body.reviewed_by),
                )
        conn.commit()
    return {"approved": len(body.question_ids)}


@router.delete("/questions")
def delete_questions(question_ids: list[UUID]) -> dict[str, Any]:
    """Hard delete — CHỈ xóa câu chưa có kết quả eval (dọn rác).

    Câu đã chạy eval bị bỏ qua để giữ lịch sử run (kết quả/biểu đồ so sánh) —
    muốn ẩn loại câu đó thì dùng archive. Junction + approved tự cascade khi xóa.
    """
    ids = [str(q) for q in question_ids]
    if not ids:
        return {"deleted": 0, "skipped": []}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT question_id FROM eval_results WHERE question_id = ANY(%s)",
                (ids,),
            )
            has_results = {str(r["question_id"]) for r in cur.fetchall()}
            deletable = [i for i in ids if i not in has_results]
            if deletable:
                cur.execute("DELETE FROM eval_questions WHERE id = ANY(%s)", (deletable,))
        conn.commit()
    return {"deleted": len(deletable), "skipped": sorted(has_results)}


@router.post("/questions/archive")
def archive_questions(question_ids: list[UUID]) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_questions SET deleted_at = NOW() WHERE id = ANY(%s)",
                ([str(q) for q in question_ids],),
            )
        conn.commit()
    return {"archived": len(question_ids)}


@router.post("/questions/restore")
def restore_questions(question_ids: list[UUID]) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_questions SET deleted_at = NULL WHERE id = ANY(%s)",
                ([str(q) for q in question_ids],),
            )
        conn.commit()
    return {"restored": len(question_ids)}


@router.post("/datasets/{dataset_id}/questions/add")
def add_questions_to_dataset(dataset_id: UUID, question_ids: list[UUID]) -> dict[str, Any]:
    """Thêm câu hỏi đã approved vào dataset (eval subset)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            added = 0
            for qid in question_ids:
                cur.execute(
                    """
                    INSERT INTO eval_dataset_questions (dataset_id, question_id)
                    SELECT %s, %s
                    WHERE EXISTS (
                      SELECT 1 FROM eval_questions_approved WHERE question_id = %s
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    (str(dataset_id), str(qid), str(qid)),
                )
                added += cur.rowcount
        conn.commit()
    return {"added": added}


@router.delete("/datasets/{dataset_id}/questions/remove")
def remove_questions_from_dataset(dataset_id: UUID, question_ids: list[UUID]) -> dict[str, Any]:
    """Xóa câu hỏi khỏi dataset (không xóa câu hỏi khỏi pool)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM eval_dataset_questions
                WHERE dataset_id = %s AND question_id = ANY(%s)
                """,
                (str(dataset_id), [str(q) for q in question_ids]),
            )
            removed = cur.rowcount
        conn.commit()
    return {"removed": removed}


@router.get("/datasets/{dataset_id}/doc-question-counts")
def doc_question_counts(dataset_id: UUID) -> dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
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


@router.get("/doc-question-counts")
def doc_question_counts_all() -> dict[str, Any]:
    """Đếm câu hỏi theo document_id trên TOÀN BỘ datasets (bảng lớn), kèm breakdown
    review: total / approved — FE tự suy ra pending = total - approved."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT q.document_id,
                       COUNT(*) AS total,
                       COUNT(a.id) AS approved
                FROM eval_questions q
                LEFT JOIN eval_questions_approved a ON a.question_id = q.id
                WHERE q.deleted_at IS NULL
                GROUP BY q.document_id
                """
        )
        return {
            r["document_id"]: {"total": r["total"], "approved": r["approved"]}
            for r in cur.fetchall()
        }


@router.get("/chunks/{chunk_id}")
def get_chunk_content(chunk_id: str) -> dict[str, Any]:
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


def _section_question_counts(document_id: str) -> dict[str, int]:
    """Đếm số câu đã sinh theo section của 1 document — TOÀN BỘ dataset (global).

    Gồm cả câu đã review lẫn chưa review (chỉ bỏ câu đã xóa). "Đã sinh / chưa
    sinh" tính trên toàn thể, không chia riêng từng dataset — khớp với cách
    document-level dùng /doc-question-counts (global).
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT section, COUNT(*) AS cnt
                FROM eval_questions
                WHERE document_id = %s AND deleted_at IS NULL
                GROUP BY section
                """,
            (document_id,),
        )
        return {r["section"]: r["cnt"] for r in cur.fetchall() if r["section"]}


@router.get("/autodata/sections")
def list_sections_global(document_id: str) -> list[dict[str, Any]]:
    """Sections của 1 document — sinh câu là bước toàn cục, không gắn dataset."""
    return _sections_for_document(document_id)


@router.get("/datasets/{dataset_id}/sections")
def list_sections(dataset_id: str, document_id: str) -> list[dict[str, Any]]:
    """(Giữ tương thích cũ) dataset_id không tham gia logic — dùng /autodata/sections."""
    return _sections_for_document(document_id)


def _sections_for_document(document_id: str) -> list[dict[str, Any]]:
    """Danh sách section + số chunk + số câu đã sinh (global) của 1 document."""
    try:
        from agentic_rag.generation.evidence import source_provider_from_env
        from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider

        provider = source_provider_from_env()
        if not isinstance(provider, LocalPdfEvidenceProvider):
            return []
        doc_chunks = provider.document_chunks(document_id=document_id)
        sections: dict[str, int] = {}
        for chunk in doc_chunks.chunks:
            # Fallback PHẢI khớp _section_chunks_for_document ("General") — lệch tên
            # thì filter/đếm question_count theo section sẽ không bao giờ match.
            section = str(chunk.metadata.get("section") or chunk.metadata.get("title") or "General")
            sections[section] = sections.get(section, 0) + 1
        q_counts = _section_question_counts(document_id)
        return [
            {"section": s, "chunk_count": c, "question_count": q_counts.get(s, 0)}
            for s, c in sorted(sections.items())
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── AutoData Generate ─────────────────────────────────────────────────────────

# Prompt mặc định cho LLM sinh Q&A. Placeholder thay bằng .replace() (không dùng
# .format() — template do user nhập có thể chứa { } lạc gây KeyError).
_DEFAULT_GENERATE_PROMPT = """\
Dựa vào đoạn văn bản sau, hãy tạo ra {n} câu hỏi và câu trả lời ngắn gọn.
Section: {section}

Văn bản:
{context}

Trả về JSON array với format:
[{"question": "...", "answer": "..."}]
Chỉ trả về JSON, không thêm gì khác."""


def _render_prompt(template: str, *, n: int, section: str, context: str) -> str:
    rendered = (
        template.replace("{n}", str(n)).replace("{section}", section).replace("{context}", context)
    )
    # User quên {context} thì vẫn phải đưa văn bản cho LLM — nối vào cuối.
    if "{context}" not in template:
        rendered += f"\n\nVăn bản:\n{context}"
    return rendered


@router.get("/autodata/prompt-template")
def get_prompt_template() -> dict[str, Any]:
    """Trả prompt mặc định để FE hiển thị cho user chỉnh trực tiếp trên UI."""
    return {"template": _DEFAULT_GENERATE_PROMPT}


# Job lưu trong RAM. value: {status, total_sections, done_sections, questions_created}.
# Lưu ý: job mất khi restart server — nhưng câu đã sinh được commit ngay vào DB,
# nên chạy lại với only_missing=True sẽ tự bỏ qua section đã xong (resumable).
_generate_jobs: dict[str, dict[str, Any]] = {}

_JOB_MESSAGES = {
    "running": "Đang sinh câu hỏi...",
    "done": "Hoàn thành",
    "failed": "Thất bại",
    "not_found": "Không tìm thấy job",
}


def _new_job() -> tuple[str, dict[str, Any]]:
    job_id = str(uuid.uuid4())
    job = {"status": "running", "total_sections": 0, "done_sections": 0, "questions_created": 0}
    _generate_jobs[job_id] = job
    return job_id, job


@router.post("/autodata/generate", response_model=GenerateJob)
def generate_questions(body: GenerateRequest, background: BackgroundTasks) -> dict[str, Any]:
    job_id, _ = _new_job()
    background.add_task(_run_generate, job_id, body)
    return {"job_id": job_id, "status": "running", "message": _JOB_MESSAGES["running"]}


@router.post("/autodata/generate-bulk", response_model=GenerateJob)
def generate_bulk(body: GenerateBulkRequest, background: BackgroundTasks) -> dict[str, Any]:
    job_id, _ = _new_job()
    background.add_task(_run_generate_bulk, job_id, body)
    return {"job_id": job_id, "status": "running", "message": _JOB_MESSAGES["running"]}


@router.get("/autodata/jobs/{job_id}", response_model=GenerateJob)
def get_generate_job(job_id: str) -> dict[str, Any]:
    job = _generate_jobs.get(job_id)
    status = job["status"] if job else "not_found"
    return {
        "job_id": job_id,
        "status": status,
        "message": _JOB_MESSAGES.get(status, ""),
        "total_sections": job["total_sections"] if job else 0,
        "done_sections": job["done_sections"] if job else 0,
        "questions_created": job["questions_created"] if job else 0,
    }


def _persist_questions(questions: list[QuestionCreate]) -> int:
    """Điểm ghi câu hỏi duy nhất (dùng chung cho single + bulk). Trả về số câu ghi."""
    if not questions:
        return 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for q in questions:
                cur.execute(
                    """
                    INSERT INTO eval_questions
                      (dataset_id, document_id, section, question, ground_truth, source_chunk_ids)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(q.dataset_id) if q.dataset_id else None,
                        q.document_id,
                        q.section,
                        q.question,
                        q.ground_truth,
                        q.source_chunk_ids,
                    ),
                )
        conn.commit()
    return len(questions)


def _section_chunks_for_document(
    document_id: str,
    *,
    section_filters: list[str] | None,
    only_missing: bool,
) -> dict[str, list[Chunk]]:
    """Gom chunk theo section, áp dụng filter section + bỏ section đã có câu (only_missing).

    only_missing tính trên TOÀN BỘ dataset (global) — khớp định nghĩa "chưa sinh".
    """
    provider = LocalPdfEvidenceProvider.from_env()
    chunks = provider.document_chunks(document_id=document_id).chunks

    section_chunks: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        section = chunk.metadata.get("section") or chunk.metadata.get("title") or "General"
        if section_filters and section not in section_filters:
            continue
        section_chunks.setdefault(section, []).append(chunk)

    if only_missing:
        existing = _section_question_counts(document_id)
        section_chunks = {s: c for s, c in section_chunks.items() if existing.get(s, 0) == 0}

    return section_chunks


def _generate_for_document(
    document_id: str,
    *,
    dataset_id: UUID | None,
    section_chunks: dict[str, list[Chunk]],
    questions_per_section: int,
    job: dict[str, Any],
    custom_prompt: str | None = None,
) -> None:
    """Sinh câu cho từng section của 1 document, cập nhật tiến độ vào job."""
    for section, sec_chunks in section_chunks.items():
        context = "\n\n".join(c.text for c in sec_chunks[:10])
        generated = _call_llm_generate(context, questions_per_section, section, custom_prompt)
        questions = [
            QuestionCreate(
                dataset_id=dataset_id,
                document_id=document_id,
                section=section,
                question=item["question"],
                ground_truth=item["answer"],
                source_chunk_ids=[c.chunk_id for c in sec_chunks[:5]],
            )
            for item in generated
        ]
        job["questions_created"] += _persist_questions(questions)
        job["done_sections"] += 1


def _run_generate(job_id: str, body: GenerateRequest) -> None:
    job = _generate_jobs[job_id]
    try:
        section_chunks = _section_chunks_for_document(
            body.document_id,
            section_filters=body.section_filters,
            only_missing=False,
        )
        job["total_sections"] = len(section_chunks)
        _generate_for_document(
            body.document_id,
            dataset_id=body.dataset_id,
            section_chunks=section_chunks,
            questions_per_section=body.questions_per_section,
            job=job,
            custom_prompt=body.custom_prompt,
        )
        job["status"] = "done"
    except Exception as exc:
        logger.error("Generate job %s failed: %s", job_id, exc)
        job["status"] = "failed"


def _run_generate_bulk(job_id: str, body: GenerateBulkRequest) -> None:
    job = _generate_jobs[job_id]
    try:
        # Pass 1: gom section cho từng doc + tính tổng để hiển thị tiến độ
        per_doc: list[tuple[str, dict[str, list[Chunk]]]] = []
        for document_id in body.document_ids:
            section_chunks = _section_chunks_for_document(
                document_id,
                section_filters=None,
                only_missing=body.only_missing,
            )
            per_doc.append((document_id, section_chunks))
        job["total_sections"] = sum(len(sc) for _, sc in per_doc)

        # Pass 2: sinh câu
        for document_id, section_chunks in per_doc:
            _generate_for_document(
                document_id,
                dataset_id=body.dataset_id,
                section_chunks=section_chunks,
                questions_per_section=body.questions_per_section,
                job=job,
                custom_prompt=body.custom_prompt,
            )
        job["status"] = "done"
    except Exception as exc:
        logger.error("Bulk generate job %s failed: %s", job_id, exc)
        job["status"] = "failed"


def _call_llm_generate(
    context: str, n: int, section: str, custom_prompt: str | None = None
) -> list[dict[str, str]]:
    import os

    import litellm

    template = (custom_prompt or "").strip() or _DEFAULT_GENERATE_PROMPT
    prompt = _render_prompt(template, n=n, section=section, context=context[:3000])

    # OpenAI bắt buộc prompt chứa chữ "JSON" khi dùng response_format json_object —
    # prompt user tự sửa có thể thiếu, lúc đó bỏ response_format thay vì để 400.
    kwargs: dict[str, Any] = {}
    if "json" in prompt.lower():
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = litellm.completion(
            model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            **kwargs,
        )
    except Exception:
        # Lỗi 1 section (prompt sai, rate limit...) không được giết cả job
        logger.exception("LLM generate failed for section %s", section)
        return []
    raw = response.choices[0].message.content or "[]"
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = parsed.get(
                "questions",
                parsed.get("items", next(iter(parsed.values())) if parsed else []),
            )
        return [q for q in parsed if isinstance(q, dict) and "question" in q and "answer" in q][:n]
    except Exception:
        return []


# ── Eval Runs ─────────────────────────────────────────────────────────────────
_RUN_NOT_FOUND = "Run không tồn tại"


@router.get("/runs", response_model=list[EvalRun])
def list_runs(dataset_id: UUID | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        if dataset_id:
            cur.execute(
                "SELECT * FROM eval_runs WHERE dataset_id = %s ORDER BY created_at DESC",
                (str(dataset_id),),
            )
        else:
            cur.execute("SELECT * FROM eval_runs ORDER BY created_at DESC")
        return cur.fetchall()


@router.post("/runs", response_model=EvalRun)
def create_run(body: RunCreate, background: BackgroundTasks) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Đóng băng danh sách câu tại thời điểm tạo run.
            # Worker sẽ chỉ xử lý đúng các câu này — câu mới approve sau khi run
            # bắt đầu sẽ không bị kéo vào, tránh vòng lặp vô hạn và over-count.
            if body.question_ids:
                # Lọc id client gửi: chỉ giữ câu tồn tại + đã duyệt + chưa xóa.
                # Id rác lọt vào frozen list sẽ làm run 'done' nhưng success < total.
                cur.execute(
                    """
                    SELECT q.id
                    FROM eval_questions q
                    JOIN eval_questions_approved a ON a.question_id = q.id
                    WHERE q.id = ANY(%s) AND q.deleted_at IS NULL
                    """,
                    ([str(qid) for qid in body.question_ids],),
                )
                question_ids = [str(r["id"]) for r in cur.fetchall()]
            else:
                cur.execute(
                    """
                    SELECT q.id
                    FROM eval_dataset_questions dq
                    JOIN eval_questions q ON q.id = dq.question_id
                    JOIN eval_questions_approved a ON a.question_id = q.id
                    WHERE dq.dataset_id = %s AND q.deleted_at IS NULL
                    ORDER BY q.created_at
                    """,
                    (str(body.dataset_id),),
                )
                question_ids = [str(r["id"]) for r in cur.fetchall()]

            total = len(question_ids)
            config = {**snapshot_pipeline_config(), **(body.config or {})}

            cur.execute(
                """
                INSERT INTO eval_runs
                  (dataset_id, name, description, config, status, total, frozen_question_ids)
                VALUES (%s, %s, %s, %s, 'queued', %s, %s)
                RETURNING *
                """,
                (
                    str(body.dataset_id),
                    body.name,
                    body.description,
                    json.dumps(config),
                    total,
                    question_ids,
                ),
            )
            run = cur.fetchone()
        conn.commit()

    if run is None:
        raise HTTPException(status_code=500, detail="Run was not created")
    background.add_task(run_eval_worker, str(run["id"]))
    return run


@router.get("/runs/{run_id}/progress", response_model=RunProgress)
def get_run_progress(run_id: UUID) -> dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT r.status, r.total, r.success, r.failed,
                  (r.total - r.success - r.failed) AS not_started,
                  (SELECT COUNT(*) FROM eval_results er
                   WHERE er.run_id = r.id AND er.ragas_faithfulness IS NOT NULL) AS ragas_done
                FROM eval_runs r WHERE r.id = %s
                """,
            (str(run_id),),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND)
    return {"run_id": run_id, **row}


@router.post("/runs/{run_id}/pause")
def pause_run(run_id: UUID) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_runs SET status = 'paused' WHERE id = %s AND status = 'running'",
                (str(run_id),),
            )
        conn.commit()
    return {"status": "paused"}


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: UUID, background: BackgroundTasks) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_runs SET status = 'running' WHERE id = %s AND status = 'paused'",
                (str(run_id),),
            )
        conn.commit()
    background.add_task(run_eval_worker, str(run_id))
    return {"status": "running"}


@router.patch("/runs/{run_id}")
def rename_run(run_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tên không được để trống")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE eval_runs SET name = %s WHERE id = %s RETURNING id, name",
                (name, str(run_id)),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND)
    return row


@router.delete("/runs/{run_id}")
def delete_run(run_id: UUID) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            # eval_results có ON DELETE CASCADE nên tự xóa theo
            cur.execute("DELETE FROM eval_runs WHERE id = %s RETURNING id", (str(run_id),))
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND)
    return {"deleted": str(run_id)}


@router.post("/runs/{run_id}/ragas")
def run_ragas(
    run_id: UUID,
    background: BackgroundTasks,
    question_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    ids = [str(q) for q in question_ids] if question_ids else None
    background.add_task(run_ragas_worker, str(run_id), ids)
    return {"status": "started", "message": "RAGAS đang chạy ngầm..."}


# ── Results ───────────────────────────────────────────────────────────────────


@router.get("/runs/{run_id}/metrics")
def run_metrics(run_id: UUID) -> dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
              SELECT
                  COUNT(*)                                               AS total,
                  AVG(recall_at_5)                                       AS recall,
                  AVG(mrr_at_5)                                          AS mrr,
                  AVG(citation_chunk_match)                              AS citation,
                  AVG(CASE WHEN guardrail_pass THEN 1.0 ELSE 0.0 END)   AS guardrail,
                  AVG(ragas_faithfulness)                                AS faithfulness,
                  AVG(ragas_answer_relevancy)                            AS relevancy,
                  AVG(ragas_context_precision)                           AS ctx_precision,
                  AVG(ragas_context_recall)                              AS ctx_recall
                FROM eval_results WHERE run_id = %s
            """,
            (str(run_id),),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND)
        return row


@router.get("/runs/{run_id}/results", response_model=list[EvalResult])
def list_results(run_id: UUID, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM eval_results WHERE run_id = %s ORDER BY ran_at LIMIT %s OFFSET %s",
            (str(run_id), limit, offset),
        )
        return cur.fetchall()


class ResultImport(BaseModel):
    question_id: UUID
    run_id: UUID
    rag_context: str | None = None
    bot_response: str | None = None
    bot_citations: str | None = None
    trace_url: str | None = None
    retrieved_top5_ids: str | None = None
    ground_truth_rank: int | None = None
    recall_at_5: float | None = None
    mrr_at_5: float | None = None
    citation_chunk_match: float | None = None
    guardrail_pass: bool | None = None
    ragas_faithfulness: float | None = None
    ragas_answer_relevancy: float | None = None
    ragas_context_precision: float | None = None
    ragas_context_recall: float | None = None


@router.post("/runs/{run_id}/results/import")
def import_single_result(run_id: UUID, body: ResultImport) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO eval_results (
                    question_id, run_id, rag_context, bot_response, bot_citations,
                    trace_url, retrieved_top5_ids, ground_truth_rank,
                    recall_at_5, mrr_at_5, citation_chunk_match, guardrail_pass,
                    ragas_faithfulness, ragas_answer_relevancy,
                    ragas_context_precision, ragas_context_recall
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (
                    str(body.question_id),
                    str(run_id),
                    body.rag_context,
                    body.bot_response,
                    body.bot_citations,
                    body.trace_url,
                    body.retrieved_top5_ids,
                    body.ground_truth_rank,
                    body.recall_at_5,
                    body.mrr_at_5,
                    body.citation_chunk_match,
                    body.guardrail_pass,
                    body.ragas_faithfulness,
                    body.ragas_answer_relevancy,
                    body.ragas_context_precision,
                    body.ragas_context_recall,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return {"inserted": row is not None, "id": str(row["id"]) if row else None}


# ── Compare ───────────────────────────────────────────────────────────────────


@router.get("/compare", response_model=list[RunSummary])
def compare_runs(dataset_id: UUID) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
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


# ── Startup recovery ──────────────────────────────────────────────────────────


def recover_stuck_runs() -> None:
    """Khởi động lại worker cho các run đang 'running' khi server restart.
    Chỉ restart 'running' — 'paused' là dừng có chủ ý, không auto-resume.
    """
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM eval_runs WHERE status = 'running'")
            rows = cur.fetchall()

        for row in rows:
            run_id = str(row["id"])
            logger.info("Recovering stuck run %s on startup", run_id)
            t = threading.Thread(
                target=run_eval_worker,
                args=(run_id,),
                daemon=True,
            )
            t.start()

        if rows:
            logger.info("Recovered %d stuck run(s)", len(rows))
    except Exception:
        logger.exception("Failed to recover stuck runs on startup")
