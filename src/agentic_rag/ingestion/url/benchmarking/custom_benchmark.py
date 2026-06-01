"""Runnable wrapper for URL and HTML parser benchmark outputs.

The cases are small local fixtures that represent common web page shapes. They
let the team compare parser behavior without network access or paid services.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

_NOISE_TAGS = {"script", "style", "nav", "footer", "header", "aside"}
_SECTION_TAGS = {"h1", "h2", "h3"}


@dataclass(frozen=True)
class ParserOutput:
    """Clean text and section metadata returned by a parser."""

    parser: str
    text: str
    sections: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkCase:
    """A deterministic HTML benchmark case."""

    case_id: str
    html: str
    expected_terms: tuple[str, ...]
    expected_sections: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkResult:
    """Score for one parser on one benchmark case."""

    case_id: str
    parser: str
    extracted_chars: int
    matched_terms: tuple[str, ...]
    missing_terms: tuple[str, ...]
    detected_sections: tuple[str, ...]
    score: float


@dataclass(frozen=True)
class BenchmarkReport:
    """Aggregated benchmark output for JSON reporting."""

    parser: str
    average_score: float
    results: tuple[BenchmarkResult, ...]


class _MainContentParser(HTMLParser):
    """Tiny stdlib parser that strips common boilerplate tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._current_heading: str | None = None
        self._text_parts: list[str] = []
        self._heading_parts: list[str] = []
        self.sections: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized_tag = tag.lower()
        if normalized_tag in _NOISE_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth == 0 and normalized_tag in _SECTION_TAGS:
            self._current_heading = normalized_tag
            self._heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _NOISE_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth == 0 and normalized_tag == self._current_heading:
            section = _normalize_space(" ".join(self._heading_parts))
            if section:
                self.sections.append(section)
                self._text_parts.append(section)
            self._current_heading = None
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = _normalize_space(data)
        if not text:
            return
        if self._current_heading is not None:
            self._heading_parts.append(text)
            return
        self._text_parts.append(text)

    @property
    def text(self) -> str:
        return _normalize_space(" ".join(self._text_parts))


CUSTOM_HTML_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        case_id="article_with_navigation_noise",
        html="""
        <html>
          <body>
            <nav>Home Pricing Login</nav>
            <article>
              <h1>Admissions Guide</h1>
              <p>Applications require transcripts and an interview.</p>
            </article>
            <footer>Contact and copyright links</footer>
          </body>
        </html>
        """,
        expected_terms=("Admissions Guide", "transcripts", "interview"),
        expected_sections=("Admissions Guide",),
    ),
    BenchmarkCase(
        case_id="docs_page_with_code_noise",
        html="""
        <html>
          <body>
            <header>Product docs</header>
            <main>
              <h1>Installation</h1>
              <p>Install the package with uv sync before running tests.</p>
              <script>console.log("tracking")</script>
              <h2>Quality Gate</h2>
              <p>Run ruff, mypy, and pytest before review.</p>
            </main>
          </body>
        </html>
        """,
        expected_terms=("Installation", "uv sync", "Quality Gate", "pytest"),
        expected_sections=("Installation", "Quality Gate"),
    ),
)


def parse_html_builtin(html: str) -> ParserOutput:
    """Parse local HTML into clean text and section names using stdlib only."""

    parser = _MainContentParser()
    parser.feed(html)
    parser.close()
    return ParserOutput(
        parser="builtin-html-parser", text=parser.text, sections=tuple(parser.sections)
    )


def run_custom_benchmark(
    parser_name: str = "builtin",
    cases: tuple[BenchmarkCase, ...] = CUSTOM_HTML_CASES,
) -> BenchmarkReport:
    """Run local benchmark cases for the selected parser."""

    if parser_name != "builtin":
        raise ValueError(f"Unsupported parser: {parser_name}")

    results = tuple(_score_case(case, parse_html_builtin(case.html)) for case in cases)
    average_score = sum(result.score for result in results) / len(results) if results else 0.0
    return BenchmarkReport(
        parser="builtin-html-parser",
        average_score=round(average_score, 4),
        results=results,
    )


def report_to_dict(report: BenchmarkReport) -> dict[str, Any]:
    """Convert a benchmark report into JSON-serializable data."""

    return {
        "parser": report.parser,
        "average_score": report.average_score,
        "results": [
            {
                "case_id": result.case_id,
                "parser": result.parser,
                "extracted_chars": result.extracted_chars,
                "matched_terms": list(result.matched_terms),
                "missing_terms": list(result.missing_terms),
                "detected_sections": list(result.detected_sections),
                "score": result.score,
            }
            for result in report.results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Run the custom local HTML parser benchmark from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parser", default="builtin", choices=["builtin"])
    parser.add_argument("--output", type=Path, help="Optional JSON output file.")
    args = parser.parse_args(argv)

    report = run_custom_benchmark(parser_name=args.parser)
    payload = json.dumps(report_to_dict(report), ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


def _score_case(case: BenchmarkCase, output: ParserOutput) -> BenchmarkResult:
    extracted_text = output.text.lower()
    matched_terms = tuple(term for term in case.expected_terms if term.lower() in extracted_text)
    missing_terms = tuple(
        term for term in case.expected_terms if term.lower() not in extracted_text
    )
    expected_section_count = len(case.expected_sections)
    matched_sections = tuple(
        section for section in case.expected_sections if section in output.sections
    )
    term_score = len(matched_terms) / len(case.expected_terms) if case.expected_terms else 1.0
    section_score = (
        len(matched_sections) / expected_section_count if expected_section_count else 1.0
    )
    score = round((term_score * 0.8) + (section_score * 0.2), 4)
    return BenchmarkResult(
        case_id=case.case_id,
        parser=output.parser,
        extracted_chars=len(output.text),
        matched_terms=matched_terms,
        missing_terms=missing_terms,
        detected_sections=output.sections,
        score=score,
    )


def _normalize_space(value: str) -> str:
    return " ".join(value.split())


if __name__ == "__main__":
    raise SystemExit(main())
