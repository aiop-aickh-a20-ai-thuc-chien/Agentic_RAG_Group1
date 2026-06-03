from pathlib import Path

import pytest

from agentic_rag.ingestion.url.artifact import DebugArtifact, persist_debug_artifacts


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
