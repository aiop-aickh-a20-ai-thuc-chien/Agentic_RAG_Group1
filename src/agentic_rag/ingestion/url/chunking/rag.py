"""RAG-oriented Markdown chunking for URL ingestion.

This module keeps Markdown structure as the primary chunking boundary. It is
designed for URL pages where headings, lists, tables, links, and code blocks
carry retrieval context that is easy to lose with plain character windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

DEFAULT_MAX_TOKENS = 450
DEFAULT_OVERLAP_TOKENS = 70


class TokenCounter(Protocol):
    """Minimal token counter protocol used by the chunker."""

    def count(self, text: str) -> int:
        """Return the token count for text."""


@dataclass(frozen=True)
class RagMarkdownBlock:
    """One semantic Markdown block with its active heading path."""

    text: str
    kind: str
    section_path: tuple[str, ...] = ()
    heading_level: int | None = None


@dataclass(frozen=True)
class RagMarkdownChunk:
    """Chunk payload and metadata suitable for retrieval/citation."""

    chunk_index: int
    content: str
    section_path: tuple[str, ...]
    token_count: int
    char_count: int
    block_kinds: tuple[str, ...] = field(default_factory=tuple)


class WhitespaceTokenCounter:
    """Small deterministic fallback when tiktoken is not installed."""

    def count(self, text: str) -> int:
        return len(text.split())


class TiktokenTokenCounter:
    """Token counter backed by tiktoken when available."""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        try:
            import tiktoken
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("tiktoken is required for TiktokenTokenCounter") from exc

        self._encoding = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))


def chunk_markdown_for_rag(
    markdown: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    token_counter: TokenCounter | None = None,
) -> tuple[RagMarkdownChunk, ...]:
    """Split Markdown into heading-aware chunks for RAG.

    The chunker first parses Markdown into semantic blocks, then packs blocks
    into token-bounded chunks. Each chunk gets heading context prepended when it
    would otherwise be detached from its parent section.
    """

    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than 0")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must be greater than or equal to 0")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    counter = token_counter or _default_token_counter()
    blocks = parse_markdown_blocks(markdown)
    outline_chunks = _build_outline_chunks(blocks, counter=counter)
    content_chunks = _chunk_blocks(
        blocks,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        counter=counter,
    )
    return _reindex_chunks([*outline_chunks, *content_chunks])


def _chunk_blocks(
    blocks: tuple[RagMarkdownBlock, ...],
    *,
    max_tokens: int,
    overlap_tokens: int,
    counter: TokenCounter,
) -> list[RagMarkdownChunk]:
    chunks: list[RagMarkdownChunk] = []
    pending_blocks: list[RagMarkdownBlock] = []
    pending_texts: list[str] = []
    pending_kinds: list[str] = []
    pending_section_path: tuple[str, ...] = ()

    for block in blocks:
        if block.kind == "heading" and pending_texts and _has_non_heading_block(pending_blocks):
            chunks.append(
                _build_chunk(
                    chunk_index=len(chunks),
                    texts=pending_texts,
                    blocks=pending_blocks,
                    section_path=pending_section_path,
                    counter=counter,
                )
            )
            pending_blocks = []
            pending_texts = []
            pending_kinds = []

        candidate_texts = [*pending_texts, block.text]
        candidate_content = _with_context("\n\n".join(candidate_texts), block.section_path)
        if pending_texts and counter.count(candidate_content) > max_tokens:
            chunks.append(
                _build_chunk(
                    chunk_index=len(chunks),
                    texts=pending_texts,
                    blocks=pending_blocks,
                    section_path=pending_section_path,
                    counter=counter,
                )
            )
            pending_blocks, pending_texts, pending_kinds = _overlap_tail(
                pending_blocks, overlap_tokens=overlap_tokens, counter=counter
            )
            pending_texts.append(block.text)
            pending_blocks.append(block)
            pending_kinds.append(block.kind)
            pending_section_path = block.section_path or pending_section_path
            continue

        pending_blocks.append(block)
        pending_texts.append(block.text)
        pending_kinds.append(block.kind)
        pending_section_path = block.section_path or pending_section_path

    if pending_texts:
        chunks.append(
            _build_chunk(
                chunk_index=len(chunks),
                texts=pending_texts,
                blocks=pending_blocks,
                section_path=pending_section_path,
                counter=counter,
            )
        )

    return chunks


def parse_markdown_blocks(markdown: str) -> tuple[RagMarkdownBlock, ...]:
    """Parse Markdown into coarse semantic blocks with heading hierarchy."""

    blocks: list[RagMarkdownBlock] = []
    section_stack: list[str] = []
    lines = markdown.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            block_lines = [line]
            index += 1
            while index < len(lines):
                block_lines.append(lines[index])
                if lines[index].strip().startswith("```"):
                    index += 1
                    break
                index += 1
            blocks.append(
                RagMarkdownBlock(
                    text="\n".join(block_lines).strip(),
                    kind="code",
                    section_path=tuple(section_stack),
                )
            )
            continue

        heading = _parse_heading(stripped)
        if heading is not None:
            level, title = heading
            section_stack = [*section_stack[: level - 1], title]
            blocks.append(
                RagMarkdownBlock(
                    text=stripped,
                    kind="heading",
                    section_path=tuple(section_stack),
                    heading_level=level,
                )
            )
            index += 1
            continue

        if _is_table_start(lines, index):
            block_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index]:
                block_lines.append(lines[index])
                index += 1
            blocks.append(
                RagMarkdownBlock(
                    text="\n".join(block_lines).strip(),
                    kind="table",
                    section_path=tuple(section_stack),
                )
            )
            continue

        if _is_list_item(stripped):
            block_lines = [line]
            index += 1
            while index < len(lines):
                next_stripped = lines[index].strip()
                if not next_stripped:
                    index += 1
                    break
                if not _is_list_item(next_stripped) and not lines[index].startswith((" ", "\t")):
                    break
                block_lines.append(lines[index])
                index += 1
            blocks.append(
                RagMarkdownBlock(
                    text="\n".join(block_lines).strip(),
                    kind="list",
                    section_path=tuple(section_stack),
                )
            )
            continue

        block_lines = [line]
        index += 1
        while index < len(lines):
            next_line = lines[index]
            next_stripped = next_line.strip()
            if not next_stripped:
                index += 1
                break
            if (
                _parse_heading(next_stripped) is not None
                or next_stripped.startswith("```")
                or _is_list_item(next_stripped)
                or _is_table_start(lines, index)
            ):
                break
            block_lines.append(next_line)
            index += 1
        blocks.append(
            RagMarkdownBlock(
                text="\n".join(block_lines).strip(),
                kind="paragraph",
                section_path=tuple(section_stack),
            )
        )

    return tuple(blocks)


def _build_outline_chunks(
    blocks: tuple[RagMarkdownBlock, ...],
    *,
    counter: TokenCounter,
) -> list[RagMarkdownChunk]:
    outline_blocks = _build_section_outline_blocks(blocks)
    return [
        _build_chunk(
            chunk_index=index,
            texts=[block.text],
            blocks=[block],
            section_path=block.section_path,
            counter=counter,
        )
        for index, block in enumerate(outline_blocks)
    ]


def _build_section_outline_blocks(
    blocks: tuple[RagMarkdownBlock, ...],
) -> list[RagMarkdownBlock]:
    heading_blocks = [block for block in blocks if block.kind == "heading" and block.heading_level]
    outline_blocks: list[RagMarkdownBlock] = []

    for index, heading in enumerate(heading_blocks):
        children = _direct_child_headings(heading, heading_blocks[index + 1 :])
        if len(children) < 2:
            continue
        outline_text = "\n".join(
            [
                _heading_line_for_path(heading.section_path),
                "",
                "Common related sections:",
                *[f"- {child.section_path[-1]}" for child in children],
            ]
        )
        outline_blocks.append(
            RagMarkdownBlock(
                text=outline_text,
                kind="section_outline",
                section_path=heading.section_path,
                heading_level=heading.heading_level,
            )
        )

    return outline_blocks


def _direct_child_headings(
    parent: RagMarkdownBlock,
    candidates: list[RagMarkdownBlock],
) -> list[RagMarkdownBlock]:
    if parent.heading_level is None:
        return []
    child_level = parent.heading_level + 1
    children: list[RagMarkdownBlock] = []
    for candidate in candidates:
        if candidate.heading_level is None:
            continue
        if candidate.heading_level <= parent.heading_level:
            break
        if candidate.heading_level == child_level:
            children.append(candidate)
    return children


def _heading_line_for_path(section_path: tuple[str, ...]) -> str:
    if not section_path:
        return "# main"
    level = min(len(section_path), 6)
    return f"{'#' * level} {section_path[-1]}"


def _reindex_chunks(chunks: list[RagMarkdownChunk]) -> tuple[RagMarkdownChunk, ...]:
    return tuple(
        RagMarkdownChunk(
            chunk_index=index,
            content=chunk.content,
            section_path=chunk.section_path,
            token_count=chunk.token_count,
            char_count=chunk.char_count,
            block_kinds=chunk.block_kinds,
        )
        for index, chunk in enumerate(chunks)
    )


def _default_token_counter() -> TokenCounter:
    try:
        return TiktokenTokenCounter()
    except RuntimeError:
        return WhitespaceTokenCounter()


def _has_non_heading_block(blocks: list[RagMarkdownBlock]) -> bool:
    return any(block.kind != "heading" for block in blocks)


def _build_chunk(
    *,
    chunk_index: int,
    texts: list[str],
    blocks: list[RagMarkdownBlock],
    section_path: tuple[str, ...],
    counter: TokenCounter,
) -> RagMarkdownChunk:
    content = _with_context("\n\n".join(texts).strip(), section_path)
    return RagMarkdownChunk(
        chunk_index=chunk_index,
        content=content,
        section_path=section_path,
        token_count=counter.count(content),
        char_count=len(content),
        block_kinds=tuple(block.kind for block in blocks),
    )


def _with_context(content: str, section_path: tuple[str, ...]) -> str:
    if not section_path:
        return content.strip()

    context_lines = [
        f"{'#' * min(level, 6)} {title}" for level, title in enumerate(section_path, start=1)
    ]
    context = "\n".join(context_lines)
    stripped = content.strip()
    if stripped.startswith(context):
        return stripped
    existing_heading_count = _matching_leading_context_heading_count(
        stripped,
        context_lines,
    )
    if existing_heading_count:
        missing_context = "\n".join(context_lines[: len(context_lines) - existing_heading_count])
        if missing_context:
            return f"{missing_context}\n\n{stripped}".strip()
        return stripped
    return f"{context}\n\n{stripped}".strip()


def _matching_leading_context_heading_count(
    content: str,
    context_lines: list[str],
) -> int:
    content_lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not content_lines:
        return 0
    for start in range(len(context_lines)):
        suffix = context_lines[start:]
        if content_lines[: len(suffix)] == suffix:
            return len(suffix)
    return 0


def _overlap_tail(
    blocks: list[RagMarkdownBlock],
    *,
    overlap_tokens: int,
    counter: TokenCounter,
) -> tuple[list[RagMarkdownBlock], list[str], list[str]]:
    if overlap_tokens == 0:
        return [], [], []

    selected: list[RagMarkdownBlock] = []
    token_total = 0
    for block in reversed(blocks):
        block_tokens = counter.count(block.text)
        if selected and token_total + block_tokens > overlap_tokens:
            break
        selected.append(block)
        token_total += block_tokens
    selected.reverse()
    return selected, [block.text for block in selected], [block.kind for block in selected]


def _parse_heading(line: str) -> tuple[int, str] | None:
    marker_count = len(line) - len(line.lstrip("#"))
    if marker_count == 0 or marker_count > 6:
        return None
    if len(line) <= marker_count or line[marker_count] != " ":
        return None
    title = line[marker_count:].strip()
    if not title:
        return None
    return marker_count, title


def _is_list_item(line: str) -> bool:
    if line.startswith(("- ", "* ", "+ ")):
        return True
    marker, _, rest = line.partition(". ")
    return marker.isdigit() and bool(rest.strip())


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    header = lines[index].strip()
    separator = lines[index + 1].strip()
    if "|" not in header or "|" not in separator:
        return False
    separator_chars = set(separator.replace("|", "").replace(":", "").replace(" ", "").strip())
    return bool(separator_chars) and separator_chars <= {"-"}
