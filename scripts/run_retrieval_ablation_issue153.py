"""Run a small retrieval ablation report for issue #153.

The default mode uses deterministic fixture data so the script can run without
OpenAI keys, uploaded documents, or external vector stores.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_rag.core.contracts import SearchResult
from agentic_rag.retrieval.fusion import (
    build_evidence_context,
    normalized_score_fusion,
    rerank_with_metadata,
    rrf_fusion,
    weighted_rrf_fusion,
)
from agentic_rag.testing.fixtures import sample_chunks

OUTPUT_DIR = Path(".tmp/issue153_retrieval_ablation")
SUMMARY_PATH = OUTPUT_DIR / "summary.md"
RESULTS_PATH = OUTPUT_DIR / "results.jsonl"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = _run_fixture_ablation()
    _write_jsonl(rows)
    _write_summary(rows)
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Wrote {RESULTS_PATH}")


def _run_fixture_ablation() -> list[dict[str, object]]:
    question = "Pin bao hanh bao lau?"
    chunks = sample_chunks()
    bm25_results = [
        SearchResult(chunk=chunks[0], score=9.0, rank=1, retriever="bm25"),
        SearchResult(chunk=chunks[1], score=1.0, rank=2, retriever="bm25"),
    ]
    dense_results = [
        SearchResult(chunk=chunks[1], score=0.82, rank=1, retriever="dense"),
        SearchResult(chunk=chunks[0], score=0.78, rank=2, retriever="dense"),
    ]
    experiments = {
        "bm25_only": bm25_results,
        "dense_only": dense_results,
        "rrf_default": rrf_fusion(bm25_results, dense_results, top_k=5),
        "weighted_rrf_055_045": weighted_rrf_fusion(
            bm25_results,
            dense_results,
            top_k=5,
            bm25_weight=0.55,
            dense_weight=0.45,
        ),
        "weighted_rrf_070_030": weighted_rrf_fusion(
            bm25_results,
            dense_results,
            top_k=5,
            bm25_weight=0.70,
            dense_weight=0.30,
        ),
        "normalized_score_fusion_055": normalized_score_fusion(
            bm25_results,
            dense_results,
            top_k=5,
            alpha=0.55,
        ),
    }
    rows: list[dict[str, object]] = []
    for name, candidates in experiments.items():
        reranked, rerank_trace = rerank_with_metadata(question, candidates, top_k=5)
        rows.append(
            {
                "query": question,
                "experiment": name,
                "bm25": [_result_row(result) for result in bm25_results],
                "dense": [_result_row(result) for result in dense_results],
                "candidates": [_result_row(result) for result in candidates],
                "reranked": [_result_row(result) for result in reranked],
                "rerank_trace": rerank_trace,
                "evidence_context": build_evidence_context(reranked),
            }
        )
    return rows


def _result_row(result: SearchResult) -> dict[str, object]:
    metadata = result.chunk.metadata
    return {
        "chunk_id": result.chunk.chunk_id,
        "rank": result.rank,
        "score": result.score,
        "retriever": result.retriever,
        "source": metadata.get("source"),
        "page": metadata.get("page"),
        "section": metadata.get("section"),
        "text": result.chunk.text,
    }


def _write_jsonl(rows: list[dict[str, object]]) -> None:
    with RESULTS_PATH.open("w", encoding="utf-8") as result_file:
        for row in rows:
            result_file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_summary(rows: list[dict[str, object]]) -> None:
    lines = [
        "# Issue #153 Retrieval Ablation",
        "",
        "Fixture-based smoke report. Use real local-provider traces for final calibration.",
        "",
        "| Experiment | Top evidence | Rerank provider | Evidence context chars |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        reranked = row["reranked"]
        top_evidence = "none"
        if isinstance(reranked, list) and reranked:
            first = reranked[0]
            if isinstance(first, dict):
                top_evidence = str(first.get("chunk_id"))
        rerank_trace = row["rerank_trace"]
        used_provider = "unknown"
        if isinstance(rerank_trace, dict):
            used_provider = str(rerank_trace.get("used_provider", "unknown"))
        evidence_context = row["evidence_context"]
        context_chars = len(evidence_context) if isinstance(evidence_context, str) else 0
        lines.append(
            f"| {row['experiment']} | {top_evidence} | {used_provider} | {context_chars} |"
        )
    lines.extend(
        [
            "",
            "## Initial observations",
            "",
            "- BM25 helps exact warranty wording in the fixture.",
            "- Dense contributes semantic or URL evidence candidates.",
            "- Rerank should be calibrated on real traces before enabling hard thresholds.",
        ]
    )
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
