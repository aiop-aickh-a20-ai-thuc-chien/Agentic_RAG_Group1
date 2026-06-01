import json
from pathlib import Path

import pytest

from agentic_rag.ingestion.url.benchmarking import cli


def test_parse_html_cli_emits_parser_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    html_file = tmp_path / "sample.html"
    html_file.write_text(
        """
        <html>
          <body>
            <nav>Navigation noise</nav>
            <main>
              <h1>URL Ingestion</h1>
              <p>Clean content should remain.</p>
            </main>
            <script>alert("noise")</script>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    exit_code = cli.main(["parse-html", "--html-file", str(html_file)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["parser"] == "builtin-html-parser"
    assert payload["source_type"] == "html"
    assert payload["sections"] == ["URL Ingestion"]
    assert "Clean content should remain." in payload["text"]
    assert "Navigation noise" not in payload["text"]


def test_custom_cli_writes_json_output_file(tmp_path: Path) -> None:
    output_file = tmp_path / "benchmark.json"

    exit_code = cli.main(["custom", "--output", str(output_file)])

    assert exit_code == 0
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["parser"] == "builtin-html-parser"
    assert payload["average_score"] == 1.0
    assert len(payload["results"]) == 2
