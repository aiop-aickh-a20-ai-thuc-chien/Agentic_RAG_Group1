"""Optional LLM review for URL visual/dynamic artifacts."""

from __future__ import annotations

import json
import re

from agentic_rag.core.contracts import LLMCompletionInput
from agentic_rag.core.ports import LLMClient
from agentic_rag.ingestion.url.llm_review.models import (
    UrlLlmReviewInput,
    UrlLlmReviewOutput,
)
from agentic_rag.ingestion.url.llm_review.validation import validate_review_output
from agentic_rag.model_runtime.errors import (
    ModelInvocationError,
    ModelRuntimeConfigurationError,
)

SYSTEM_MESSAGE = (
    "You review URL ingestion artifacts. Return only JSON. Do not invent price, "
    "model, image URL, availability, warranty, range, or product facts. If a "
    "fact is not present in evidence, put it in unvalidated_facts."
)


def review_url_artifacts_with_llm(
    review_input: UrlLlmReviewInput,
    *,
    client: LLMClient | None = None,
) -> UrlLlmReviewOutput | None:
    """Review URL artifacts with the configured ingestion LLM when available."""

    llm_client = client or _configured_ingestion_client()
    if llm_client is None:
        return None
    request = LLMCompletionInput(
        prompt=_build_review_prompt(review_input),
        system_message=SYSTEM_MESSAGE,
        temperature=0.0,
    )
    try:
        response = llm_client.complete(request)
    except ModelInvocationError:
        return None
    parsed = parse_review_response(response.text)
    if parsed is None:
        return None
    return validate_review_output(parsed, review_input)


def parse_review_response(text: str) -> UrlLlmReviewOutput | None:
    """Parse a JSON object returned by the review LLM."""

    payload = _extract_json_object(text)
    if payload is None:
        return None
    try:
        return UrlLlmReviewOutput.model_validate(payload)
    except ValueError:
        return None


def _configured_ingestion_client() -> LLMClient | None:
    try:
        from agentic_rag.model_runtime.factory import get_llm_client

        return get_llm_client("ingestion")
    except ModelRuntimeConfigurationError:
        return None


def _build_review_prompt(review_input: UrlLlmReviewInput) -> str:
    evidence_payload = [evidence.model_dump(mode="json") for evidence in review_input.evidence]
    payload = {
        "task": review_input.task,
        "markdown": review_input.markdown[:6000],
        "current_metadata": review_input.current_metadata,
        "evidence": evidence_payload,
        "output_schema": {
            "proposed_markdown": "string",
            "semantic_role": "string",
            "field_mapping": {"metadata.field": "exact evidence value"},
            "evidence_refs": ["evidence_id or artifact reference"],
            "confidence": "number 0..1",
            "needs_human_review": "boolean",
            "unvalidated_facts": ["facts not present in evidence"],
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _extract_json_object(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    candidates = [stripped]
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidates.append(stripped[first_brace : last_brace + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


__all__ = ["parse_review_response", "review_url_artifacts_with_llm"]
