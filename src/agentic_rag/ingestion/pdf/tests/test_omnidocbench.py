from pathlib import Path

import pytest
from pydantic import ValidationError

from agentic_rag.ingestion.pdf.benchmarking.omnidocbench import (
    OmniDocBenchRunConfig,
    build_omnidocbench_command,
    write_omnidocbench_config,
)


def _run_config(tmp_path: Path, *, backend: str = "docker") -> OmniDocBenchRunConfig:
    return OmniDocBenchRunConfig(
        backend=backend,
        ground_truth_path=tmp_path / "OmniDocBench.json",
        predictions_dir=tmp_path / "parser_outputs",
        output_dir=tmp_path / "results",
        config_output_path=tmp_path / "config" / "end2end.yaml",
        omnidocbench_repo=tmp_path / "OmniDocBench" if backend == "local" else None,
        dry_run=True,
    )


def test_writes_end2end_config_for_markdown_parser_outputs(tmp_path: Path) -> None:
    run_config = _run_config(tmp_path)

    config_path = write_omnidocbench_config(run_config)

    config_text = config_path.read_text(encoding="utf-8")
    assert "end2end_eval:" in config_text
    assert "dataset_name: end2end_dataset" in config_text
    assert "match_method: quick_match" in config_text
    assert 'data_path: "/workspace/input/ground_truth/OmniDocBench.json"' in config_text
    assert 'data_path: "/workspace/input/predictions"' in config_text
    assert config_path == run_config.config_output_path


def test_local_backend_requires_omnidocbench_repo(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="omnidocbench_repo"):
        OmniDocBenchRunConfig(
            backend="local",
            ground_truth_path=tmp_path / "OmniDocBench.json",
            predictions_dir=tmp_path / "parser_outputs",
            output_dir=tmp_path / "results",
            config_output_path=tmp_path / "config" / "end2end.yaml",
            dry_run=True,
        )


def test_ground_truth_must_be_json_file_path(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="JSON"):
        OmniDocBenchRunConfig(
            ground_truth_path=tmp_path / "ground_truth.txt",
            predictions_dir=tmp_path / "parser_outputs",
            output_dir=tmp_path / "results",
            config_output_path=tmp_path / "config" / "end2end.yaml",
            dry_run=True,
        )


def test_builds_docker_command_without_requiring_docker(tmp_path: Path) -> None:
    run_config = _run_config(tmp_path)

    command = build_omnidocbench_command(run_config)

    assert command.backend == "docker"
    assert command.cwd is None
    assert command.command[:3] == ["docker", "run", "--rm"]
    assert run_config.docker_image in command.command
    assert "python" in command.command
    assert "pdf_validation.py" in command.command
    assert "--config" in command.command
    assert "/workspace/config/end2end.yaml" in command.command
    assert any("/workspace/OmniDocBench/result" in part for part in command.command)


def test_builds_local_command_with_repo_as_pythonpath(tmp_path: Path) -> None:
    run_config = _run_config(tmp_path, backend="local")

    command = build_omnidocbench_command(run_config)

    assert command.backend == "local"
    assert command.cwd == run_config.output_dir
    assert run_config.omnidocbench_repo is not None
    assert command.command == [
        "python",
        str(run_config.omnidocbench_repo / "pdf_validation.py"),
        "--config",
        str(run_config.config_output_path),
    ]
    assert command.environment == {"PYTHONPATH": str(run_config.omnidocbench_repo)}
