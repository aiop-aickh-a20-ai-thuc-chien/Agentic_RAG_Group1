from __future__ import annotations

from agentic_rag.ingestion.url.chunking.rag import (
    RagMarkdownBlock,
    WhitespaceTokenCounter,
    chunk_markdown_for_rag,
    parse_markdown_blocks,
)


def test_parse_markdown_blocks_preserves_heading_hierarchy() -> None:
    markdown = """# Parent

Intro paragraph.

## Child

Child paragraph.

### Grandchild

- first
- second
"""

    blocks = parse_markdown_blocks(markdown)

    assert blocks[0] == RagMarkdownBlock(
        text="# Parent",
        kind="heading",
        section_path=("Parent",),
        heading_level=1,
    )
    assert blocks[3].section_path == ("Parent", "Child")
    assert blocks[-1].kind == "list"
    assert blocks[-1].section_path == ("Parent", "Child", "Grandchild")


def test_parse_markdown_blocks_keeps_table_as_one_block() -> None:
    markdown = """# Specs

| Name | Value |
| --- | --- |
| Battery | 50 kWh |
| Range | 300 km |

After table.
"""

    blocks = parse_markdown_blocks(markdown)
    table_blocks = [block for block in blocks if block.kind == "table"]

    assert len(table_blocks) == 1
    assert "| Battery | 50 kWh |" in table_blocks[0].text
    assert table_blocks[0].section_path == ("Specs",)


def test_parse_markdown_blocks_keeps_code_fence_as_one_block() -> None:
    markdown = """# API

```python
def hello() -> str:
    return "hello"
```

Done.
"""

    blocks = parse_markdown_blocks(markdown)
    code_blocks = [block for block in blocks if block.kind == "code"]

    assert len(code_blocks) == 1
    assert 'return "hello"' in code_blocks[0].text


def test_chunk_markdown_for_rag_adds_heading_context_to_child_chunks() -> None:
    markdown = """# Page

## Section

Alpha beta gamma.

Delta epsilon zeta.
"""

    chunks = chunk_markdown_for_rag(
        markdown,
        max_tokens=8,
        overlap_tokens=2,
        token_counter=WhitespaceTokenCounter(),
    )

    assert len(chunks) > 1
    assert chunks[-1].section_path == ("Page", "Section")
    assert chunks[-1].content.startswith("# Page\n## Section")


def test_chunk_markdown_for_rag_does_not_duplicate_current_heading_context() -> None:
    markdown = """# Page

## Section

Alpha beta gamma.

## Next

Delta epsilon zeta.
"""

    chunks = chunk_markdown_for_rag(
        markdown,
        max_tokens=20,
        overlap_tokens=0,
        token_counter=WhitespaceTokenCounter(),
    )

    section_chunk = next(chunk for chunk in chunks if chunk.section_path == ("Page", "Section"))

    assert section_chunk.content.count("## Section") == 1
    assert section_chunk.content.startswith("# Page\n\n## Section")


def test_chunk_markdown_for_rag_adds_section_outline_chunks_for_child_headings() -> None:
    markdown = """# Web scraping

## Techniques

### HTML parsing

HTML parser details.

### DOM parsing

DOM parser details.

### Vertical aggregation

Aggregation details.
"""

    chunks = chunk_markdown_for_rag(
        markdown,
        max_tokens=40,
        overlap_tokens=0,
        token_counter=WhitespaceTokenCounter(),
    )

    outline_chunk = next(chunk for chunk in chunks if "section_outline" in chunk.block_kinds)

    assert outline_chunk.section_path == ("Web scraping", "Techniques")
    assert "Common related sections:" in outline_chunk.content
    assert "- HTML parsing" in outline_chunk.content
    assert "- DOM parsing" in outline_chunk.content
    assert "- Vertical aggregation" in outline_chunk.content


def test_chunk_markdown_for_rag_tracks_token_and_block_metadata() -> None:
    markdown = """# Page

## Section

One two three.

- four
- five
"""

    chunks = chunk_markdown_for_rag(
        markdown,
        max_tokens=20,
        overlap_tokens=3,
        token_counter=WhitespaceTokenCounter(),
    )

    assert chunks
    assert chunks[0].token_count > 0
    assert chunks[0].char_count == len(chunks[0].content)
    assert "heading" in chunks[0].block_kinds
    assert any("list" in chunk.block_kinds for chunk in chunks)


def test_chunk_markdown_for_rag_validates_token_settings() -> None:
    markdown = "# Page\n\nText."

    try:
        chunk_markdown_for_rag(markdown, max_tokens=0)
    except ValueError as exc:
        assert "max_tokens" in str(exc)
    else:
        raise AssertionError("Expected ValueError for max_tokens=0")

    try:
        chunk_markdown_for_rag(markdown, max_tokens=10, overlap_tokens=10)
    except ValueError as exc:
        assert "overlap_tokens" in str(exc)
    else:
        raise AssertionError("Expected ValueError for overlap_tokens >= max_tokens")
