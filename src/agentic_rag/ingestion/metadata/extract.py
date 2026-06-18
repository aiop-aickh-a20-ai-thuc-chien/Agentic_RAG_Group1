"""LLM-based metadata extraction — stage [L] of the metadata pipeline.

This stage takes the rule-based ``[P]`` fields already present on a chunk as
*context* and asks the configured ``ingestion`` LLM (resolved from the env file,
see ``INGESTION_LLM_*`` / ``LLM_*``) to produce the semantic fields in a single
structured call.

⚠️ The OUTPUT of this stage is :class:`LLMExtractedMetadata` — a deliberately
small schema kept SEPARATE from :class:`ChunkMetadata`, so the LLM-extracted
subset never gets confused with the full unified chunk metadata. Only the seven
fields declared on :class:`LLMExtractedMetadata` are produced here; every other
field on a chunk comes from the rule-based loaders or the storage layer.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agentic_rag.ingestion.metadata.schema import (
    DOCUMENT_TYPE_VALUES,
    LANGUAGE_VALUES,
    ChunkMetadata,
)

if TYPE_CHECKING:
    # Imported only for typing: the metadata package is imported *by*
    # core.contracts, so importing it back here at runtime would be circular.
    from agentic_rag.core.contracts import Chunk
    from agentic_rag.core.ports import LLMClient

# --- tuning knobs (keep the single call bounded and deterministic) -----------
MAX_CONTENT_CHARS: Final[int] = 6000
MAX_CONTEXT_FIELD_CHARS: Final[int] = 300
MIN_CONTENT_CHARS: Final[int] = 40
MAX_LIST_ITEMS: Final[int] = 8
DEFAULT_DOCUMENT_TYPE: Final[str] = "unknown"
DEFAULT_LANGUAGE: Final[str] = "unknown"

EXTRACTION_SYSTEM_MESSAGE: Final[str] = (
    "Bạn là bộ trích xuất metadata cho hệ thống RAG tiếng Việt về xe điện. "
    "Chỉ trả về DUY NHẤT một JSON object đúng schema được yêu cầu, "
    "không thêm giải thích, markdown hay code fence."
)


class MetadataExtractionInput(BaseModel):
    """The context fed to the LLM for one chunk (input, not output)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    title: str | None = None
    section: str | None = None
    section_path: list[str] = Field(default_factory=list)
    source_type: str | None = None
    source_hint: str | None = None  # file_name or url


class LLMExtractedMetadata(BaseModel):
    """⚠️ LLM Extract OUTPUT schema — the ``[L]`` subset ONLY (not ChunkMetadata).

    Exactly these seven fields are produced by the LLM Extract stage:

    - ``summary``       : 1-2 sentence summary of the chunk        (retrieval)
    - ``keywords``      : salient keywords                         (retrieval)
    - ``questions``     : questions this chunk can answer          (retrieval)
    - ``entities``      : named entities mentioned                 (retrieval)
    - ``document_type`` : enum in DOCUMENT_TYPE_VALUES             (filter)
    - ``language``      : enum in LANGUAGE_VALUES                  (filter)
    - ``quality_score`` : 0.0-1.0 self-contained/usefulness rating (ranking)
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    document_type: str = DEFAULT_DOCUMENT_TYPE
    language: str = DEFAULT_LANGUAGE
    quality_score: float | None = None

    @field_validator("summary", mode="before")
    @classmethod
    def _coerce_summary(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("keywords", "questions", "entities", mode="before")
    @classmethod
    def _coerce_list(cls, value: object) -> list[str]:
        if isinstance(value, (list, tuple)):
            raw_items: list[object] = list(value)
        elif isinstance(value, str):
            raw_items = [value]
        else:
            return []

        cleaned: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            text = str(item).strip()
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                cleaned.append(text)
        return cleaned[:MAX_LIST_ITEMS]

    @field_validator("document_type", mode="before")
    @classmethod
    def _coerce_document_type(cls, value: object) -> str:
        return _coerce_enum(value, DOCUMENT_TYPE_VALUES, DEFAULT_DOCUMENT_TYPE)

    @field_validator("language", mode="before")
    @classmethod
    def _coerce_language(cls, value: object) -> str:
        return _coerce_enum(value, LANGUAGE_VALUES, DEFAULT_LANGUAGE)

    @field_validator("quality_score", mode="before")
    @classmethod
    def _coerce_quality_score(cls, value: object) -> float | None:
        # bool is an int subclass — reject it so True/False never become 1.0/0.0.
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        if isinstance(value, str):
            try:
                return max(0.0, min(1.0, float(value.strip())))
            except ValueError:
                return None
        return None


def build_extraction_input(chunk: Chunk) -> MetadataExtractionInput:
    """Build the LLM input context from a chunk's rule-based [P] metadata."""

    metadata = chunk.metadata
    source_hint = metadata.get("file_name") or metadata.get("url") or metadata.get("source")
    section_path = metadata.get("section_path") or []
    return MetadataExtractionInput(
        text=chunk.text,
        title=metadata.get("title"),
        section=metadata.get("section"),
        section_path=[str(part) for part in section_path],
        source_type=metadata.get("source_type"),
        source_hint=str(source_hint) if source_hint is not None else None,
    )


def build_extraction_prompt(payload: MetadataExtractionInput) -> str:
    """Render the XML extraction prompt for one chunk."""

    section_path = " > ".join(payload.section_path)
    document_types = "|".join(sorted(DOCUMENT_TYPE_VALUES))
    languages = "|".join(sorted(LANGUAGE_VALUES))
    content = _clip_content(payload.text, MAX_CONTENT_CHARS)

    lines: list[str] = [
        "<task>",
        "Trích xuất metadata ngữ nghĩa cho một đoạn (chunk) tài liệu,",
        "phục vụ tìm kiếm và lọc trong hệ thống RAG.",
        "</task>",
        "",
        "<context>",
        f"  <title>{_clip_field(payload.title)}</title>",
        f"  <section>{_clip_field(payload.section)}</section>",
        f"  <section_path>{_clip_field(section_path)}</section_path>",
        f"  <source_type>{_clip_field(payload.source_type)}</source_type>",
        f"  <source>{_clip_field(payload.source_hint)}</source>",
        "</context>",
        "",
        "<content>",
        content,
        "</content>",
        "",
        "<output_schema>",
        "Trả về DUY NHẤT một JSON object với đúng các khóa sau:",
        "{",
        '  "summary": "1-2 câu tóm tắt nội dung chính của đoạn",',
        f'  "keywords": ["tối đa {MAX_LIST_ITEMS} từ khóa nổi bật"],',
        '  "questions": ["2-4 câu hỏi mà đoạn này trả lời được"],',
        '  "entities": ["tên riêng: sản phẩm, model, tổ chức, địa điểm, chính sách"],',
        f'  "document_type": "một trong: {document_types}",',
        f'  "language": "một trong: {languages}",',
        '  "quality_score": 0.0',
        "}",
        "</output_schema>",
        "",
        "<instructions>",
        "- Chỉ dùng thông tin trong <content>; <context> chỉ để định hướng.",
        "- Viết summary/keywords/questions bằng đúng ngôn ngữ của nội dung.",
        "- document_type và language phải thuộc tập giá trị cho phép;",
        '  nếu không chắc, dùng "unknown".',
        "- quality_score: số thực 0.0-1.0 — đoạn càng tự chứa, rõ ràng và",
        "  nhiều thông tin hữu ích cho việc trả lời thì điểm càng cao.",
        "- Trả về JSON thuần: KHÔNG markdown, KHÔNG giải thích, KHÔNG code fence.",
        "</instructions>",
    ]
    return "\n".join(lines)


def parse_extraction_response(text: str) -> LLMExtractedMetadata | None:
    """Parse and validate a raw LLM response into the LLM Extract schema."""

    payload = _extract_json_object(text)
    if payload is None:
        return None
    try:
        return LLMExtractedMetadata.model_validate(payload)
    except ValidationError:
        return None


def extract_chunk_metadata(
    source: Chunk | MetadataExtractionInput,
    *,
    client: LLMClient | None = None,
) -> LLMExtractedMetadata | None:
    """Run the LLM Extract stage for one chunk.

    Returns ``None`` (and leaves the chunk on rule-based metadata only) when no
    ingestion LLM is configured, the content is too short, or the call/parse
    fails — extraction never raises into the ingestion path.
    """

    if isinstance(source, MetadataExtractionInput):
        payload = source
    else:
        payload = build_extraction_input(source)
    if len(payload.text.strip()) < MIN_CONTENT_CHARS:
        return None

    # Lazy imports keep the metadata package free of a runtime dependency on
    # core.contracts / model_runtime (both of which import this package).
    from agentic_rag.core.contracts import LLMCompletionInput
    from agentic_rag.model_runtime.errors import ModelInvocationError

    if client is None:
        from agentic_rag.model_runtime.factory import get_llm_client

        client = get_llm_client("ingestion")
    if client is None:
        return None

    request = LLMCompletionInput(
        prompt=build_extraction_prompt(payload),
        system_message=EXTRACTION_SYSTEM_MESSAGE,
        temperature=0.0,
    )
    try:
        response = client.complete(request)
    except ModelInvocationError:
        return None
    return parse_extraction_response(response.text)


def apply_extracted_metadata(
    metadata: ChunkMetadata, extracted: LLMExtractedMetadata
) -> ChunkMetadata:
    """Write the LLM Extract ``[L]`` fields onto an existing ChunkMetadata in place."""

    metadata["summary"] = extracted.summary or None
    metadata["keywords"] = list(extracted.keywords)
    metadata["questions"] = list(extracted.questions)
    metadata["entities"] = list(extracted.entities)
    metadata["document_type"] = extracted.document_type
    metadata["language"] = extracted.language
    metadata["quality_score"] = extracted.quality_score
    return metadata


def _coerce_enum(value: object, allowed: frozenset[str], default: str) -> str:
    if not isinstance(value, str):
        return default
    candidate = value.strip().lower()
    return candidate if candidate in allowed else default


def _clip_field(value: str | None) -> str:
    if not value:
        return ""
    compact = " ".join(value.split())
    if len(compact) <= MAX_CONTEXT_FIELD_CHARS:
        return compact
    return compact[: MAX_CONTEXT_FIELD_CHARS - 1] + "…"


def _clip_content(value: str, limit: int) -> str:
    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1] + "…"


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
