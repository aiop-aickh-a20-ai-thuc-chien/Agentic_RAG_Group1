"""Pydantic models cho eval pipeline API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ── Dataset ───────────────────────────────────────────────────────────────────


class DatasetCreate(BaseModel):
    name: str
    description: str | None = None
    is_benchmark: bool = False


class Dataset(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_benchmark: bool
    created_at: datetime


# ── Question (draft) ──────────────────────────────────────────────────────────


class QuestionCreate(BaseModel):
    # Sinh câu là bước toàn cục — KHÔNG gắn dataset. Gán dataset là bước sau
    # (trang Datasets, qua eval_dataset_questions).
    dataset_id: UUID | None = None
    document_id: str
    section: str | None = None
    question: str
    ground_truth: str
    source_chunk_ids: list[str] = Field(default_factory=list)


class Question(BaseModel):
    id: UUID
    dataset_id: UUID | None
    document_id: str
    section: str | None
    question: str
    ground_truth: str
    source_chunk_ids: list[str]
    deleted_at: datetime | None
    created_at: datetime


class QuestionWithStatus(Question):
    is_approved: bool = False
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    has_results: bool = False
    global_seq: int = 0


class QuestionUpdate(BaseModel):
    question: str | None = None
    ground_truth: str | None = None


# ── Approve ───────────────────────────────────────────────────────────────────


class ApproveRequest(BaseModel):
    question_ids: list[UUID]
    reviewed_by: str = "internal"


# ── Eval Run ──────────────────────────────────────────────────────────────────


class RunCreate(BaseModel):
    dataset_id: UUID
    name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    question_ids: list[UUID] | None = None  # None = toàn bộ dataset


class EvalRun(BaseModel):
    id: UUID
    dataset_id: UUID | None
    name: str
    description: str | None
    config: dict[str, Any]
    status: str
    total: int
    success: int
    failed: int
    created_at: datetime
    completed_at: datetime | None


class RunProgress(BaseModel):
    run_id: UUID
    status: str
    total: int
    success: int
    failed: int
    not_started: int
    ragas_done: int = 0


# ── Eval Result ───────────────────────────────────────────────────────────────


class EvalResult(BaseModel):
    id: UUID
    question_id: UUID
    run_id: UUID
    rag_context: str | None
    bot_response: str | None
    bot_citations: list[Any] | None
    trace_url: str | None
    retrieved_top5_ids: list[str] | None
    ground_truth_rank: int | None
    recall_at_5: float | None
    mrr_at_5: float | None
    citation_chunk_match: float | None
    guardrail_pass: bool | None
    ragas_faithfulness: float | None
    ragas_answer_relevancy: float | None
    ragas_context_precision: float | None
    ragas_context_recall: float | None
    eval_error: str | None
    ran_at: datetime | None


# ── AutoData Generate ─────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    document_id: str
    dataset_id: UUID | None = None  # sinh câu toàn cục, dataset gán sau
    section_filters: list[str] | None = None  # None = toàn bộ document
    questions_per_section: int = Field(default=3, ge=1, le=10)
    custom_prompt: str | None = None  # template với {n}/{section}/{context}; None = dùng mặc định


class GenerateBulkRequest(BaseModel):
    """Sinh câu cho nhiều document cùng lúc."""

    dataset_id: UUID | None = None  # sinh câu toàn cục, dataset gán sau
    document_ids: list[str]
    questions_per_section: int = Field(default=3, ge=1, le=10)
    only_missing: bool = True  # chỉ sinh cho section chưa có câu (resumable)
    custom_prompt: str | None = None


class GenerateJob(BaseModel):
    job_id: str
    status: str
    message: str
    total_sections: int = 0
    done_sections: int = 0
    questions_created: int = 0


# ── Compare ───────────────────────────────────────────────────────────────────


class RunSummary(BaseModel):
    run_id: UUID
    name: str
    config: dict[str, Any]
    total_questions: int
    avg_recall: float | None
    avg_mrr: float | None
    avg_citation: float | None
    guardrail_rate: float | None
    has_ragas: bool
    avg_ragas_faithfulness: float | None
    avg_ragas_relevancy: float | None
