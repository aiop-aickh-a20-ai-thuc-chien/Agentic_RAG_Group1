from pathlib import Path

import pytest

from agentic_rag.ingestion.pdf.benchmarking import cli


def test_cli_dry_run_prints_command_without_external_execution(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "run-omnidocbench",
            "--backend",
            "docker",
            "--ground-truth",
            str(tmp_path / "OmniDocBench.json"),
            "--predictions",
            str(tmp_path / "parser_outputs"),
            "--output-dir",
            str(tmp_path / "results"),
            "--config-output",
            str(tmp_path / "config" / "end2end.yaml"),
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Dry run: external OmniDocBench command was not executed." in output
    assert "python pdf_validation.py --config /workspace/config/end2end.yaml" in output
    assert (tmp_path / "config" / "end2end.yaml").exists()
