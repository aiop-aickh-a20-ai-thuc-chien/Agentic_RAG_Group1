"""Graders for document relevance, hallucination, and answer quality."""

from __future__ import annotations

import json
import re
from typing import Any

from agentic_rag.core.contracts import Answer, LLMCompletionInput, SearchResult
from agentic_rag.core.ports import LLMClient
from agentic_rag.generation.answering import GROUNDING_SYSTEM_MESSAGE
from agentic_rag.retrieval.fusion import build_evidence_context


def _noop_traceable(*, name: str = "", run_type: str = "chain", **_: object) -> Any:
    def _noop(func: Any) -> Any:
        return func

    return _noop


try:
    from langsmith import traceable as _ls_traceable
except ImportError:
    _ls_traceable = _noop_traceable  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PREPROCESS_PROMPT = """\
<task>
Choose the best preprocessing action for the current user question, \
then identify which entities from the menu below are relevant.
</task>

<actions>
1. If the question uses pronouns or references previous messages \
("nó", "cái đó", "còn X thì?", "thế còn..."), \
rewrite it as a complete standalone question preserving the original intent.
2. If the question asks about 2+ clearly distinct topics at the same time, \
split into separate sub-questions.
3. For comparison questions with multiple entities/models, use multi and split \
by entity/model first. Each sub-question should retrieve comparable facts for \
one entity/model. Do not split by aspect if every sub-question still contains \
all compared entities.
   Good example for "so sánh VF3 và VF7":
   ["thông tin tổng quan, giá bán và thông số kỹ thuật của VF 3",
    "thông tin tổng quan, giá bán và thông số kỹ thuật của VF 7"]
   Bad example:
   ["so sánh thiết kế VF3 và VF7", "so sánh tính năng VF3 và VF7"]
4. If the question is already clear and standalone, keep it exactly as-is.
</actions>

<entity_menu>
{entity_menu}
</entity_menu>

<context>
<conversation_history>
{history}
</conversation_history>

<current_question>
{question}
</current_question>
</context>

<output>
Return JSON only. Keep rewritten questions in the same language as the original question.
"entities" must only contain names EXACTLY as written in the entity_menu. Use [] if none apply.
Examples: 'Vinfast 8' → 'VF 8', 'xe 7 chỗ điện' → 'VF 9', 'VF9' → 'VF 9'.
  Single question: {{"type": "single", "question": "...", "entities": ["canonical1"]}}
  Multiple:        {{"type": "multi",  "questions": ["q1", "q2"], "entities": [["VF 8"], ["VF 9"]]}}
For multi, "entities" is a list of lists — one list per question, same order.
</output>"""

_GRADE_HALLUCINATION_PROMPT = """\
<task>
Check whether every factual claim in the answer is supported by the evidence.
</task>

<context>
<question>
{question}
</question>

<answer>
{answer}
</answer>

<evidence>
{evidence_context}
</evidence>
</context>

<rules>
Do NOT penalize "not found" answers — those are grounded by definition.
</rules>

<output>
Return JSON only: {{"grounded": true/false, "reason": "one sentence"}}
</output>"""


_TRANSFORM_QUERY_PROMPT = """\
<task>
Rewrite the search query to find missing information. Choose ONE:
</task>

<methods>
- decompose: question has 2+ distinct parts -> split into sub-queries
- expand:    query too narrow -> rephrase or broaden
- requery:   specific gap -> targeted query for what's missing
</methods>

<context>
<reason>
The search results were insufficient to answer the question.
</reason>

<question>
{question}
</question>

<queries_already_tried>
{queries_tried}
</queries_already_tried>

<evidence_summary chunk_count="{chunk_count}">
{evidence_summary}
</evidence_summary>

<missing_coverage>
{missing_entities}
</missing_coverage>
</context>

<rules>
For comparison questions with multiple entities/models, prefer decompose by \
entity/model when evidence is missing or imbalanced. Each query should focus on \
one entity/model and ask for comparable facts/specs/pricing needed to answer the \
comparison. Do not output sub-queries that all still contain every compared \
entity.
Good example for "so sánh VF3 và VF7":
  ["thông tin tổng quan, giá bán và thông số kỹ thuật của VF 3",
   "thông tin tổng quan, giá bán và thông số kỹ thuật của VF 7"]
</rules>

<output>
Return JSON only. Keep queries in the same language as the original question.
  {{"method": "decompose", "queries": ["q1", "q2"]}}
  {{"method": "expand",    "query": "broader query"}}
  {{"method": "requery",   "query": "gap-fill query"}}
</output>"""


# ---------------------------------------------------------------------------
# Public graders
# ---------------------------------------------------------------------------

_MULTI_INTENT_SIGNALS = {
    # Vietnamese
    "và",
    "so sánh",
    "vs",
    "hoặc",
    "cũng như",
    "khác nhau",
    "giống nhau",
    # English
    "compare",
    "versus",
    "difference",
    "between",
    "also",
}
_HISTORY_SIGNALS = {
    # Vietnamese
    "nó",
    "cái đó",
    "điều đó",
    "thế còn",
    "còn",
    "vậy còn",
    "thêm",
    # English
    "it",
    "that",
    "what about",
    "how about",
}


def preprocess_query(
    question: str,
    history: list[dict[str, str]],
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    """Rewrite with history context and/or decompose multi-intent queries.

    Returns {"type": "single", "question": "...", "entities": [...]} or
            {"type": "multi",  "questions": [...], "entities": [[...], [...]]}
    "entities" contains validated canonical names from the allowlist.
    Falls back to single passthrough (no entities key) when no LLM or simple query.
    """
    q_lower = question.lower()
    has_history = bool(history)
    has_multi = any(s in q_lower for s in _MULTI_INTENT_SIGNALS)
    has_ref = any(re.search(r"\b" + re.escape(s) + r"\b", q_lower) for s in _HISTORY_SIGNALS)

    if not (has_history or has_multi or has_ref) or llm_client is None:
        return {"type": "single", "question": question}

    history_text = (
        "\n".join(
            f"{m.get('role', 'user').capitalize()}: {m.get('content', '')}"
            for m in history[-6:]  # last 3 turns
        )
        or "none"
    )

    from agentic_rag.ingestion.metadata import allowlisted_canonicals, build_entity_menu

    prompt = _PREPROCESS_PROMPT.format(
        entity_menu=build_entity_menu(),
        history=history_text,
        question=question,
    )
    try:
        raw = _traced_preprocess_llm(prompt, llm_client)
        result: dict[str, Any] = json.loads(raw)
        if result.get("type") not in {"single", "multi"}:
            return {"type": "single", "question": question}
        allow = allowlisted_canonicals()
        if result["type"] == "single":
            raw_ents = result.get("entities") or []
            result["entities"] = [e for e in raw_ents if e in allow]
        else:
            questions = result.get("questions") or []
            raw_ents_list = result.get("entities") or []
            result["entities"] = [
                [e for e in (raw_ents_list[i] if i < len(raw_ents_list) else []) if e in allow]
                for i in range(len(questions))
            ]
        return result
    except Exception:
        return {"type": "single", "question": question}


def grade_hallucination(
    question: str,
    answer: Answer,
    docs: list[SearchResult],
    llm_client: LLMClient | None = None,
) -> bool:
    """Return True if answer is grounded in evidence."""
    if answer.status == "not_found":
        return True
    if not docs:
        return False
    if llm_client is None:
        from agentic_rag.generation.answering import validate_answer_with_citations

        citations = [c.model_dump() for c in answer.citations]
        return validate_answer_with_citations(answer.answer, citations, docs)

    try:
        context = build_evidence_context(docs)
        prompt = _GRADE_HALLUCINATION_PROMPT.format(
            question=question,
            answer=answer.answer,
            evidence_context=context,
        )
        raw = _traced_hallucination_llm(prompt, llm_client)
        payload = json.loads(raw)
        return bool(payload.get("grounded", True))
    except Exception:
        return True


def transform_query(
    question: str,
    docs: list[SearchResult],
    queries_tried: list[str],
    missing_entities: list[str] | None = None,
    llm_client: LLMClient | None = None,
    lang: str = "vi",
) -> dict[str, Any]:
    """Return {"method": ..., "query"/"queries": ...} for next retrieval."""
    if llm_client is None:
        return {"method": "requery", "query": question}

    summary = _evidence_summary(docs)
    if lang == "en":
        missing_text = (
            "Missing information for: " + ", ".join(missing_entities)
            if missing_entities
            else "Could not determine what is missing."
        )
    else:
        missing_text = (
            "Các phần còn thiếu thông tin: " + ", ".join(missing_entities)
            if missing_entities
            else "Không xác định được phần còn thiếu."
        )
    prompt = _TRANSFORM_QUERY_PROMPT.format(
        question=question,
        queries_tried=", ".join(queries_tried) if queries_tried else "none",
        chunk_count=len(docs),
        evidence_summary=summary,
        missing_entities=missing_text,
    )
    try:
        raw = _traced_transform_llm(prompt, llm_client)
        result: dict[str, Any] = json.loads(raw)
        if result.get("method") not in {"decompose", "expand", "requery"}:
            result["method"] = "requery"
        return result
    except Exception:
        return {"method": "requery", "query": question}


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------


def _evidence_summary(docs: list[SearchResult]) -> str:
    if not docs:
        return "none"
    return "; ".join(d.chunk.text[:80].replace("\n", " ") for d in docs[:3])


@_ls_traceable(name="preprocess-llm", run_type="llm")
def _traced_preprocess_llm(prompt: str, llm_client: LLMClient) -> str:
    return _complete_text(prompt, llm_client)


@_ls_traceable(name="grade-hallucination-llm", run_type="llm")
def _traced_hallucination_llm(prompt: str, llm_client: LLMClient) -> str:
    return _complete_text(prompt, llm_client)


@_ls_traceable(name="transform-query-llm", run_type="llm")
def _traced_transform_llm(prompt: str, llm_client: LLMClient) -> str:
    return _complete_text(prompt, llm_client)


def _complete_text(prompt: str, llm_client: LLMClient) -> str:
    return llm_client.complete(
        LLMCompletionInput(prompt=prompt, system_message=GROUNDING_SYSTEM_MESSAGE)
    ).text
