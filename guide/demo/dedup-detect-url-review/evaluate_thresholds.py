"""Evaluate dedup thresholds against guide golden labels."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agentic_rag.ingestion.dedup_detect import (
    DedupDocument,
    configured_embedding_candidates,
    embedding_vectors_from_first_available_client,
    find_embedding_duplicates,
    find_exact_duplicates,
    find_simhash_duplicates,
)

DEMO_DIR = Path(__file__).resolve().parent
DEFAULT_CHUNKS = DEMO_DIR / "output" / "chunks_with_dedup.jsonl"
DEFAULT_GOLDEN = DEMO_DIR / "golden_samples.json"
DEFAULT_OUTPUT = DEMO_DIR / "output"


@dataclass(frozen=True)
class GoldenPair:
    """One human-reviewed duplicate/non-duplicate pair."""

    left_id: str
    right_id: str
    is_duplicate: bool
    reason: str

    @property
    def key(self) -> tuple[str, str]:
        return _pair_key(self.left_id, self.right_id)


@dataclass(frozen=True)
class EvalRow:
    """One threshold configuration result."""

    simhash_threshold: int
    layer3_embedding_threshold: float | None
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float
    fp_ids: list[str]
    fn_ids: list[str]


def main() -> None:
    args = _parse_args()
    chunks = _read_chunks(args.chunks)
    documents = [
        DedupDocument(
            document_id=str(chunk["chunk_id"]),
            text=str(chunk.get("text", "")),
            metadata=_metadata(chunk),
        )
        for chunk in chunks
    ]
    labels = _read_golden(args.golden)
    _validate_labels(labels, documents)

    embedding_vectors = None
    if args.enable_embedding:
        result = embedding_vectors_from_first_available_client(
            documents,
            candidates=configured_embedding_candidates(),
        )
        embedding_vectors = result.vectors

    rows = _evaluate_thresholds(
        documents,
        labels,
        simhash_thresholds=args.simhash_thresholds,
        layer3_thresholds=args.layer3_thresholds if args.enable_embedding else [None],
        embedding_vectors=embedding_vectors,
    )
    best = max(rows, key=lambda row: (row.f1, row.precision, row.recall, -row.fp, -row.fn))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "threshold_confusion_report.json", rows, best)
    _write_markdown(args.output_dir / "threshold_confusion_report.md", rows, best)
    print(f"Wrote {args.output_dir / 'threshold_confusion_report.md'}")
    print(f"Wrote {args.output_dir / 'threshold_confusion_report.json'}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sweep dedup thresholds and report TP/FP/FN/TN against golden labels."
    )
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--simhash-thresholds",
        type=int,
        nargs="+",
        default=[2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40],
        help="Layer 2 Hamming thresholds to sweep.",
    )
    parser.add_argument(
        "--enable-embedding",
        action="store_true",
        help="Also sweep Layer 3 using configured EMBEDDING_* runtime.",
    )
    parser.add_argument(
        "--embedding-thresholds",
        "--layer3-thresholds",
        dest="layer3_thresholds",
        type=float,
        nargs="+",
        default=[0.86, 0.88, 0.9, 0.92, 0.94, 0.96, 0.98],
        help="Layer 3 embedding cosine thresholds to sweep when --enable-embedding is set.",
    )
    return parser.parse_args()


def _read_chunks(path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                chunks.append(json.loads(stripped))
    return chunks


def _read_golden(path: Path) -> list[GoldenPair]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        GoldenPair(
            left_id=str(item["left_id"]),
            right_id=str(item["right_id"]),
            is_duplicate=bool(item["is_duplicate"]),
            reason=str(item.get("reason", "")),
        )
        for item in payload.get("labels", [])
    ]


def _validate_labels(labels: list[GoldenPair], documents: list[DedupDocument]) -> None:
    document_ids = {document.document_id for document in documents}
    missing = sorted(
        {
            chunk_id
            for label in labels
            for chunk_id in (label.left_id, label.right_id)
            if chunk_id not in document_ids
        }
    )
    if missing:
        joined = "\n".join(f"- {chunk_id}" for chunk_id in missing)
        raise SystemExit(f"Golden labels reference missing chunk IDs:\n{joined}")


def _evaluate_thresholds(
    documents: list[DedupDocument],
    labels: list[GoldenPair],
    *,
    simhash_thresholds: list[int],
    layer3_thresholds: list[float | None],
    embedding_vectors: dict[str, list[float]] | None,
) -> list[EvalRow]:
    rows: list[EvalRow] = []
    exact_pairs = _pairs_from_matches(find_exact_duplicates(documents))
    for simhash_threshold in simhash_thresholds:
        simhash_pairs = _pairs_from_matches(
            find_simhash_duplicates(
                documents,
                hamming_threshold=simhash_threshold,
                exclude_pairs=exact_pairs,
            )
        )
        for layer3_threshold in layer3_thresholds:
            embedding_pairs: set[tuple[str, str]] = set()
            if layer3_threshold is not None:
                if embedding_vectors is None:
                    raise ValueError(
                        "embedding_vectors are required for embedding threshold sweep."
                    )
                embedding_pairs = _pairs_from_matches(
                    find_embedding_duplicates(
                        documents,
                        vectors=embedding_vectors,
                        similarity_threshold=layer3_threshold,
                        exclude_pairs=exact_pairs | simhash_pairs,
                    )
                )
            predicted = exact_pairs | simhash_pairs | embedding_pairs
            rows.append(
                _score_labels(
                    labels,
                    predicted=predicted,
                    simhash_threshold=simhash_threshold,
                    layer3_embedding_threshold=layer3_threshold,
                )
            )
    return rows


def _score_labels(
    labels: list[GoldenPair],
    *,
    predicted: set[tuple[str, str]],
    simhash_threshold: int,
    layer3_embedding_threshold: float | None,
) -> EvalRow:
    tp = fp = fn = tn = 0
    fp_ids: list[str] = []
    fn_ids: list[str] = []
    for label in labels:
        is_predicted = label.key in predicted
        if label.is_duplicate and is_predicted:
            tp += 1
        elif not label.is_duplicate and is_predicted:
            fp += 1
            fp_ids.append(_format_pair(label))
        elif label.is_duplicate and not is_predicted:
            fn += 1
            fn_ids.append(_format_pair(label))
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return EvalRow(
        simhash_threshold=simhash_threshold,
        layer3_embedding_threshold=layer3_embedding_threshold,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=round(precision, 6),
        recall=round(recall, 6),
        f1=round(f1, 6),
        fp_ids=fp_ids,
        fn_ids=fn_ids,
    )


def _pairs_from_matches(matches: Iterable[Any]) -> set[tuple[str, str]]:
    return {
        _pair_key(str(match.document_id), str(match.duplicate_document_id)) for match in matches
    }


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _format_pair(label: GoldenPair) -> str:
    return f"{label.left_id} <-> {label.right_id}"


def _metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    metadata = chunk.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _write_json(path: Path, rows: list[EvalRow], best: EvalRow) -> None:
    path.write_text(
        json.dumps(
            {
                "best": best.__dict__,
                "rows": [row.__dict__ for row in rows],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_markdown(path: Path, rows: list[EvalRow], best: EvalRow) -> None:
    lines = [
        "# Dedup Threshold Confusion Matrix",
        "",
        "## Best Threshold",
        "",
        f"- SimHash threshold: {best.simhash_threshold}",
        f"- Layer 3 embedding threshold: {best.layer3_embedding_threshold}",
        f"- Precision: {best.precision}",
        f"- Recall: {best.recall}",
        f"- F1: {best.f1}",
        f"- TP/FP/FN/TN: {best.tp}/{best.fp}/{best.fn}/{best.tn}",
        "",
        "## Sweep Results",
        "",
        "| Layer 2 SimHash | Layer 3 Embedding | TP | FP | FN | TN | Precision | Recall | F1 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        layer3_threshold = (
            "" if row.layer3_embedding_threshold is None else str(row.layer3_embedding_threshold)
        )
        lines.append(
            f"| {row.simhash_threshold} | {layer3_threshold} | {row.tp} | {row.fp} | "
            f"{row.fn} | {row.tn} | {row.precision} | {row.recall} | {row.f1} |"
        )
    lines.extend(["", "## Best False Positives", ""])
    lines.extend(_error_lines(best.fp_ids))
    lines.extend(["", "## Best False Negatives", ""])
    lines.extend(_error_lines(best.fn_ids))
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _error_lines(pair_ids: list[str]) -> list[str]:
    if not pair_ids:
        return ["None."]
    return [f"- `{pair_id}`" for pair_id in pair_ids]


if __name__ == "__main__":
    main()
