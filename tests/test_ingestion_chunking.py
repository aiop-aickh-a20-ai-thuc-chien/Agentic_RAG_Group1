from agentic_rag.ingestion import chunking
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


def test_url_chunking_reuses_shared_text_helpers() -> None:
    text = "alpha beta gamma delta epsilon"

    assert url_chunking.split_markdown(text, chunk_size=16, chunk_overlap=5) == (
        chunking.split_markdown(text, chunk_size=16, chunk_overlap=5)
    )
    assert url_chunking.normalize_space is chunking.normalize_space
    assert url_chunking.short_hash is chunking.short_hash
    assert url_chunking.slugify is chunking.slugify
