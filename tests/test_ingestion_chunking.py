from agentic_rag.ingestion import chunking
from agentic_rag.ingestion.chunking.chunkers import DeterministicMarkdownChunker
from agentic_rag.ingestion.chunking.models import ChunkCandidate, ChunkingInput
from agentic_rag.ingestion.chunking.splitters import (
    chunk_markdown_by_sections,
    detect_lang,
    paragraph_chunk,
    split_markdown,
    split_markdown_paragraphs,
    split_sentences,
)
from agentic_rag.ingestion.pdf import chunking as pdf_chunking
from agentic_rag.ingestion.url import chunking as url_chunking


def test_shared_markdown_chunking_is_pdf_compatibility_source() -> None:
    markdown = "# Warranty\nPin duoc bao hanh 8 nam."

    shared_chunks = chunking.chunk_markdown(markdown)
    pdf_chunks = pdf_chunking.chunk_markdown(markdown)

    assert pdf_chunks == shared_chunks
    assert pdf_chunking.MarkdownChunk is chunking.MarkdownChunk
    assert pdf_chunks[0].section == "Warranty"
    assert pdf_chunks[0].text == "Pin duoc bao hanh 8 nam."


def test_shared_chunker_contract_accepts_normalized_chunking_input() -> None:
    chunking_input = chunking.ChunkingInput(
        markdown="# Warranty\nPin duoc bao hanh 8 nam.",
        source_type="pdf",
        parser="docling",
        source_path="warranty.pdf",
    )

    chunker = chunking.DeterministicMarkdownChunker()
    chunks = chunker.chunk(chunking_input)

    assert chunks == [chunking.ChunkCandidate(section="Warranty", text="Pin duoc bao hanh 8 nam.")]
    assert chunker.chunker_name == "deterministic"
    assert chunker.requires_native_document is False


def test_chunking_package_exposes_focused_submodules_and_compat_exports() -> None:
    assert chunking.ChunkingInput is ChunkingInput
    assert chunking.ChunkCandidate is ChunkCandidate
    assert chunking.DeterministicMarkdownChunker is DeterministicMarkdownChunker
    assert chunking.split_markdown is split_markdown
    assert chunking.paragraph_chunk is paragraph_chunk
    assert chunking.split_markdown_paragraphs is split_markdown_paragraphs
    assert chunking.split_sentences is split_sentences
    assert chunking.detect_lang is detect_lang
    assert chunking.chunk_markdown_by_sections is chunk_markdown_by_sections


def test_url_chunking_reuses_shared_text_helpers() -> None:
    text = "alpha beta gamma delta epsilon"

    assert url_chunking.split_markdown(text, chunk_size=16, chunk_overlap=5) == (
        chunking.split_markdown(text, chunk_size=16, chunk_overlap=5)
    )
    assert url_chunking.normalize_space is chunking.normalize_space
    assert url_chunking.short_hash is chunking.short_hash
    assert url_chunking.slugify is chunking.slugify
    assert url_chunking.paragraph_chunk is chunking.paragraph_chunk
    assert url_chunking.split_markdown_paragraphs is chunking.split_markdown_paragraphs
    assert url_chunking.split_sentences is chunking.split_sentences
    assert url_chunking.detect_lang is chunking.detect_lang
    assert url_chunking.chunk_markdown_by_sections is chunking.chunk_markdown_by_sections


def test_shared_paragraph_chunking_uses_boundaries_and_overlap() -> None:
    text = "\n\n".join(
        [
            "Alpha one two three.",
            "Beta one two three.",
            "Gamma one two three.",
        ]
    )

    chunks = chunking.split_markdown_paragraphs(text, max_tokens=7, overlap_paragraphs=1)

    assert chunks == [
        "Alpha one two three.",
        "Alpha one two three.\n\nBeta one two three.",
        "Beta one two three.\n\nGamma one two three.",
    ]


def test_shared_sentence_splitting_detects_english_and_vietnamese() -> None:
    english_sentences = chunking.split_sentences("Open the page. Extract clean Markdown.")
    vietnamese_sentences = chunking.split_sentences(
        "M\u1edf trang URL. Tr\u00edch xu\u1ea5t Markdown s\u1ea1ch."
    )

    assert chunking.detect_lang("Open the page.") == "en"
    assert chunking.detect_lang("Tr\u00edch xu\u1ea5t n\u1ed9i dung ti\u1ebfng Vi\u1ec7t.") == "vi"
    assert english_sentences == ["Open the page.", "Extract clean Markdown."]
    assert vietnamese_sentences == [
        "M\u1edf trang URL.",
        "Tr\u00edch xu\u1ea5t Markdown s\u1ea1ch.",
    ]


def test_shared_hierarchical_markdown_chunking_preserves_section_metadata() -> None:
    chunks = chunking.chunk_markdown_by_sections(
        "# Section\nDoan mot ngan du dai de giu lai trong pipeline.\n\n"
        "Doan hai ngan nhung van vuot nguong toi thieu.",
        max_chars=100,
        overlap_chars=10,
    )

    assert [item.section for item in chunks] == ["Section"]
    assert chunks[0].section_level == 1
    assert chunks[0].section_path == ("Section",)
    assert chunks[0].text == (
        "# Section\n\nDoan mot ngan du dai de giu lai trong pipeline.\n\n"
        "Doan hai ngan nhung van vuot nguong toi thieu."
    )
    assert chunks[0].chunk_token_count is not None
    assert chunks[0].chunk_token_count > 0
    assert chunks[0].semantic_unit == "hierarchical_markdown_subsection"
    assert chunks[0].section_path == ("Section",)
    assert chunks[0].metadata["chunk_part_index"] == 1
    assert chunks[0].metadata["chunk_part_total"] == 1
