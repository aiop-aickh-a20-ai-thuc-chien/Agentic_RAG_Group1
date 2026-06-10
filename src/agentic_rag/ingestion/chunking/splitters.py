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

DEFAULT_CHUNK_SIZE = 2048  # 512 tokens x ~4 chars/token
DEFAULT_CHUNK_OVERLAP = 0
DEFAULT_PARAGRAPH_MAX_TOKENS = 512
DEFAULT_PARAGRAPH_OVERLAP = 1
DEFAULT_HIERARCHICAL_TARGET_MIN = 512  # 128 tokens x ~4 chars/token; min chars before coalescing
DEFAULT_HIERARCHICAL_MIN_CHARS = 40

_HEADING_RE = re.compile(r"^(?P<marker>#{1,6})(?!#)\s*(?P<title>.+?)\s*$")
_SUBSECTION_NUMBER_RE = re.compile(r"^\s*(?:-\s*)?(\d+(?:\.\d+)*?)[.)]\s+(.{3,120})$")
_BOLD_LEAD_RE = re.compile(r"^\s*(?:-\s*)?\*\*(.{2,80}?)\*\*:?\s*$")
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
    section_body_start = 0
    pos = 0

    def flush_current(body_end: int) -> None:
        raw = markdown[section_body_start:body_end]
        text = raw.strip()
        if text:
            stripped_offset = len(raw) - len(raw.lstrip())
            src_start = section_body_start + stripped_offset
            sections.append(
                MarkdownSection(
                    title=current_title,
                    level=current_level,
                    path=current_path,
                    text=text,
                    source_start=src_start,
                    source_end=src_start + len(text),
                )
            )

    for line in markdown.splitlines(keepends=True):
        heading_match = _HEADING_RE.match(line.strip())
        if heading_match is None:
            pos += len(line)
            continue

        flush_current(pos)
        heading_level = len(heading_match.group("marker"))
        heading_title = heading_match.group("title").strip()
        heading_stack = [heading for heading in heading_stack if heading[0] < heading_level]
        heading_stack.append((heading_level, heading_title))
        current_title = heading_title
        current_level = heading_level
        current_path = tuple(title for _, title in heading_stack)
        pos += len(line)
        section_body_start = pos

    flush_current(len(markdown))
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
    root_title: str | None = None,
) -> list[MarkdownChunk]:
    """Split Markdown into deterministic hierarchical chunks."""

    effective_max_chars = max_chars or DEFAULT_CHUNK_SIZE
    if max_chars is None and max_tokens != DEFAULT_PARAGRAPH_MAX_TOKENS:
        effective_max_chars = max(1, max_tokens * 4)
    effective_overlap_chars = (
        min(DEFAULT_CHUNK_OVERLAP, effective_max_chars - 1)
        if overlap_chars is None
        else overlap_chars
    )
    if max_chars is not None and max_chars <= 0:
        raise ValueError("max_chars must be greater than zero.")
    if effective_overlap_chars < 0:
        raise ValueError("overlap_chars must be greater than or equal to zero.")
    if effective_overlap_chars >= effective_max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars.")
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero.")
    if overlap_paragraphs < 0:
        raise ValueError("overlap_paragraphs must be greater than or equal to zero.")

    chunks: list[MarkdownChunk] = []
    blocks = _merge_blocks_by_major(
        _coalesce_short_blocks(
            _flatten_hierarchical_blocks(markdown, root_title=root_title),
            max_chars=effective_max_chars,
        ),
        max_chars=effective_max_chars,
    )
    for path, section_level, _merged_text, src_start, src_end in blocks:
        body = markdown[src_start:src_end]
        parts = (
            _split_with_overlap(
                body,
                max_chars=effective_max_chars,
                overlap_chars=effective_overlap_chars,
            )
            if len(body) > effective_max_chars
            else [body]
        )
        part_total = len(parts)
        part_search_from = 0
        for part_index, part in enumerate(parts, start=1):
            chunk_text = part.strip()
            if not chunk_text:
                continue
            if (
                part_total == 1
                and len(chunk_text) < DEFAULT_HIERARCHICAL_MIN_CHARS
                and not any(char.isdigit() for char in chunk_text)
            ):
                continue
            part_start, part_end = _part_source_range(
                chunk_text, body, src_start, src_end, part_search_from
            )
            part_search_from = part_start - src_start + len(chunk_text)
            section = path[-1] if path else None
            chunks.append(
                MarkdownChunk(
                    section=section,
                    section_level=section_level,
                    section_path=tuple(path),
                    text=_with_path_heading(
                        path=path, section_level=section_level, text=chunk_text
                    ),
                    metadata={
                        "chunk_part_index": part_index,
                        "chunk_part_total": part_total,
                        "chunk_input_range": [part_start, part_end],
                    },
                    chunk_token_count=_count_tokens(chunk_text),
                    semantic_unit="hierarchical_markdown_subsection",
                )
            )
    return chunks


def _flatten_hierarchical_blocks(
    markdown: str,
    *,
    root_title: str | None = None,
) -> list[tuple[list[str], int, str, int, int]]:
    blocks: list[tuple[list[str], int, str, int, int]] = []
    for section in split_markdown_into_sections(markdown):
        if not section.text.strip():
            continue
        section_path = _section_path_with_root(section.path, root_title=root_title)
        blocks.extend(_blocks_for_section(section, section_path))
    return blocks


def _subsection_source_range(
    section: MarkdownSection, text: str, search_from: int
) -> tuple[int, int]:
    idx = section.text.find(text, search_from)
    if idx >= 0:
        src_start = section.source_start + idx
        return src_start, src_start + len(text)
    return section.source_start, section.source_end


def _extend_src_start_to_title(section: MarkdownSection, src_start: int) -> int:
    """Pull src_start back to include the numbered/bold title line that precedes the body.

    _split_subsections strips the title line from the body text, so the default
    src_start points to the first body character. This helper walks backward through
    section.text to find the matching title line and returns its start position.
    """
    relative_pos = src_start - section.source_start
    if relative_pos <= 0:
        return src_start
    preceding = section.text[:relative_pos].rstrip("\r\n")
    if not preceding:
        return src_start
    lines = preceding.split("\n")
    last_line = lines[-1].strip()
    if not (
        _SUBSECTION_NUMBER_RE.match(last_line)
        or _BOLD_LEAD_RE.match(last_line)
        or _is_allcaps_heading_line(last_line)
    ):
        return src_start
    # Compute the offset of the title line in section.text
    prefix = "\n".join(lines[:-1])
    title_offset = len(prefix) + (1 if lines[:-1] else 0)
    return section.source_start + title_offset


def _blocks_for_section(
    section: MarkdownSection,
    section_path: list[str],
) -> list[tuple[list[str], int, str, int, int]]:
    result: list[tuple[list[str], int, str, int, int]] = []
    search_from = 0
    for subsection_title, subsection_text in _split_subsections(section.text):
        text = subsection_text.strip()
        if not text:
            continue
        full_path = section_path + ([subsection_title] if subsection_title else [])
        src_start, src_end = _subsection_source_range(section, text, search_from)
        if subsection_title is not None:
            src_start = _extend_src_start_to_title(section, src_start)
        search_from = src_end - section.source_start
        result.append((full_path, section.level, text, src_start, src_end))
    return result


def _section_path_with_root(
    section_path: tuple[str, ...],
    *,
    root_title: str | None,
) -> list[str]:
    path = list(section_path)
    cleaned_root = (root_title or "").strip()
    if not cleaned_root:
        return path
    if path and _normalized_heading(path[0]) == _normalized_heading(cleaned_root):
        return path
    return [cleaned_root, *path]


def _normalized_heading(value: str) -> str:
    return value.strip().lower()


def _is_allcaps_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 60 or stripped.startswith(("#", "|", "-")):
        return False
    letter_count = sum(1 for c in stripped if c.isalpha())
    return letter_count >= 3 and stripped.isupper()


def _split_subsections(content: str) -> list[tuple[str | None, str]]:
    groups: list[tuple[str | None, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def push_current() -> None:
        text = "\n".join(current_lines).strip()
        if text or current_title:
            groups.append((current_title, text))

    for line in content.splitlines():
        stripped = line.strip()
        numbered_match = _SUBSECTION_NUMBER_RE.match(stripped)
        bold_match = _BOLD_LEAD_RE.match(stripped)
        if numbered_match is not None:
            push_current()
            current_title = f"{numbered_match.group(1)} {numbered_match.group(2)}".strip()
            current_lines = []
            continue
        if bold_match is not None:
            push_current()
            current_title = bold_match.group(1).strip()
            current_lines = []
            continue
        if _is_allcaps_heading_line(stripped):
            push_current()
            current_title = stripped
            current_lines = []
            continue
        current_lines.append(line)

    push_current()
    if len(groups) <= 1:
        return [(None, content.strip())]
    return groups


def _coalesce_short_blocks(
    blocks: list[tuple[list[str], int, str, int, int]],
    *,
    max_chars: int,
) -> list[tuple[list[str], int, str, int, int]]:
    output: list[tuple[list[str], int, str, int, int]] = []
    group: list[tuple[list[str], int, str, int, int]] = []
    group_parent: tuple[str, ...] | None = None
    group_len = 0

    def block_len(path: list[str], text: str) -> int:
        label_len = len(path[-1]) + 2 if path else 0
        return label_len + len(text) + 1

    def is_short_candidate(path: list[str], text: str) -> bool:
        return (
            len(path) >= 2
            and len(text.strip()) < DEFAULT_HIERARCHICAL_TARGET_MIN
            and len(text) <= max_chars
        )

    def flush_group() -> None:
        nonlocal group, group_parent, group_len
        if not group:
            return
        if len(group) == 1:
            output.append(group[0])
        else:
            common_path, merged_text = _format_merged_blocks(group)
            merged_start = min(b[3] for b in group)
            merged_end = max(b[4] for b in group)
            output.append((common_path, group[0][1], merged_text, merged_start, merged_end))
        group = []
        group_parent = None
        group_len = 0

    for path, section_level, text, src_start, src_end in blocks:
        parent = tuple(path[:-1]) if len(path) >= 2 else None
        additional_len = block_len(path, text)
        if is_short_candidate(path, text):
            if group and parent == group_parent and group_len + additional_len <= max_chars:
                group.append((path, section_level, text, src_start, src_end))
                group_len += additional_len
                continue
            flush_group()
            group = [(path, section_level, text, src_start, src_end)]
            group_parent = parent
            group_len = additional_len
            continue
        flush_group()
        output.append((path, section_level, text, src_start, src_end))

    flush_group()
    return output


def _merge_blocks_by_major(
    blocks: list[tuple[list[str], int, str, int, int]],
    *,
    max_chars: int,
) -> list[tuple[list[str], int, str, int, int]]:
    output: list[tuple[list[str], int, str, int, int]] = []
    buffer: list[tuple[list[str], int, str, int, int]] = []
    buffer_len = 0
    buffer_major: tuple[str, ...] | None = None

    def flush_buffer() -> None:
        nonlocal buffer, buffer_len, buffer_major
        if not buffer:
            return
        common_path, merged_text = _format_merged_blocks(buffer)
        merged_start = min(b[3] for b in buffer)
        merged_end = max(b[4] for b in buffer)
        output.append((common_path, buffer[0][1], merged_text, merged_start, merged_end))
        buffer = []
        buffer_len = 0
        buffer_major = None

    for path, section_level, text, src_start, src_end in blocks:
        major = tuple(path[:2])
        if len(text) > max_chars:
            flush_buffer()
            output.append((path, section_level, text, src_start, src_end))
            continue
        if buffer and (major != buffer_major or buffer_len + len(text) + 1 > max_chars):
            flush_buffer()
        if not buffer:
            buffer_major = major
        buffer.append((path, section_level, text, src_start, src_end))
        buffer_len += len(text) + 1

    flush_buffer()
    return output


def _format_merged_blocks(
    blocks: list[tuple[list[str], int, str, int, int]],
) -> tuple[list[str], str]:
    common_path = _common_prefix([b[0] for b in blocks])
    lines: list[str] = []
    for path, _, text, _s, _e in blocks:
        label = " / ".join(path[len(common_path) :])
        lines.append(f"{label}: {text}" if label else text)
    return common_path, "\n".join(lines).strip()


def _common_prefix(paths: list[list[str]]) -> list[str]:
    if not paths:
        return []
    common: list[str] = []
    for index in range(min(len(path) for path in paths)):
        values = {path[index] for path in paths}
        if len(values) != 1:
            break
        common.append(paths[0][index])
    return common


def _split_with_overlap(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    base_parts = _pack_units(text, max_chars=max_chars)
    if len(base_parts) <= 1:
        return base_parts
    parts = [base_parts[0]]
    for index in range(1, len(base_parts)):
        previous = base_parts[index - 1]
        tail = previous[-overlap_chars:] if len(previous) > overlap_chars else previous
        if " " in tail:
            tail = tail[tail.index(" ") + 1 :]
        parts.append(f"{tail}\n{base_parts[index]}".strip())
    return parts


def _pack_units(text: str, *, max_chars: int) -> list[str]:
    stripped_text = text.strip()
    if not stripped_text:
        return []
    if len(stripped_text) <= max_chars:
        return [stripped_text]

    units: list[str] = []
    for block in re.split(r"\n\s*\n", stripped_text):
        block = block.strip()
        if not block:
            continue
        if len(block) <= max_chars:
            units.append(block)
            continue
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if len(line) <= max_chars:
                units.append(line)
            else:
                units.extend(_hard_split(line, max_chars=max_chars))

    chunks: list[str] = []
    current_units: list[str] = []
    current_len = 0
    for unit in units:
        additional_len = len(unit) + (1 if current_units else 0)
        if current_units and current_len + additional_len > max_chars:
            chunks.append("\n".join(current_units))
            current_units = [unit]
            current_len = len(unit)
            continue
        current_units.append(unit)
        current_len += additional_len
    if current_units:
        chunks.append("\n".join(current_units))
    return chunks


def _hard_split(text: str, *, max_chars: int) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+", text)
    output: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) + 1 > max_chars:
            output.append(current.strip())
            current = part
        else:
            current = f"{current} {part}".strip()
        while len(current) > max_chars:
            output.append(current[:max_chars])
            current = current[max_chars:]
    if current.strip():
        output.append(current.strip())
    return output


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


def _part_source_range(
    chunk_text: str,
    body: str,
    src_start: int,
    src_end: int,
    search_from: int,
) -> tuple[int, int]:
    idx = body.find(chunk_text, search_from)
    if idx >= 0:
        part_start = src_start + idx
        return part_start, part_start + len(chunk_text)
    return src_start, src_end


def _with_path_heading(*, path: list[str], section_level: int, text: str) -> str:
    if not path:
        return text
    heading_level = min(max(section_level, 1), 6)
    heading = path[-1]
    return f"{'#' * heading_level} {heading}\n\n{text}"
