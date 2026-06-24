from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("guide/demo/url-crawl-review/output/artifact_review_payload.json")
DEFAULT_OUTPUT = Path("guide/demo/url-crawl-review/output/artifact_review_evaluation.json")
REQUIRED_ARTIFACTS = (
    "source_html",
    "cleaned_html",
    "parsed_sections",
    "extracted_markdown",
    "cleaned_markdown",
    "quality",
    "chunks",
    "manifest",
)


def main() -> None:
    args = _parse_args()
    payload_path = Path(args.input)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    evaluation = evaluate_payload(payload)
    output = {
        "input_path": payload_path.as_posix(),
        "output_schema_version": 1,
        "evaluation": evaluation,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output_path)


def evaluate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    artifacts = [item for item in payload.get("artifacts", []) if isinstance(item, dict)]
    artifact_scores = _artifact_scores(artifacts)
    chunk_score = _chunk_score(payload)
    quality_score = _quality_score(payload)
    manifest_score = _manifest_score(payload)
    dedup_score = _dedup_score(payload)
    score = round(
        artifact_scores["score"] * 0.35
        + chunk_score["score"] * 0.25
        + quality_score["score"] * 0.2
        + manifest_score["score"] * 0.1
        + dedup_score["score"] * 0.1,
        2,
    )
    return {
        "url": payload.get("url"),
        "status": _verdict(score, payload.get("error")),
        "score": score,
        "summary_status": summary.get("status") or payload.get("status"),
        "artifact_score": artifact_scores,
        "chunk_score": chunk_score,
        "quality_score": quality_score,
        "manifest_score": manifest_score,
        "dedup_score": dedup_score,
        "issues": _issues(
            payload,
            artifact_scores,
            chunk_score,
            quality_score,
            manifest_score,
            dedup_score,
        ),
    }


def _artifact_scores(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    by_key = {str(item.get("key")): item for item in artifacts}
    missing = [key for key in REQUIRED_ARTIFACTS if not by_key.get(key, {}).get("exists")]
    empty = [
        key
        for key in REQUIRED_ARTIFACTS
        if by_key.get(key, {}).get("exists")
        and int(by_key.get(key, {}).get("size_bytes") or 0) == 0
    ]
    present_count = len(REQUIRED_ARTIFACTS) - len(missing)
    score = round((present_count / len(REQUIRED_ARTIFACTS)) * 100, 2)
    if empty:
        score = max(0, score - 10 * len(empty))
    return {
        "score": score,
        "present_count": present_count,
        "required_count": len(REQUIRED_ARTIFACTS),
        "missing": missing,
        "empty": empty,
    }


def _chunk_score(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    chunks = [item for item in payload.get("chunks", []) if isinstance(item, dict)]
    usable_count = sum(1 for chunk in chunks if chunk.get("is_usable_for_retrieval") is True)
    valuable_count = int(summary.get("valuable_chunk_count") or 0)
    product_fact_count = int(summary.get("product_fact_chunk_count") or 0)
    entity_count = int(summary.get("entity_chunk_count") or 0)
    noise_count = int(summary.get("noise_chunk_count") or 0)
    ratio = usable_count / len(chunks) if chunks else 0.0
    if not chunks:
        score = 0.0
    elif ratio >= 0.8:
        score = 100.0
    elif ratio >= 0.5:
        score = 70.0
    else:
        score = 35.0
    return {
        "score": score,
        "chunk_count": len(chunks),
        "usable_chunk_count": usable_count,
        "valuable_chunk_count": valuable_count,
        "product_fact_chunk_count": product_fact_count,
        "entity_chunk_count": entity_count,
        "noise_chunk_count": noise_count,
        "usable_ratio": round(ratio, 3),
    }


def _quality_score(payload: dict[str, Any]) -> dict[str, Any]:
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    gate = (
        quality.get("url_quality_gate") if isinstance(quality.get("url_quality_gate"), dict) else {}
    )
    report = quality.get("url_quality") if isinstance(quality.get("url_quality"), dict) else {}
    accepted = gate.get("accepted")
    verdict = report.get("verdict")
    if accepted is True and verdict == "useful":
        score = 100.0
    elif accepted is True:
        score = 80.0
    elif accepted is False:
        score = 40.0
    else:
        score = 55.0 if quality else 0.0
    return {
        "score": score,
        "gate_status": gate.get("status"),
        "accepted": accepted,
        "reason": gate.get("reason"),
        "verdict": verdict,
    }


def _manifest_score(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    required = ("parser", "input_source", "stage_paths", "chunk_count")
    missing = [key for key in required if key not in manifest or manifest.get(key) in (None, "")]
    score = round(((len(required) - len(missing)) / len(required)) * 100, 2)
    return {
        "score": score,
        "missing": missing,
        "parser": manifest.get("parser"),
        "source_html_stage": manifest.get("source_html_stage"),
    }


def _dedup_score(payload: dict[str, Any]) -> dict[str, Any]:
    dedup = payload.get("deduplication") if isinstance(payload.get("deduplication"), dict) else {}
    summary = dedup.get("summary") if isinstance(dedup.get("summary"), dict) else {}
    duplicate_chunks = (
        dedup.get("duplicate_chunks") if isinstance(dedup.get("duplicate_chunks"), list) else []
    )
    matches = dedup.get("matches") if isinstance(dedup.get("matches"), list) else []
    candidate_count = int(summary.get("duplicate_candidate_count") or 0)
    malformed_candidates = [
        item
        for item in duplicate_chunks
        if not isinstance(item, dict)
        or not isinstance(item.get("deduplication"), dict)
        or not item["deduplication"].get("canonical_chunk_id")
        or not item["deduplication"].get("primary_layer")
    ]
    if not dedup:
        score = 0.0
    elif malformed_candidates:
        score = 50.0
    elif candidate_count != len(duplicate_chunks):
        score = 75.0
    else:
        score = 100.0
    return {
        "score": score,
        "document_count": int(summary.get("document_count") or 0),
        "exact_match_count": int(summary.get("exact_match_count") or 0),
        "simhash_match_count": int(summary.get("simhash_match_count") or 0),
        "duplicate_candidate_count": candidate_count,
        "duplicate_chunk_count": len(duplicate_chunks),
        "match_count": len(matches),
        "malformed_candidate_count": len(malformed_candidates),
    }


def _issues(
    payload: dict[str, Any],
    artifact_score: dict[str, Any],
    chunk_score: dict[str, Any],
    quality_score: dict[str, Any],
    manifest_score: dict[str, Any],
    dedup_score: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if payload.get("error"):
        issues.append(str(payload["error"]))
    if artifact_score["missing"]:
        issues.append(f"missing artifacts: {', '.join(artifact_score['missing'])}")
    if artifact_score["empty"]:
        issues.append(f"empty artifacts: {', '.join(artifact_score['empty'])}")
    if chunk_score["chunk_count"] == 0:
        issues.append("no chunks generated")
    elif chunk_score["usable_ratio"] < 0.8:
        issues.append("usable chunk ratio below 0.8")
    if chunk_score["chunk_count"] > 0 and chunk_score["valuable_chunk_count"] == 0:
        issues.append("no valuable chunks after cleaned HTML/Markdown cleanup")
    if quality_score["accepted"] is False:
        issues.append(f"quality gate rejected: {quality_score['reason']}")
    if manifest_score["missing"]:
        issues.append(f"manifest missing keys: {', '.join(manifest_score['missing'])}")
    if dedup_score["score"] == 0:
        issues.append("deduplication summary missing from review payload")
    elif dedup_score["malformed_candidate_count"]:
        issues.append("deduplication candidates missing canonical chunk or primary layer")
    elif dedup_score["duplicate_candidate_count"] != dedup_score["duplicate_chunk_count"]:
        issues.append("deduplication candidate count does not match duplicate chunk list")
    return issues


def _verdict(score: float, error: object) -> str:
    if error:
        return "fail"
    if score >= 85:
        return "pass"
    if score >= 60:
        return "review"
    return "fail"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a single-URL artifact review payload.",
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="artifact_review_payload JSON path.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Evaluation JSON output path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
