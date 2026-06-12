"""Opt-in model verification over deterministically narrowed chunk pairs."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agentic_rag.core.contracts import (
    Chunk,
    KnowledgeQualityFinding,
    LLMCompletionInput,
    LLMCompletionOutput,
)
from agentic_rag.core.ports import LLMClient
from agentic_rag.ingestion.knowledge_quality.registry import (
    KnowledgeQualityInvocationError,
)

_MAX_AGENTIC_CANDIDATE_PAIRS = 20
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_ENTITY_RE = re.compile(r"\b(?:vinfast\s+)?vf\s*-?\s*[0-9][a-z0-9]*(?:\s+plus)?\b", re.I)

ConflictType = Literal[
    "numeric",
    "temporal",
    "policy",
    "entity_relation",
    "causal",
    "exception",
    "recommendation",
]
Verdict = Literal["contradiction", "support", "unrelated", "uncertain"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _VerifierResult(_StrictModel):
    verdict: Verdict
    conflict_type: ConflictType
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_spans: list[str] = Field(default_factory=list)
    reason: str


class _ExtractedClaims(_StrictModel):
    claims: list[str] = Field(min_length=1)


def semantic_verifier_findings(
    chunks: list[Chunk],
    *,
    llm_client: LLMClient,
) -> list[KnowledgeQualityFinding]:
    """Use one strict model verdict for each narrowed candidate pair."""

    findings: list[KnowledgeQualityFinding] = []
    for left, right in candidate_chunk_pairs(chunks):
        output = _complete(
            llm_client,
            system_message=(
                "You are a semantic contradiction verifier. Return only strict JSON "
                "with verdict, conflict_type, confidence, evidence_spans, and reason."
            ),
            prompt=_pair_prompt(left, right),
        )
        result = _parse_verifier_result(output.text)
        if result.verdict == "contradiction":
            findings.append(
                _model_finding(
                    method="semantic_verifier",
                    left=left,
                    right=right,
                    result=result,
                    output=output,
                )
            )
    return findings


def agentic_review_findings(
    chunks: list[Chunk],
    *,
    llm_client: LLMClient,
) -> list[KnowledgeQualityFinding]:
    """Run claim extraction, verification, and arbitration sequentially."""

    findings: list[KnowledgeQualityFinding] = []
    for left, right in candidate_chunk_pairs(
        chunks,
        max_pairs=_MAX_AGENTIC_CANDIDATE_PAIRS,
    ):
        extracted_output = _complete(
            llm_client,
            system_message=(
                "You are the claim extractor. Return only strict JSON with a non-empty "
                "claims array containing the claims that should be compared."
            ),
            prompt=_pair_prompt(left, right),
        )
        extracted = _parse_claims(extracted_output.text)
        verifier_output = _complete(
            llm_client,
            system_message=(
                "You are the verifier. Return only strict JSON with verdict, "
                "conflict_type, confidence, evidence_spans, and reason."
            ),
            prompt=(
                f"Claims: {json.dumps(extracted.claims, ensure_ascii=True)}\n"
                f"{_pair_prompt(left, right)}"
            ),
        )
        verifier = _parse_verifier_result(verifier_output.text)
        arbiter_output = _complete(
            llm_client,
            system_message=(
                "You are the arbiter. Return the final strict JSON verdict with "
                "conflict_type, confidence, evidence_spans, and reason."
            ),
            prompt=(
                f"Extracted claims: {json.dumps(extracted.claims, ensure_ascii=True)}\n"
                f"Verifier result: {verifier.model_dump_json()}\n"
                f"{_pair_prompt(left, right)}"
            ),
        )
        arbiter = _parse_verifier_result(arbiter_output.text)
        if arbiter.verdict == "contradiction":
            findings.append(
                _model_finding(
                    method="agentic_review",
                    left=left,
                    right=right,
                    result=arbiter,
                    output=arbiter_output,
                    agent_notes={
                        "claims": extracted.claims,
                        "verifier": verifier.model_dump(),
                        "arbiter_reason": arbiter.reason,
                    },
                )
            )
    return findings


def candidate_chunk_pairs(
    chunks: list[Chunk],
    *,
    max_pairs: int = 20,
) -> list[tuple[Chunk, Chunk]]:
    """Return stable, topic-related pairs without embeddings or external storage."""

    scored: list[tuple[float, str, str, Chunk, Chunk]] = []
    for left_index, left in enumerate(chunks):
        for right in chunks[left_index + 1 :]:
            if left.chunk_id == right.chunk_id:
                continue
            entity_match = _entity(left.text) == _entity(right.text)
            score = _token_similarity(left.text, right.text)
            if not entity_match or score < 0.35:
                continue
            scored.append(
                (
                    score,
                    min(left.chunk_id, right.chunk_id),
                    max(left.chunk_id, right.chunk_id),
                    left,
                    right,
                )
            )
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [(left, right) for _score, _left_id, _right_id, left, right in scored[:max_pairs]]


def _model_finding(
    *,
    method: str,
    left: Chunk,
    right: Chunk,
    result: _VerifierResult,
    output: LLMCompletionOutput,
    agent_notes: dict[str, object] | None = None,
) -> KnowledgeQualityFinding:
    chunk_ids = sorted([left.chunk_id, right.chunk_id])
    raw_id = f"{method}:{result.conflict_type}:{'|'.join(chunk_ids)}"
    metadata: dict[str, object] = {
        "method": method,
        "conflict_type": result.conflict_type,
        "verdict": result.verdict,
        "evidence_spans": result.evidence_spans,
        "verifier_provider": output.provider,
        "verifier_model": output.model,
    }
    if agent_notes is not None:
        metadata.update(
            {
                "agent_notes": agent_notes,
                "max_candidate_pairs": _MAX_AGENTIC_CANDIDATE_PAIRS,
                "max_rounds": 1,
                "concurrency": 1,
            }
        )
    return KnowledgeQualityFinding(
        finding_id=f"kq-{hashlib.sha1(raw_id.encode()).hexdigest()[:12]}",
        kind="conflict",
        severity="warning",
        chunk_ids=chunk_ids,
        summary=result.reason,
        suggested_action="Review both evidence spans and source authority before answering.",
        confidence=result.confidence,
        metadata=metadata,
    )


def _complete(
    client: LLMClient,
    *,
    system_message: str,
    prompt: str,
) -> LLMCompletionOutput:
    try:
        return client.complete(
            LLMCompletionInput(
                prompt=prompt,
                system_message=system_message,
                temperature=0.0,
            )
        )
    except Exception as exc:
        raise KnowledgeQualityInvocationError(
            f"Knowledge-quality model invocation failed: {exc}"
        ) from exc


def _parse_verifier_result(text: str) -> _VerifierResult:
    try:
        return _VerifierResult.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise KnowledgeQualityInvocationError(
            "Knowledge-quality model did not return valid JSON for the verifier contract."
        ) from exc


def _parse_claims(text: str) -> _ExtractedClaims:
    try:
        return _ExtractedClaims.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise KnowledgeQualityInvocationError(
            "Knowledge-quality claim extractor did not return valid JSON."
        ) from exc


def _pair_prompt(left: Chunk, right: Chunk) -> str:
    return (
        f"LEFT chunk_id={left.chunk_id}:\n{left.text}\n\n"
        f"RIGHT chunk_id={right.chunk_id}:\n{right.text}"
    )


def _entity(text: str) -> str:
    match = _ENTITY_RE.search(text)
    return _normalize(match.group(0)).replace("vinfast ", "") if match else "global"


def _token_similarity(left: str, right: str) -> float:
    left_tokens = set(_TOKEN_RE.findall(_normalize(left)))
    right_tokens = set(_TOKEN_RE.findall(_normalize(right)))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _normalize(value: str) -> str:
    value = value.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())
