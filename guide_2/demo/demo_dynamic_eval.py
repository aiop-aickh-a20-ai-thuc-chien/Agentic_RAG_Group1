import os
import sys
import re
import json
import pathlib
import logging

# Set up paths and imports
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from agentic_rag.runtime_env import load_local_env
from agentic_rag.model_runtime.factory import get_llm_client
from agentic_rag.core.contracts import LLMCompletionInput

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Default Ground Truth & Actual Markdown files for the offline fallback
GT_DIR = PROJECT_ROOT / "guide_2" / "ground_truth" / "https-shop-vinfastauto-com-vn-vi-dat-coc-o-to-dien-vinfast-html-modelid-products-car-VF9"
GT_FILE = GT_DIR / "vf9_ground_truth.md"
OFFLINE_ACTUAL_FILE = PROJECT_ROOT / "guide_2" / "demo" / "verify_ingestion" / "offline_self_check" / "actual_output.md"

PROMPTS_FILE = PROJECT_ROOT / "guide_2" / "test_prompts.md"

def extract_prompt_block(text, title):
    """Extract prompt text inside a markdown code block under a specific heading."""
    pattern = rf"###\s+{re.escape(title)}.*?\n```text\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback to general block search if heading parsing is slightly different
    pattern_fallback = rf"###\s+{re.escape(title)}.*?\n```\n(.*?)\n```"
    match_fallback = re.search(pattern_fallback, text, re.DOTALL | re.IGNORECASE)
    if match_fallback:
        return match_fallback.group(1).strip()
    return None

def main():
    print("======================================================================")
    print("      VinFast Dynamic and Structured Ingestion Evaluation Demo        ")
    print("======================================================================\n")

    # 1. Load prompts from guide_2/test_prompts.md
    if not PROMPTS_FILE.exists():
        print(f"Error: Prompts file not found at {PROMPTS_FILE}")
        sys.exit(1)
        
    prompts_content = PROMPTS_FILE.read_text(encoding="utf-8")
    
    struct_prompt_template = extract_prompt_block(prompts_content, "2.1. Structural & Formatting Verification Prompt")
    hidden_prompt_template = extract_prompt_block(prompts_content, "2.2. Hidden List & Accordion Completeness Prompt")
    pricing_prompt_template = extract_prompt_block(prompts_content, "2.3. State-Aware Dynamic Pricing Prompt")

    if not struct_prompt_template or not hidden_prompt_template or not pricing_prompt_template:
        print("Error: Could not extract prompt blocks from test_prompts.md.")
        print(f"Struct block present: {struct_prompt_template is not None}")
        print(f"Hidden block present: {hidden_prompt_template is not None}")
        print(f"Pricing block present: {pricing_prompt_template is not None}")
        sys.exit(1)

    print("Successfully loaded prompt templates from test_prompts.md.")

    # 2. Resolve actual output and ground truth Markdown
    if not GT_FILE.exists():
        print(f"Error: Ground truth file not found at {GT_FILE}")
        sys.exit(1)
    
    ground_truth_md = GT_FILE.read_text(encoding="utf-8")
    
    if OFFLINE_ACTUAL_FILE.exists():
        print(f"Using offline actual output from: {OFFLINE_ACTUAL_FILE.name}")
        actual_md = OFFLINE_ACTUAL_FILE.read_text(encoding="utf-8")
    else:
        # Check if we have another output file under guide_2/demo/output
        fallback_actual = PROJECT_ROOT / "guide_2" / "demo" / "output" / "actual_output.md"
        if fallback_actual.exists():
            print(f"Using local actual output from: {fallback_actual}")
            actual_md = fallback_actual.read_text(encoding="utf-8")
        else:
            print("Error: No actual output markdown file found. Please run the ingestion verifier first.")
            sys.exit(1)

    # 3. Initialize LLM client
    try:
        load_local_env()
        llm_client = get_llm_client("evaluation")
        if not llm_client:
            llm_client = get_llm_client("ingestion")
        if not llm_client:
            llm_client = get_llm_client("default")
    except Exception as e:
        print(f"Error initializing LLM client: {e}")
        sys.exit(1)

    if not llm_client:
        print("Error: LLM client could not be resolved from your .env settings.")
        sys.exit(1)
        
    print(f"Using LLM Client: {llm_client}")

    # 4. Run LLM evaluations
    def run_llm_eval(template, actual, gt, title):
        print(f"Running LLM evaluation: {title}...")
        prompt = template.replace("{actual_md}", actual).replace("{ground_truth_md}", gt)
        try:
            response = llm_client.complete(
                LLMCompletionInput(
                    prompt=prompt,
                    system_message="You are an expert Quality Assurance evaluator for RAG systems.",
                    temperature=0.0,
                )
            )
            return response.text.strip()
        except Exception as err:
            return f"LLM Evaluation failed: {err}"

    struct_result = run_llm_eval(struct_prompt_template, actual_md, ground_truth_md, "Structural & Formatting Integrity")
    hidden_result = run_llm_eval(hidden_prompt_template, actual_md, ground_truth_md, "Hidden List & Accordion Completeness")
    pricing_result = run_llm_eval(pricing_prompt_template, actual_md, ground_truth_md, "State-Aware Dynamic Pricing")

    # 5. Generate rich HTML report
    output_dir = PROJECT_ROOT / "guide_2" / "demo" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    html_report_path = output_dir / "dynamic_eval_report.html"
    markdown_report_path = output_dir / "dynamic_eval_report.md"

    # Save Markdown report
    md_content = f"""# Ingestion Evaluation Report for Dynamic Structures

This report evaluates our URL ingestion outputs using the structured test prompts in `guide_2/test_prompts.md`.

## 1. Structural & Formatting Verification
{struct_result}

## 2. Hidden List & Accordion Completeness
{hidden_result}

## 3. State-Aware Dynamic Pricing Checklist
{pricing_result}
"""
    markdown_report_path.write_text(md_content, encoding="utf-8")

    # Build beautiful CSS/HTML report
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dynamic Ingestion Evaluation Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #f7f9fa;
            color: #333;
            margin: 0;
            padding: 2em;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            background: #fff;
            padding: 3em;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
        }}
        h1 {{
            color: #0c2340;
            border-bottom: 2px solid #0056b3;
            padding-bottom: 15px;
            margin-top: 0;
            font-size: 2.2em;
        }}
        h2 {{
            color: #0056b3;
            margin-top: 2em;
            border-bottom: 1px solid #e1e4e6;
            padding-bottom: 8px;
            font-size: 1.5em;
        }}
        pre, code {{
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
            background-color: #f1f3f5;
            border-radius: 6px;
        }}
        code {{
            padding: 0.2em 0.4em;
            font-size: 85%;
        }}
        pre {{
            padding: 1.5em;
            overflow-x: auto;
            border: 1px solid #dee2e6;
            font-size: 14px;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .card {{
            background: #f8f9fa;
            border-left: 5px solid #0056b3;
            padding: 1.5em;
            margin: 1.5em 0;
            border-radius: 0 8px 8px 0;
        }}
        .badge-info {{
            background-color: #e7f3ff;
            color: #0066cc;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
            display: inline-block;
        }}
        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5em;
            margin-top: 1.5em;
        }}
        .half-pre {{
            max-height: 400px;
            overflow-y: auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Dynamic Ingestion Evaluation Report</h1>
        <p>This report presents the LLM evaluation of our crawler output using the custom test prompts in <code>guide_2/test_prompts.md</code>, verifying dynamic states (VinClub membership, premium colors, model selection) and structure preservation.</p>
        
        <div class="card">
            <strong>Target Page Profile:</strong> <code>vehicle_configurator / booking_flow (VF 9)</code><br>
            <strong>Evaluated URL:</strong> <a href="https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9" target="_blank">VinFast Deposit Page (VF 9)</a>
        </div>

        <h2>1. Structural & Formatting Verification</h2>
        <pre>{struct_result}</pre>

        <h2>2. Hidden List & Accordion Completeness</h2>
        <pre>{hidden_result}</pre>

        <h2>3. State-Aware Dynamic Pricing Checklist</h2>
        <pre>{pricing_result}</pre>

        <h2>Input Data Snapshots (Collapsible)</h2>
        <div class="grid">
            <div>
                <h3>Ground Truth (Target Ideal)</h3>
                <pre class="half-pre">{ground_truth_md}</pre>
            </div>
            <div>
                <h3>Actual Ingested Output</h3>
                <pre class="half-pre">{actual_md}</pre>
            </div>
        </div>
    </div>
</body>
</html>
"""
    html_report_path.write_text(html_content, encoding="utf-8")

    print("\n=======================================================================")
    print("  Evaluation Completed Successfully! Reports Saved:                    ")
    print(f"  - Markdown: {markdown_report_path.resolve()}")
    print(f"  - HTML:     {html_report_path.resolve()}")
    print("=======================================================================")

if __name__ == "__main__":
    main()
