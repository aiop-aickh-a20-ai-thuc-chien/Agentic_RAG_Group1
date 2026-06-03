"""Evaluation runner for the end-to-end RAG pipeline."""

from __future__ import annotations

import json
import logging

import openpyxl

from agentic_rag.evaluation.metrics import mrr_at_k, recall_at_k
from agentic_rag.generation.answering import generate_answer_with_trace
from agentic_rag.generation.evidence import evidence_for_question

logger = logging.getLogger(__name__)


class EvaluationRunner:
    """Runs the RAG pipeline over a test dataset and calculates metrics."""

    def __init__(self, input_file: str, output_file: str, run_ragas: bool = False) -> None:
        self.input_file = input_file
        self.output_file = output_file
        self.run_ragas = run_ragas

    def run(self) -> None:
        """Execute the evaluation pipeline."""
        logger.info(f"Loading dataset from {self.input_file}")
        wb = openpyxl.load_workbook(self.input_file)
        if "Evaluation" not in wb.sheetnames:
            raise ValueError("Input file must contain an 'Evaluation' sheet.")

        ws = wb["Evaluation"]

        # Determine column indices from header (row 2)
        header = {cell.value: idx for idx, cell in enumerate(ws[2], start=1) if cell.value}

        for row_idx in range(3, ws.max_row + 1):
            question_cell = ws.cell(row=row_idx, column=header.get("question", -1))
            if not question_cell.value:
                continue

            question = str(question_cell.value).strip()
            if not question:
                continue

            # Skip if already evaluated
            bot_response_cell = ws.cell(row=row_idx, column=header.get("bot_response", -1))
            if bot_response_cell.value:
                logger.info(f"Skipping row {row_idx} (already evaluated)")
                continue

            logger.info(f"Evaluating row {row_idx}: {question}")

            is_out_of_scope = (
                ws.cell(row=row_idx, column=header.get("is_out_of_scope", -1)).value is True
            )

            # 1. Run Pipeline
            try:
                evidence_chunks, evidence_context = evidence_for_question(question=question)
                generation = generate_answer_with_trace(
                    question=question,
                    evidence_context=evidence_context,
                    evidence_chunks=evidence_chunks,
                )
            except Exception as e:
                logger.error(f"Error generating answer for row {row_idx}: {e}")
                continue

            # Format chunks to JSON
            rag_context_json = json.dumps(
                [
                    {
                        "id": chunk.chunk.chunk_id,
                        "text": chunk.chunk.text,
                        "score": chunk.score,
                        "retriever": chunk.retriever,
                    }
                    for chunk in evidence_chunks
                ],
                ensure_ascii=False,
            )

            bot_citations_json = json.dumps(
                [c.model_dump() for c in generation.answer.citations], ensure_ascii=False
            )

            # Write pipeline output
            ws.cell(row=row_idx, column=header["rag_input"]).value = question
            ws.cell(row=row_idx, column=header["rag_context"]).value = rag_context_json
            ws.cell(row=row_idx, column=header["bot_response"]).value = generation.answer.answer
            ws.cell(row=row_idx, column=header["bot_citations"]).value = bot_citations_json
            ws.cell(row=row_idx, column=header["trace_url"]).value = "N/A (check local traces)"

            # 2. Calculate Metrics
            top5_ids = [chunk.chunk.chunk_id for chunk in evidence_chunks[:5]]
            ws.cell(row=row_idx, column=header["retrieved_top5_ids"]).value = ", ".join(top5_ids)

            gt_chunks_raw = ws.cell(
                row=row_idx, column=header.get("ground_truth_chunk_ids", -1)
            ).value

            if is_out_of_scope:
                is_not_found = generation.answer.status == "not_found"
                ws.cell(row=row_idx, column=header["guardrail_pass"]).value = is_not_found
            else:
                ws.cell(row=row_idx, column=header["guardrail_pass"]).value = "N/A"

                if gt_chunks_raw and str(gt_chunks_raw).strip() != "NONE":
                    relevant_ids = {c.strip() for c in str(gt_chunks_raw).split(",")}

                    # Compute ground truth rank
                    gt_rank = -1
                    for i, cid in enumerate(top5_ids, start=1):
                        if cid in relevant_ids:
                            gt_rank = i
                            break
                    ws.cell(row=row_idx, column=header["ground_truth_rank"]).value = gt_rank

                    # Compute recall and mrr
                    recall = recall_at_k(top5_ids, relevant_ids, k=5)
                    mrr = mrr_at_k(top5_ids, relevant_ids, k=5)
                    ws.cell(row=row_idx, column=header["recall_at_5"]).value = recall
                    ws.cell(row=row_idx, column=header["mrr_at_5"]).value = mrr

                    # Citation chunk match
                    bot_citation_ids = {c.chunk_id for c in generation.answer.citations}
                    has_match = bool(relevant_ids.intersection(bot_citation_ids))
                    ws.cell(row=row_idx, column=header["citation_chunk_match"]).value = has_match

        # 3. RAGAS Evaluation
        if self.run_ragas:
            from agentic_rag.evaluation.ragas_eval import run_ragas_evaluation

            logger.info("Preparing data for RAGAS evaluation...")
            eval_data = []
            row_mapping = []

            for row_idx in range(3, ws.max_row + 1):
                is_out_of_scope = (
                    ws.cell(row=row_idx, column=header.get("is_out_of_scope", -1)).value is True
                )
                if is_out_of_scope:
                    continue

                question = str(ws.cell(row=row_idx, column=header.get("question", -1)).value or "")
                answer = str(
                    ws.cell(row=row_idx, column=header.get("bot_response", -1)).value or ""
                )
                expected_answer = str(
                    ws.cell(row=row_idx, column=header.get("expected_answer", -1)).value or ""
                )
                rag_context_raw = ws.cell(row=row_idx, column=header.get("rag_context", -1)).value

                if not question or not answer:
                    continue

                contexts = []
                if rag_context_raw:
                    try:
                        ctx_list = json.loads(rag_context_raw)
                        contexts = [item.get("text", "") for item in ctx_list]
                    except Exception:
                        pass

                eval_data.append(
                    {
                        "question": question,
                        "answer": answer,
                        "contexts": contexts,
                        "ground_truth": expected_answer,
                    }
                )
                row_mapping.append(row_idx)

            if eval_data:
                ragas_results = run_ragas_evaluation(eval_data)
                for row_idx, scores in zip(row_mapping, ragas_results, strict=False):
                    ws.cell(
                        row=row_idx, column=header.get("ragas_faithfulness", -1)
                    ).value = scores.get("ragas_faithfulness", 0.0)
                    ws.cell(
                        row=row_idx, column=header.get("ragas_answer_relevancy", -1)
                    ).value = scores.get("ragas_answer_relevancy", 0.0)
                    ws.cell(
                        row=row_idx, column=header.get("ragas_context_precision", -1)
                    ).value = scores.get("ragas_context_precision", 0.0)
                    ws.cell(
                        row=row_idx, column=header.get("ragas_context_recall", -1)
                    ).value = scores.get("ragas_context_recall", 0.0)

        # Save workbook
        logger.info(f"Saving evaluation results to {self.output_file}")
        wb.save(self.output_file)
