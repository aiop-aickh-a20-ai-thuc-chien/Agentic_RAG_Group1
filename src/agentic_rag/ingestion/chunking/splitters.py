"""Shared deterministic splitters and text normalization helpers."""

from __future__ import annotations

import hashlib
import re
from importlib import import_module
from typing import Any, Protocol, cast

from agentic_rag.ingestion.chunking.models import (
    ChunkingInput,
    MarkdownChunk,
    MarkdownSection,
)

DEFAULT_CHUNK_SIZE = 1_200
DEFAULT_CHUNK_OVERLAP = 150
DEFAULT_PARAGRAPH_MAX_TOKENS = 512
DEFAULT_PARAGRAPH_OVERLAP = 1

_HEADING_RE = re.compile(r"^(?P<marker>#{1,6})(?!#)\s*(?P<title>.+?)\s*$")
_VIETNAMESE_MARKERS = set("ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ")


class _TextChunkingStrategy(Protocol):
    def split(self, chunking_input: ChunkingInput) -> list[str]:
        """Return chunk strings for the provided text."""


def split_markdown_into_sections(markdown: str) -> list[MarkdownSection]:
    """Split Markdown into heading-scoped sections and preserve heading hierarchy."""

    sections: list[MarkdownSection] = []
    heading_stack: list[tuple[int, str]] = []
    current_title: str | None = None
    current_level = 0
    current_path: tuple[str, ...] = ()
    current_lines: list[str] = []

    def flush_current() -> None:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append(
                MarkdownSection(
                    title=current_title,
                    level=current_level,
                    path=current_path,
                    text=text,
                )
            )

    for line in markdown.splitlines():
        heading_match = _HEADING_RE.match(line.strip())
        if heading_match is None:
            current_lines.append(line)
            continue

        flush_current()
        heading_level = len(heading_match.group("marker"))
        heading_title = heading_match.group("title").strip()
        heading_stack = [heading for heading in heading_stack if heading[0] < heading_level]
        heading_stack.append((heading_level, heading_title))
        current_title = heading_title
        current_level = heading_level
        current_path = tuple(title for _, title in heading_stack)
        current_lines = []

    flush_current()
    return sections


def chunk_markdown(
    markdown: str,
    *,
    max_chars: int = DEFAULT_CHUNK_SIZE,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP,
) -> list[MarkdownChunk]:
    """Split Markdown into deterministic section-aware chunks."""

    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero.")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be greater than or equal to zero.")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars.")

    chunks: list[MarkdownChunk] = []
    for section in split_markdown_into_sections(markdown):
        for text in _split_section_text(
            section.text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        ):
            chunks.append(MarkdownChunk(section=section.title, text=text))
    return chunks


def split_markdown(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split Markdown/text deterministically with word-boundary preference."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")

    cleaned_text = normalize_space(text)
    if not cleaned_text:
        return []
    if len(cleaned_text) <= chunk_size:
        return [cleaned_text]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned_text):
        end = min(start + chunk_size, len(cleaned_text))
        if end < len(cleaned_text):
            split_at = cleaned_text.rfind(" ", start, end)
            if split_at > start:
                end = split_at
        chunk = cleaned_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned_text):
            break
        next_start = max(end - chunk_overlap, 0)
        start = end if next_start <= start else next_start
    return chunks


def paragraph_chunk(
    md_text: str,
    *,
    max_tokens: int = DEFAULT_PARAGRAPH_MAX_TOKENS,
    overlap_paragraphs: int = DEFAULT_PARAGRAPH_OVERLAP,
) -> list[dict[str, int | str]]:
    """Split Markdown by paragraph boundaries using a token budget."""

    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than 0.")
    if overlap_paragraphs < 0:
        raise ValueError("overlap_paragraphs must be greater than or equal to 0.")

    paragraphs = _split_markdown_paragraph_units(md_text, max_tokens=max_tokens)
    chunks: list[dict[str, int | str]] = []
    buffer: list[str] = []
    buffer_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = _count_tokens(paragraph)
        if buffer and buffer_tokens + paragraph_tokens > max_tokens:
            chunks.append({"text": "\n\n".join(buffer), "token_count": buffer_tokens})
            buffer = buffer[-overlap_paragraphs:] if overlap_paragraphs else []
            buffer_tokens = sum(_count_tokens(item) for item in buffer)

        buffer.append(paragraph)
        buffer_tokens += paragraph_tokens

    if buffer:
        chunks.append({"text": "\n\n".join(buffer), "token_count": buffer_tokens})

    return chunks


def detect_lang(text: str) -> str:
    """Detect whether text is likely Vietnamese or English for sentence splitting."""

    lowered = text.lower()
    return "vi" if any(marker in lowered for marker in _VIETNAMESE_MARKERS) else "en"


def split_sentences(text: str) -> list[str]:
    """Split text into multilingual sentences using pysbd when available."""

    stripped_text = text.strip()
    if not stripped_text:
        return []

    language = detect_lang(stripped_text)
    try:
        return _segment_with_pysbd(stripped_text, language)
    except (ImportError, ModuleNotFoundError, RuntimeError, TypeError, ValueError, AttributeError):
        if language != "en":
            try:
                return _segment_with_pysbd(stripped_text, "en")
            except (
                ImportError,
                ModuleNotFoundError,
                RuntimeError,
                TypeError,
                ValueError,
                AttributeError,
            ):
                pass
    return _fallback_sentence_split(stripped_text)


def split_markdown_paragraphs(
    md_text: str,
    *,
    max_tokens: int = DEFAULT_PARAGRAPH_MAX_TOKENS,
    overlap_paragraphs: int = DEFAULT_PARAGRAPH_OVERLAP,
) -> list[str]:
    """Return paragraph-based Markdown chunks."""

    return [
        str(chunk["text"])
        for chunk in paragraph_chunk(
            md_text,
            max_tokens=max_tokens,
            overlap_paragraphs=overlap_paragraphs,
        )
        if str(chunk["text"]).strip()
    ]


def chunk_markdown_by_sections(
    markdown: str,
    *,
    max_tokens: int = DEFAULT_PARAGRAPH_MAX_TOKENS,
    overlap_paragraphs: int = DEFAULT_PARAGRAPH_OVERLAP,
    max_chars: int | None = None,
    overlap_chars: int | None = None,
) -> list[MarkdownChunk]:
    """Split Markdown into deterministic, section-aware token chunks.

    ``max_chars`` and ``overlap_chars`` are accepted for compatibility with the
    previous char-window API. When provided, ``max_chars`` is converted to a
    conservative token budget.
    """

    if max_chars is not None:
        if max_chars <= 0:
            raise ValueError("max_chars must be greater than zero.")
        max_tokens = max(1, max_chars // 4)
    if overlap_chars is not None:
        if overlap_chars < 0:
            raise ValueError("overlap_chars must be greater than or equal to zero.")
        if max_chars is not None and overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars.")
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero.")
    if overlap_paragraphs < 0:
        raise ValueError("overlap_paragraphs must be greater than or equal to zero.")

    chunks: list[MarkdownChunk] = []
    for section in split_markdown_into_sections(markdown):
        for paragraph_result in paragraph_chunk(
            section.text,
            max_tokens=max_tokens,
            overlap_paragraphs=overlap_paragraphs,
        ):
            text = str(paragraph_result["text"]).strip()
            if not text:
                continue
            chunks.append(
                MarkdownChunk(
                    section=section.title,
                    section_level=section.level,
                    section_path=section.path,
                    text=_with_section_heading(section=section, text=text),
                    chunk_token_count=int(paragraph_result["token_count"]),
                    semantic_unit="markdown_section_paragraph_sentence",
                )
            )
    return chunks


def build_chunk_id(source_type: str, source: str, section: str, index: int) -> str:
    """Build a deterministic chunk ID from source and section metadata."""

    return f"{source_type}_{short_hash(source)}_{slugify(section)}_c{index:03d}"


def short_hash(value: str) -> str:
    """Return a stable short SHA-256 digest."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def slugify(value: str) -> str:
    """Normalize a section name for use inside a chunk ID."""

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "main"


def normalize_space(value: str) -> str:
    """Collapse repeated whitespace into single spaces."""

    return " ".join(value.split())


def split_text_with_strategy(
    text: str | ChunkingInput,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    chunking_strategy: _TextChunkingStrategy | None = None,
) -> list[str]:
    """Split text with either deterministic or injected model-assisted chunking."""

    chunking_input = _coerce_chunking_input(text)
    if chunking_strategy is None:
        return split_markdown(
            chunking_input.markdown,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    return [
        normalize_space(chunk)
        for chunk in chunking_strategy.split(chunking_input)
        if normalize_space(chunk)
    ]


def chunking_text(value: str | ChunkingInput) -> str:
    """Return Markdown/text from either raw text or shared chunking input."""

    return _coerce_chunking_input(value).markdown


def _coerce_chunking_input(value: str | ChunkingInput) -> ChunkingInput:
    if isinstance(value, ChunkingInput):
        return value
    return ChunkingInput(markdown=value)


def _split_section_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    normalized_text = text.strip()
    if not normalized_text:
        return []
    if len(normalized_text) <= max_chars:
        return [normalized_text]

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", normalized_text)]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.extend(
                _split_windowed(current, max_chars=max_chars, overlap_chars=overlap_chars)
            )
        current = ""
        chunks.extend(_split_windowed(paragraph, max_chars=max_chars, overlap_chars=overlap_chars))

    if current:
        chunks.extend(_split_windowed(current, max_chars=max_chars, overlap_chars=overlap_chars))

    return chunks


def _split_windowed(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - overlap_chars
    return chunks


def _count_tokens(text: str) -> int:
    try:
        tiktoken = cast(Any, import_module("tiktoken"))
        encoding = tiktoken.get_encoding("o200k_base")
        return len(encoding.encode(text))
    except (ImportError, ModuleNotFoundError, RuntimeError, AttributeError):
        return len(text.split())


def _split_markdown_paragraph_units(md_text: str, *, max_tokens: int) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in md_text.split("\n\n") if paragraph.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        units.extend(_split_oversized_paragraph(paragraph, max_tokens=max_tokens))
    return units


def _split_oversized_paragraph(paragraph: str, *, max_tokens: int) -> list[str]:
    if _count_tokens(paragraph) <= max_tokens:
        return [paragraph]

    sentences = split_sentences(paragraph)
    if len(sentences) <= 1:
        return _split_by_words(paragraph, max_tokens=max_tokens)

    chunks: list[str] = []
    buffer: list[str] = []
    buffer_tokens = 0
    for sentence in sentences:
        sentence_tokens = _count_tokens(sentence)
        if sentence_tokens > max_tokens:
            if buffer:
                chunks.append(" ".join(buffer).strip())
                buffer = []
                buffer_tokens = 0
            chunks.extend(_split_by_words(sentence, max_tokens=max_tokens))
            continue
        if buffer and buffer_tokens + sentence_tokens > max_tokens:
            chunks.append(" ".join(buffer).strip())
            buffer = []
            buffer_tokens = 0
        buffer.append(sentence)
        buffer_tokens += sentence_tokens

    if buffer:
        chunks.append(" ".join(buffer).strip())
    return [chunk for chunk in chunks if chunk]


def _split_by_words(text: str, *, max_tokens: int) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    buffer: list[str] = []
    for word in words:
        candidate = [*buffer, word]
        if buffer and _count_tokens(" ".join(candidate)) > max_tokens:
            chunks.append(" ".join(buffer))
            buffer = [word]
            continue
        buffer = candidate
    if buffer:
        chunks.append(" ".join(buffer))
    return chunks


def _segment_with_pysbd(text: str, language: str) -> list[str]:
    pysbd = cast(Any, import_module("pysbd"))
    segmenter = pysbd.Segmenter(language=language, clean=True)
    sentences = [sentence.strip() for sentence in segmenter.segment(text) if sentence.strip()]
    return sentences or [text]


def _fallback_sentence_split(text: str) -> list[str]:
    sentences = [
        sentence.strip() for sentence in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+", text)
    ]
    return [sentence for sentence in sentences if sentence] or [text]


def _with_section_heading(*, section: MarkdownSection, text: str) -> str:
    if section.title is None:
        return text
    heading_level = min(max(section.level, 1), 6)
    return f"{'#' * heading_level} {section.title}\n\n{text}"
