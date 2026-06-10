from pathlib import Path

import pytest
from pydantic import ValidationError

from agentic_rag.ingestion.url.artifact import (
    DebugArtifact,
    IngestionArtifacts,
    persist_debug_artifacts,
)


def test_persist_debug_artifacts_writes_files(tmp_path: Path) -> None:
    written_paths = persist_debug_artifacts(
        tmp_path,
        (
            DebugArtifact(name="raw.html", content="<html></html>"),
            DebugArtifact(name="parsed.txt", content="Parsed content"),
        ),
    )

    assert [path.name for path in written_paths] == ["raw.html", "parsed.txt"]
    assert (tmp_path / "raw.html").read_text(encoding="utf-8") == "<html></html>"
    assert (tmp_path / "parsed.txt").read_text(encoding="utf-8") == "Parsed content"


def test_persist_debug_artifacts_can_be_disabled() -> None:
    assert persist_debug_artifacts(None, (DebugArtifact(name="skip.txt", content="skip"),)) == ()


def test_persist_debug_artifacts_rejects_nested_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="plain file name"):
        persist_debug_artifacts(tmp_path, (DebugArtifact(name="nested/file.txt", content="bad"),))


def test_ingestion_artifacts_is_frozen_and_strict(tmp_path: Path) -> None:
    artifacts = IngestionArtifacts(
        run_dir=tmp_path,
        markdown_path=tmp_path / "parsed.md",
        chunks_path=tmp_path / "chunks.jsonl",
        manifest_path=tmp_path / "manifest.json",
    )

    assert artifacts.run_dir == tmp_path

    with pytest.raises(ValidationError):
        IngestionArtifacts.model_validate(
            {
                "run_dir": tmp_path,
                "markdown_path": tmp_path / "parsed.md",
                "chunks_path": tmp_path / "chunks.jsonl",
                "manifest_path": tmp_path / "manifest.json",
                "unexpected": True,
            }
        )
