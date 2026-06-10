from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

from agentic_rag.core.contracts import Chunk

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

    assert knowledge_quality.__all__ == ["KnowledgeQualityProcessor"]
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

    assert imported_modules <= {
        "__future__",
        "abc",
        "agentic_rag.core.contracts",
        "agentic_rag.ingestion.knowledge_quality.ports",
        "typing",
    }


def test_protocol_process_method_must_be_implemented() -> None:
    from agentic_rag.ingestion.knowledge_quality import KnowledgeQualityProcessor

    class IncompleteProcessor(KnowledgeQualityProcessor):
        pass

    assert getattr(KnowledgeQualityProcessor.process, "__isabstractmethod__", False) is True
    assert IncompleteProcessor.__abstractmethods__ == {"process"}
