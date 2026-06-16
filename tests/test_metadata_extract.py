"""Unit tests for the LLM Extract metadata stage (no network calls)."""

from __future__ import annotations

from collections.abc import Iterator

from agentic_rag.core.contracts import LLMCompletionInput, LLMCompletionOutput, LLMStreamDelta
from agentic_rag.ingestion.metadata import (
    LLMExtractedMetadata,
    MetadataExtractionInput,
    apply_extracted_metadata,
    build_extraction_prompt,
    extract_chunk_metadata,
    parse_extraction_response,
)
from agentic_rag.ingestion.metadata.schema import ChunkMetadata

LONG_TEXT = (
    "VinFast VF e34 có quãng đường di chuyển khoảng 285 km mỗi lần sạc đầy. "
    "Chính sách bảo hành pin áp dụng trong 10 năm."
)


class _FakeClient:
    """Minimal LLMClient stub returning a canned completion."""

    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, request: LLMCompletionInput) -> LLMCompletionOutput:
        return LLMCompletionOutput(text=self._text, provider="test", model="test")

    def stream(self, request: LLMCompletionInput) -> Iterator[LLMStreamDelta]:
        yield from ()


def test_output_schema_coerces_string_and_enums() -> None:
    extracted = LLMExtractedMetadata.model_validate(
        {
            "summary": "  Tóm tắt  ",
            "keywords": "pin",  # string coerced to list
            "questions": ["Quãng đường?", "quãng đường?", ""],  # dedup + drop empty
            "entities": ["VF e34"],
            "document_type": "SPEC_SHEET",  # case-insensitive enum
            "language": "klingon",  # invalid -> unknown
        }
    )
    assert extracted.summary == "Tóm tắt"
    assert extracted.keywords == ["pin"]
    assert extracted.questions == ["Quãng đường?"]
    assert extracted.document_type == "spec_sheet"
    assert extracted.language == "unknown"


def test_parse_extraction_response_strips_code_fence() -> None:
    raw = '```json\n{"summary": "ok", "language": "vi"}\n```'
    extracted = parse_extraction_response(raw)
    assert extracted is not None
    assert extracted.summary == "ok"
    assert extracted.language == "vi"


def test_parse_extraction_response_rejects_non_json() -> None:
    assert parse_extraction_response("not json at all") is None


def test_build_extraction_prompt_contains_context_and_schema() -> None:
    payload = MetadataExtractionInput(
        text=LONG_TEXT,
        title="Cẩm nang VF e34",
        section="Quãng đường",
        section_path=["Thông số", "Pin"],
        source_type="pdf",
        source_hint="vfe34.pdf",
    )
    prompt = build_extraction_prompt(payload)
    assert "<output_schema>" in prompt
    assert "Cẩm nang VF e34" in prompt
    assert "Thông số > Pin" in prompt
    assert "spec_sheet" in prompt  # enum values rendered


def test_extract_chunk_metadata_uses_injected_client() -> None:
    client = _FakeClient(
        '{"summary": "Quãng đường VF e34", "keywords": ["pin", "quãng đường"], '
        '"questions": ["Quãng đường bao xa?"], "entities": ["VF e34"], '
        '"document_type": "spec_sheet", "language": "vi"}'
    )
    payload = MetadataExtractionInput(text=LONG_TEXT, source_type="pdf")
    extracted = extract_chunk_metadata(payload, client=client)
    assert extracted is not None
    assert extracted.document_type == "spec_sheet"
    assert "pin" in extracted.keywords


def test_extract_chunk_metadata_skips_short_text() -> None:
    payload = MetadataExtractionInput(text="quá ngắn")
    assert extract_chunk_metadata(payload, client=_FakeClient("{}")) is None


def test_apply_extracted_metadata_writes_llm_fields() -> None:
    metadata = ChunkMetadata(chunk_id="c1", source_type="pdf")
    extracted = LLMExtractedMetadata(
        summary="Tóm tắt",
        keywords=["pin"],
        questions=["Quãng đường?"],
        entities=["VF e34"],
        document_type="spec_sheet",
        language="vi",
    )
    apply_extracted_metadata(metadata, extracted)
    assert metadata.summary == "Tóm tắt"
    assert metadata.questions == ["Quãng đường?"]
    assert metadata.document_type == "spec_sheet"
    assert metadata.language == "vi"
