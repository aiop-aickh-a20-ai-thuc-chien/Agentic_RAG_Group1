"""Grounded answer generation and citation validation."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from agentic_rag.core.contracts import Answer, Citation, SearchResult
from agentic_rag.generation.llm import configured_llm_client

NOT_FOUND_ANSWER = "Mình chưa tìm thấy thông tin này trong tài liệu được cung cấp."
MIN_EVIDENCE_TEXT_LENGTH = 12


@dataclass(frozen=True)
class AnswerDelta:
    """A streamed answer text delta."""

    text: str


@dataclass(frozen=True)
class AnswerDone:
    """The final validated answer for a streamed generation."""

    answer: Answer


AnswerStreamEvent = AnswerDelta | AnswerDone


def generate_answer(
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> Answer:
    """Generate a grounded answer from retrieved evidence."""

    usable_evidence = _usable_evidence(evidence_chunks)
    if not question.strip() or not usable_evidence:
        return Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[])

    context = evidence_context.strip() or format_evidence_context(usable_evidence)
    if len(context) < MIN_EVIDENCE_TEXT_LENGTH:
        return Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[])

    prompt = build_grounded_prompt(question=question, evidence_context=context)
    client = configured_llm_client()
    answer_text = client.complete(prompt).strip() if client else _fallback_answer(usable_evidence)

    return _answer_from_text(answer_text=answer_text, usable_evidence=usable_evidence)


def stream_answer(
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> Iterator[AnswerStreamEvent]:
    """Stream a grounded answer directly from the configured LLM when available."""

    usable_evidence = _usable_evidence(evidence_chunks)
    if not question.strip() or not usable_evidence:
        yield AnswerDone(Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[]))
        return

    context = evidence_context.strip() or format_evidence_context(usable_evidence)
    if len(context) < MIN_EVIDENCE_TEXT_LENGTH:
        yield AnswerDone(Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[]))
        return

    prompt = build_grounded_prompt(question=question, evidence_context=context)
    client = configured_llm_client()
    if client is None:
        final_answer = _answer_from_text(
            answer_text=_fallback_answer(usable_evidence),
            usable_evidence=usable_evidence,
        )
        for delta in _chunk_text(final_answer.answer):
            yield AnswerDelta(delta)
        yield AnswerDone(final_answer)
        return

    answer_text = ""

    for delta in client.stream_complete(prompt):
        answer_text += delta
        yield AnswerDelta(delta)

    final_answer = _answer_from_text(
        answer_text=answer_text.strip(), usable_evidence=usable_evidence
    )
    if final_answer.status == "answered" and final_answer.answer.startswith(answer_text):
        marker_delta = final_answer.answer[len(answer_text) :]
        if marker_delta:
            yield AnswerDelta(marker_delta)

    yield AnswerDone(final_answer)


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
    cleaned_answer_text = _strip_trailing_citation_list(answer_text)
    if not cleaned_answer_text or _is_not_found_answer(cleaned_answer_text):
        return Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[])

    citations = _citations_from_evidence(usable_evidence)
    citation_payload = [citation.model_dump() for citation in citations]
    if not validate_answer_with_citations(cleaned_answer_text, citation_payload, usable_evidence):
        return Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[])

    marked_answer = apply_citation_markers(cleaned_answer_text, citations)
    return Answer(answer=marked_answer, status="answered", citations=citations)


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
        "Question:\n"
        f"{question.strip()}\n\n"
        "Evidence context:\n"
        f"{evidence_context.strip()}\n\n"
        "Instructions:\n"
        "- Answer in Vietnamese.\n"
        "- Use only the evidence context.\n"
        "- Do not invent facts or citations.\n"
        "- Put citation markers like [1] or [2] immediately after the sentence or "
        "clause supported by that evidence.\n"
        "- Do not put all citation markers at the end of the whole answer.\n"
        "- Do not add a references, sources, bibliography, or citation list at the end.\n"
        "- Every factual sentence must include at least one evidence marker.\n"
        "- Use only marker numbers that appear in the evidence context.\n"
        f"- If the evidence is insufficient, answer exactly: {NOT_FOUND_ANSWER}\n"
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
