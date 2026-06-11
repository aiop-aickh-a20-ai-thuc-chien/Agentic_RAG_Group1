"""Manual threshold sweep for embedding-based near-duplicate detection."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from agentic_rag.ingestion.dedup_detect.embedding import cosine_similarity

DEFAULT_MODEL_ENV_VAR = "DEDUP_DETECT_SENTENCE_TRANSFORMER_MODEL"
PROJECT_EMBEDDING_MODEL_ENV_VAR = "EMBEDDING_MODEL"
DEFAULT_SENTENCE_TRANSFORMER_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_DATASET = Path(__file__).resolve().parent / "sample_pairs.jsonl"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
PairLabel = Literal["duplicate", "near_duplicate", "different"]


def _load_env_file_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


_load_env_file_if_available()
DEFAULT_MODEL = (
    os.environ.get(DEFAULT_MODEL_ENV_VAR)
    or os.environ.get(PROJECT_EMBEDDING_MODEL_ENV_VAR)
    or DEFAULT_SENTENCE_TRANSFORMER_MODEL
)


class _SentenceTransformerModel(Protocol):
    def encode(self, texts: list[str], **kwargs: object) -> object:
        """Encode texts into vectors."""


@dataclass(frozen=True)
class LabeledPair:
    pair_id: str
    left: str
    right: str
    label: PairLabel

    @property
    def is_positive(self) -> bool:
        return self.label in {"duplicate", "near_duplicate"}


def main() -> int:
    args = _parse_args()
    pairs = load_pairs(args.dataset)
    vectors = embed_pair_texts(
        pairs,
        model_name=args.model,
        device=args.device,
        batch_size=args.batch_size,
        local_files_only=args.local_files_only,
    )
    pair_scores = score_pairs(pairs, vectors)
    threshold_rows = sweep_thresholds(
        pair_scores,
        start=args.threshold_start,
        stop=args.threshold_stop,
        step=args.threshold_step,
    )
    recommended = recommend_threshold(threshold_rows)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "model": args.model,
        "dataset": str(args.dataset),
        "positive_labels": ["duplicate", "near_duplicate"],
        "recommended_threshold": recommended["threshold"],
        "recommended_metrics": recommended,
        "pair_scores": pair_scores,
        "threshold_rows": threshold_rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "threshold_sweep_report.json"
    markdown_path = args.output_dir / "threshold_sweep_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"Recommended threshold: {recommended['threshold']:.2f}")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    return 0


def load_pairs(path: Path) -> list[LabeledPair]:
    pairs: list[LabeledPair] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        label = payload.get("label")
        if label not in {"duplicate", "near_duplicate", "different"}:
            raise ValueError(f"Invalid label at line {line_number}: {label!r}")
        pairs.append(
            LabeledPair(
                pair_id=str(payload["pair_id"]),
                left=str(payload["left"]),
                right=str(payload["right"]),
                label=cast(PairLabel, label),
            )
        )
    if not pairs:
        raise ValueError(f"Dataset has no pairs: {path}")
    return pairs


def embed_pair_texts(
    pairs: list[LabeledPair],
    *,
    model_name: str,
    device: str | None,
    batch_size: int,
    local_files_only: bool,
) -> dict[str, list[float]]:
    model = load_sentence_transformer(
        model_name,
        device=device,
        local_files_only=local_files_only,
    )
    unique_texts = sorted({text for pair in pairs for text in (pair.left, pair.right)})
    raw_vectors = model.encode(
        unique_texts,
        batch_size=batch_size,
        convert_to_numpy=False,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    vectors = coerce_vectors(raw_vectors)
    return dict(zip(unique_texts, vectors, strict=True))


def load_sentence_transformer(
    model_name: str,
    *,
    device: str | None,
    local_files_only: bool,
) -> _SentenceTransformerModel:
    try:
        sentence_transformers = importlib.import_module("sentence_transformers")
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Run: uv sync --extra local-models"
        ) from exc
    sentence_transformer = sentence_transformers.SentenceTransformer
    kwargs: dict[str, object] = {}
    if device:
        kwargs["device"] = device
    if local_files_only:
        kwargs["local_files_only"] = True
    return cast(_SentenceTransformerModel, sentence_transformer(model_name, **kwargs))


def coerce_vectors(raw_vectors: object) -> list[list[float]]:
    if hasattr(raw_vectors, "tolist"):
        raw_vectors = raw_vectors.tolist()
    if not isinstance(raw_vectors, list):
        raw_vectors = list(cast(Any, raw_vectors))
    vectors: list[list[float]] = []
    for vector in cast(list[object], raw_vectors):
        if hasattr(vector, "tolist"):
            vector = vector.tolist()
        vectors.append([float(value) for value in cast(Any, vector)])
    return vectors


def score_pairs(
    pairs: list[LabeledPair],
    vectors: dict[str, list[float]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for pair in pairs:
        similarity = cosine_similarity(vectors[pair.left], vectors[pair.right])
        rows.append(
            {
                "pair_id": pair.pair_id,
                "label": pair.label,
                "is_positive": pair.is_positive,
                "similarity": round(similarity, 6),
                "left": pair.left,
                "right": pair.right,
            }
        )
    return sorted(rows, key=lambda row: cast(float, row["similarity"]), reverse=True)


def sweep_thresholds(
    pair_scores: list[dict[str, object]],
    *,
    start: float,
    stop: float,
    step: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    threshold = start
    while threshold <= stop + 1e-9:
        rows.append(evaluate_threshold(pair_scores, threshold=round(threshold, 6)))
        threshold += step
    return rows


def evaluate_threshold(
    pair_scores: list[dict[str, object]],
    *,
    threshold: float,
) -> dict[str, object]:
    tp = fp = tn = fn = 0
    for row in pair_scores:
        predicted = cast(float, row["similarity"]) >= threshold
        actual = cast(bool, row["is_positive"])
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "threshold": threshold,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def recommend_threshold(rows: list[dict[str, object]]) -> dict[str, object]:
    return max(
        rows,
        key=lambda row: (
            cast(float, row["f1"]),
            cast(float, row["precision"]),
            cast(float, row["threshold"]),
        ),
    )


def render_markdown(report: dict[str, object]) -> str:
    recommended = cast(dict[str, object], report["recommended_metrics"])
    lines = [
        "# Dedup Embedding Threshold Sweep",
        "",
        f"- Created: `{report['created_at']}`",
        f"- Model: `{report['model']}`",
        f"- Dataset: `{report['dataset']}`",
        f"- Recommended threshold: `{recommended['threshold']}`",
        f"- Recommended F1: `{recommended['f1']}`",
        f"- Precision: `{recommended['precision']}`",
        f"- Recall: `{recommended['recall']}`",
        "",
        "## Pair Scores",
        "",
        "| Pair | Label | Similarity |",
        "| --- | --- | ---: |",
    ]
    for row in cast(list[dict[str, object]], report["pair_scores"]):
        lines.append(f"| {row['pair_id']} | {row['label']} | {row['similarity']} |")
    lines.extend(
        [
            "",
            "## Threshold Sweep",
            "",
            "| Threshold | Precision | Recall | F1 | TP | FP | TN | FN |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in cast(list[dict[str, object]], report["threshold_rows"]):
        lines.append(
            "| {threshold} | {precision} | {recall} | {f1} | "
            "{true_positive} | {false_positive} | {true_negative} | {false_negative} |".format(
                **row
            )
        )
    lines.append("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--device", help="Optional sentence-transformers device, e.g. cpu or cuda.")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Require the model to already exist in the local Hugging Face cache.",
    )
    parser.add_argument("--threshold-start", type=float, default=0.70)
    parser.add_argument("--threshold-stop", type=float, default=0.99)
    parser.add_argument("--threshold-step", type=float, default=0.01)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
