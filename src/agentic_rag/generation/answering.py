"""Grounded answer generation and citation validation."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from agentic_rag.core.contracts import Answer, Citation, SearchResult
from agentic_rag.generation.llm import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OPENAI_MODEL,
    LLMClient,
    configured_llm_client,
)


def _noop_traceable(*, name: str = "", run_type: str = "chain", **_: object) -> Any:
    def _noop(func: Any) -> Any:
        return func

    return _noop


try:
    from langsmith import traceable as _ls_traceable
except ImportError:
    _ls_traceable = _noop_traceable  # type: ignore[assignment]

NOT_FOUND_ANSWER = "Mình chưa tìm thấy thông tin này trong tài liệu được cung cấp."
MIN_EVIDENCE_TEXT_LENGTH = 12
MAX_AUTO_CITATIONS = 3


@dataclass(frozen=True)
class AnswerDelta:
    """A streamed answer text delta."""

    text: str


@dataclass(frozen=True)
class AnswerDone:
    """The final validated answer for a streamed generation."""

    answer: Answer
    trace: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationResult:
    """Final answer plus internal trace details for observability."""

    answer: Answer
    trace: dict[str, object]


@dataclass(frozen=True)
class ParsedGenerationText:
    """Normalized answer text parsed from a raw LLM response."""

    answer_text: str
    status: str | None
    requested_citation_ids: list[int]
    reason: str | None
    structured: bool


AnswerStreamEvent = AnswerDelta | AnswerDone


@_ls_traceable(name="llm-call", run_type="llm")
def _traced_complete(prompt: str, client: LLMClient) -> str:
    return client.complete(prompt).strip()


@_ls_traceable(name="answer-parse", run_type="tool")
def _traced_parse(
    answer_text: str,
    usable_evidence: list[SearchResult],
) -> tuple[Answer, dict[str, object]]:
    return _answer_from_text_with_trace(answer_text=answer_text, usable_evidence=usable_evidence)


def generate_answer(
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> Answer:
    """Generate a grounded answer from retrieved evidence."""

    return generate_answer_with_trace(
        question=question,
        evidence_context=evidence_context,
        evidence_chunks=evidence_chunks,
    ).answer


def generate_answer_with_trace(
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> GenerationResult:
    """Generate a grounded answer and return trace details for debugging."""

    usable_evidence = _usable_evidence(evidence_chunks)
    if not question.strip() or not usable_evidence:
        answer = Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[])
        return GenerationResult(
            answer=answer,
            trace=_build_generation_trace(
                question=question,
                evidence_chunks=usable_evidence,
                evidence_context=evidence_context,
                prompt="",
                raw_answer="",
                answer=answer,
                parse_trace={},
                guardrail_reason="missing_question_or_evidence",
                llm_source="skipped",
                streaming=False,
            ),
        )

    context = evidence_context.strip() or format_evidence_context(usable_evidence)
    if len(context) < MIN_EVIDENCE_TEXT_LENGTH:
        answer = Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[])
        return GenerationResult(
            answer=answer,
            trace=_build_generation_trace(
                question=question,
                evidence_chunks=usable_evidence,
                evidence_context=context,
                prompt="",
                raw_answer="",
                answer=answer,
                parse_trace={},
                guardrail_reason="evidence_context_too_short",
                llm_source="skipped",
                streaming=False,
            ),
        )

    prompt = build_grounded_prompt(question=question, evidence_context=context)
    client = configured_llm_client()
    llm_source = "configured_llm" if client else "deterministic_fallback"
    answer_text = _traced_complete(prompt, client) if client else _fallback_answer(usable_evidence)
    answer, parse_trace = _traced_parse(answer_text, usable_evidence)

    return GenerationResult(
        answer=answer,
        trace=_build_generation_trace(
            question=question,
            evidence_chunks=usable_evidence,
            evidence_context=context,
            prompt=prompt,
            raw_answer=answer_text,
            answer=answer,
            parse_trace=parse_trace,
            guardrail_reason=_guardrail_reason(answer=answer, parse_trace=parse_trace),
            llm_source=llm_source,
            streaming=False,
        ),
    )


def stream_answer(
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> Iterator[AnswerStreamEvent]:
    """Stream a grounded answer directly from the configured LLM when available."""

    usable_evidence = _usable_evidence(evidence_chunks)
    if not question.strip() or not usable_evidence:
        answer = Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[])
        yield AnswerDone(
            answer,
            _build_generation_trace(
                question=question,
                evidence_chunks=usable_evidence,
                evidence_context=evidence_context,
                prompt="",
                raw_answer="",
                answer=answer,
                parse_trace={},
                guardrail_reason="missing_question_or_evidence",
                llm_source="skipped",
                streaming=True,
            ),
        )
        return

    context = evidence_context.strip() or format_evidence_context(usable_evidence)
    if len(context) < MIN_EVIDENCE_TEXT_LENGTH:
        answer = Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[])
        yield AnswerDone(
            answer,
            _build_generation_trace(
                question=question,
                evidence_chunks=usable_evidence,
                evidence_context=context,
                prompt="",
                raw_answer="",
                answer=answer,
                parse_trace={},
                guardrail_reason="evidence_context_too_short",
                llm_source="skipped",
                streaming=True,
            ),
        )
        return

    prompt = build_grounded_prompt(question=question, evidence_context=context)
    client = configured_llm_client()
    if client is None:
        raw_answer = _fallback_answer(usable_evidence)
        final_answer, parse_trace = _answer_from_text_with_trace(
            answer_text=raw_answer,
            usable_evidence=usable_evidence,
        )
        trace = _build_generation_trace(
            question=question,
            evidence_chunks=usable_evidence,
            evidence_context=context,
            prompt=prompt,
            raw_answer=raw_answer,
            answer=final_answer,
            parse_trace=parse_trace,
            guardrail_reason=_guardrail_reason(answer=final_answer, parse_trace=parse_trace),
            llm_source="deterministic_fallback",
            streaming=True,
        )
        for delta in _chunk_text(final_answer.answer):
            yield AnswerDelta(delta)
        yield AnswerDone(final_answer, trace)
        return

    answer_text = ""

    for delta in client.stream_complete(prompt):
        answer_text += delta
        yield AnswerDelta(delta)

    final_answer, parse_trace = _answer_from_text_with_trace(
        answer_text=answer_text.strip(), usable_evidence=usable_evidence
    )
    if final_answer.status == "answered" and final_answer.answer.startswith(answer_text):
        marker_delta = final_answer.answer[len(answer_text) :]
        if marker_delta:
            yield AnswerDelta(marker_delta)

    yield AnswerDone(
        final_answer,
        _build_generation_trace(
            question=question,
            evidence_chunks=usable_evidence,
            evidence_context=context,
            prompt=prompt,
            raw_answer=answer_text.strip(),
            answer=final_answer,
            parse_trace=parse_trace,
            guardrail_reason=_guardrail_reason(answer=final_answer, parse_trace=parse_trace),
            llm_source="configured_llm",
            streaming=True,
        ),
    )


def apply_citation_markers(answer: str, citations: list[Citation]) -> str:
    """Attach stable citation markers next to supported answer sentences."""

    if not citations:
        return answer

    if _has_citation_marker(answer):
        return answer

    stripped = answer.strip()
    if not stripped:
        return answer

    markers = [f"[{index}]" for index in range(1, len(citations) + 1)]
    paragraphs = [paragraph.strip() for paragraph in stripped.splitlines() if paragraph.strip()]
    if len(paragraphs) >= len(markers):
        marked_paragraphs = [
            _append_marker(paragraph, markers[index]) if index < len(markers) else paragraph
            for index, paragraph in enumerate(paragraphs)
        ]
        return "\n\n".join(marked_paragraphs)

    sentences = _split_sentences(stripped)
    if len(sentences) >= len(markers):
        marked_sentences = [
            _append_marker(sentence, markers[index]) if index < len(markers) else sentence
            for index, sentence in enumerate(sentences)
        ]
        return " ".join(marked_sentences)

    marker_suffix = "".join(markers)
    return _append_marker(stripped, marker_suffix)


def _answer_from_text(answer_text: str, usable_evidence: list[SearchResult]) -> Answer:
    return _answer_from_text_with_trace(
        answer_text=answer_text,
        usable_evidence=usable_evidence,
    )[0]


def _answer_from_text_with_trace(
    answer_text: str,
    usable_evidence: list[SearchResult],
) -> tuple[Answer, dict[str, object]]:
    parsed = _parse_generation_text(answer_text)
    cleaned_answer_text = _strip_trailing_citation_list(parsed.answer_text)
    parse_trace: dict[str, object] = {
        "structured": parsed.structured,
        "requested_citation_ids": parsed.requested_citation_ids,
        "declared_status": parsed.status,
        "reason": parsed.reason,
        "cleaned_answer_preview": cleaned_answer_text[:1000],
    }
    if (
        not cleaned_answer_text
        or parsed.status == "not_found"
        or _is_not_found_answer(cleaned_answer_text)
    ):
        parse_trace["decision"] = "not_found_text"
        return Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[]), parse_trace

    citations = _citations_from_evidence(usable_evidence)
    marked_answer, selected_citations, citation_trace = _select_answer_citations(
        answer_text=cleaned_answer_text,
        citations=citations,
        requested_citation_ids=parsed.requested_citation_ids,
    )
    parse_trace["citation_selection"] = citation_trace
    if not selected_citations:
        parse_trace["decision"] = "no_valid_citation"
        return Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[]), parse_trace

    citation_payload = [citation.model_dump() for citation in selected_citations]
    if not validate_answer_with_citations(marked_answer, citation_payload, usable_evidence):
        parse_trace["decision"] = "citation_validation_failed"
        return Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[]), parse_trace

    parse_trace["decision"] = "answered"
    return Answer(
        answer=marked_answer, status="answered", citations=selected_citations
    ), parse_trace


def validate_answer_with_citations(
    answer: str,
    citations: list[dict[str, object]],
    evidence_chunks: list[SearchResult],
) -> bool:
    """Validate that citations refer only to provided evidence chunks."""

    if _is_not_found_answer(answer):
        return citations == []

    if not answer.strip() or not citations:
        return False

    evidence_by_chunk_id = {result.chunk.chunk_id: result for result in evidence_chunks}
    if not evidence_by_chunk_id:
        return False

    for raw_citation in citations:
        try:
            citation = Citation.model_validate(raw_citation)
        except ValidationError:
            return False

        result = evidence_by_chunk_id.get(citation.chunk_id)
        if result is None:
            return False

        metadata = result.chunk.metadata
        if not _matches_metadata(citation.source, metadata, "source"):
            return False
        if citation.page is not None and not _matches_metadata(citation.page, metadata, "page"):
            return False
        if citation.section is not None and not _matches_metadata(
            citation.section, metadata, "section"
        ):
            return False
        if citation.url is not None and not _matches_metadata(citation.url, metadata, "url"):
            return False

    return True


def build_grounded_prompt(*, question: str, evidence_context: str) -> str:
    """Build a prompt that constrains the LLM to retrieved evidence."""

    return (
        "<task>\n"
        "Answer the user's question using only the supplied evidence.\n"
        "</task>\n\n"
        "<context>\n"
        "<question>\n"
        f"{question.strip()}\n"
        "</question>\n\n"
        "<evidence_context>\n"
        f"{evidence_context.strip()}\n"
        "</evidence_context>\n"
        "</context>\n\n"
        "<instructions>\n"
        "- Answer in Vietnamese.\n"
        "- Be thorough and complete: cover all entities, aspects, or items mentioned "
        "in the question. Do not stop after the first relevant fact.\n"
        "- For comparison or multi-entity questions, address each entity separately "
        "and include all relevant details from the evidence.\n"
        "- Use bullet points or a table when listing specs or comparing multiple items.\n"
        "- Use only the evidence context.\n"
        "- Do not invent facts or citations.\n"
        "- Put citation markers like [1] or [2] immediately after the sentence or "
        "clause supported by that evidence.\n"
        "- Do not put all citation markers at the end of the whole answer.\n"
        "- Do not add a references, sources, bibliography, or citation list at the end.\n"
        "- Every factual sentence must include at least one evidence marker.\n"
        "- Use only marker numbers that appear in the evidence context.\n"
        "- If you return JSON for internal parsing, use keys answer, status, "
        "used_citation_ids, and reason; otherwise return only the user-facing answer.\n"
        f"- If the evidence is insufficient, answer exactly: {NOT_FOUND_ANSWER}\n"
        "</instructions>\n"
    )


def format_evidence_context(evidence_chunks: list[SearchResult]) -> str:
    """Format evidence chunks for an LLM prompt."""

    lines: list[str] = []
    for result in evidence_chunks:
        metadata = result.chunk.metadata
        source = _metadata_value(metadata, "source") or "unknown"
        page = _metadata_value(metadata, "page")
        section = _metadata_value(metadata, "section")
        location = _format_location(page=page, section=section)
        lines.append(
            f"[{result.rank}] chunk_id={result.chunk.chunk_id}; "
            f"source={source}{location}; text={result.chunk.text}"
        )

    return "\n".join(lines)


def _usable_evidence(evidence_chunks: list[SearchResult]) -> list[SearchResult]:
    return [
        result
        for result in sorted(evidence_chunks, key=lambda item: item.rank)
        if len(result.chunk.text.strip()) >= MIN_EVIDENCE_TEXT_LENGTH
    ]


def _chunk_text(text: str, chunk_size: int = 28) -> Iterator[str]:
    for start in range(0, len(text), chunk_size):
        yield text[start : start + chunk_size]


def _fallback_answer(evidence_chunks: list[SearchResult]) -> str:
    evidence_texts = [
        result.chunk.text.strip() for result in evidence_chunks[:3] if result.chunk.text.strip()
    ]
    if not evidence_texts:
        return NOT_FOUND_ANSWER
    return "\n\n".join(evidence_texts)


def _parse_generation_text(answer_text: str) -> ParsedGenerationText:
    raw = answer_text.strip()
    payload = _extract_json_object(raw)
    if payload is None:
        return ParsedGenerationText(
            answer_text=raw,
            status=None,
            requested_citation_ids=[],
            reason=None,
            structured=False,
        )

    answer_value = payload.get("answer")
    if not isinstance(answer_value, str):
        answer_value = raw
    status_value = payload.get("status")
    status = status_value if isinstance(status_value, str) else None
    reason_value = payload.get("reason")
    reason = reason_value if isinstance(reason_value, str) else None
    return ParsedGenerationText(
        answer_text=answer_value,
        status=status,
        requested_citation_ids=_citation_ids_from_payload(payload),
        reason=reason,
        structured=True,
    )


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


def _citation_ids_from_payload(payload: Mapping[str, object]) -> list[int]:
    raw_ids = payload.get("used_citation_ids") or payload.get("used_citations")
    if not isinstance(raw_ids, list):
        return []

    ids: list[int] = []
    for raw_id in raw_ids:
        if isinstance(raw_id, bool):
            continue
        if isinstance(raw_id, int):
            ids.append(raw_id)
        elif isinstance(raw_id, str) and raw_id.strip().isdigit():
            ids.append(int(raw_id.strip()))
    return _unique_preserving_order(ids)


def _select_answer_citations(
    *,
    answer_text: str,
    citations: list[Citation],
    requested_citation_ids: list[int],
) -> tuple[str, list[Citation], dict[str, object]]:
    marker_numbers = citation_markers(answer_text)
    trace: dict[str, object] = {
        "answer_marker_numbers": marker_numbers,
        "requested_citation_ids": requested_citation_ids,
        "available_citation_count": len(citations),
    }

    if marker_numbers:
        if not _valid_citation_numbers(marker_numbers, citations):
            trace["decision"] = "invalid_answer_markers"
            return answer_text, [], trace
        selected = [citations[number - 1] for number in marker_numbers]
        trace["decision"] = "answer_markers"
        trace["selected_citation_ids"] = [citation.chunk_id for citation in selected]
        return _renumber_citation_markers(answer_text, marker_numbers), selected, trace

    if requested_citation_ids:
        if not _valid_citation_numbers(requested_citation_ids, citations):
            trace["decision"] = "invalid_structured_citation_ids"
            return answer_text, [], trace
        selected = [citations[number - 1] for number in requested_citation_ids]
        trace["decision"] = "structured_citation_ids"
        trace["selected_citation_ids"] = [citation.chunk_id for citation in selected]
        return apply_citation_markers(answer_text, selected), selected, trace

    selected = citations[: _auto_citation_count(answer_text, citations)]
    trace["decision"] = "auto_top_evidence"
    trace["selected_citation_ids"] = [citation.chunk_id for citation in selected]
    return apply_citation_markers(answer_text, selected), selected, trace


def citation_markers(answer_text: str) -> list[int]:
    return _unique_preserving_order(
        int(match.group(1)) for match in re.finditer(r"\[(\d+)\]", answer_text)
    )


def _valid_citation_numbers(numbers: list[int], citations: list[Citation]) -> bool:
    return bool(numbers) and all(1 <= number <= len(citations) for number in numbers)


def _renumber_citation_markers(answer_text: str, selected_numbers: list[int]) -> str:
    mapping = {old_number: index for index, old_number in enumerate(selected_numbers, start=1)}

    def replace_marker(match: re.Match[str]) -> str:
        number = int(match.group(1))
        replacement = mapping.get(number)
        return f"[{replacement}]" if replacement is not None else ""

    return re.sub(r"\[(\d+)\]", replace_marker, answer_text)


def _auto_citation_count(answer_text: str, citations: list[Citation]) -> int:
    if not citations:
        return 0
    sentence_count = max(len(_split_sentences(answer_text)), 1)
    return min(len(citations), sentence_count, MAX_AUTO_CITATIONS)


def _unique_preserving_order(values: Iterable[int]) -> list[int]:
    seen: set[int] = set()
    unique: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _citations_from_evidence(evidence_chunks: list[SearchResult]) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[str] = set()

    for result in evidence_chunks:
        chunk = result.chunk
        if chunk.chunk_id in seen:
            continue

        source = _metadata_value(chunk.metadata, "source")
        if source is None:
            continue

        citations.append(
            Citation(
                source=str(source),
                chunk_id=chunk.chunk_id,
                page=_metadata_int(chunk.metadata, "page"),
                section=_metadata_text(chunk.metadata, "section"),
                url=_metadata_text(chunk.metadata, "url"),
            )
        )
        seen.add(chunk.chunk_id)

    return citations


def _matches_metadata(value: object, metadata: Mapping[str, object], key: str) -> bool:
    metadata_value = _metadata_value(metadata, key)
    if metadata_value is None:
        return False
    return str(value) == str(metadata_value)


def _metadata_value(metadata: Mapping[str, object], key: str) -> object | None:
    value = metadata.get(key)
    if value is None:
        return None
    return value


def _metadata_text(metadata: Mapping[str, object], key: str) -> str | None:
    value = _metadata_value(metadata, key)
    if value is None:
        return None
    return str(value)


def _metadata_int(metadata: Mapping[str, object], key: str) -> int | None:
    value = _metadata_value(metadata, key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _format_location(*, page: object | None, section: object | None) -> str:
    parts: list[str] = []
    if page is not None:
        parts.append(f"page={page}")
    if section is not None:
        parts.append(f"section={section}")
    return f"; {', '.join(parts)}" if parts else ""


def _is_not_found_answer(answer: str) -> bool:
    normalized = answer.strip().lower().rstrip(".")
    return normalized in {
        NOT_FOUND_ANSWER.lower().rstrip("."),
        "không có trong tài liệu được cung cấp",
        "không tìm thấy trong tài liệu",
        "không có thông tin trong tài liệu được cung cấp",
        "mình chưa tìm thấy thông tin này trong tài liệu được cung cấp",
        "khong co trong tai lieu",
        "khong tim thay trong tai lieu",
        "khong co thong tin trong tai lieu duoc cung cap",
    }


def _guardrail_reason(*, answer: Answer, parse_trace: Mapping[str, object]) -> str:
    if answer.status == "answered":
        return "answered_with_valid_citations"
    decision = parse_trace.get("decision")
    return decision if isinstance(decision, str) else "not_found"


def _has_citation_marker(answer: str) -> bool:
    return re.search(r"\[\d+\]", answer) is not None


def _split_sentences(answer: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", answer) if sentence.strip()]


def _append_marker(text: str, marker: str) -> str:
    stripped = text.rstrip()
    if not stripped:
        return text
    return f"{stripped} {marker}"


def _strip_trailing_citation_list(answer: str) -> str:
    lines = answer.strip().splitlines()
    while lines and not lines[-1].strip():
        lines.pop()

    strip_from = len(lines)
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index].strip()
        if _is_reference_list_item(line) or _is_reference_heading(line):
            strip_from = index
            continue
        break

    return "\n".join(lines[:strip_from]).strip()


def _is_reference_list_item(line: str) -> bool:
    return re.match(r"^\[\d+\]\s+\S+", line) is not None


def _is_reference_heading(line: str) -> bool:
    normalized = line.lower().rstrip(":")
    return normalized in {
        "references",
        "reference",
        "sources",
        "source",
        "citations",
        "citation",
        "trich dan",
        "nguon",
        "tai lieu tham khao",
    }


def _build_generation_trace(
    *,
    question: str,
    evidence_chunks: list[SearchResult],
    evidence_context: str,
    prompt: str,
    raw_answer: str,
    answer: Answer,
    parse_trace: dict[str, object],
    guardrail_reason: str,
    llm_source: str,
    streaming: bool,
) -> dict[str, object]:
    evidence_ids = [result.chunk.chunk_id for result in evidence_chunks]
    citations = [citation.model_dump() for citation in answer.citations]
    return {
        "prompt_build": {
            "tech": {
                "prompt": "grounded_evidence_prompt",
                "citation_style": "inline_numeric_markers",
                "output_contract": "internal_parse_answer_status_used_citation_ids",
            },
            "latency_ms": 1,
            "input": {
                "question": question,
                "evidence_chunk_ids": evidence_ids,
                "evidence_context_chars": len(evidence_context),
            },
            "output": {
                "prompt_preview": prompt[:2000],
                "instruction_summary": [
                    "answer in Vietnamese",
                    "use only evidence context for document questions",
                    "do not invent facts or citations",
                    "place citation markers next to supported claims",
                    "do not append a separate citation list",
                    "return not_found when evidence is insufficient",
                ],
            },
        },
        "llm_call": {
            "tech": {
                "provider": _configured_llm_provider(),
                "model": _configured_generation_model(),
                "temperature": 0,
                "streaming": streaming,
                "source": llm_source,
            },
            "latency_ms": 5,
            "input": {
                "question": question,
                "prompt_preview": prompt[:2000],
            },
            "output": {
                "raw_answer": raw_answer,
                "raw_answer_preview": raw_answer[:2000],
            },
        },
        "answer_parse": {
            "tech": {
                "steps": [
                    "parse optional JSON answer payload",
                    "strip trailing reference list",
                    "select only citations used by inline markers or structured ids",
                    "renumber citations to match returned citation array",
                ],
            },
            "latency_ms": 5,
            "input": {
                "raw_answer_preview": raw_answer[:2000],
                "evidence_chunk_ids": evidence_ids,
            },
            "output": {
                **parse_trace,
                "answer": answer.answer,
                "status": answer.status,
                "citation_count": len(answer.citations),
            },
        },
        "guardrail_decision": {
            "tech": {
                "method": "question/evidence/citation grounded boundary checks",
            },
            "latency_ms": 1,
            "input": {
                "has_question": bool(question.strip()),
                "evidence_count": len(evidence_chunks),
                "evidence_context_chars": len(evidence_context),
            },
            "output": {
                "status": answer.status,
                "reason": guardrail_reason,
                "not_found_answer": NOT_FOUND_ANSWER if answer.status == "not_found" else None,
            },
        },
        "citation_validation": {
            "tech": {
                "method": "validate citation source/page/section/url against retrieved chunks",
            },
            "latency_ms": 5,
            "input": {
                "citations": citations,
                "evidence_chunk_ids": evidence_ids,
            },
            "output": {
                "valid": answer.status == "not_found" or bool(citations),
                "used_citation_count": len(citations),
                "citations": citations,
            },
        },
    }


def _configured_generation_model() -> str:
    provider = _configured_llm_provider()
    if provider == "ollama":
        return os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    return os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


def _configured_llm_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    return provider or "openai"
