import agentic_rag.ingestion.url.benchmarking as benchmarking_package
from agentic_rag.ingestion.url.benchmarking.famous_benchmark import (
    BenchmarkCase,
    BenchmarkReport,
    BenchmarkResult,
    ParserOutput,
    parse_html_builtin,
    report_to_dict,
    run_famous_benchmark,
)


def test_benchmarking_package_re_exports_public_helpers() -> None:
    assert benchmarking_package.__all__ == [
        "BenchmarkCase",
        "BenchmarkReport",
        "BenchmarkResult",
        "ParserOutput",
        "parse_html_builtin",
        "report_to_dict",
        "run_famous_benchmark",
    ]
    assert benchmarking_package.BenchmarkCase is BenchmarkCase
    assert benchmarking_package.BenchmarkReport is BenchmarkReport
    assert benchmarking_package.BenchmarkResult is BenchmarkResult
    assert benchmarking_package.ParserOutput is ParserOutput
    assert benchmarking_package.parse_html_builtin is parse_html_builtin
    assert benchmarking_package.report_to_dict is report_to_dict
    assert benchmarking_package.run_famous_benchmark is run_famous_benchmark
