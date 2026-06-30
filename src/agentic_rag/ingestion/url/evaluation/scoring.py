"""Golden-data evaluation for URL ingestion outputs."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.core.contracts import Chunk

CheckSeverity = Literal["error", "warning", "info"]

_NAVIGATION_SNIPPETS = (
    "Home",
    "Support",
    "Đăng nhập",
    "Giỏ hàng",
    "Danh mục",
    "Menu",
)
_FOOTER_SNIPPETS = (
    "Copyright",
    "All rights reserved",
    "Theo dõi chúng tôi",
    "Đăng ký nhận tin",
    "Hotline",
)


class _EvaluationModel(BaseModel):
    """Base model for strict URL evaluation DTOs."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class UrlGoldenInput(_EvaluationModel):
    """Input source described by a golden sample."""

    source_url: str | None = None
    source: str | None = None
    source_file: str | None = None


class UrlEntityBoundaryCheck(_EvaluationModel):
    """Expected relationship between entity names and chunk boundaries."""

    name: str
    enabled: bool = False
    entity_names: list[str] = Field(default_factory=list)
    expected_same_chunk: bool | None = None


class UrlProductSpecCheck(_EvaluationModel):
    """Expected product-spec metadata emitted by URL ingestion."""

    name: str
    field: str
    expected_value: str | None = None
    expected_contains: str | None = None
    required: bool = True


class UrlNormalizationChecks(_EvaluationModel):
    """Normalization expectations for one URL sample."""

    strip_navigation: bool = False
    strip_footer: bool = False
    preserve_canonical_url: bool = False
    preserve_query_params: bool = False
    language_expected: str | None = None
    deduplicate_repeated_ui_text: bool = False


class UrlGoldenExpectations(_EvaluationModel):
    """Pass/fail expectations for one URL sample."""

    min_chunk_count: int = Field(default=1, ge=0)
    max_chunk_count: int | None = Field(default=None, ge=0)
    required_metadata_keys: list[str] = Field(default_factory=list)
    required_text_snippets: list[str] = Field(default_factory=list)
    optional_text_snippets: list[str] = Field(default_factory=list)
    forbidden_text_snippets: list[str] = Field(default_factory=list)
    product_spec_checks: list[UrlProductSpecCheck] = Field(default_factory=list)
    entity_boundary_checks: list[UrlEntityBoundaryCheck] = Field(default_factory=list)
    normalization_checks: UrlNormalizationChecks = Field(default_factory=UrlNormalizationChecks)


class UrlGoldenSample(_EvaluationModel):
    """One URL golden sample loaded from the golden JSON."""

    sample_id: str
    description: str | None = None
    input: UrlGoldenInput
    expectations: UrlGoldenExpectations
    notes: list[str] = Field(default_factory=list)


class UrlGoldenDataset(_EvaluationModel):
    """Collection of URL golden samples."""

    version: str
    description: str | None = None
    generated_from: dict[str, Any] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)
    samples: list[UrlGoldenSample] = Field(default_factory=list)


class UrlEvaluationCheck(_EvaluationModel):
    """One evaluation check result."""

    name: str
    passed: bool
    severity: CheckSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class UrlSampleEvaluation(_EvaluationModel):
    """Evaluation result for one URL sample."""

    sample_id: str
    source_url: str | None
    passed: bool
    score: float
    checks: list[UrlEvaluationCheck]

    @property
    def errors(self) -> list[UrlEvaluationCheck]:
        """Return failing hard checks."""

        return [check for check in self.checks if check.severity == "error" and not check.passed]


class UrlEvaluationSummary(_EvaluationModel):
    """Aggregate evaluation result across URL samples."""

    passed: bool
    sample_count: int
    passed_count: int
    failed_count: int
    results: list[UrlSampleEvaluation]


def load_golden_dataset(path: str | Path) -> UrlGoldenDataset:
    """Load URL golden expectations from JSON."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return UrlGoldenDataset.model_validate(payload)


def find_sample_for_url(dataset: UrlGoldenDataset, url: str) -> UrlGoldenSample | None:
    """Return the sample matching a URL by source URL or source value."""

    normalized_url = _normalize_url_for_identity(url)
    for sample in dataset.samples:
        candidates = [sample.input.source_url, sample.input.source]
        if any(
            _normalize_url_for_identity(candidate) == normalized_url for candidate in candidates
        ):
            return sample
    return None


def evaluate_sample(
    sample: UrlGoldenSample,
    *,
    markdown: str,
    chunks: list[Chunk],
) -> UrlSampleEvaluation:
    """Evaluate one URL ingestion result against one golden sample."""

    combined_text = _combined_text(markdown, chunks)
    required_text = _combined_required_text(sample, markdown, chunks)
    expectations = sample.expectations
    checks = [
        _check_chunk_count(chunks, expectations),
        _check_required_metadata(chunks, expectations.required_metadata_keys),
        *_check_required_snippets(required_text, expectations.required_text_snippets),
        *_check_forbidden_snippets(combined_text, expectations.forbidden_text_snippets),
        *_check_optional_snippets(combined_text, expectations.optional_text_snippets),
        *_check_product_specs(chunks, expectations.product_spec_checks),
        *_check_normalization(sample, combined_text, chunks, expectations.normalization_checks),
        *_check_entity_boundaries(chunks, expectations.entity_boundary_checks),
    ]
    hard_checks = [check for check in checks if check.severity == "error"]
    passed_hard_checks = [check for check in hard_checks if check.passed]
    passed = all(check.passed for check in hard_checks)
    score = len(passed_hard_checks) / len(hard_checks) if hard_checks else 1.0
    return UrlSampleEvaluation(
        sample_id=sample.sample_id,
        source_url=sample.input.source_url or sample.input.source,
        passed=passed,
        score=round(score, 6),
        checks=checks,
    )


def evaluate_results_by_url(
    dataset: UrlGoldenDataset,
    results_by_url: dict[str, tuple[str, list[Chunk]]],
) -> UrlEvaluationSummary:
    """Evaluate multiple URL outputs keyed by URL.

    `results_by_url` values are `(markdown, chunks)` pairs.
    """

    results: list[UrlSampleEvaluation] = []
    for url, (markdown, chunks) in results_by_url.items():
        sample = find_sample_for_url(dataset, url)
        if sample is None:
            results.append(_missing_sample_result(url))
            continue
        results.append(evaluate_sample(sample, markdown=markdown, chunks=chunks))
    passed_count = sum(1 for result in results if result.passed)
    failed_count = len(results) - passed_count
    return UrlEvaluationSummary(
        passed=failed_count == 0,
        sample_count=len(results),
        passed_count=passed_count,
        failed_count=failed_count,
        results=results,
    )


def _check_chunk_count(
    chunks: list[Chunk],
    expectations: UrlGoldenExpectations,
) -> UrlEvaluationCheck:
    chunk_count = len(chunks)
    max_chunk_count = expectations.max_chunk_count
    too_few = chunk_count < expectations.min_chunk_count
    too_many = max_chunk_count is not None and chunk_count > max_chunk_count
    passed = not too_few and not too_many
    return UrlEvaluationCheck(
        name="chunk_count",
        passed=passed,
        severity="error",
        message=(
            f"Chunk count {chunk_count} is within expected bounds."
            if passed
            else "Chunk count is outside expected bounds."
        ),
        details={
            "actual": chunk_count,
            "min": expectations.min_chunk_count,
            "max": max_chunk_count,
        },
    )


def _check_required_metadata(
    chunks: list[Chunk],
    required_keys: list[str],
) -> UrlEvaluationCheck:
    missing_by_chunk = {
        chunk.chunk_id: [key for key in required_keys if key not in chunk.metadata]
        for chunk in chunks
    }
    missing_by_chunk = {key: value for key, value in missing_by_chunk.items() if value}
    passed = bool(chunks) and not missing_by_chunk
    return UrlEvaluationCheck(
        name="required_metadata_keys",
        passed=passed,
        severity="error",
        message=(
            "All chunks contain required metadata keys."
            if passed
            else "One or more chunks are missing required metadata keys."
        ),
        details={"missing_by_chunk": missing_by_chunk, "required_keys": required_keys},
    )


def _check_required_snippets(
    text: str,
    snippets: list[str],
) -> list[UrlEvaluationCheck]:
    return [
        UrlEvaluationCheck(
            name="required_text_snippet",
            passed=_contains_required_snippet(text, snippet),
            severity="error",
            message=(
                f"Required snippet found: {snippet}"
                if _contains_required_snippet(text, snippet)
                else f"Required snippet missing: {snippet}"
            ),
            details={"snippet": snippet},
        )
        for snippet in snippets
    ]


def _check_forbidden_snippets(
    text: str,
    snippets: list[str],
) -> list[UrlEvaluationCheck]:
    checks: list[UrlEvaluationCheck] = []
    for snippet in snippets:
        found = _contains_snippet(text, snippet)
        checks.append(
            UrlEvaluationCheck(
                name="forbidden_text_snippet",
                passed=not found,
                severity="error",
                message=(
                    f"Forbidden snippet absent: {snippet}"
                    if not found
                    else f"Forbidden snippet found: {snippet}"
                ),
                details={"snippet": snippet},
            )
        )
    return checks


def _check_optional_snippets(
    text: str,
    snippets: list[str],
) -> list[UrlEvaluationCheck]:
    return [
        UrlEvaluationCheck(
            name="optional_text_snippet",
            passed=True,
            severity="info",
            message=(
                f"Optional snippet found: {snippet}"
                if _contains_snippet(text, snippet)
                else f"Optional snippet missing: {snippet}"
            ),
            details={"snippet": snippet, "found": _contains_snippet(text, snippet)},
        )
        for snippet in snippets
    ]


def _check_product_specs(
    chunks: list[Chunk],
    checks: list[UrlProductSpecCheck],
) -> list[UrlEvaluationCheck]:
    return [_check_product_spec(chunks, check) for check in checks]


def _check_product_spec(
    chunks: list[Chunk],
    check: UrlProductSpecCheck,
) -> UrlEvaluationCheck:
    values = _product_spec_values(chunks, check.field)
    matched_value = _matching_product_spec_value(values, check)
    passed = matched_value is not None or (not check.required and not values)
    severity: CheckSeverity = "error" if check.required else "info"
    return UrlEvaluationCheck(
        name="product_spec",
        passed=passed,
        severity=severity,
        message=(
            f"Product spec check passed: {check.name}"
            if passed
            else f"Product spec check failed: {check.name}"
        ),
        details={
            "field": check.field,
            "expected_value": check.expected_value,
            "expected_contains": check.expected_contains,
            "values": values,
            "matched_value": matched_value,
        },
    )


def _product_spec_values(chunks: list[Chunk], field: str) -> list[str]:
    metadata_keys = _product_spec_metadata_keys(field)
    values: list[str] = []
    for chunk in chunks:
        for key in metadata_keys:
            value = chunk.metadata.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value)
        product_specs = chunk.metadata.get("product_specs")
        if isinstance(product_specs, dict):
            value = product_specs.get(field)
            if isinstance(value, str) and value.strip():
                values.append(value)
    return _deduplicate_text(values)


def _product_spec_metadata_keys(field: str) -> tuple[str, ...]:
    aliases = {
        "model_name": ("product_model",),
        "price": ("product_price",),
        "driving_range": ("driving_range",),
        "battery_capacity": ("battery_capacity",),
        "charging_time": ("charging_time",),
    }
    return aliases.get(field, ())


def _matching_product_spec_value(
    values: list[str],
    check: UrlProductSpecCheck,
) -> str | None:
    if not values:
        return None
    if check.expected_value is None and check.expected_contains is None:
        return values[0]
    for value in values:
        if check.expected_value is not None and _contains_snippet(value, check.expected_value):
            return value
        if check.expected_contains is not None and _contains_snippet(
            value, check.expected_contains
        ):
            return value
    return None


def _deduplicate_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = _normalize_for_match(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(value)
    return output


def _check_normalization(
    sample: UrlGoldenSample,
    text: str,
    chunks: list[Chunk],
    checks: UrlNormalizationChecks,
) -> list[UrlEvaluationCheck]:
    output: list[UrlEvaluationCheck] = []
    if checks.strip_navigation:
        output.append(_snippet_group_absent("strip_navigation", text, _NAVIGATION_SNIPPETS))
    if checks.strip_footer:
        output.append(_snippet_group_absent("strip_footer", text, _FOOTER_SNIPPETS))
    if checks.preserve_canonical_url:
        output.append(_check_canonical_url(sample, chunks))
    if checks.preserve_query_params:
        output.append(_check_query_params(sample, chunks))
    if checks.language_expected:
        output.append(_check_language(chunks, checks.language_expected))
    if checks.deduplicate_repeated_ui_text:
        output.append(_check_repeated_ui_text(text))
    return output


def _snippet_group_absent(
    name: str,
    text: str,
    snippets: tuple[str, ...],
) -> UrlEvaluationCheck:
    found = [snippet for snippet in snippets if _contains_snippet(text, snippet)]
    return UrlEvaluationCheck(
        name=name,
        passed=not found,
        severity="error",
        message=(
            f"{name} passed; no grouped boilerplate snippets found."
            if not found
            else f"{name} failed; grouped boilerplate snippets remain."
        ),
        details={"found": found},
    )


def _check_canonical_url(
    sample: UrlGoldenSample,
    chunks: list[Chunk],
) -> UrlEvaluationCheck:
    source_url = sample.input.source_url or sample.input.source
    canonical_values = [
        str(chunk.metadata.get("canonical_url"))
        for chunk in chunks
        if chunk.metadata.get("canonical_url")
    ]
    passed = bool(canonical_values)
    if source_url and canonical_values:
        source_domain = urlparse(source_url).netloc
        passed = all(urlparse(value).netloc == source_domain for value in canonical_values)
    return UrlEvaluationCheck(
        name="preserve_canonical_url",
        passed=passed,
        severity="error",
        message=(
            "Canonical URL metadata is present and source-aligned."
            if passed
            else "Canonical URL metadata is missing or not source-aligned."
        ),
        details={"canonical_values": canonical_values, "source_url": source_url},
    )


def _check_query_params(
    sample: UrlGoldenSample,
    chunks: list[Chunk],
) -> UrlEvaluationCheck:
    source_url = sample.input.source_url or sample.input.source or ""
    expected_params = dict(parse_qsl(urlparse(source_url).query))
    output_urls = [str(chunk.metadata.get("url")) for chunk in chunks if chunk.metadata.get("url")]
    actual_param_sets = [dict(parse_qsl(urlparse(url).query)) for url in output_urls]
    passed = not expected_params or any(
        all(params.get(key) == value for key, value in expected_params.items())
        for params in actual_param_sets
    )
    return UrlEvaluationCheck(
        name="preserve_query_params",
        passed=passed,
        severity="error",
        message=(
            "Expected query parameters are preserved."
            if passed
            else "Expected query parameters were not preserved."
        ),
        details={"expected_params": expected_params, "actual_param_sets": actual_param_sets},
    )


def _check_language(chunks: list[Chunk], expected_language: str) -> UrlEvaluationCheck:
    language_values = [
        str(chunk.metadata.get("language")) for chunk in chunks if chunk.metadata.get("language")
    ]
    expected = expected_language.casefold()
    passed = bool(language_values) and all(
        value.casefold() == expected or value.casefold().startswith(f"{expected}-")
        for value in language_values
    )
    return UrlEvaluationCheck(
        name="language_expected",
        passed=passed,
        severity="error",
        message=(
            f"Language metadata matches {expected_language}."
            if passed
            else f"Language metadata does not match {expected_language}."
        ),
        details={"expected": expected_language, "actual": language_values},
    )


def _check_repeated_ui_text(text: str) -> UrlEvaluationCheck:
    lines = [
        _normalize_for_match(line)
        for line in text.splitlines()
        if len(_normalize_for_match(line)) >= 5
    ]
    counts: dict[str, int] = {}
    for line in lines:
        counts[line] = counts.get(line, 0) + 1
    repeated = {
        line: count
        for line, count in counts.items()
        if count >= 4 and any(_contains_snippet(line, snippet) for snippet in _NAVIGATION_SNIPPETS)
    }
    return UrlEvaluationCheck(
        name="deduplicate_repeated_ui_text",
        passed=not repeated,
        severity="error",
        message=(
            "Repeated UI text is not dominant."
            if not repeated
            else "Repeated UI text remains in output."
        ),
        details={"repeated": repeated},
    )


def _check_entity_boundaries(
    chunks: list[Chunk],
    boundary_checks: list[UrlEntityBoundaryCheck],
) -> list[UrlEvaluationCheck]:
    output: list[UrlEvaluationCheck] = []
    for boundary_check in boundary_checks:
        if not boundary_check.enabled or not boundary_check.entity_names:
            output.append(
                UrlEvaluationCheck(
                    name="entity_boundary",
                    passed=True,
                    severity="info",
                    message=f"Entity boundary check disabled: {boundary_check.name}",
                    details={"entity_names": boundary_check.entity_names},
                )
            )
            continue
        if boundary_check.expected_same_chunk is None:
            output.append(
                UrlEvaluationCheck(
                    name="entity_boundary",
                    passed=False,
                    severity="error",
                    message=(
                        "Enabled entity boundary check must define expected_same_chunk: "
                        f"{boundary_check.name}"
                    ),
                    details={"entity_names": boundary_check.entity_names},
                )
            )
            continue
        matching_chunks = [
            chunk.chunk_id
            for chunk in chunks
            if all(_contains_snippet(chunk.text, name) for name in boundary_check.entity_names)
        ]
        found_same_chunk = bool(matching_chunks)
        passed = found_same_chunk == boundary_check.expected_same_chunk
        output.append(
            UrlEvaluationCheck(
                name="entity_boundary",
                passed=passed,
                severity="error",
                message=(
                    f"Entity boundary check passed: {boundary_check.name}"
                    if passed
                    else f"Entity boundary check failed: {boundary_check.name}"
                ),
                details={
                    "entity_names": boundary_check.entity_names,
                    "expected_same_chunk": boundary_check.expected_same_chunk,
                    "matching_chunks": matching_chunks,
                },
            )
        )
    return output


def _missing_sample_result(url: str) -> UrlSampleEvaluation:
    return UrlSampleEvaluation(
        sample_id="missing_golden_sample",
        source_url=url,
        passed=False,
        score=0.0,
        checks=[
            UrlEvaluationCheck(
                name="golden_sample_lookup",
                passed=False,
                severity="error",
                message="No golden sample exists for this URL.",
                details={"url": url},
            )
        ],
    )


def _combined_text(markdown: str, chunks: list[Chunk]) -> str:
    return "\n\n".join([markdown, *(chunk.text for chunk in chunks)])


def _combined_required_text(
    sample: UrlGoldenSample,
    markdown: str,
    chunks: list[Chunk],
) -> str:
    metadata_values: list[str] = []
    url_values = [sample.input.source_url, sample.input.source]
    for chunk in chunks:
        metadata_values.extend(
            str(chunk.metadata[key])
            for key in ("source", "url", "canonical_url", "original_url", "final_url")
            if chunk.metadata.get(key)
        )
    for value in [*url_values, *metadata_values]:
        if value:
            metadata_values.extend(_url_text_variants(str(value)))
    return "\n\n".join([_combined_text(markdown, chunks), *metadata_values])


def _url_text_variants(value: str) -> list[str]:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return []
    path = unquote(parsed.path)
    slug = path.rsplit("/", 1)[-1]
    slug_without_extension = re.sub(r"\.[a-z0-9]+$", "", slug, flags=re.I)
    readable_path = re.sub(r"[-_/.:]+", " ", path)
    readable_slug = re.sub(r"[-_/.:]+", " ", slug_without_extension)
    return [value, path, slug, slug_without_extension, readable_path, readable_slug]


def _contains_snippet(text: str, snippet: str) -> bool:
    normalized_text = _normalize_for_match(text)
    return any(
        _normalize_for_match(candidate) in normalized_text
        for candidate in _snippet_candidates(snippet)
    )


def _contains_required_snippet(text: str, snippet: str) -> bool:
    normalized_text = _normalize_for_match(text)
    return any(
        _normalize_for_match(candidate) in normalized_text
        or _contains_candidate_words_in_order(normalized_text, _normalize_for_match(candidate))
        for candidate in _snippet_candidates(snippet)
    )


def _contains_candidate_words_in_order(text: str, candidate: str) -> bool:
    candidate_words = re.findall(r"\w+", candidate, flags=re.UNICODE)
    if len(candidate_words) < 3:
        return False
    text_words = re.findall(r"\w+", text, flags=re.UNICODE)
    search_from = 0
    for candidate_word in candidate_words:
        try:
            found_at = text_words.index(candidate_word, search_from)
        except ValueError:
            return False
        search_from = found_at + 1
    return True


def _snippet_candidates(snippet: str) -> set[str]:
    candidates = {snippet}
    repaired = _repair_mojibake(snippet)
    if repaired:
        candidates.add(repaired)
    candidates.update(_fold_accents(candidate) for candidate in list(candidates))
    return {candidate for candidate in candidates if candidate}


def _repair_mojibake(value: str) -> str | None:
    try:
        repaired = value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return None
    return repaired if repaired != value else None


def _fold_accents(value: str) -> str:
    normalized = value.replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFKD", normalized)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().casefold()


def _normalize_url_for_identity(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{netloc}{path}{query}"


__all__ = [
    "UrlEntityBoundaryCheck",
    "UrlEvaluationCheck",
    "UrlEvaluationSummary",
    "UrlGoldenDataset",
    "UrlGoldenExpectations",
    "UrlGoldenInput",
    "UrlGoldenSample",
    "UrlNormalizationChecks",
    "UrlProductSpecCheck",
    "UrlSampleEvaluation",
    "evaluate_results_by_url",
    "evaluate_sample",
    "find_sample_for_url",
    "load_golden_dataset",
]
