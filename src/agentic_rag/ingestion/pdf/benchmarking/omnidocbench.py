"""Runnable OmniDocBench wrapper for PDF parser benchmark outputs."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OmniDocBenchBackend = Literal["docker", "local"]
OmniDocBenchMatchMethod = Literal["quick_match", "simple_match", "no_split"]

_DOCKER_GT_DIR = Path("/workspace/input/ground_truth")
_DOCKER_PREDICTIONS_DIR = Path("/workspace/input/predictions")
_DOCKER_CONFIG_DIR = Path("/workspace/config")
_DOCKER_RESULT_DIR = Path("/workspace/OmniDocBench/result")


class _OmniDocBenchModel(BaseModel):
    """Shared strict configuration for OmniDocBench wrapper models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class OmniDocBenchRunConfig(_OmniDocBenchModel):
    """Configuration for one OmniDocBench end-to-end benchmark run."""

    backend: OmniDocBenchBackend = "docker"
    ground_truth_path: Path
    predictions_dir: Path
    output_dir: Path
    config_output_path: Path
    omnidocbench_repo: Path | None = None
    docker_image: str = "opendatalab/omnidocbench:latest"
    match_method: OmniDocBenchMatchMethod = "quick_match"
    dry_run: bool = False

    @field_validator("ground_truth_path")
    @classmethod
    def validate_ground_truth_path(cls, value: Path) -> Path:
        if value.suffix.lower() != ".json":
            raise ValueError("ground_truth_path must point to an OmniDocBench JSON file")
        return value

    @field_validator("config_output_path")
    @classmethod
    def validate_config_output_path(cls, value: Path) -> Path:
        if value.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError("config_output_path must point to a YAML file")
        return value

    @field_validator("docker_image")
    @classmethod
    def validate_docker_image(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("docker_image must not be empty")
        return value

    @model_validator(mode="after")
    def validate_backend_requirements(self) -> Self:
        if self.backend == "local" and self.omnidocbench_repo is None:
            raise ValueError("omnidocbench_repo is required when backend is local")
        return self


class OmniDocBenchCommand(_OmniDocBenchModel):
    """External command prepared for an OmniDocBench run."""

    backend: OmniDocBenchBackend
    config_path: Path
    command: list[str]
    cwd: Path | None = None
    environment: dict[str, str] = Field(default_factory=dict)


def write_omnidocbench_config(run_config: OmniDocBenchRunConfig) -> Path:
    """Write an OmniDocBench end-to-end config for Markdown parser outputs."""

    run_config.config_output_path.parent.mkdir(parents=True, exist_ok=True)
    run_config.output_dir.mkdir(parents=True, exist_ok=True)
    run_config.config_output_path.write_text(
        _render_end2end_config(run_config),
        encoding="utf-8",
    )
    return run_config.config_output_path


def build_omnidocbench_command(run_config: OmniDocBenchRunConfig) -> OmniDocBenchCommand:
    """Build the Docker or local command without executing OmniDocBench."""

    config_path = write_omnidocbench_config(run_config)
    if run_config.backend == "docker":
        return _build_docker_command(run_config, config_path)
    return _build_local_command(run_config, config_path)


def execute_omnidocbench_command(
    command: OmniDocBenchCommand,
) -> subprocess.CompletedProcess[str]:
    """Execute a prepared OmniDocBench command."""

    environment = os.environ.copy()
    environment.update(command.environment)
    return subprocess.run(
        command.command,
        cwd=command.cwd,
        env=environment,
        check=False,
        text=True,
    )


def _render_end2end_config(run_config: OmniDocBenchRunConfig) -> str:
    ground_truth_path = _ground_truth_path_for_config(run_config)
    predictions_dir = _predictions_dir_for_config(run_config)
    return "\n".join(
        [
            "end2end_eval:",
            "  metrics:",
            "    text_block:",
            "      metric:",
            "        - Edit_dist",
            "        - BLEU",
            "        - METEOR",
            "    display_formula:",
            "      metric:",
            "        - Edit_dist",
            "        - CDM",
            "    table:",
            "      metric:",
            "        - TEDS",
            "        - Edit_dist",
            "    reading_order:",
            "      metric:",
            "        - Edit_dist",
            "  dataset:",
            "    dataset_name: end2end_dataset",
            "    ground_truth:",
            f"      data_path: {_yaml_string(ground_truth_path)}",
            "    prediction:",
            f"      data_path: {_yaml_string(predictions_dir)}",
            f"    match_method: {run_config.match_method}",
            "",
        ]
    )


def _ground_truth_path_for_config(run_config: OmniDocBenchRunConfig) -> Path:
    if run_config.backend == "docker":
        return _DOCKER_GT_DIR / run_config.ground_truth_path.name
    return run_config.ground_truth_path


def _predictions_dir_for_config(run_config: OmniDocBenchRunConfig) -> Path:
    if run_config.backend == "docker":
        return _DOCKER_PREDICTIONS_DIR
    return run_config.predictions_dir


def _build_docker_command(
    run_config: OmniDocBenchRunConfig,
    config_path: Path,
) -> OmniDocBenchCommand:
    docker_config_path = _DOCKER_CONFIG_DIR / config_path.name
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{_absolute(run_config.ground_truth_path.parent)}:{_DOCKER_GT_DIR}:ro",
        "-v",
        f"{_absolute(run_config.predictions_dir)}:{_DOCKER_PREDICTIONS_DIR}:ro",
        "-v",
        f"{_absolute(config_path.parent)}:{_DOCKER_CONFIG_DIR}:ro",
        "-v",
        f"{_absolute(run_config.output_dir)}:{_DOCKER_RESULT_DIR}",
        run_config.docker_image,
        "python",
        "pdf_validation.py",
        "--config",
        str(docker_config_path),
    ]
    return OmniDocBenchCommand(
        backend="docker",
        config_path=config_path,
        command=command,
    )


def _build_local_command(
    run_config: OmniDocBenchRunConfig,
    config_path: Path,
) -> OmniDocBenchCommand:
    if run_config.omnidocbench_repo is None:
        raise ValueError("omnidocbench_repo is required when backend is local")
    return OmniDocBenchCommand(
        backend="local",
        config_path=config_path,
        command=[
            "python",
            str(run_config.omnidocbench_repo / "pdf_validation.py"),
            "--config",
            str(config_path),
        ],
        cwd=run_config.output_dir,
        environment={"PYTHONPATH": str(run_config.omnidocbench_repo)},
    )


def _absolute(path: Path) -> Path:
    return path.resolve(strict=False)


def _yaml_string(path: Path) -> str:
    return json.dumps(str(path), ensure_ascii=False)
