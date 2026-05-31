"""Lightweight scoring helpers for PDF parser benchmark outputs."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.ingestion.pdf.benchmarking.manifest import PdfBenchmarkDocument

_VIETNAMESE_DIACRITIC_PATTERN = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễ"
    r"ìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
    r"ùúụủũưừứựửữỳýỵỷỹđ"
    r"ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄ"
    r"ÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ"
    r"ÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]"
)


class _ScoreModel(BaseModel):
    """Shared strict configuration for PDF benchmark score models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class TextOutputScore(_ScoreModel):
    """Automated checks over parser text output for one benchmark document."""

    doc_id: str
    has_vietnamese_diacritics: bool
    matched_snippets: list[str]
    missing_snippets: list[str]
    snippet_recall: float


class HumanReviewScore(_ScoreModel):
    """Human review rubric for Document AI parser output quality."""

    doc_id: str
    parser_name: str
    vietnamese_text: int = Field(ge=0, le=5)
    reading_order: int = Field(ge=0, le=5)
    table_fidelity: int = Field(ge=0, le=5)
    formula_fidelity: int = Field(ge=0, le=5)
    chart_image_usefulness: int = Field(ge=0, le=5)
    rag_readiness: int = Field(ge=0, le=5)
    notes: str = ""

    @property
    def total_score(self) -> int:
        """Total score across all 0-5 rubric dimensions."""

        return (
            self.vietnamese_text
            + self.reading_order
            + self.table_fidelity
            + self.formula_fidelity
            + self.chart_image_usefulness
            + self.rag_readiness
        )

    @property
    def max_score(self) -> int:
        """Maximum possible score for the rubric."""

        return 30


def evaluate_text_output(document: PdfBenchmarkDocument, parsed_text: str) -> TextOutputScore:
    """Run lightweight deterministic checks over parser text output."""

    normalized_output = _normalize_text(parsed_text)
    matched_snippets: list[str] = []
    missing_snippets: list[str] = []

    for snippet in document.expected_snippets:
        if _normalize_text(snippet) in normalized_output:
            matched_snippets.append(snippet)
        else:
            missing_snippets.append(snippet)

    snippet_count = len(document.expected_snippets)
    snippet_recall = len(matched_snippets) / snippet_count if snippet_count else 0.0

    return TextOutputScore(
        doc_id=document.doc_id,
        has_vietnamese_diacritics=bool(_VIETNAMESE_DIACRITIC_PATTERN.search(parsed_text)),
        matched_snippets=matched_snippets,
        missing_snippets=missing_snippets,
        snippet_recall=snippet_recall,
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())
