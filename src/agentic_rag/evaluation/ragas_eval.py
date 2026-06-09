"""Typed deferred RAGAS integration boundary for LLM-as-a-judge evaluation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _RagasModel(BaseModel):
    """Base model for immutable RAGAS evaluation boundary objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class RagasEvaluationInput(_RagasModel):
    """One RAGAS evaluation item prepared from an evaluation workbook row."""

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    contexts: list[str] = Field(default_factory=list)
    ground_truth: str = ""


class RagasEvaluationScores(_RagasModel):
    """RAGAS metric scores aligned to evaluation workbook columns."""

    ragas_faithfulness: float = 0.0
    ragas_answer_relevancy: float = 0.0
    ragas_context_precision: float = 0.0
    ragas_context_recall: float = 0.0


class RagasEvaluationDeferredError(RuntimeError):
    """Raised while automated RAGAS execution remains intentionally deferred."""


RAGAS_DEFERRED_MESSAGE = (
    "RAGAS evaluation is deferred in the model-runtime refactor. "
    "Install the evaluation extra and complete the RAGAS/LangChain compatibility "
    "repair before enabling automated RAGAS scoring."
)


def run_ragas_evaluation(eval_data: list[RagasEvaluationInput]) -> list[RagasEvaluationScores]:
    """Validate typed input and return deferred zero scores until RAGAS repair lands."""

    validated = [RagasEvaluationInput.model_validate(item) for item in eval_data]
    return [RagasEvaluationScores() for _ in validated]
