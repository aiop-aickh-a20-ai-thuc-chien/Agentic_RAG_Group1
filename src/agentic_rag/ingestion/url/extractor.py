"""Main-content extraction adapters for URL ingestion."""

from __future__ import annotations

import re
from collections.abc import Callable
from importlib import import_module
from typing import Any, cast

_MARKDOWN_LINK_PATTERN = r"\[[^\]\n]+\]\((?:[^()\n]|\([^()\n]*\))*\)"
_MARKDOWN_LINK_RE = re.compile(_MARKDOWN_LINK_PATTERN)
_WORD_CHAR_RE = r"A-Za-z0-9À-ỹ"


def extract_markdown_with_trafilatura(html: str, *, source_url: str | None) -> str | None:
    """Extract cleaner Markdown with trafilatura when the dependency is available."""

    trafilatura = cast(Any, import_module("trafilatura"))
    extract = cast(Callable[..., str | None], trafilatura.extract)
    markdown = extract(
        html,
        url=source_url,
        output_format="markdown",
        include_images=True,
        include_links=True,
        favor_recall=True,
    )
    if not markdown:
        return None
    cleaned_markdown = normalize_extracted_markdown(markdown)
    return cleaned_markdown or None


def normalize_extracted_markdown(markdown: str) -> str:
    """Fix common inline spacing artifacts from HTML-to-Markdown extraction."""

    lines = markdown.strip().splitlines()
    normalized_lines: list[str] = []
    for index, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line:
            if _blank_before_inline_link(lines, index, normalized_lines):
                continue
            normalized_lines.append("")
            continue
        if (
            normalized_lines
            and _starts_with_markdown_link(stripped_line)
            and _is_inline_continuation(normalized_lines[-1])
        ):
            normalized_lines[-1] = f"{normalized_lines[-1].rstrip()} {stripped_line}"
            continue
        normalized_lines.append(line.rstrip())

    normalized_markdown = "\n".join(normalized_lines)
    normalized_markdown = re.sub(
        rf"({_MARKDOWN_LINK_PATTERN})(?=[{_WORD_CHAR_RE}(])",
        r"\1 ",
        normalized_markdown,
    )
    normalized_markdown = re.sub(
        rf"(?<=[{_WORD_CHAR_RE}])(?={_MARKDOWN_LINK_PATTERN})",
        " ",
        normalized_markdown,
    )
    normalized_markdown = re.sub(r"\n{3,}", "\n\n", normalized_markdown)
    return normalized_markdown.strip()


def _blank_before_inline_link(
    lines: list[str],
    index: int,
    normalized_lines: list[str],
) -> bool:
    if not normalized_lines or not _is_inline_continuation(normalized_lines[-1]):
        return False
    for next_line in lines[index + 1 :]:
        stripped_next_line = next_line.strip()
        if not stripped_next_line:
            continue
        return _starts_with_markdown_link(stripped_next_line)
    return False


def _starts_with_markdown_link(line: str) -> bool:
    return _MARKDOWN_LINK_RE.match(line) is not None


def _is_inline_continuation(line: str) -> bool:
    stripped_line = line.strip()
    if not stripped_line:
        return False
    if stripped_line.startswith(("#", "-", "*", ">")):
        return False
    return stripped_line[-1] not in ".!?:;|"
