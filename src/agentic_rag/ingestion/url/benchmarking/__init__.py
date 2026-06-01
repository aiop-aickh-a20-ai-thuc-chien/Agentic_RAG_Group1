"""Benchmark helpers for URL and HTML ingestion."""

from agentic_rag.ingestion.url.benchmarking.famous_benchmark import (
    BenchmarkCase,
    BenchmarkReport,
    BenchmarkResult,
    ParserOutput,
    parse_html_builtin,
    report_to_dict,
    run_famous_benchmark,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkReport",
    "BenchmarkResult",
    "ParserOutput",
    "parse_html_builtin",
    "report_to_dict",
    "run_famous_benchmark",
]
