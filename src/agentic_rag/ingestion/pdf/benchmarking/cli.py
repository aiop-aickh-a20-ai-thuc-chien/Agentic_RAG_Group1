"""Command line interface for PDF-local benchmark helpers."""

from __future__ import annotations

import argparse
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from agentic_rag.ingestion.pdf.benchmarking.omnidocbench import (
    OmniDocBenchBackend,
    OmniDocBenchMatchMethod,
    OmniDocBenchRunConfig,
    build_omnidocbench_command,
    execute_omnidocbench_command,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the PDF benchmark CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run-omnidocbench":
        return _run_omnidocbench(args)
    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-benchmark",
        description="PDF-local parser benchmark helpers.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser(
        "run-omnidocbench",
        help="Prepare and optionally execute an OmniDocBench end-to-end run.",
    )
    run_parser.add_argument("--backend", choices=("docker", "local"), default="docker")
    run_parser.add_argument("--ground-truth", required=True, type=Path)
    run_parser.add_argument("--predictions", required=True, type=Path)
    run_parser.add_argument("--output-dir", required=True, type=Path)
    run_parser.add_argument("--config-output", required=True, type=Path)
    run_parser.add_argument("--omnidocbench-repo", type=Path)
    run_parser.add_argument("--docker-image", default="opendatalab/omnidocbench:latest")
    run_parser.add_argument(
        "--match-method",
        choices=("quick_match", "simple_match", "no_split"),
        default="quick_match",
    )
    run_parser.add_argument("--dry-run", action="store_true")
    return parser


def _run_omnidocbench(args: argparse.Namespace) -> int:
    backend = cast(OmniDocBenchBackend, args.backend)
    match_method = cast(OmniDocBenchMatchMethod, args.match_method)
    run_config = OmniDocBenchRunConfig(
        backend=backend,
        ground_truth_path=args.ground_truth,
        predictions_dir=args.predictions,
        output_dir=args.output_dir,
        config_output_path=args.config_output,
        omnidocbench_repo=args.omnidocbench_repo,
        docker_image=args.docker_image,
        match_method=match_method,
        dry_run=args.dry_run,
    )
    command = build_omnidocbench_command(run_config)
    print(f"Config: {command.config_path}")
    if command.cwd is not None:
        print(f"CWD: {command.cwd}")
    for key, value in sorted(command.environment.items()):
        print(f"{key}: {value}")
    print(f"Command: {shlex.join(command.command)}")
    if run_config.dry_run:
        print("Dry run: external OmniDocBench command was not executed.")
        return 0
    completed_process = execute_omnidocbench_command(command)
    return completed_process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
