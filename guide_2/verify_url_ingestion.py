import argparse
import difflib
import json
import logging
import pathlib
import re
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse

# Add src to path to allow direct execution from guide_2.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if not (SRC_DIR / "agentic_rag").exists():
    raise RuntimeError(f"Could not find agentic_rag package under: {SRC_DIR.resolve()}")
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agentic_rag.core.contracts import LLMCompletionInput, ModelRole  # noqa: E402
from agentic_rag.ingestion.url.loader import load_url_with_artifacts  # noqa: E402
from agentic_rag.model_runtime.factory import get_llm_client  # noqa: E402
from agentic_rag.runtime_env import load_local_env  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_MODEL_ROLES: tuple[ModelRole, ...] = (
    "query_rewrite",
    "query_transform",
    "generation",
    "ingestion",
    "evaluation",
)

EVALUATION_PROMPT_TEMPLATE = "\n".join(
    [
        "You are an expert in web data extraction for RAG systems. Below are two "
        "versions of Markdown extracted from the same web page.",
        "The first is the 'Ground Truth' which is considered the ideal extraction.",
        "The second is the 'Actual Output' from our ingestion pipeline.",
        "",
        "Please compare the 'Actual Output' against the 'Ground-Truth' and provide "
        "a detailed evaluation in Markdown format. Focus on:",
        "1.  **Content Completeness**: Is any important information from the ground "
        "truth missing in the actual output?",
        "2.  **Content Correctness**: Is all information in the actual output "
        "accurate? Are there any hallucinations?",
        "3.  **Structure and Formatting**: Is the structure (headings, lists, "
        "tables) preserved correctly and logically?",
        "4.  **Noise and Boilerplate**: Has the actual output successfully removed "
        "irrelevant content (like navigation, footers, ads)?",
        "5.  **Overall Score**: Provide a score from 1 to 10 (10 being a perfect "
        "match in semantic content) and a summary of your findings.",
        "",
        "<GROUND_TRUTH>",
        "{ground_truth_md}",
        "</GROUND_TRUTH>",
        "",
        "<ACTUAL_OUTPUT>",
        "{actual_md}",
        "</ACTUAL_OUTPUT>",
        "",
    ]
)


def run_ingestion(url: str, artifacts_dir: pathlib.Path) -> pathlib.Path:
    """Runs the URL ingestion pipeline and returns the path to the parsed markdown."""
    logging.info(f"Running ingestion for URL: {url}")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    document = load_url_with_artifacts(
        url,
        data_artifact_dir=str(artifacts_dir),
        include_interactions=True,  # Assume interactions are needed for complex pages
    )

    if document.artifacts is None:
        raise FileNotFoundError("Ingestion did not produce a parsed.md artifact.")

    logging.info(f"Ingestion artifacts saved to: {artifacts_dir.resolve()}")
    return document.artifacts.markdown_path


def load_markdown(path: pathlib.Path) -> str:
    """Loads a Markdown file as UTF-8 text."""
    logging.info(f"Loading Markdown from: {path.resolve()}")
    return path.read_text(encoding="utf-8")


def find_ground_truth_markdown(ground_truth_path: pathlib.Path) -> pathlib.Path:
    """Finds the ground truth Markdown file from a file path or directory."""
    if ground_truth_path.is_file():
        return ground_truth_path

    gt_path = ground_truth_path / "parsed.md"
    if not gt_path.exists():
        markdown_files = sorted(ground_truth_path.glob("*.md"))
        if len(markdown_files) == 1:
            gt_path = markdown_files[0]
        else:
            candidates = ", ".join(path.name for path in markdown_files) or "none"
            raise FileNotFoundError(
                f"Ground truth file not found at: {gt_path.resolve()}. "
                f"Expected parsed.md, a direct .md file path, or exactly one .md file "
                f"in the directory. Found: {candidates}"
            )
    return gt_path


def find_ground_truth_json(ground_truth_path: pathlib.Path) -> pathlib.Path | None:
    """Finds an optional structured ground truth JSON file."""
    if ground_truth_path.is_file():
        return ground_truth_path if ground_truth_path.suffix.lower() == ".json" else None

    json_files = sorted(ground_truth_path.glob("*.json"))
    if len(json_files) == 1:
        return json_files[0]
    return None


def _normalize_for_match(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _flatten_json_scalars(data: Any, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(data, dict):
        values: list[tuple[str, str]] = []
        for key, value in data.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            values.extend(_flatten_json_scalars(value, child_prefix))
        return values

    if isinstance(data, list):
        values = []
        for index, value in enumerate(data):
            values.extend(_flatten_json_scalars(value, f"{prefix}[{index}]"))
        return values

    if data is None or isinstance(data, bool):
        return []

    text = str(data).strip()
    if not text or len(text) < 2:
        return []
    return [(prefix, text)]


def _term_variants(term: str) -> set[str]:
    variants = {_normalize_for_match(term)}
    if term.isdigit() and len(term) > 4:
        groups: list[str] = []
        remaining = term
        while remaining:
            groups.append(remaining[-3:])
            remaining = remaining[:-3]
        variants.add(".".join(reversed(groups)))
        variants.add(",".join(reversed(groups)))
    return {variant for variant in variants if variant}


def extract_url_routing_info(url: str | None) -> dict[str, Any] | None:
    """Extracts URL query values that route a dynamic product page."""
    if not url:
        return None

    parsed = urlparse(url)
    query_params = {
        key: values[0] if len(values) == 1 else values
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
    }
    model_id = query_params.get("modelId")
    if isinstance(model_id, list):
        model_id = model_id[0] if model_id else None

    return {
        "url": url,
        "path": parsed.path,
        "query_params": query_params,
        "primary_routing_param": "modelId" if model_id else None,
        "primary_model_id": model_id,
    }


def _text_contains_any_variant(text: str, term: str | None) -> bool:
    if not term:
        return False
    normalized_text = _normalize_for_match(text)
    return any(variant in normalized_text for variant in _term_variants(term))


def _read_text_if_exists(path: pathlib.Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _artifact_text(path: pathlib.Path) -> str | None:
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".xlsx"}:
        return None

    # Special processing for chunks.jsonl to avoid loading massive metadata fields
    if path.name == "chunks.jsonl":
        try:
            texts = []
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            if "text" in chunk:
                                texts.append(chunk["text"])
                        except Exception:
                            continue
            return f"\n\n<!-- artifact (extracted chunks): {path.as_posix()} -->\n" + "\n\n".join(texts)
        except Exception as e:
            logging.warning(f"Failed to extract text from chunks.jsonl: {e}")
            return None

    # Special processing for visual_semantics.json to avoid loading massive DOM paths/CSS rules
    if path.name == "visual_semantics.json":
        try:
            texts = []
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                facts = data.get("facts", [])
                for fact in facts:
                    if isinstance(fact, dict) and "text" in fact:
                        texts.append(str(fact["text"]))
            return f"\n\n<!-- artifact (extracted visual semantics): {path.as_posix()} -->\n" + "\n\n".join(texts)
        except Exception as e:
            logging.warning(f"Failed to extract text from visual_semantics.json: {e}")
            return None

    text = _read_text_if_exists(path)
    if text is None:
        return None
    return f"\n\n<!-- artifact: {path.as_posix()} -->\n{text}"


def collect_artifact_evidence(artifact_dir: pathlib.Path | None) -> tuple[str, list[str]]:
    """Collect source-backed evidence emitted by URL ingestion for verification."""
    if artifact_dir is None or not artifact_dir.exists():
        return "", []

    candidate_names = {
        "source.html",
        "cleaned.html",
        "extracted.md",
        "parsed.md",
        "parsed_sections.txt",
        "manifest.json",
        "quality.json",
        "visual_semantics.json",
        "interaction_states.json",
        "network_payloads.jsonl",
        "panel_snapshots.json",
        "panel_diffs.json",
        "image_snapshots.json",
        "chunks.jsonl",
    }
    parts: list[str] = []
    paths: list[str] = []
    for path in sorted(artifact_dir.parent.rglob("*")):
        if path.name not in candidate_names:
            continue
        text = _artifact_text(path)
        if text is None:
            continue
        parts.append(text)
        paths.append(path.as_posix())
    return "\n".join(parts), paths


def compare_with_ground_truth(
    *,
    ground_truth_md: str,
    actual_md: str,
    evidence_text: str,
    evidence_paths: list[str],
    ground_truth_json_path: pathlib.Path | None,
    output_dir: pathlib.Path,
    routing_info: dict[str, Any] | None,
) -> str:
    """Creates a deterministic local comparison report."""
    normalized_actual = _normalize_for_match(actual_md)
    normalized_evidence = _normalize_for_match("\n\n".join([actual_md, evidence_text]))
    gt_lines = ground_truth_md.splitlines()
    actual_lines = actual_md.splitlines()
    similarity = difflib.SequenceMatcher(
        None,
        _normalize_for_match(ground_truth_md),
        normalized_actual,
    ).ratio()

    summary: dict[str, Any] = {
        "ground_truth": {
            "characters": len(ground_truth_md),
            "words": _word_count(ground_truth_md),
            "lines": len(gt_lines),
        },
        "actual": {
            "characters": len(actual_md),
            "words": _word_count(actual_md),
            "lines": len(actual_lines),
        },
        "evidence_corpus": {
            "characters": len(evidence_text),
            "words": _word_count(evidence_text),
            "artifact_count": len(evidence_paths),
            "artifact_paths": evidence_paths,
        },
        "text_similarity_ratio": round(similarity, 4),
    }

    if routing_info is not None:
        model_id = routing_info.get("primary_model_id")
        summary["source_url_routing"] = {
            **routing_info,
            "model_id_present_in_actual_markdown": _text_contains_any_variant(actual_md, model_id),
            "model_id_present_in_evidence_corpus": _text_contains_any_variant(
                "\n\n".join([actual_md, evidence_text]), model_id
            ),
            "model_id_present_in_ground_truth": _text_contains_any_variant(
                ground_truth_md, model_id
            ),
        }

    covered_terms: list[tuple[str, str]] = []
    missing_terms: list[tuple[str, str]] = []
    if ground_truth_json_path is not None:
        ground_truth_json = json.loads(ground_truth_json_path.read_text(encoding="utf-8"))
        terms = _flatten_json_scalars(ground_truth_json)
        seen: set[tuple[str, str]] = set()
        for path, term in terms:
            key = (path, term)
            if key in seen:
                continue
            seen.add(key)
            variants = _term_variants(term)
            if any(variant in normalized_evidence for variant in variants):
                covered_terms.append(key)
            else:
                missing_terms.append(key)

        total_terms = len(covered_terms) + len(missing_terms)
        summary["structured_ground_truth"] = {
            "json_path": str(ground_truth_json_path),
            "checked_terms": total_terms,
            "covered_terms": len(covered_terms),
            "missing_terms": len(missing_terms),
            "coverage_ratio": round(len(covered_terms) / total_terms, 4) if total_terms else 0.0,
        }

    diff_lines = list(
        difflib.unified_diff(
            gt_lines,
            actual_lines,
            fromfile="ground_truth.md",
            tofile="actual_output.md",
            lineterm="",
            n=3,
        )
    )
    diff_path = output_dir / "ground_truth_diff.patch"
    diff_path.write_text("\n".join(diff_lines) + ("\n" if diff_lines else ""), encoding="utf-8")

    summary_path = output_dir / "comparison_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    missing_preview = missing_terms[:40]
    covered_preview = covered_terms[:20]
    report_lines = [
        "# Local Ground-Truth Verification Report",
        "",
        "This report was generated locally without sending content to an LLM.",
        "",
        "## Summary",
        "",
        f"- Text similarity ratio: `{summary['text_similarity_ratio']}`",
        f"- Ground truth: {summary['ground_truth']['words']} words, "
        f"{summary['ground_truth']['lines']} lines",
        f"- Actual output: {summary['actual']['words']} words, {summary['actual']['lines']} lines",
        f"- Evidence artifacts searched: {summary['evidence_corpus']['artifact_count']}",
    ]

    source_url_routing = summary.get("source_url_routing")
    if source_url_routing:
        model_id = source_url_routing.get("primary_model_id")
        report_lines.extend(
            [
                "",
                "## Primary URL routing signal",
                "",
                f"- Source URL path: `{source_url_routing['path']}`",
                "- Primary routing parameter: `modelId`",
                f"- Primary model ID: `{model_id}`",
                f"- Model ID present in actual markdown: "
                f"`{source_url_routing['model_id_present_in_actual_markdown']}`",
                f"- Model ID present in evidence corpus: "
                f"`{source_url_routing['model_id_present_in_evidence_corpus']}`",
                f"- Model ID present in ground truth: "
                f"`{source_url_routing['model_id_present_in_ground_truth']}`",
                "",
                "`modelId` is treated as the page-routing variable for VinFast model-selector "
                "URLs, so changing it to VF3/VF5/VF6/VF7/etc. should change the target page "
                "being verified.",
            ]
        )

    structured_summary = summary.get("structured_ground_truth")
    if structured_summary:
        report_lines.extend(
            [
                f"- Structured key-fact coverage: "
                f"{structured_summary['covered_terms']}/{structured_summary['checked_terms']} "
                f"(`{structured_summary['coverage_ratio']}`)",
                f"- Structured coverage verdict: "
                f"`{'pass' if structured_summary['coverage_ratio'] >= 0.8 else 'fail'}`",
                "",
                "## Missing structured ground-truth facts",
                "",
            ]
        )
        if missing_preview:
            report_lines.extend(f"- `{path}`: {term}" for path, term in missing_preview)
            if len(missing_terms) > len(missing_preview):
                report_lines.append(f"- ... and {len(missing_terms) - len(missing_preview)} more")
        else:
            report_lines.append("- None detected by exact local matching.")

        report_lines.extend(["", "## Covered structured ground-truth facts", ""])
        if covered_preview:
            report_lines.extend(f"- `{path}`: {term}" for path, term in covered_preview)
            if len(covered_terms) > len(covered_preview):
                report_lines.append(f"- ... and {len(covered_terms) - len(covered_preview)} more")
        else:
            report_lines.append("- None detected by exact local matching.")

    report_lines.extend(
        [
            "",
            "## Generated artifacts",
            "",
            f"- JSON summary: `{summary_path.as_posix()}`",
            f"- Unified diff: `{diff_path.as_posix()}`",
            "",
            "Use the diff for line-level review, and use the structured-fact section as "
            "a fast smoke test for whether important ground-truth values appeared in the "
            "ingestion output.",
            "",
        ]
    )
    return "\n".join(report_lines)


def evaluate_with_llm(ground_truth_md: str, actual_md: str, llm_role: ModelRole) -> str:
    """Uses an LLM to evaluate the actual output against the ground truth."""
    logging.info(f"Sending data to LLM role '{llm_role}' for evaluation...")
    try:
        # Load environment variables from .env
        load_local_env()
        llm_client = get_llm_client(llm_role)
    except Exception as e:
        raise RuntimeError(
            f"Failed to initialize the '{llm_role}' LLM role. "
            "Please ensure your .env file is configured correctly."
        ) from e

    if llm_client is None:
        raise RuntimeError(
            f"The '{llm_role}' LLM role is disabled. Configure a provider for this role "
            "in .env before running this verifier."
        )

    prompt = EVALUATION_PROMPT_TEMPLATE.format(ground_truth_md=ground_truth_md, actual_md=actual_md)

    try:
        response = llm_client.complete(
            LLMCompletionInput(
                prompt=prompt,
                system_message="You are an expert evaluator for RAG ingestion outputs.",
                temperature=0.0,
            )
        )
        logging.info("LLM evaluation complete.")
        return response.text
    except Exception as e:
        raise RuntimeError("LLM completion failed.") from e


def verify_chunks_for_colors_and_images(artifact_dir: pathlib.Path | None) -> str:
    """Explicitly verifies chunk content for text, color codes, and fallback images."""
    if not artifact_dir or not artifact_dir.exists():
        return ""

    chunks_path = artifact_dir / "chunks.jsonl"
    if not chunks_path.exists():
        found = list(artifact_dir.parent.rglob("chunks.jsonl"))
        if found:
            chunks_path = found[0]
        else:
            return "## Ingested Chunks Verification (Colors & Fallbacks)\n\n- **Status**: No `chunks.jsonl` found to analyze."

    try:
        with chunks_path.open("r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]
    except Exception as e:
        return f"## Ingested Chunks Verification (Colors & Fallbacks)\n\n- **Error reading chunks**: {e}"

    total_chunks = len(lines)
    color_chunks = []

    color_code_pattern = re.compile(r"\b[A-Z][A-Z0-9]{2,5}\b")
    image_pattern = re.compile(r"https?://\S+?\.(?:png|jpg|jpeg|webp)", re.I)

    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            chunk = json.loads(line)
            text = chunk.get("text", "")
            metadata = chunk.get("metadata", {})

            has_color_keyword = any(kw in text for kw in ("Màu", "màu", "color", "colour", "exterior", "interior"))
            codes = sorted(list(set(color_code_pattern.findall(text))))
            images = sorted(list(set(image_pattern.findall(text))))

            # Filter codes to only include those that look like color codes (exclude section numbers, etc.)
            filtered_codes = [
                code for code in codes
                if not code.isdigit() and len(code) in (3, 4, 5) and code not in {"VND", "VNĐ", "USD", "VAT", "CTA", "HTML"}
            ]

            if has_color_keyword or filtered_codes or images:
                color_chunks.append({
                    "chunk_id": chunk.get("chunk_id") or f"index_{i}",
                    "section": metadata.get("section") or "Unknown",
                    "text": text,
                    "codes": filtered_codes,
                    "images": images,
                })
        except Exception:
            continue

    report_lines = [
        "## Ingested Chunks Verification (Colors & Fallbacks)",
        "",
        f"- **Total Chunks Loaded**: `{total_chunks}`",
        f"- **Chunks Containing Color/Asset Data**: `{len(color_chunks)}`",
        "",
    ]

    if color_chunks:
        report_lines.append("| Chunk ID | Section | Detected Codes | Images Fallback? | Preview |")
        report_lines.append("| --- | --- | --- | --- | --- |")
        for c in color_chunks:
            codes_str = ", ".join(f"`{code}`" for code in c["codes"]) if c["codes"] else "None"
            images_str = "Yes" if c["images"] else "No"
            preview = c["text"][:120].replace("\n", " ") + "..."
            report_lines.append(f"| `{c['chunk_id']}` | {c['section']} | {codes_str} | {images_str} | {preview} |")

        report_lines.append("")
        report_lines.append("### Detailed Ingested Color Chunks")
        report_lines.append("")
        for c in color_chunks:
            report_lines.append(f"#### Chunk `{c['chunk_id']}`")
            report_lines.append(f"- **Section**: {c['section']}")
            report_lines.append(f"- **Codes**: {', '.join(c['codes']) if c['codes'] else 'None'}")
            if c["images"]:
                report_lines.append("- **Fallback/Visual Images**:")
                for img in c["images"]:
                    report_lines.append(f"  - `{img}`")
            report_lines.append("- **Content Preview**:")
            report_lines.append("  ```")
            report_lines.append(f"  {c['text']}")
            report_lines.append("  ```")
            report_lines.append("")
    else:
        report_lines.append("- No color codes, names, or fallback images were found in the generated chunks.")

    return "\n".join(report_lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify URL ingestion output against a Markdown/JSON ground truth."
    )
    parser.add_argument("--url", help="The URL to ingest and verify.")
    parser.add_argument(
        "--actual-md",
        help="Existing actual Markdown output to compare. When set, ingestion is skipped.",
    )
    parser.add_argument(
        "--source-url",
        help=(
            "Original URL for --actual-md comparisons. Used to verify routing variables "
            "such as modelId without rerunning ingestion."
        ),
    )
    parser.add_argument(
        "--artifact-dir",
        help=(
            "URL ingestion artifact directory to include in structured verification. "
            "Defaults to the generated artifact directory when --url is used, or the "
            "parent directory of --actual-md when it looks like a url-ingestion artifact."
        ),
    )
    parser.add_argument(
        "--ground-truth-dir",
        required=True,
        help="Directory containing ground truth Markdown/JSON, or a direct Markdown file path.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to save ingestion artifacts and the evaluation report.",
    )
    parser.add_argument(
        "--llm-role",
        default="evaluation",
        choices=_MODEL_ROLES,
        help="The LLM client role to use for evaluation.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help=(
            "Also send ground truth and actual output to the configured LLM for qualitative "
            "evaluation. By default, verification is local-only."
        ),
    )
    args = parser.parse_args()

    if not args.url and not args.actual_md:
        parser.error("Provide --url to run ingestion or --actual-md to compare an existing output.")

    output_path = pathlib.Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Run ingestion to get actual output, or load an existing output.
        if args.actual_md:
            actual_md_path = pathlib.Path(args.actual_md)
            actual_md = load_markdown(actual_md_path)
            artifact_dir = pathlib.Path(args.artifact_dir) if args.artifact_dir else None
            if artifact_dir is None and actual_md_path.parent.name == "url-ingestion":
                artifact_dir = actual_md_path.parent
        else:
            ingestion_artifacts_dir = output_path / "ingestion_artifacts"
            actual_md_path = run_ingestion(args.url, ingestion_artifacts_dir)
            actual_md = load_markdown(actual_md_path)
            artifact_dir = (
                pathlib.Path(args.artifact_dir) if args.artifact_dir else actual_md_path.parent
            )

        evidence_text, evidence_paths = collect_artifact_evidence(artifact_dir)

        # 2. Load ground truth
        ground_truth_path = pathlib.Path(args.ground_truth_dir)
        ground_truth_md_path = find_ground_truth_markdown(ground_truth_path)
        ground_truth_json_path = find_ground_truth_json(ground_truth_path)
        ground_truth_md = load_markdown(ground_truth_md_path)

        # 3. Always generate deterministic local comparison artifacts.
        local_report = compare_with_ground_truth(
            ground_truth_md=ground_truth_md,
            actual_md=actual_md,
            evidence_text=evidence_text,
            evidence_paths=evidence_paths,
            ground_truth_json_path=ground_truth_json_path,
            output_dir=output_path,
            routing_info=extract_url_routing_info(args.url or args.source_url),
        )

        # 3b. Verify chunks contain colors, codes, and fallback images.
        chunk_report = verify_chunks_for_colors_and_images(artifact_dir)
        if chunk_report:
            local_report = "\n\n".join([local_report, chunk_report])

        # 4. Optionally evaluate with LLM.
        if args.use_llm:
            llm_role: ModelRole = args.llm_role
            llm_report = evaluate_with_llm(ground_truth_md, actual_md, llm_role)
            evaluation_report = "\n\n".join(
                [local_report, "# LLM Evaluation Report", "", llm_report]
            )
        else:
            evaluation_report = local_report

        # 5. Save report and review copies.
        actual_copy_path = output_path / "actual_output.md"
        ground_truth_copy_path = output_path / "ground_truth.md"
        actual_copy_path.write_text(actual_md, encoding="utf-8")
        ground_truth_copy_path.write_text(ground_truth_md, encoding="utf-8")
        report_path = output_path / "evaluation_report.md"
        report_path.write_text(evaluation_report, encoding="utf-8")
        logging.info(f"Evaluation report saved to: {report_path.resolve()}")

    except Exception as e:
        logging.error(f"Verification process failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
