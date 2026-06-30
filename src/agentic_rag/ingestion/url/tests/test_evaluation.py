from __future__ import annotations

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.evaluation import (
    UrlEntityBoundaryCheck,
    UrlGoldenExpectations,
    UrlGoldenInput,
    UrlGoldenSample,
    UrlNormalizationChecks,
    UrlProductSpecCheck,
    evaluate_sample,
)


def _chunk(text: str, metadata: dict[str, object] | None = None) -> Chunk:
    return Chunk(
        chunk_id="url_sample_c0001",
        text=text,
        metadata={
            "source": "https://shop.vinfastauto.com/vn_vi/sample",
            "source_type": "official",
            "title": "Sample",
            "section": "main",
            "section_path": ["Sample"],
            "content_hash": "abc123",
            "canonical_url": "https://shop.vinfastauto.com/vn_vi/sample",
            "captured_at": "2026-06-12T00:00:00+00:00",
            "language": "vi",
            "domain": "shop.vinfastauto.com",
            "page_type": "product_page",
            **(metadata or {}),
        },
    )


def test_evaluate_sample_passes_required_checks_and_keeps_optional_info() -> None:
    sample = UrlGoldenSample(
        sample_id="sample",
        input=UrlGoldenInput(source_url="https://shop.vinfastauto.com/vn_vi/sample"),
        expectations=UrlGoldenExpectations(
            min_chunk_count=1,
            max_chunk_count=2,
            required_metadata_keys=[
                "source",
                "source_type",
                "title",
                "section",
                "section_path",
                "content_hash",
                "canonical_url",
                "captured_at",
                "language",
                "domain",
                "page_type",
            ],
            required_text_snippets=["VF 8", "giá", "VNĐ"],
            optional_text_snippets=["Mua ngay"],
            forbidden_text_snippets=["Copyright"],
            normalization_checks=UrlNormalizationChecks(
                strip_navigation=True,
                strip_footer=True,
                preserve_canonical_url=True,
                language_expected="vi",
                deduplicate_repeated_ui_text=True,
            ),
        ),
    )
    chunk = _chunk("# VF 8\n\nThông tin giá 849.000.000 VNĐ cho xe điện.")

    result = evaluate_sample(
        sample,
        markdown="# VF 8\n\nThông tin giá 849.000.000 VNĐ cho xe điện.",
        chunks=[chunk],
    )

    assert result.passed is True
    assert result.score == 1.0
    assert any(check.name == "optional_text_snippet" for check in result.checks)


def test_evaluate_sample_fails_for_missing_required_snippet_and_forbidden_text() -> None:
    sample = UrlGoldenSample(
        sample_id="sample",
        input=UrlGoldenInput(source_url="https://shop.vinfastauto.com/vn_vi/sample"),
        expectations=UrlGoldenExpectations(
            min_chunk_count=1,
            max_chunk_count=1,
            required_metadata_keys=["source", "source_type"],
            required_text_snippets=["VF 8"],
            forbidden_text_snippets=["Copyright"],
        ),
    )
    chunk = _chunk("Copyright footer only")

    result = evaluate_sample(sample, markdown="Copyright footer only", chunks=[chunk])

    assert result.passed is False
    assert {error.name for error in result.errors} == {
        "required_text_snippet",
        "forbidden_text_snippet",
    }


def test_evaluate_sample_repairs_mojibake_golden_snippets() -> None:
    sample = UrlGoldenSample(
        sample_id="sample",
        input=UrlGoldenInput(source_url="https://shop.vinfastauto.com/vn_vi/sample"),
        expectations=UrlGoldenExpectations(
            min_chunk_count=1,
            required_metadata_keys=["source", "source_type"],
            required_text_snippets=["giÃ¡", "VNÄ"],
        ),
    )
    chunk = _chunk("Thông tin giá 849.000.000 VNĐ.")

    result = evaluate_sample(sample, markdown=chunk.text, chunks=[chunk])

    assert result.passed is True


def test_evaluate_sample_allows_required_identifier_from_source_url() -> None:
    sample = UrlGoldenSample(
        sample_id="sample",
        input=UrlGoldenInput(source_url="https://vinfastauto.com/vn_vi/o-to-dien-vinfast-mo-ban"),
        expectations=UrlGoldenExpectations(
            min_chunk_count=1,
            required_metadata_keys=["source", "source_type"],
            required_text_snippets=["dien vinfast ban"],
            forbidden_text_snippets=["Hotline"],
        ),
    )
    chunk = _chunk(
        "# O to dien VinFast\n\nThong tin xe dien.",
        metadata={
            "source": "https://vinfastauto.com/vn_vi/o-to-dien-vinfast-mo-ban",
            "canonical_url": "https://vinfastauto.com/vn_vi/o-to-dien-vinfast-mo-ban",
        },
    )

    result = evaluate_sample(sample, markdown=chunk.text, chunks=[chunk])

    assert result.passed is True


def test_evaluate_sample_treats_empty_entity_boundary_as_disabled() -> None:
    sample = UrlGoldenSample(
        sample_id="sample",
        input=UrlGoldenInput(source_url="https://example.com/faq"),
        expectations=UrlGoldenExpectations(
            min_chunk_count=1,
            required_metadata_keys=["source", "source_type"],
            entity_boundary_checks=[
                UrlEntityBoundaryCheck(
                    name="no configured entities",
                    enabled=True,
                    entity_names=[],
                    expected_same_chunk=False,
                )
            ],
        ),
    )
    chunk = _chunk("# FAQ\n\nUseful question and answer.")

    result = evaluate_sample(sample, markdown=chunk.text, chunks=[chunk])

    assert result.passed is True
    assert any(
        check.name == "entity_boundary" and check.severity == "info" for check in result.checks
    )


def test_evaluate_sample_does_not_fuzzy_match_forbidden_snippets() -> None:
    sample = UrlGoldenSample(
        sample_id="sample",
        input=UrlGoldenInput(source_url="https://example.com/article"),
        expectations=UrlGoldenExpectations(
            min_chunk_count=1,
            required_metadata_keys=["source", "source_type"],
            forbidden_text_snippets=["Theo dõi chúng tôi"],
        ),
    )
    chunk = _chunk(
        "Theo đó người dùng có thể theo dõi tình trạng pin, còn chúng tôi "
        "giữ nội dung này như một câu bình thường."
    )

    result = evaluate_sample(sample, markdown=chunk.text, chunks=[chunk])

    assert result.passed is True


def test_evaluate_sample_checks_product_spec_metadata() -> None:
    sample = UrlGoldenSample(
        sample_id="sample",
        input=UrlGoldenInput(source_url="https://vinfastauto.com/vn_vi/vf-8"),
        expectations=UrlGoldenExpectations(
            min_chunk_count=1,
            required_metadata_keys=["source", "source_type"],
            product_spec_checks=[
                UrlProductSpecCheck(
                    name="model name",
                    field="model_name",
                    expected_value="VF 8",
                ),
                UrlProductSpecCheck(
                    name="driving range",
                    field="driving_range",
                    expected_contains="471 km",
                ),
                UrlProductSpecCheck(
                    name="battery capacity present",
                    field="battery_capacity",
                ),
            ],
        ),
    )
    chunk = _chunk(
        "# VF 8\n\nThong so xe dien.",
        metadata={
            "product_model": ["VF 8"],
            "driving_range": "471 km",
            "product_specs": {
                "model_name": "VF 8",
                "price": "1.019.000.000 VND",
                "driving_range": "471 km",
                "battery_capacity": "87,7 kWh",
            },
        },
    )

    result = evaluate_sample(sample, markdown=chunk.text, chunks=[chunk])

    assert result.passed is True
    product_checks = [check for check in result.checks if check.name == "product_spec"]
    assert len(product_checks) == 3
    assert all(check.passed for check in product_checks)


def test_evaluate_sample_fails_missing_required_product_spec_metadata() -> None:
    sample = UrlGoldenSample(
        sample_id="sample",
        input=UrlGoldenInput(source_url="https://vinfastauto.com/vn_vi/vf-8"),
        expectations=UrlGoldenExpectations(
            min_chunk_count=1,
            required_metadata_keys=["source", "source_type"],
            product_spec_checks=[
                UrlProductSpecCheck(
                    name="price",
                    field="price",
                    expected_contains="1.019.000.000",
                )
            ],
        ),
    )
    chunk = _chunk("# VF 8\n\nThong so xe dien.", metadata={"product_model": ["VF 8"]})

    result = evaluate_sample(sample, markdown=chunk.text, chunks=[chunk])

    assert result.passed is False
    assert any(error.name == "product_spec" for error in result.errors)
