"""Use configured OpenAI/LLM runtime to judge dedup threshold choices."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agentic_rag.core.contracts import LLMCompletionInput
from agentic_rag.model_runtime.factory import get_llm_client

DEMO_DIR = Path(__file__).resolve().parent
DEFAULT_REPORT = DEMO_DIR / "output" / "threshold_confusion_report.md"
DEFAULT_OUTPUT_DIR = DEMO_DIR / "output"


def main() -> None:
    args = _parse_args()
    report_text = args.report.read_text(encoding="utf-8")
    prompt = _build_prompt(report_text)
    client = get_llm_client("evaluation")
    if client is None:
        raise SystemExit(
            "No evaluation LLM is configured. Set LLM_PROVIDER/LLM_MODEL/LLM_API_KEY "
            "or EVALUATION_LLM_* in .env."
        )

    output = client.complete(
        LLMCompletionInput(
            system_message=(
                "You are a careful evaluation engineer. Judge threshold tradeoffs "
                "from confusion-matrix reports. Return only valid JSON."
            ),
            prompt=prompt,
            temperature=0.0,
        )
    )
    judgement = _parse_json_object(output.text)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "threshold_llm_judgement.json", judgement)
    _write_markdown(args.output_dir / "threshold_llm_judgement.md", judgement)
    print(f"Wrote {args.output_dir / 'threshold_llm_judgement.md'}")
    print(f"Wrote {args.output_dir / 'threshold_llm_judgement.json'}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Judge dedup threshold report with the configured evaluation LLM."
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to threshold_confusion_report.md.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for LLM judgement outputs.",
    )
    return parser.parse_args()


def _build_prompt(report_text: str) -> str:
    return f"""Read this dedup threshold confusion-matrix report and judge the threshold choices.

Return one JSON object with these exact top-level keys:

- best_choice
- optimized_choice
- compromised_choice
- worst_choice
- decision_notes
- follow_up_labeling_advice

Each choice object must contain:

- layer2_simhash_threshold
- layer3_embedding_threshold
- precision
- recall
- f1
- tp
- fp
- fn
- tn
- rationale
- fp_ids
- fn_ids

Definitions:

- best_choice: highest overall quality from the table, considering F1 first.
- optimized_choice: the practical recommendation for deployment after weighing FP/FN risk.
- compromised_choice: an acceptable fallback when you want to trade some quality for safer behavior.
- worst_choice: the threshold row that should be avoided.

For duplicate detection, false positives can incorrectly merge unrelated evidence,
while false negatives leave duplicate noise in the corpus. Explain the tradeoff.
If Layer 3 is disabled in the report, use null for layer3_embedding_threshold and
say that the choice is based only on Layer 1 + Layer 2.

Report:

```markdown
{report_text}
```
"""


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("LLM judgement must be a JSON object.")
    return parsed


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_markdown(path: Path, judgement: dict[str, Any]) -> None:
    lines = ["# Dedup Threshold LLM Judgement", ""]
    for key, title in (
        ("best_choice", "Best Choice"),
        ("optimized_choice", "Optimized Choice"),
        ("compromised_choice", "Compromised Choice"),
        ("worst_choice", "Worst Choice"),
    ):
        choice = judgement.get(key)
        lines.extend([f"## {title}", ""])
        if not isinstance(choice, dict):
            lines.extend(["No choice returned.", ""])
            continue
        lines.extend(
            [
                f"- Layer 2 SimHash threshold: {choice.get('layer2_simhash_threshold')}",
                f"- Layer 3 embedding threshold: {choice.get('layer3_embedding_threshold')}",
                f"- Precision: {choice.get('precision')}",
                f"- Recall: {choice.get('recall')}",
                f"- F1: {choice.get('f1')}",
                (
                    "- TP/FP/FN/TN: "
                    f"{choice.get('tp')}/{choice.get('fp')}/"
                    f"{choice.get('fn')}/{choice.get('tn')}"
                ),
                "",
                str(choice.get("rationale", "")),
                "",
            ]
        )
        lines.extend(_ids_section("FP IDs", choice.get("fp_ids")))
        lines.extend(_ids_section("FN IDs", choice.get("fn_ids")))

    lines.extend(["## Decision Notes", "", str(judgement.get("decision_notes", "")), ""])
    lines.extend(
        [
            "## Follow-Up Labeling Advice",
            "",
            str(judgement.get("follow_up_labeling_advice", "")),
            "",
        ]
    )
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _ids_section(title: str, ids: Any) -> list[str]:
    lines = [f"### {title}", ""]
    if not isinstance(ids, list) or not ids:
        return [*lines, "None.", ""]
    return [*lines, *(f"- `{item}`" for item in ids), ""]


if __name__ == "__main__":
    main()
