from agentic_rag.ingestion import chunking
from agentic_rag.ingestion.chunking.chunkers import DeterministicMarkdownChunker
from agentic_rag.ingestion.chunking.models import ChunkCandidate, ChunkingInput
from agentic_rag.ingestion.chunking.splitters import split_markdown
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


def test_url_chunking_reuses_shared_text_helpers() -> None:
    text = "alpha beta gamma delta epsilon"

    assert url_chunking.split_markdown(text, chunk_size=16, chunk_overlap=5) == (
        chunking.split_markdown(text, chunk_size=16, chunk_overlap=5)
    )
    assert url_chunking.normalize_space is chunking.normalize_space
    assert url_chunking.short_hash is chunking.short_hash
    assert url_chunking.slugify is chunking.slugify
