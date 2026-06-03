"""Deterministic Markdown/text chunking for URL ingestion."""

from __future__ import annotations

import hashlib
import re
from importlib import import_module
from typing import Any, cast

from agentic_rag.core.contracts import Chunk

DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 1
DEFAULT_PARAGRAPH_MAX_TOKENS = 512
DEFAULT_PARAGRAPH_OVERLAP = 1
_VIETNAMESE_MARKERS = set("ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ")


def build_chunks(
    *,
    text: str,
    source: str,
    source_type: str,
    section: str,
    url: str | None,
    title: str | None,
    fetched_at: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Build shared Chunk objects from normalized Markdown/text."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")

    chunks: list[Chunk] = []
    content_hash = short_hash(text)
    text_chunks = _split_text(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    for index, chunk_text in enumerate(text_chunks, start=1):
        chunks.append(
            Chunk(
                chunk_id=build_chunk_id(source_type, source, section, index),
                text=chunk_text,
                metadata={
                    "source": source,
                    "source_type": source_type,
                    "file_name": None,
                    "url": url,
                    "page": None,
                    "section": section,
                    "title": title,
                    "fetched_at": fetched_at,
                    "content_hash": content_hash,
                    "chunk_index": index,
                },
            )
        )
    return chunks


def split_markdown(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split Markdown/text deterministically with word-boundary preference."""

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
            chunks.append(
                {
                    "text": "\n\n".join(buffer),
                    "token_count": buffer_tokens,
                }
            )
            buffer = buffer[-overlap_paragraphs:] if overlap_paragraphs else []
            buffer_tokens = sum(_count_tokens(item) for item in buffer)

        buffer.append(paragraph)
        buffer_tokens += paragraph_tokens

    if buffer:
        chunks.append(
            {
                "text": "\n\n".join(buffer),
                "token_count": buffer_tokens,
            }
        )

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


def _split_text(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    return split_markdown_paragraphs(
        text,
        max_tokens=chunk_size,
        overlap_paragraphs=chunk_overlap,
    )


def _count_tokens(text: str) -> int:
    try:
        tiktoken = cast(Any, import_module("tiktoken"))
        encoding = tiktoken.get_encoding("cl100k_base")
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
