"""CLI script to run the automated evaluation pipeline."""

import argparse
import logging
import sys

from agentic_rag.evaluation.runner import EvaluationRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAG evaluation pipeline.")
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Path to the input evaluation dataset (Excel file).",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path to save the output evaluation results (Excel file).",
    )
    parser.add_argument(
        "--ragas",
        action="store_true",
        help="Run LLM-as-a-judge evaluation using RAGAS on the results.",
    )
    args = parser.parse_args()

    try:
        runner = EvaluationRunner(
            input_file=args.input, output_file=args.output, run_ragas=args.ragas
        )
        runner.run()
        logger.info("Evaluation completed successfully.")
        return 0
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
