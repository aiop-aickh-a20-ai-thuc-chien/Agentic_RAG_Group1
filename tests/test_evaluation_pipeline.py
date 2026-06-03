from pathlib import Path
from typing import Any

import pytest

from agentic_rag.core.contracts import Answer, Chunk, Citation, SearchResult
from agentic_rag.evaluation.metrics import mrr_at_k, recall_at_k
from agentic_rag.evaluation.runner import EvaluationRunner
from agentic_rag.generation.answering import GenerationResult

EVALUATION_HEADERS = [
    "id",
    "section_name",
    "question",
    "expected_answer",
    "ground_truth_chunk_ids",
    "ground_truth_doc",
    "ground_truth_page",
    "is_out_of_scope",
    "custom_preconds",
    "rag_input",
    "rag_context",
    "bot_response",
    "bot_citations",
    "trace_url",
    "retrieved_top5_ids",
    "ground_truth_rank",
    "recall_at_5",
    "mrr_at_5",
    "citation_chunk_match",
    "guardrail_pass",
    "check_answer_correct",
    "check_answer_reason",
    "check_kb_used",
    "check_kb_reason",
    "check_citation_correct",
    "check_citation_reason",
    "error_type",
    "overall_verdict",
    "ragas_faithfulness",
    "ragas_answer_relevancy",
    "ragas_context_precision",
    "ragas_context_recall",
]


def test_recall_at_k_returns_fraction_of_relevant_ids() -> None:
    recall = recall_at_k(
        ["chunk-a", "chunk-c", "chunk-d"],
        {"chunk-a", "chunk-b"},
        k=3,
    )

    assert recall == 0.5


def test_mrr_at_k_returns_first_relevant_reciprocal_rank() -> None:
    mrr = mrr_at_k(
        ["chunk-x", "chunk-a", "chunk-b"],
        {"chunk-a", "chunk-b"},
        k=3,
    )

    assert mrr == 0.5


def test_evaluation_runner_populates_outputs_and_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openpyxl = _openpyxl()
    input_path = tmp_path / "evaluation.xlsx"
    output_path = tmp_path / "evaluation_results.xlsx"
    _write_workbook(
        input_path,
        rows=[
            {
                "id": "Q01",
                "question": "Pin bao hanh bao lau?",
                "expected_answer": "Pin duoc bao hanh 8 nam.",
                "ground_truth_chunk_ids": "chunk-a, chunk-b",
                "is_out_of_scope": False,
            },
            {
                "id": "Q02",
                "question": "Gia co phieu hom nay?",
                "expected_answer": "Khong co trong tai lieu.",
                "ground_truth_chunk_ids": "NONE",
                "is_out_of_scope": "TRUE",
            },
        ],
    )
    chunk_a = Chunk(
        chunk_id="chunk-a",
        text="Pin duoc bao hanh 8 nam.",
        metadata={"source": "warranty.pdf", "page": 1},
    )
    chunk_c = Chunk(
        chunk_id="chunk-c",
        text="Thong tin bao duong xe.",
        metadata={"source": "warranty.pdf", "page": 2},
    )
    evidence_chunks = [
        SearchResult(chunk=chunk_a, score=0.9, rank=1, retriever="rerank"),
        SearchResult(chunk=chunk_c, score=0.5, rank=2, retriever="rerank"),
    ]

    def fake_evidence_for_question(
        *,
        question: str,
    ) -> tuple[list[SearchResult], str]:
        return evidence_chunks, "context"

    def fake_generate_answer_with_trace(
        *,
        question: str,
        evidence_context: str,
        evidence_chunks: list[SearchResult],
    ) -> GenerationResult:
        if "co phieu" in question:
            return GenerationResult(
                answer=Answer(answer="Khong co trong tai lieu.", status="not_found"),
                trace={},
            )
        return GenerationResult(
            answer=Answer(
                answer="Pin duoc bao hanh 8 nam.",
                status="answered",
                citations=[Citation(source="warranty.pdf", chunk_id="chunk-a", page=1)],
            ),
            trace={},
        )

    monkeypatch.setattr(
        "agentic_rag.evaluation.runner.evidence_for_question",
        fake_evidence_for_question,
    )
    monkeypatch.setattr(
        "agentic_rag.evaluation.runner.generate_answer_with_trace",
        fake_generate_answer_with_trace,
    )

    EvaluationRunner(str(input_path), str(output_path)).run()

    wb = openpyxl.load_workbook(output_path)
    ws = wb["Evaluation"]
    header = _header(ws)
    assert ws.cell(row=3, column=header["retrieved_top5_ids"]).value == "chunk-a, chunk-c"
    assert ws.cell(row=3, column=header["ground_truth_rank"]).value == 1
    assert ws.cell(row=3, column=header["recall_at_5"]).value == 0.5
    assert ws.cell(row=3, column=header["mrr_at_5"]).value == 1.0
    assert ws.cell(row=3, column=header["citation_chunk_match"]).value is True
    assert ws.cell(row=3, column=header["guardrail_pass"]).value == "N/A"
    assert ws.cell(row=4, column=header["guardrail_pass"]).value is True
    assert ws.cell(row=4, column=header["recall_at_5"]).value is None


def test_evaluation_runner_reports_missing_required_columns(tmp_path: Path) -> None:
    openpyxl = _openpyxl()
    input_path = tmp_path / "missing_headers.xlsx"
    output_path = tmp_path / "unused.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Evaluation"
    ws.cell(row=2, column=1).value = "question"
    wb.save(input_path)

    with pytest.raises(ValueError, match="missing required columns"):
        EvaluationRunner(str(input_path), str(output_path)).run()


def _write_workbook(path: Path, *, rows: list[dict[str, object]]) -> None:
    openpyxl = _openpyxl()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Evaluation"
    for column_idx, header in enumerate(EVALUATION_HEADERS, start=1):
        ws.cell(row=2, column=column_idx).value = header
    for row_idx, row in enumerate(rows, start=3):
        for column_idx, header in enumerate(EVALUATION_HEADERS, start=1):
            if header in row:
                ws.cell(row=row_idx, column=column_idx).value = row[header]
    wb.save(path)


def _header(ws: Any) -> dict[str, int]:
    return {cell.value: idx for idx, cell in enumerate(ws[2], start=1) if cell.value}


def _openpyxl() -> Any:
    return pytest.importorskip("openpyxl")
