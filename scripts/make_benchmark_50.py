"""Chọn 50 câu hỏi phân biệt cao từ "Benchmark gốc (1002 câu)" và tạo dataset eval.

Mỗi feature retrieval chỉ lộ tác dụng trên một loại câu. Script chấm điểm từng câu
theo tín hiệu (entity trong câu + metadata của chunk ground-truth) rồi chọn 50 câu
CÂN BẰNG để A/B các cờ (hard filter / question-index / boosting / dedup / LLM-map)
đều có nhóm phản ứng rõ.

Chạy:
    PYTHONIOENCODING=utf-8 uv run python scripts/make_benchmark_50.py            # dry-run, chỉ in
    PYTHONIOENCODING=utf-8 uv run python scripts/make_benchmark_50.py --create  # tạo + link
"""

from __future__ import annotations

import os
import sys

import psycopg
from dotenv import load_dotenv

NEW_DATASET_NAME = "50-evaluate"
SOURCE_NAME_LIKE = "%enchmark%"  # "Benchmark gốc (1002 câu)"

# (bucket, target). Tổng = 50. Ưu tiên gán câu vào bucket hiếm trước (từ trên xuống).
BUCKETS = [
    ("dedup", 4),  # GT chunk là bản trùng (dedup ảnh hưởng)
    ("paraphrase", 6),  # GT có entity_canonical nhưng câu KHÔNG match từ điển → LLM-map
    ("multi_entity", 6),  # đa model / so sánh → hard filter dễ cắt nhầm
    ("question_idx", 8),  # GT chunk có field questions → question-index lộ tác dụng
    ("doc_type", 6),  # GT doc_type rõ (faq/spec/policy/manual) → boosting
    ("negative", 8),  # không entity → kiểm tra filter KHÔNG làm hại
    ("entity_single", 12),  # entity rõ, đơn model (hard filter giúp)
]
_COMPARE_HINTS = ("so sánh", " vs ", "khác nhau", "so với", "chênh")
_BOOST_TYPES = {"faq", "spec_sheet", "policy", "manual"}


def _qdrant_metadata_index() -> dict[str, dict]:
    """chunk_id (mọi biến thể khoá) -> metadata dict, scroll toàn collection 1 lần."""
    from qdrant_client import QdrantClient

    client = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ.get("QDRANT_API_KEY"))
    collection = os.environ["QDRANT_COLLECTION"]
    index: dict[str, dict] = {}
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=collection,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in batch:
            payload = point.payload or {}
            md = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            for key in (
                payload.get("chunk_id"),
                payload.get("storage_chunk_id"),
                md.get("storage_chunk_id"),
                md.get("chunk_id"),
            ):
                if key:
                    index[str(key)] = md
        if offset is None:
            break
    return index


def _classify(question: str, gt_md: dict, detect) -> str:
    ents = detect(question)
    has_entity = len(ents) > 0
    multi = len({e for e in ents}) >= 2 or any(h in question.lower() for h in _COMPARE_HINTS)
    canonical = bool(gt_md.get("entities_canonical"))
    has_questions = isinstance(gt_md.get("questions"), (list, tuple)) and bool(
        gt_md.get("questions")
    )
    dedup = bool((gt_md.get("deduplication") or {}).get("primary_layer"))
    doc_type = str(gt_md.get("document_type") or "").lower()

    # Ưu tiên gán bucket hiếm/đặc thù trước.
    if dedup:
        return "dedup"
    if canonical and not has_entity:
        return "paraphrase"
    if multi:
        return "multi_entity"
    if has_questions:
        return "question_idx"
    if doc_type in _BOOST_TYPES:
        return "doc_type"
    if not has_entity and not canonical:
        return "negative"
    return "entity_single"


def _arg(flag: str, default: str) -> str:
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main() -> None:
    load_dotenv()
    create = "--create" in sys.argv
    dataset_name = _arg("--name", NEW_DATASET_NAME)
    # Bỏ câu có GT chunk thuộc các dedup layer này (vì khi bật filter layer đó,
    # eval-run sẽ ẩn câu — GT bị loại). VD bật L1 → --exclude-gt-layers exact_sha256.
    exclude_gt_layers = {x.strip() for x in _arg("--exclude-gt-layers", "").split(",") if x.strip()}
    from agentic_rag.ingestion.metadata import detect_in_query

    conn = psycopg.connect(os.environ["NEON_CONNECTION"])
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM eval_datasets WHERE name ILIKE %s", (SOURCE_NAME_LIKE,))
    src = cur.fetchone()
    if not src:
        print("Không tìm thấy dataset nguồn.")
        return
    src_id = str(src[0])
    print(f"Nguồn: {src[1]} ({src_id})")

    # Chỉ lấy câu đã approved (điều kiện để link vào dataset).
    cur.execute(
        """
        SELECT q.id, q.question, q.source_chunk_ids
        FROM eval_dataset_questions dq
        JOIN eval_questions q ON q.id = dq.question_id
        JOIN eval_questions_approved a ON a.question_id = q.id
        WHERE dq.dataset_id = %s
        ORDER BY q.id
        """,
        (src_id,),
    )
    rows = cur.fetchall()
    print(f"Câu approved trong nguồn: {len(rows)}")

    print("Đang nạp metadata Qdrant...")
    qmd = _qdrant_metadata_index()

    by_bucket: dict[str, list] = {b: [] for b, _ in BUCKETS}
    skipped = 0
    for qid, question, chunk_ids in rows:
        gt = qmd.get(str((chunk_ids or [None])[0]), {})
        gt_layer = str((gt.get("deduplication") or {}).get("primary_layer") or "")
        if gt_layer in exclude_gt_layers:
            skipped += 1  # GT bị loại khi bật filter layer này → bỏ câu
            continue
        bucket = _classify(question, gt, detect_in_query)
        by_bucket[bucket].append((str(qid), question))
    if exclude_gt_layers:
        print(f"Bỏ {skipped} câu có GT thuộc layer {sorted(exclude_gt_layers)} (sẽ bị ẩn khi bật).")

    print("\n=== Phân bố nguyên liệu ===")
    for b, _ in BUCKETS:
        print(f"  {b:14} có {len(by_bucket[b]):4} câu")

    # Chọn theo target; thiếu thì bù từ entity_single (rồi các bucket dư khác).
    selected: list[tuple[str, str, str]] = []
    chosen_ids: set[str] = set()
    for bucket, target in BUCKETS:
        for qid, q in by_bucket[bucket][:target]:
            if qid not in chosen_ids:
                selected.append((qid, q, bucket))
                chosen_ids.add(qid)
    if len(selected) < 50:
        leftovers = [
            (qid, q, b) for b, _ in BUCKETS for qid, q in by_bucket[b] if qid not in chosen_ids
        ]
        for qid, q, b in leftovers:
            if len(selected) >= 50:
                break
            selected.append((qid, q, b))
            chosen_ids.add(qid)
    selected = selected[:50]

    print(f"\n=== Đã chọn {len(selected)} câu ===")
    for i, (_, q, b) in enumerate(selected, 1):
        print(f"  {i:2}. [{b:13}] {q[:66]}")

    if not create:
        print("\n(dry-run) Thêm --create để tạo dataset + link.")
        return

    cur.execute("SELECT id FROM eval_datasets WHERE name = %s", (dataset_name,))
    if cur.fetchone():
        print(
            f"\nDataset '{dataset_name}' đã tồn tại — bỏ qua tạo (xoá thủ công nếu muốn làm lại)."
        )
        return
    cur.execute(
        "INSERT INTO eval_datasets (name, description, is_benchmark) "
        "VALUES (%s, %s, %s) RETURNING id",
        (
            dataset_name,
            "50 câu phân biệt cao chọn từ Benchmark gốc "
            "(hard-filter/question-index/boosting/dedup/LLM-map/negative)",
            True,
        ),
    )
    new_id = str(cur.fetchone()[0])
    for qid, _, _ in selected:
        cur.execute(
            "INSERT INTO eval_dataset_questions (dataset_id, question_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (new_id, qid),
        )
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM eval_dataset_questions WHERE dataset_id = %s", (new_id,))
    print(f"\nĐã tạo dataset '{dataset_name}' ({new_id}) với {cur.fetchone()[0]} câu.")


if __name__ == "__main__":
    main()
