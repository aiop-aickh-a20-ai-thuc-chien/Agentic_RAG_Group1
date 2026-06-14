"""Re-run eval questions that failed (eval_error set) — vd lỗi timeout Qdrant tạm thời.

Worker bình thường KHÔNG tự retry: câu lỗi đã có row trong eval_results nên bị coi là
"đã xử lý". Script này xoá row lỗi, chỉnh lại bộ đếm failed, chạy lại pipeline (có retry
vài lần) rồi ghi kết quả mới.

Dùng:
  python scripts/rerun_failed_questions.py                       # chạy lại MỌI câu lỗi
  python scripts/rerun_failed_questions.py --question-id <uuid>  # chỉ 1 câu
  python scripts/rerun_failed_questions.py --run-id <uuid>       # chỉ 1 run
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from typing import Any

from dotenv import load_dotenv

from agentic_rag.autodata_eval.db import get_conn
from agentic_rag.autodata_eval.worker import _write_result, run_pipeline_for_question
from agentic_rag.runtime_env import load_local_env

_MAX_ATTEMPTS = 3


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-run failed eval questions.")
    parser.add_argument("--question-id", default=None, help="Chỉ chạy lại câu này.")
    parser.add_argument("--run-id", default=None, help="Chỉ chạy lại câu lỗi trong run này.")
    args = parser.parse_args()

    # Console Windows mặc định cp1252 — ép UTF-8 để in tiếng Việt không crash.
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

    load_dotenv()
    load_local_env()

    failed = _fetch_failed(question_id=args.question_id, run_id=args.run_id)
    if not failed:
        print("Không có câu lỗi nào khớp điều kiện.")
        return

    print(f"Tìm thấy {len(failed)} câu lỗi. Bắt đầu chạy lại...")
    fixed = 0
    for row in failed:
        run_id = str(row["run_id"])
        question_id = str(row["question_id"])
        exclude_layers = _exclude_layers(row.get("config"))

        # Xoá row lỗi + trả lại bộ đếm để re-run ghi mới đúng (xem _write_result).
        _clear_failed_row(run_id, question_id)

        payload = _run_with_retry(
            question_id=question_id,
            question=row["question"],
            source_chunk_ids=row.get("source_chunk_ids") or [],
            exclude_dedup_layers=exclude_layers,
        )
        _write_result(run_id, question_id, payload)

        status = "OK" if not payload.get("eval_error") else f"VẪN LỖI: {payload['eval_error']}"
        if not payload.get("eval_error"):
            fixed += 1
        print(f"  - run {run_id[:8]} · câu {question_id[:8]}: {status}")

    print(f"Xong. {fixed}/{len(failed)} câu chạy lại thành công.")


def _run_with_retry(
    *,
    question_id: str,
    question: str,
    source_chunk_ids: list[str],
    exclude_dedup_layers: list[str] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        payload = run_pipeline_for_question(
            question_id=question_id,
            question=question,
            source_chunk_ids=source_chunk_ids,
            exclude_dedup_layers=exclude_dedup_layers,
        )
        if not payload.get("eval_error"):
            return payload
        if attempt < _MAX_ATTEMPTS:
            time.sleep(2.0 * attempt)
    return payload


def _fetch_failed(
    *,
    question_id: str | None,
    run_id: str | None,
) -> list[dict[str, Any]]:
    clauses = ["r.eval_error IS NOT NULL"]
    params: list[Any] = []
    if question_id:
        clauses.append("r.question_id = %s")
        params.append(question_id)
    if run_id:
        clauses.append("r.run_id = %s")
        params.append(run_id)
    where_sql = " AND ".join(clauses)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT r.run_id, r.question_id, q.question, q.source_chunk_ids, run.config
            FROM eval_results r
            JOIN eval_questions q ON q.id = r.question_id
            JOIN eval_runs run ON run.id = r.run_id
            WHERE {where_sql}
            """,
            params,
        )
        return cur.fetchall()


def _clear_failed_row(run_id: str, question_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM eval_results WHERE run_id = %s AND question_id = %s "
                "AND eval_error IS NOT NULL",
                (run_id, question_id),
            )
            if cur.rowcount:
                cur.execute(
                    "UPDATE eval_runs SET failed = GREATEST(failed - %s, 0) WHERE id = %s",
                    (cur.rowcount, run_id),
                )
        conn.commit()


def _exclude_layers(config: Any) -> list[str] | None:
    import json

    if not config:
        return None
    data = json.loads(config) if isinstance(config, str) else dict(config)
    layers = data.get("exclude_dedup_layers") or []
    return [str(layer) for layer in layers] or None


if __name__ == "__main__":
    main()
