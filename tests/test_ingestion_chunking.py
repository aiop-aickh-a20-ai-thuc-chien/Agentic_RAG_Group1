from agentic_rag.ingestion import chunking
from agentic_rag.ingestion.chunking.chunkers import DeterministicMarkdownChunker
from agentic_rag.ingestion.chunking.models import ChunkCandidate, ChunkingInput
from agentic_rag.ingestion.chunking.splitters import (
    chunk_markdown_by_sections,
    chunk_structural_clarity,
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
    assert chunking.chunk_text_quality("tiny") == {
        "char_count": 4,
        "word_count": 1,
        "has_structured_signal": False,
        "structural_clarity": {
            "label": "clear",
            "issue_codes": [],
            "numeric_value_count": 0,
            "numeric_density": 0.0,
            "line_count": 1,
            "repeated_phrase_density": 0.0,
            "needs_table_reconstruction": False,
            "needs_deduplication": False,
            "is_clear": True,
        },
        "is_usable": False,
    }
    assert chunking.split_markdown_paragraphs is split_markdown_paragraphs
    assert chunking.split_sentences is split_sentences
    assert chunking.detect_lang is detect_lang
    assert chunking.chunk_markdown_by_sections is chunk_markdown_by_sections
    assert chunking.chunk_structural_clarity is chunk_structural_clarity


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
    assert url_chunking.chunk_text_quality is chunking.chunk_text_quality
    assert url_chunking.is_usable_chunk_text is chunking.is_usable_chunk_text


def test_shared_chunk_quality_marks_low_signal_and_useful_chunks() -> None:
    assert chunking.is_usable_chunk_text("Ưu đãi chỉ tới 31/12!") is False
    assert (
        chunking.is_usable_chunk_text(
            "Dòng xe E-SUV có 6-7 chỗ ngồi, quãng đường lên tới 626 km "
            "và giá bán từ 1.229.180.000 VNĐ."
        )
        is True
    )


def test_shared_chunk_quality_rejects_flattened_numeric_tables() -> None:
    flattened_table = (
        "# VinFast\n\n"
        "D-SUV 5 cho 480 km 819.180.000 VND 999.000.000 VND "
        "MPV 7 cho 450 km 704.340.000 VND 819.000.000 VND "
        "A-SUV 326 km 411.940.000 VND 479.000.000 VND "
        "B-SUV 318 km 644.140.000 VND 749.000.000 VND "
        "C-SUV 496 km 678.540.000 VND 789.000.000 VND "
        "E-SUV 626 km 1.229.180.000 VND 1.499.000.000 VND "
        "MiniCar 170 km 231.340.000 VND 269.000.000 VND "
        "Van 150 km 245.100.000 VND 285.000.000 VND "
        "Scooter 49 km/h 78 km 14.400.000 VND 2300 W "
        "Scooter 70 km/h 156 km 39.900.000 VND 3000 W"
    )

    quality = chunking.chunk_text_quality(flattened_table)

    assert quality["is_usable"] is False
    assert quality["structural_clarity"]["label"] == "low"
    assert quality["structural_clarity"]["needs_table_reconstruction"] is True


def test_shared_chunk_quality_rejects_repeated_phrase_blocks() -> None:
    repeated = (
        "Pin va tram sac o to dien voi phuong cham luon dat loi ich khach hang len dau. "
        "VinFast ap dung chinh sach cho thue pin doc dao uu viet va khac biet. "
        "Pin va tram sac o to dien voi phuong cham luon dat loi ich khach hang len dau. "
        "VinFast ap dung chinh sach cho thue pin doc dao uu viet va khac biet."
    )

    quality = chunking.chunk_text_quality(repeated)

    assert quality["is_usable"] is False
    assert quality["structural_clarity"]["needs_deduplication"] is True


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
    assert chunks[0].metadata["full_path"] == ["Section"]
    assert chunks[0].metadata["part_index"] == 1
    assert chunks[0].metadata["part_total"] == 1
