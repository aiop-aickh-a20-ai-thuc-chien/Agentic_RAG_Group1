"""RAGAS integration for automated LLM-as-a-judge evaluation."""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def run_ragas_evaluation(eval_data: list[dict[str, Any]]) -> list[dict[str, float]]:
    """
    Run RAGAS evaluation on a batch of data.

    Args:
        eval_data: A list of dicts, each containing:
            - question (str)
            - answer (str)
            - contexts (list of str)
            - ground_truth (str)

    Returns:
        A list of dicts containing the scores for each row.
    """
    try:
        from datasets import Dataset
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError:
        logger.error(
            "RAGAS or its dependencies are not installed. "
            "Please install with `pip install -e '.[evaluation]'`."
        )
        raise

    # Prepare dataset
    data = {
        "question": [row["question"] for row in eval_data],
        "answer": [row["answer"] for row in eval_data],
        "contexts": [row["contexts"] for row in eval_data],
        "ground_truth": [row["ground_truth"] for row in eval_data],
    }
    dataset = Dataset.from_dict(data)

    # Configure LLM from env
    model_name = os.getenv("RAGAS_MODEL", "gpt-4o-mini")
    api_key = os.getenv("RAGAS_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

    if not api_key:
        logger.warning("No OpenAI API key found for RAGAS. Evaluation might fail.")

    llm = ChatOpenAI(model=model_name, api_key=api_key)
    embeddings = OpenAIEmbeddings(api_key=api_key)  # type: ignore[call-arg]

    metrics = [
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    ]

    logger.info(
        f"Running RAGAS evaluation on {len(eval_data)} examples using model {model_name}..."
    )

    try:
        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
        )

        # Convert result back to list of dicts for each row
        result_df = result.to_pandas()  # type: ignore[union-attr]
        scores_list = []

        for _, row in result_df.iterrows():
            scores = {
                "ragas_faithfulness": float(row.get("faithfulness", 0.0)),
                "ragas_answer_relevancy": float(row.get("answer_relevancy", 0.0)),
                "ragas_context_precision": float(row.get("context_precision", 0.0)),
                "ragas_context_recall": float(row.get("context_recall", 0.0)),
            }
            scores_list.append(scores)

        return scores_list

    except Exception as e:
        logger.error(f"RAGAS evaluation failed: {e}")
        # Return empty scores if it fails
        return [
            {
                "ragas_faithfulness": 0.0,
                "ragas_answer_relevancy": 0.0,
                "ragas_context_precision": 0.0,
                "ragas_context_recall": 0.0,
            }
            for _ in eval_data
        ]
