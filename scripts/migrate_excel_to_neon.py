"""Migrate result_final.xlsx → Neon PostgreSQL (one-time).

Phân loại:
  - Tất cả câu → eval_questions (draft)
  - review_status == 'approved' hoặc đã có bot_response → eval_questions_approved
  - Có bot_response (đã chạy eval) → eval_results trong run lịch sử

Chạy: uv run scripts/migrate_excel_to_neon.py
      uv run scripts/migrate_excel_to_neon.py --dry-run
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agentic_rag.runtime_env import load_local_env

load_local_env()

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXCEL_PATH = Path(
    os.environ.get(
        "EVAL_EXCEL_PATH",
        str(PROJECT_ROOT / "guide" / "reports" / "result_final.xlsx"),
    )
)
SHEET_NAME = "Evaluation"

DATASET_NAME = "Benchmark gốc (1002 câu)"
DATASET_DESC = "Bộ câu hỏi benchmark migrate từ result_final.xlsx"
RUN_NAME = "Lần đánh giá gốc (Excel)"
RUN_DESC = "Kết quả eval từ file Excel result_final.xlsx"

DRY_RUN = "--dry-run" in sys.argv


# ── DB ────────────────────────────────────────────────────────────────────────


def _conn() -> psycopg.Connection:
    raw = os.environ.get("NEON_CONNECTION", "")
    if not raw:
        raise RuntimeError("NEON_CONNECTION is not set")
    url = re.sub(r"^postgresql\+psycopg://", "postgresql://", raw)
    return psycopg.connect(url, row_factory=dict_row)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _doc_id(chunk_ids_str: str | None) -> str:
    if not chunk_ids_str:
        return "unknown"
    first = str(chunk_ids_str).split(",")[0].strip()
    parts = first.split("_")
    return f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else (first or "unknown")


def _parse_ids(val) -> list[str] | None:
    if val is None or (isinstance(val, float) and str(val) == "nan"):
        return None
    ids = [x.strip() for x in str(val).split(",") if x.strip()]
    return ids or None


def _float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if str(f) == "nan" else f
    except (ValueError, TypeError):
        return None


def _bool(val) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).lower().strip()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


def _str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return None if s in ("", "nan", "None") else s


def _jsonb(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    s = str(val).strip()
    if not s or s in ("nan", "None"):
        return None
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        return None


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    if not EXCEL_PATH.exists():
        print(f"ERROR: File không tìm thấy: {EXCEL_PATH}", flush=True)
        sys.exit(1)

    print(f"Đọc {EXCEL_PATH} ...", flush=True)
    # header=1 → dòng index 1 (dòng 2 trong Excel) là header
    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME, header=1, engine="openpyxl")
    df = df.dropna(subset=["question"])
    df = df[df["question"].astype(str).str.strip() != ""]

    total = len(df)
    approved_mask = (df.get("review_status", pd.Series(dtype=str)) == "approved") | df[
        "bot_response"
    ].notna()
    evaluated_mask = df["bot_response"].notna()

    approved_count = int(approved_mask.sum())
    evaluated_count = int(evaluated_mask.sum())

    print(f"\nTổng câu: {total}", flush=True)
    print(f"  Chưa duyệt (draft):   {total - approved_count}", flush=True)
    print(f"  Đã duyệt (approved):  {approved_count}", flush=True)
    print(f"  Đã eval (có kết quả): {evaluated_count}", flush=True)

    if DRY_RUN:
        print("\n[DRY RUN] Không ghi vào DB.", flush=True)
        return

    print("\nKết nối Neon ...", flush=True)
    db = _conn()
    print("Kết nối OK. Bắt đầu ghi ...", flush=True)

    with db:
        cur = db.cursor()

        # 1. Dataset
        cur.execute(
            """
            INSERT INTO eval_datasets (name, description, is_benchmark)
            VALUES (%s, %s, TRUE)
            RETURNING id
            """,
            (DATASET_NAME, DATASET_DESC),
        )
        dataset_id: str = cur.fetchone()["id"]
        print(f"Dataset: {dataset_id}", flush=True)

        # 2. Eval run lịch sử
        run_id: str | None = None
        if evaluated_count:
            cur.execute(
                """
                INSERT INTO eval_runs (dataset_id, name, description, status, total, success)
                VALUES (%s, %s, %s, 'done', %s, %s) RETURNING id
                """,
                (dataset_id, RUN_NAME, RUN_DESC, evaluated_count, evaluated_count),
            )
            run_id = cur.fetchone()["id"]
            print(f"Eval run: {run_id}", flush=True)

        # 3. Batch insert questions
        print("Inserting questions ...", flush=True)
        q_rows = [
            (
                dataset_id,
                _doc_id(_str(row.get("ground_truth_chunk_ids"))),
                _str(row.get("section_name")),
                str(row["question"]).strip(),
                str(row.get("expected_answer") or "").strip(),
                _parse_ids(_str(row.get("ground_truth_chunk_ids"))),
            )
            for _, row in df.iterrows()
            if str(row.get("expected_answer") or "").strip()
        ]

        cur.executemany(
            """
            INSERT INTO eval_questions (
                dataset_id,
                document_id,
                section,
                question,
                ground_truth,
                source_chunk_ids
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            q_rows,
        )
        print(f"  {len(q_rows)} questions inserted", flush=True)

        # Lấy lại IDs theo thứ tự
        cur.execute(
            """
            SELECT id, question, ground_truth
            FROM eval_questions
            WHERE dataset_id = %s
            ORDER BY created_at
            """,
            (dataset_id,),
        )
        inserted = cur.fetchall()
        # Map question+ground_truth → id
        q_map = {(r["question"], r["ground_truth"]): r["id"] for r in inserted}

        # 4. Batch insert approved
        print("Inserting approved ...", flush=True)
        approved_rows = []
        for _, row in df.iterrows():
            q_text = str(row["question"]).strip()
            gt = str(row.get("expected_answer") or "").strip()
            if not gt:
                continue
            qid = q_map.get((q_text, gt))
            if not qid:
                continue
            review_status = _str(row.get("review_status")) or "pending"
            has_eval = row.get("bot_response") is not None and str(
                row.get("bot_response", "")
            ).strip() not in ("", "nan")
            if review_status == "approved" or has_eval:
                approved_rows.append((qid, dataset_id, "migrated"))

        cur.executemany(
            """
            INSERT INTO eval_questions_approved (question_id, dataset_id, reviewed_by)
            VALUES (%s, %s, %s) ON CONFLICT (question_id) DO NOTHING
            """,
            approved_rows,
        )
        print(f"  {len(approved_rows)} approved inserted", flush=True)

        # 5. Batch insert eval results
        if run_id:
            print("Inserting eval results ...", flush=True)
            result_rows = []
            for _, row in df.iterrows():
                q_text = str(row["question"]).strip()
                gt = str(row.get("expected_answer") or "").strip()
                if not gt:
                    continue
                bot_resp = _str(row.get("bot_response"))
                if not bot_resp:
                    continue
                qid = q_map.get((q_text, gt))
                if not qid:
                    continue
                result_rows.append(
                    (
                        qid,
                        run_id,
                        _str(row.get("rag_context")),
                        bot_resp,
                        _jsonb(row.get("bot_citations")),
                        _str(row.get("trace_url")),
                        _parse_ids(_str(row.get("retrieved_top5_ids"))),
                        row.get("ground_truth_rank")
                        if pd.notna(row.get("ground_truth_rank", float("nan")))
                        else None,
                        _float(row.get("recall_at_5")),
                        _float(row.get("mrr_at_5")),
                        _float(row.get("citation_chunk_match")),
                        _bool(row.get("guardrail_pass")),
                        _float(row.get("ragas_faithfulness")),
                        _float(row.get("ragas_answer_relevancy")),
                        _float(row.get("ragas_context_precision")),
                        _float(row.get("ragas_context_recall")),
                    )
                )

            cur.executemany(
                """
                INSERT INTO eval_results (
                    question_id, run_id,
                    rag_context, bot_response, bot_citations, trace_url,
                    retrieved_top5_ids, ground_truth_rank,
                    recall_at_5, mrr_at_5, citation_chunk_match, guardrail_pass,
                    ragas_faithfulness, ragas_answer_relevancy,
                    ragas_context_precision, ragas_context_recall
                ) VALUES (
                    %s, %s, %s, %s, %s::jsonb, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (question_id, run_id) DO NOTHING
                """,
                result_rows,
            )
            print(f"  {len(result_rows)} eval results inserted", flush=True)

    db.close()
    print("\nMigrate hoàn tất!", flush=True)


if __name__ == "__main__":
    main()
