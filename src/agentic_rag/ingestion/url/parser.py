"""Parser adapters for URL ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from agentic_rag.ingestion.url.chunking import normalize_space

_NOISE_TAGS = {"script", "style", "nav", "footer", "header", "aside"}
_HEADING_TAGS = {"h1", "h2", "h3"}


@dataclass(frozen=True)
class Section:
    """A parsed page section."""

    heading: str
    text: str


@dataclass(frozen=True)
class ParsedHtml:
    """HTML parser output for ingestion."""

    title: str | None
    sections: tuple[Section, ...]


def parse_html(html: str) -> ParsedHtml:
    """Parse HTML into title and readable sections."""

    parser = MainContentParser()
    parser.feed(html)
    parser.close()
    return ParsedHtml(title=parser.title, sections=parser.sections)


class MainContentParser(HTMLParser):
    """Extract readable content while ignoring common boilerplate tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._capture_title = False
        self._current_heading_tag: str | None = None
        self._current_section = "main"
        self._title_parts: list[str] = []
        self._heading_parts: list[str] = []
        self._section_parts: list[str] = []
        self._sections: list[Section] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized_tag = tag.lower()
        if normalized_tag in _NOISE_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if normalized_tag == "title":
            self._capture_title = True
            self._title_parts = []
            return
        if normalized_tag in _HEADING_TAGS:
            self._current_heading_tag = normalized_tag
            self._heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _NOISE_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return
        if normalized_tag == "title":
            self._capture_title = False
            return
        if normalized_tag == self._current_heading_tag:
            heading = normalize_space(" ".join(self._heading_parts))
            if heading:
                self._flush_section()
                self._current_section = heading
                self._section_parts = [heading]
            self._current_heading_tag = None
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = normalize_space(data)
        if not text:
            return
        if self._capture_title:
            self._title_parts.append(text)
            return
        if self._current_heading_tag is not None:
            self._heading_parts.append(text)
            return
        self._section_parts.append(text)

    def close(self) -> None:
        super().close()
        self._flush_section()

    @property
    def title(self) -> str | None:
        title = normalize_space(" ".join(self._title_parts))
        return title or None

    @property
    def sections(self) -> tuple[Section, ...]:
        return tuple(self._sections)

    def _flush_section(self) -> None:
        text = normalize_space(" ".join(self._section_parts))
        if text:
            self._sections.append(Section(heading=self._current_section, text=text))
        self._section_parts = []
