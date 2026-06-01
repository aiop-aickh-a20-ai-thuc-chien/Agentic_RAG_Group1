"""Debug artifact persistence for URL ingestion."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DebugArtifact:
    """A debug artifact that can be written to a local directory."""

    name: str
    content: str


def persist_debug_artifacts(
    output_dir: str | Path | None,
    artifacts: Iterable[DebugArtifact],
) -> tuple[Path, ...]:
    """Write debug artifacts and return their paths."""

    if output_dir is None:
        return ()

    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []
    for artifact in artifacts:
        output_path = artifact_dir / _validate_artifact_name(artifact.name)
        output_path.write_text(artifact.content, encoding="utf-8")
        written_paths.append(output_path)
    return tuple(written_paths)


def _validate_artifact_name(name: str) -> str:
    if not name or Path(name).name != name:
        raise ValueError("Debug artifact name must be a plain file name.")
    return name
