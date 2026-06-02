"""Parser adapters for URL ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

from agentic_rag.ingestion.url.chunking import normalize_space

_NOISE_TAGS = {"script", "style", "nav", "footer", "header", "aside"}
_HEADING_TAGS = {"h1", "h2", "h3"}
_PARAGRAPH_TAGS = {"p"}
_LIST_ITEM_TAGS = {"li"}
_STRONG_TAGS = {"strong", "b"}
_ASSET_TAGS = {"img", "iframe", "object"}
_PUBLISHED_META_NAMES = {
    "article:published_time",
    "date",
    "dc.date",
    "dc.date.issued",
    "publish_date",
}
_AUTHOR_META_NAMES = {"author", "article:author", "dc.creator"}


@dataclass(frozen=True)
class Section:
    """A parsed page section."""

    heading: str
    text: str
    heading_level: int = 0
    markdown: str | None = None


@dataclass(frozen=True)
class Asset:
    """A related URL asset discovered in HTML."""

    kind: str
    url: str
    alt: str | None = None
    title: str | None = None
    target_url: str | None = None


@dataclass(frozen=True)
class PageMetadata:
    """Metadata discovered from canonical, Open Graph, and article tags."""

    canonical_url: str | None = None
    og_url: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    description: str | None = None
    published_at: str | None = None
    author: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class ParsedHtml:
    """HTML parser output for ingestion."""

    title: str | None
    sections: tuple[Section, ...]
    metadata: PageMetadata = PageMetadata()
    assets: tuple[Asset, ...] = ()


def parse_html(html: str, *, base_url: str | None = None) -> ParsedHtml:
    """Parse HTML into title and readable sections."""

    parser = MainContentParser(base_url=base_url)
    parser.feed(html)
    parser.close()
    return ParsedHtml(
        title=parser.title,
        sections=parser.sections,
        metadata=parser.metadata,
        assets=parser.assets,
    )


class MainContentParser(HTMLParser):
    """Extract readable content while ignoring common boilerplate tags."""

    def __init__(self, *, base_url: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self._skip_depth = 0
        self._suppressed_anchor_depth = 0
        self._capture_title = False
        self._current_heading_tag: str | None = None
        self._current_section = "main"
        self._current_section_level = 0
        self._current_block_tag: str | None = None
        self._strong_depth = 0
        self._title_parts: list[str] = []
        self._heading_parts: list[str] = []
        self._section_parts: list[str] = []
        self._markdown_lines: list[str] = []
        self._inline_parts: list[str] = []
        self._sections: list[Section] = []
        self._link_stack: list[str | None] = []
        self._canonical_url: str | None = None
        self._og_url: str | None = None
        self._og_title: str | None = None
        self._og_description: str | None = None
        self._description: str | None = None
        self._published_at: str | None = None
        self._author: str | None = None
        self._language: str | None = None
        self._assets: list[Asset] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attr_map = _attrs_to_dict(attrs)
        if normalized_tag == "html":
            self._language = _first_non_empty(attr_map.get("lang"), self._language)
            return
        if normalized_tag == "link":
            self._capture_link_metadata(attr_map)
            return
        if normalized_tag == "meta":
            self._capture_meta_metadata(attr_map)
            return
        if normalized_tag == "a":
            href = self._absolute_url(attr_map.get("href"))
            self._link_stack.append(href)
            if self._capture_pdf_link(attr_map, href):
                self._skip_depth += 1
                self._suppressed_anchor_depth += 1
            return
        if normalized_tag in _NOISE_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if normalized_tag in _ASSET_TAGS:
            self._capture_embedded_asset(normalized_tag, attr_map)
            return
        if normalized_tag == "title":
            self._capture_title = True
            self._title_parts = []
            return
        if normalized_tag in _HEADING_TAGS:
            self._flush_inline_block()
            self._current_heading_tag = normalized_tag
            self._heading_parts = []
            return
        if normalized_tag in _PARAGRAPH_TAGS | _LIST_ITEM_TAGS:
            self._flush_inline_block()
            self._current_block_tag = normalized_tag
            self._inline_parts = []
            return
        if normalized_tag in _STRONG_TAGS:
            self._strong_depth += 1

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "a" and self._link_stack:
            self._link_stack.pop()
            if self._suppressed_anchor_depth > 0:
                self._suppressed_anchor_depth -= 1
                if self._skip_depth > 0:
                    self._skip_depth -= 1
            return
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
                self._current_section_level = _heading_level(normalized_tag)
                self._section_parts = [heading]
                self._markdown_lines = [f"{'#' * self._current_section_level} {heading}"]
            self._current_heading_tag = None
            self._heading_parts = []
            return
        if normalized_tag == self._current_block_tag:
            self._flush_inline_block()
            return
        if normalized_tag in _STRONG_TAGS and self._strong_depth > 0:
            self._strong_depth -= 1

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
        if self._current_block_tag is not None:
            self._section_parts.append(text)
            self._inline_parts.append(_markdown_inline(text, strong=self._strong_depth > 0))
            return
        self._section_parts.append(text)
        self._markdown_lines.append(text)

    def close(self) -> None:
        super().close()
        self._flush_inline_block()
        self._flush_section()

    @property
    def title(self) -> str | None:
        title = normalize_space(" ".join(self._title_parts))
        return title or None

    @property
    def sections(self) -> tuple[Section, ...]:
        return tuple(self._sections)

    @property
    def metadata(self) -> PageMetadata:
        return PageMetadata(
            canonical_url=self._canonical_url,
            og_url=self._og_url,
            og_title=self._og_title,
            og_description=self._og_description,
            description=self._description,
            published_at=self._published_at,
            author=self._author,
            language=self._language,
        )

    @property
    def assets(self) -> tuple[Asset, ...]:
        return tuple(self._assets)

    def _capture_link_metadata(self, attrs: dict[str, str]) -> None:
        rel_values = {value.lower() for value in attrs.get("rel", "").split()}
        if "canonical" not in rel_values:
            return
        self._canonical_url = _first_non_empty(
            self._absolute_url(attrs.get("href")),
            self._canonical_url,
        )

    def _capture_meta_metadata(self, attrs: dict[str, str]) -> None:
        meta_name = _first_non_empty(attrs.get("property"), attrs.get("name"))
        content = normalize_space(attrs.get("content", ""))
        if not meta_name or not content:
            return

        normalized_name = meta_name.lower()
        if normalized_name == "og:url":
            self._og_url = _first_non_empty(self._absolute_url(content), self._og_url)
        elif normalized_name == "og:title":
            self._og_title = _first_non_empty(content, self._og_title)
        elif normalized_name == "og:description":
            self._og_description = _first_non_empty(content, self._og_description)
        elif normalized_name == "description":
            self._description = _first_non_empty(content, self._description)
        elif normalized_name in _PUBLISHED_META_NAMES:
            self._published_at = _first_non_empty(content, self._published_at)
        elif normalized_name in _AUTHOR_META_NAMES:
            self._author = _first_non_empty(content, self._author)

    def _capture_pdf_link(self, attrs: dict[str, str], href: str | None) -> bool:
        if not href:
            return False
        link_type = attrs.get("type", "").lower()
        if not href.lower().split("?", 1)[0].endswith(".pdf") and link_type != "application/pdf":
            return False
        self._assets.append(
            Asset(
                kind="pdf",
                url=href,
                title=_clean_optional(attrs.get("title")),
            )
        )
        return True

    def _capture_embedded_asset(self, tag: str, attrs: dict[str, str]) -> None:
        raw_url = attrs.get("data") if tag == "object" else attrs.get("src")
        asset_url = self._absolute_url(raw_url)
        if not asset_url:
            return
        self._assets.append(
            Asset(
                kind=_asset_kind(tag),
                url=asset_url,
                alt=_clean_optional(attrs.get("alt")),
                title=_clean_optional(attrs.get("title")),
                target_url=self._link_stack[-1] if tag == "img" and self._link_stack else None,
            )
        )

    def _absolute_url(self, value: str | None) -> str | None:
        cleaned_value = _clean_optional(value)
        if cleaned_value is None:
            return None
        return urljoin(self._base_url, cleaned_value) if self._base_url else cleaned_value

    def _flush_section(self) -> None:
        self._flush_inline_block()
        text = normalize_space(" ".join(self._section_parts))
        if text:
            markdown = "\n\n".join(line for line in self._markdown_lines if line).strip()
            self._sections.append(
                Section(
                    heading=self._current_section,
                    text=text,
                    heading_level=self._current_section_level,
                    markdown=markdown or text,
                )
            )
        self._section_parts = []
        self._markdown_lines = []

    def _flush_inline_block(self) -> None:
        if self._current_block_tag is None:
            return
        line = normalize_space(" ".join(self._inline_parts))
        if line:
            if self._current_block_tag in _LIST_ITEM_TAGS:
                self._markdown_lines.append(f"- {line}")
            else:
                self._markdown_lines.append(line)
        self._current_block_tag = None
        self._inline_parts = []


def _heading_level(tag: str) -> int:
    return int(tag[1]) if tag in _HEADING_TAGS else 0


def _markdown_inline(text: str, *, strong: bool) -> str:
    return f"**{text}**" if strong else text


def _attrs_to_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {name.lower(): value or "" for name, value in attrs}


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        cleaned_value = _clean_optional(value)
        if cleaned_value is not None:
            return cleaned_value
    return None


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned_value = normalize_space(value)
    return cleaned_value or None


def _asset_kind(tag: str) -> str:
    if tag == "img":
        return "image"
    if tag == "iframe":
        return "iframe"
    return "object"
