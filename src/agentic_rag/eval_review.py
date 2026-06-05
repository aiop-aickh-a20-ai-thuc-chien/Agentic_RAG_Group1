"""Eval Review router — mounted into the main FastAPI app under /eval-review."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Literal

import queue as _queue_module

import openpyxl
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

EXCEL_PATH = Path(
    os.environ.get(
        "EVAL_EXCEL_PATH",
        str(_PROJECT_ROOT / "guide" / "reports" / "result.xlsx"),
    )
)
REJECT_PATH = EXCEL_PATH.parent / "reject.xlsx"
SHEET_NAME = "Evaluation"
HEADER_ROW = 2
DATA_START_ROW = 3

# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(tags=["eval-review"])

_file_lock = threading.Lock()

# ── Per-row eval queue ────────────────────────────────────────────────────────
# Queue holds excel_row integers; single worker processes them serially.
_eval_queue: _queue_module.Queue[tuple[int, bool]] = _queue_module.Queue()  # (excel_row, force)
_row_status: dict[int, dict[str, Any]] = {}  # excel_row → {status, message, queue_pos}
_worker_lock = threading.Lock()
_worker_thread: threading.Thread | None = None

_job: dict[str, Any] = {
    "status": "idle",
    "progress": 0,
    "total": 0,
    "errors": [],
    "message": "",
}

# ── Models ────────────────────────────────────────────────────────────────────


class RowUpdate(BaseModel):
    question: str | None = None
    expected_answer: str | None = None
    ground_truth_chunk_ids: str | None = None
    is_out_of_scope: bool | None = None


class RunConfig(BaseModel):
    run_ragas: bool = True


class JobStatus(BaseModel):
    status: Literal["idle", "running", "done", "error"]
    progress: int
    total: int
    errors: list[str]
    message: str


# ── Excel helpers ─────────────────────────────────────────────────────────────


def _load_wb() -> openpyxl.Workbook:
    if not EXCEL_PATH.exists():
        raise HTTPException(status_code=404, detail=f"Excel not found: {EXCEL_PATH}")
    return openpyxl.load_workbook(EXCEL_PATH)


def _read_header(ws: Any) -> dict[str, int]:
    return {
        cell.value: idx
        for idx, cell in enumerate(ws[HEADER_ROW], start=1)
        if cell.value
    }


def _ensure_review_status_col(ws: Any, header: dict[str, int]) -> bool:
    """Return True if column was added (caller should save)."""
    if "review_status" in header:
        return False
    next_col = max(header.values()) + 1
    ws.cell(row=HEADER_ROW, column=next_col).value = "review_status"
    header["review_status"] = next_col
    q_col = header.get("question", 1)
    for row_idx in range(DATA_START_ROW, ws.max_row + 1):
        if ws.cell(row=row_idx, column=q_col).value:
            ws.cell(row=row_idx, column=next_col).value = "pending"
    return True


def _row_to_dict(ws: Any, excel_row: int, header: dict[str, int]) -> dict[str, Any]:
    row: dict[str, Any] = {"excel_row": excel_row}
    for col_name, col_idx in header.items():
        row[col_name] = ws.cell(row=excel_row, column=col_idx).value

    review_status = row.get("review_status") or "pending"
    bot_response = row.get("bot_response")
    if review_status == "approved" and bot_response:
        row["display_status"] = "evaluated"
    else:
        row["display_status"] = review_status

    return row


def _read_all_rows() -> list[dict[str, Any]]:
    with _file_lock:
        wb = _load_wb()
        ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
        header = _read_header(ws)

        col_added = _ensure_review_status_col(ws, header)
        if col_added:
            wb.save(EXCEL_PATH)

        q_col = header.get("question", 1)
        rows = []
        for excel_row in range(DATA_START_ROW, ws.max_row + 1):
            if ws.cell(row=excel_row, column=q_col).value:
                rows.append(_row_to_dict(ws, excel_row, header))

        wb.close()
        return rows


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/api/rows")
def get_rows() -> list[dict]:
    return _read_all_rows()


@router.patch("/api/rows/{excel_row}")
def update_row(excel_row: int, update: RowUpdate) -> dict:
    with _file_lock:
        wb = _load_wb()
        ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
        header = _read_header(ws)

        q_col = header.get("question", 1)
        if not ws.cell(row=excel_row, column=q_col).value:
            raise HTTPException(status_code=404, detail="Row not found")

        for field, value in update.model_dump(exclude_none=True).items():
            if field in header:
                ws.cell(row=excel_row, column=header[field]).value = value

        wb.save(EXCEL_PATH)
        result = _row_to_dict(ws, excel_row, header)
        wb.close()
        return result


@router.post("/api/rows/{excel_row}/approve")
def approve_row(excel_row: int) -> dict:
    with _file_lock:
        wb = _load_wb()
        ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
        header = _read_header(ws)
        _ensure_review_status_col(ws, header)

        ws.cell(row=excel_row, column=header["review_status"]).value = "approved"
        wb.save(EXCEL_PATH)
        result = _row_to_dict(ws, excel_row, header)
        wb.close()
        return result


@router.post("/api/rows/{excel_row}/approve-and-eval")
def approve_and_eval_row(excel_row: int) -> dict:
    """Approve a row and enqueue it for pipeline evaluation. Returns immediately."""
    with _file_lock:
        wb = _load_wb()
        ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
        header = _read_header(ws)
        _ensure_review_status_col(ws, header)

        q_col = header.get("question", 1)
        if not ws.cell(row=excel_row, column=q_col).value:
            raise HTTPException(status_code=404, detail="Row not found")

        ws.cell(row=excel_row, column=header["review_status"]).value = "approved"
        wb.save(EXCEL_PATH)
        row_dict = _row_to_dict(ws, excel_row, header)
        wb.close()

    # Enqueue (idempotent: skip if already queued/running)
    if _row_status.get(excel_row, {}).get("status") not in {"queued", "running"}:
        queue_pos = _eval_queue.qsize() + 1
        _row_status[excel_row] = {
            "status": "queued",
            "message": f"Đang chờ — vị trí #{queue_pos} trong hàng đợi",
        }
        _eval_queue.put((excel_row, False))
        _ensure_eval_worker()

    return {**row_dict, "_eval_status": _row_status[excel_row]}


@router.post("/api/rows/{excel_row}/re-eval")
def re_eval_row(excel_row: int) -> dict:
    """Re-evaluate an already-evaluated row (force=True bypasses the skip check)."""
    with _file_lock:
        wb = _load_wb()
        ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
        header = _read_header(ws)
        q_col = header.get("question", 1)
        if not ws.cell(row=excel_row, column=q_col).value:
            raise HTTPException(status_code=404, detail="Row not found")
        row_dict = _row_to_dict(ws, excel_row, header)
        wb.close()

    if _row_status.get(excel_row, {}).get("status") not in {"queued", "running"}:
        queue_pos = _eval_queue.qsize() + 1
        _row_status[excel_row] = {
            "status": "queued",
            "message": f"Đang chờ đánh giá lại — vị trí #{queue_pos}",
        }
        _eval_queue.put((excel_row, True))  # force=True
        _ensure_eval_worker()

    return {**row_dict, "_eval_status": _row_status[excel_row]}


@router.get("/api/rows/{excel_row}/eval-status")
def get_row_eval_status(excel_row: int) -> dict:
    return _row_status.get(excel_row, {"status": "idle", "message": ""})


# ── Queue worker ──────────────────────────────────────────────────────────────


def _ensure_eval_worker() -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(target=_eval_worker_loop, daemon=True)
            _worker_thread.start()


def _eval_worker_loop() -> None:
    while True:
        try:
            excel_row, force = _eval_queue.get(timeout=5)
        except _queue_module.Empty:
            break
        try:
            _row_status[excel_row] = {"status": "running", "message": "Đang chạy pipeline..."}
            _run_single_row_eval(excel_row, force=force)
            _row_status[excel_row] = {"status": "done", "message": "Hoàn thành"}
        except Exception as exc:
            _row_status[excel_row] = {"status": "error", "message": str(exc)}
        finally:
            _eval_queue.task_done()


def _run_single_row_eval(excel_row: int, *, force: bool = False) -> None:
    """Delegate to EvaluationRunner — reuses all existing pipeline + RAGAS logic."""
    from agentic_rag.runtime_env import load_local_env
    load_local_env()

    from agentic_rag.evaluation.runner import EvaluationRunner

    EvaluationRunner(
        input_file=str(EXCEL_PATH),
        output_file=str(EXCEL_PATH),
        run_ragas=True,
        target_row=excel_row,
        force=force,
        on_row_done=lambda: _row_status[excel_row].update({"message": "Đang ghi kết quả..."}),
    ).run()


@router.post("/api/rows/{excel_row}/reject")
def reject_row(excel_row: int) -> dict:
    with _file_lock:
        wb = _load_wb()
        ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
        header = _read_header(ws)

        q_col = header.get("question", 1)
        question = ws.cell(row=excel_row, column=q_col).value
        if not question:
            raise HTTPException(status_code=404, detail="Row not found")

        row_data = {
            col_name: ws.cell(row=excel_row, column=col_idx).value
            for col_name, col_idx in header.items()
        }
        _append_to_reject(row_data, header)

        ws.delete_rows(excel_row)
        wb.save(EXCEL_PATH)
        wb.close()

        return {"ok": True, "deleted_question": str(question)}


def _append_to_reject(row_data: dict, header: dict[str, int]) -> None:
    col_names = [k for k, _ in sorted(header.items(), key=lambda x: x[1])]

    if REJECT_PATH.exists():
        rb = openpyxl.load_workbook(REJECT_PATH)
        rws = rb["Rejected"] if "Rejected" in rb.sheetnames else rb.active
    else:
        rb = openpyxl.Workbook()
        rws = rb.active
        rws.title = "Rejected"
        for col_idx, col_name in enumerate(col_names, start=1):
            rws.cell(row=1, column=col_idx).value = col_name

    next_row = rws.max_row + 1
    for col_idx, col_name in enumerate(col_names, start=1):
        rws.cell(row=next_row, column=col_idx).value = row_data.get(col_name)

    rb.save(REJECT_PATH)
    rb.close()


@router.post("/api/eval/run")
def run_eval(config: RunConfig) -> dict:
    global _job
    if _job["status"] == "running":
        raise HTTPException(status_code=409, detail="Evaluation already running")

    _job = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "errors": [],
        "message": "Starting...",
    }

    thread = threading.Thread(
        target=_run_eval_job, args=(config.run_ragas,), daemon=True
    )
    thread.start()
    return {"message": "Evaluation started"}


def _run_eval_job(run_ragas: bool) -> None:
    global _job
    try:
        from agentic_rag.evaluation.runner import EvaluationRunner

        _job["message"] = "Counting approved rows..."
        rows = _read_all_rows()
        approved = [
            r for r in rows
            if r.get("review_status") == "approved" and not r.get("bot_response")
        ]
        _job["total"] = len(approved)

        if not approved:
            _job["status"] = "done"
            _job["message"] = "No approved rows to evaluate"
            return

        _job["message"] = f"Running on {len(approved)} approved rows..."

        runner = EvaluationRunner(
            input_file=str(EXCEL_PATH),
            output_file=str(EXCEL_PATH),
            run_ragas=run_ragas,
            approved_only=True,
            on_row_done=_increment_progress,
        )
        runner.run()

        _job["status"] = "done"
        _job["message"] = (
            f"Done! {_job['progress']}/{_job['total']} rows evaluated."
        )

    except Exception as exc:
        _job["status"] = "error"
        _job["errors"].append(str(exc))
        _job["message"] = f"Error: {exc}"


def _increment_progress() -> None:
    _job["progress"] += 1


@router.get("/api/eval/status")
def get_eval_status() -> JobStatus:
    return JobStatus(**_job)


@router.get("/api/doc-chunks")
def get_doc_chunks(chunk_id: str) -> dict:
    """Query pgvector cmetadata directly for all chunks from the same document."""
    import os
    import re
    import psycopg

    from agentic_rag.runtime_env import load_local_env
    load_local_env()

    conn_str = os.environ.get("DENSE_PGVECTOR_CONNECTION", "")
    collection_name = os.environ.get("DENSE_PGVECTOR_COLLECTION", "agentic_rag_chunks")

    if not conn_str:
        raise HTTPException(status_code=503, detail="DENSE_PGVECTOR_CONNECTION not set")

    # chunk_id = "url_9dd8e94fee25_section_c001" → doc_prefix = "url_9dd8e94fee25"
    parts = chunk_id.split("_")
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid chunk_id format")
    doc_prefix = f"{parts[0]}_{parts[1]}"

    # Strip SQLAlchemy dialect prefix for psycopg3
    db_url = re.sub(r"\+\w+://", "://", conn_str)  # postgresql+psycopg:// → postgresql://

    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                # DISTINCT ON deduplicates chunks indexed multiple times (e.g. hybrid retrieval)
                cur.execute(
                    """
                    SELECT DISTINCT ON (e.cmetadata->>'chunk_id') e.document, e.cmetadata
                    FROM langchain_pg_embedding e
                    JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                    WHERE c.name = %s
                      AND starts_with(e.cmetadata->>'chunk_id', %s)
                    ORDER BY e.cmetadata->>'chunk_id'
                    """,
                    (collection_name, f"{doc_prefix}_"),
                )
                rows = cur.fetchall()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"pgvector query failed: {exc}")

    if not rows:
        return {"document_id": doc_prefix, "found": False, "chunks": []}

    def _chunk_index(cid: str) -> int:
        m = re.search(r"_c(\d+)$", cid)
        return int(m.group(1)) if m else 0

    def _parse_meta(raw: Any) -> dict:
        if isinstance(raw, str):
            import json as _json
            return _json.loads(raw)
        return raw or {}

    chunks = sorted(
        [
            {
                "chunk_id": _parse_meta(meta).get("chunk_id", ""),
                "text": text,
                "score": 1.0,
                "retriever": "",
                "section": _parse_meta(meta).get("section", ""),
                "url": _parse_meta(meta).get("url", ""),
            }
            for text, meta in rows
        ],
        key=lambda c: _chunk_index(c["chunk_id"]),
    )

    return {"document_id": doc_prefix, "found": True, "chunks": chunks}


@router.get("/api/chunks")
def get_chunks(q: str) -> list[dict]:
    try:
        from agentic_rag.runtime_env import load_local_env
        load_local_env()

        from agentic_rag.generation.evidence import evidence_for_question

        results, _ = evidence_for_question(question=q)
        return [
            {
                "chunk_id": r.chunk.chunk_id,
                "text": r.chunk.text[:800],
                "score": round(float(r.score), 4),
                "retriever": getattr(r, "retriever", ""),
                "section": r.chunk.metadata.get("section", ""),
                "url": r.chunk.metadata.get("url") or "",
            }
            for r in results[:10]
        ]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Retrieval unavailable: {exc}")
