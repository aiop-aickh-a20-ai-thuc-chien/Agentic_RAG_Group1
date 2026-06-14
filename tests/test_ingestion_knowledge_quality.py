from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from agentic_rag.core.contracts import (
    Chunk,
    KnowledgeQualityFact,
    KnowledgeQualityFinding,
    KnowledgeQualityReport,
)
from agentic_rag.ingestion.knowledge_quality import (
    DeterministicKnowledgeQualityProcessor,
    analyze_chunks,
    annotate_chunks_with_quality,
)

if TYPE_CHECKING:
    from agentic_rag.ingestion.knowledge_quality import KnowledgeQualityProcessor


class _FakeKnowledgeQualityProcessor:
    def process(self, chunks: list[Chunk]) -> list[Chunk]:
        return chunks


def test_fake_processor_satisfies_runtime_protocol_and_returns_chunks() -> None:
    spec = importlib.util.find_spec("agentic_rag.ingestion.knowledge_quality")
    assert spec is not None
    module = importlib.import_module("agentic_rag.ingestion.knowledge_quality")
    protocol = module.KnowledgeQualityProcessor
    chunks = [Chunk(chunk_id="chunk-1", text="Example", metadata={})]
    processor: KnowledgeQualityProcessor = _FakeKnowledgeQualityProcessor()

    assert isinstance(processor, protocol)
    assert processor.process(chunks) is chunks


def test_package_exports_only_knowledge_quality_processor() -> None:
    spec = importlib.util.find_spec("agentic_rag.ingestion.knowledge_quality")
    assert spec is not None
    knowledge_quality = importlib.import_module("agentic_rag.ingestion.knowledge_quality")
    ports = importlib.import_module("agentic_rag.ingestion.knowledge_quality.ports")

    assert knowledge_quality.__all__ == [
        "AVAILABLE_KNOWLEDGE_QUALITY_METHODS",
        "MODEL_BACKED_KNOWLEDGE_QUALITY_METHODS",
        "DeterministicKnowledgeQualityProcessor",
        "KnowledgeQualityConfigurationError",
        "KnowledgeQualityInvocationError",
        "KnowledgeQualityProcessor",
        "UnknownKnowledgeQualityMethodError",
        "analyze_chunks",
        "annotate_chunks_with_quality",
        "parse_knowledge_quality_methods",
    ]
    assert knowledge_quality.KnowledgeQualityProcessor is ports.KnowledgeQualityProcessor


def test_package_imports_only_shared_contract_and_standard_library() -> None:
    package_root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agentic_rag"
        / "ingestion"
        / "knowledge_quality"
    )
    imported_modules: set[str] = set()

    for source_path in package_root.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    forbidden_prefixes = (
        "agentic_rag.generation",
        "agentic_rag.integrations",
        "agentic_rag.retrieval",
        "agentic_rag.model_runtime",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imported_modules), (
        imported_modules
    )


def test_protocol_process_method_must_be_implemented() -> None:
    from agentic_rag.ingestion.knowledge_quality import KnowledgeQualityProcessor

    class IncompleteProcessor(KnowledgeQualityProcessor):
        pass

    assert getattr(KnowledgeQualityProcessor.process, "__isabstractmethod__", False) is True
    assert IncompleteProcessor.__abstractmethods__ == {"process"}


def test_quality_contracts_are_strict_and_frozen() -> None:
    fact = KnowledgeQualityFact(
        fact_id="fact-c1-price-1",
        chunk_id="c1",
        entity="VF 8",
        attribute="price",
        value="399 triệu",
        normalized_value=399_000_000,
        unit="vnd",
        span="VF 8 có giá 399 triệu",
    )
    finding = KnowledgeQualityFinding(
        finding_id="finding-conflict-1",
        kind="conflict",
        severity="warning",
        status="open",
        chunk_ids=["c1", "c2"],
        fact_ids=[fact.fact_id],
        summary="Giá VF 8 mâu thuẫn giữa hai nguồn.",
        suggested_action="Review conflicting chunks before answering.",
        confidence=0.95,
    )
    report = KnowledgeQualityReport(facts=[fact], findings=[finding])

    assert report.facts[0].entity == "VF 8"
    assert any(finding.kind == "conflict" for finding in report.findings)

    with pytest.raises(ValidationError):
        finding.severity = "critical"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        KnowledgeQualityFinding.model_validate(
            {
                **finding.model_dump(),
                "unexpected": True,
            }
        )


def test_analyze_chunks_detects_duplicates_and_numeric_conflicts() -> None:
    chunks = [
        Chunk(
            chunk_id="c1",
            text="Pin VF 8 được bảo hành 8 năm hoặc 160.000 km.",
            metadata={"source": "warranty-a.pdf", "document_id": "doc-a"},
        ),
        Chunk(
            chunk_id="c2",
            text="Pin VF 8 được bảo hành 8 năm hoặc 160.000 km.",
            metadata={"source": "warranty-a-copy.pdf", "document_id": "doc-b"},
        ),
        Chunk(
            chunk_id="c3",
            text="Pin VF 8 duoc bao hanh trong 8 nam hoac 160000 km.",
            metadata={"source": "warranty-near.txt", "document_id": "doc-c"},
        ),
        Chunk(
            chunk_id="c4",
            text="Pin VF 8 được bảo hành 10 năm hoặc 160.000 km.",
            metadata={"source": "warranty-conflict.pdf", "document_id": "doc-d"},
        ),
    ]

    report = analyze_chunks(chunks)

    assert {finding.kind for finding in report.findings} >= {
        "exact_duplicate",
        "near_duplicate",
        "conflict",
    }
    conflict = next(finding for finding in report.findings if finding.kind == "conflict")
    assert conflict.severity == "warning"
    assert set(conflict.chunk_ids) == {"c1", "c4"}
    assert "VF 8" in conflict.summary
    assert conflict.metadata["attribute"] == "warranty_duration"
    assert any(fact.attribute == "warranty_duration" for fact in report.facts)
    assert any(fact.attribute == "distance_km" for fact in report.facts)


def test_analyze_chunks_normalizes_equivalent_units_without_false_conflict() -> None:
    chunks = [
        Chunk(
            chunk_id="c1",
            text="VF 8 được bảo hành 8 năm hoặc 160.000 km.",
            metadata={"source": "a.pdf"},
        ),
        Chunk(
            chunk_id="c2",
            text="VF 8 duoc bao hanh 8 nam hoac 160000 km.",
            metadata={"source": "b.pdf"},
        ),
    ]

    report = analyze_chunks(chunks)

    assert not [finding for finding in report.findings if finding.kind == "conflict"]


def test_processor_annotates_chunks_with_quality_summary() -> None:
    chunks = [
        Chunk(
            chunk_id="c1",
            text="VF 9 có giá 1,2 tỷ đồng.",
            metadata={"source": "price-a.pdf"},
        ),
        Chunk(
            chunk_id="c2",
            text="VF 9 có giá 1,5 tỷ đồng.",
            metadata={"source": "price-b.pdf"},
        ),
    ]

    annotated = DeterministicKnowledgeQualityProcessor().process(chunks)
    report = analyze_chunks(annotated)

    assert annotated != chunks
    assert all("knowledge_quality" in chunk.metadata for chunk in annotated)
    assert annotated[0].metadata["knowledge_quality"]["conflict_count"] == 1
    assert annotated[1].metadata["knowledge_quality"]["conflict_count"] == 1
    assert any(finding.kind == "conflict" for finding in report.findings)


def test_annotate_chunks_can_include_existing_context_without_rewriting_it() -> None:
    existing = [
        Chunk(
            chunk_id="old",
            text="VF 7 Plus có giá 999 triệu đồng.",
            metadata={"source": "old-price.pdf", "document_id": "old-doc"},
        )
    ]
    new = [
        Chunk(
            chunk_id="new",
            text="VF 7 Plus có giá 899 triệu đồng.",
            metadata={"source": "new-price.pdf", "document_id": "new-doc"},
        )
    ]

    annotated = annotate_chunks_with_quality(new, existing_chunks=existing)

    assert annotated[0].metadata["knowledge_quality"]["conflict_count"] == 1
    assert annotated[0].metadata["knowledge_quality"]["finding_ids"]
