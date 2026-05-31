from agentic_rag.ingestion.pdf.benchmarking.manifest import PdfBenchmarkDocument
from agentic_rag.ingestion.pdf.benchmarking.scoring import (
    HumanReviewScore,
    evaluate_text_output,
)


def test_evaluate_text_output_tracks_vietnamese_snippet_recall() -> None:
    document = PdfBenchmarkDocument(
        doc_id="sample",
        title="Sample Vietnamese PDF",
        domain="education_admin",
        language="vi",
        source_url="https://example.com/sample.pdf",
        licensing_note="URL reference only.",
        expected_features=["vietnamese_diacritics", "tables"],
        expected_snippets=[
            "Cộng hòa xã hội chủ nghĩa Việt Nam",
            "Toán, Vật lí, Tin học",
        ],
    )

    score = evaluate_text_output(
        document,
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nMột bảng tuyển sinh có các cột chương trình đào tạo.",
    )

    assert score.doc_id == "sample"
    assert score.has_vietnamese_diacritics is True
    assert score.matched_snippets == ["Cộng hòa xã hội chủ nghĩa Việt Nam"]
    assert score.missing_snippets == ["Toán, Vật lí, Tin học"]
    assert score.snippet_recall == 0.5


def test_human_review_score_aggregates_document_ai_rubric() -> None:
    review = HumanReviewScore(
        doc_id="sample",
        parser_name="paddleocr_vl",
        vietnamese_text=5,
        reading_order=4,
        table_fidelity=3,
        formula_fidelity=2,
        chart_image_usefulness=1,
        rag_readiness=4,
        notes="Strong Vietnamese OCR, weak chart interpretation.",
    )

    assert review.total_score == 19
    assert review.max_score == 30
