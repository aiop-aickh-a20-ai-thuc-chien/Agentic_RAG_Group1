import json

from agentic_rag.ingestion.url.benchmarking.custom_benchmark import (
    parse_html_builtin,
    report_to_dict,
    run_custom_benchmark,
)


def test_builtin_html_parser_removes_noise_and_keeps_sections() -> None:
    output = parse_html_builtin(
        """
        <html>
          <body>
            <header>Top links</header>
            <article>
              <h1>Main Section</h1>
              <p>Important benchmark content.</p>
            </article>
            <footer>Footer links</footer>
          </body>
        </html>
        """
    )

    assert output.parser == "builtin-html-parser"
    assert output.sections == ("Main Section",)
    assert "Important benchmark content." in output.text
    assert "Top links" not in output.text
    assert "Footer links" not in output.text


def test_custom_benchmark_report_is_json_serializable() -> None:
    report = run_custom_benchmark()
    payload = report_to_dict(report)

    assert report.average_score == 1.0
    assert payload["average_score"] == 1.0
    assert all(result["missing_terms"] == [] for result in payload["results"])
    assert all(result["chunk_count"] >= 1 for result in payload["results"])
    assert all("usable_chunk_count" in result for result in payload["results"])
    json.dumps(payload)
