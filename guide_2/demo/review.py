import argparse
import html
import json
import pathlib
import sys
from typing import Any, Dict, List

# Add src to path to allow for imports
project_root = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.agentic_rag.core.contracts import Chunk
from src.agentic_rag.ingestion.url.loader import LoadedUrlDocument, load_url_with_artifacts


def generate_html_report(
    source: str,
    chunks: List[Chunk],
    markdown: str,
    artifacts: Dict[str, Any],
    output_dir: pathlib.Path,
):
    """Generates a self-contained HTML report for ingestion review."""

    def format_json(data: Any) -> str:
        return json.dumps(data, indent=2, ensure_ascii=False)

    chunk_rows = []
    for chunk in chunks:
        metadata = chunk.model_dump().get("metadata", {})
        is_dynamic = metadata.get("chunk_type") == "dynamic_state"
        row_class = ' class="dynamic-chunk"' if is_dynamic else ""
        chunk_rows.append(
            f"""<tr{row_class}>
                <td><pre>{html.escape(chunk.id)}</pre></td>
                <td><pre>{html.escape(chunk.text)}</pre></td>
                <td><pre>{html.escape(format_json(metadata))}</pre></td>
            </tr>
            """
        )

    artifact_sections = []
    if markdown:
        artifact_sections.append(
            f"""
            <button type="button" class="collapsible">Debug: Parsed Markdown</button>
            <div class="content">
                <h2>Parsed Markdown</h2>
                <pre>{html.escape(markdown)}</pre>
            </div>
            """
        )

    for name, content in artifacts.items():
        json_str = format_json(content)
        artifact_sections.append(
            f"""
            <button type="button" class="collapsible">Debug: {name}</button>
            <div class="content">
                <h2>{name}</h2>
                <pre>{html.escape(json_str)}</pre>
            </div>
            """
        )

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ingestion Review: {html.escape(source)}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2em; line-height: 1.6; }}
            h1, h2, h3 {{ color: #111; }}
            pre {{ background: #f4f4f4; padding: 1em; border: 1px solid #ddd; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-size: 14px; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 2em; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; vertical-align: top; }}
            th {{ background-color: #f2f2f2; font-weight: 600; }}
            .container {{ max-width: 1400px; margin: auto; }}
            .dynamic-chunk {{ background-color: #fffbe6; }}
            .collapsible {{ background-color: #eee; color: #444; cursor: pointer; padding: 18px; width: 100%; border: none; text-align: left; outline: none; font-size: 15px; margin-top: 1em; border-radius: 5px; }}
            .active, .collapsible:hover {{ background-color: #ccc; }}
            .content {{ padding: 0 18px; display: none; overflow: hidden; background-color: #f9f9f9; border: 1px solid #ddd; border-top: none; }}
            td pre {{ margin: 0; border: none; padding: 0; background: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Ingestion Review</h1>
            <p><strong>Source:</strong> {html.escape(source)}</p>

            <h2>Chunks ({len(chunks)})</h2>
            <table>
                <thead>
                    <tr>
                        <th style="width: 15%;">Chunk ID</th>
                        <th style="width: 45%;">Text</th>
                        <th style="width: 40%;">Metadata</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(chunk_rows)}
                </tbody>
            </table>

            {''.join(artifact_sections)}

            <script>
                var coll = document.getElementsByClassName("collapsible");
                for (var i = 0; i < coll.length; i++) {{
                    coll[i].addEventListener("click", function() {{
                        this.classList.toggle("active");
                        var content = this.nextElementSibling;
                        if (content.style.display === "block") {{
                            content.style.display = "none";
                        }} else {{
                            content.style.display = "block";
                        }}
                    }});
                }}
            </script>
        </div>
    </body>
    </html>
    """
    report_path = output_dir / "review.html"
    report_path.write_text(html_content, encoding="utf-8")
    print(f"Report generated: {report_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(
        description="A pseudo-front-end to check ingestion outputs (chunks, markdown, json)."
    )
    parser.add_argument("source", help="URL to ingest.")
    parser.add_argument(
        "--output-dir",
        default="guide_2/demo/output",
        help="Directory to save the review artifacts.",
    )
    parser.add_argument(
        "--include-interactions",
        action="store_true",
        help="Enable dynamic interaction capture for configurator pages.",
    )
    args = parser.parse_args()

    output_path = pathlib.Path(args.output_dir)
    output_path.mkdir(exist_ok=True, parents=True)

    print(f"Processing source: {args.source}")
    if args.include_interactions:
        print("Dynamic interaction capture is ENABLED.")

    try:
        document: LoadedUrlDocument = load_url_with_artifacts(
            args.source,
            data_artifact_dir=str(output_path / "artifacts"),
            include_interactions=args.include_interactions,
        )
        chunks = document.chunks
        artifacts_obj = document.artifacts
        markdown = artifacts_obj.parsed_markdown_path.read_text(encoding="utf-8") if artifacts_obj and artifacts_obj.parsed_markdown_path and artifacts_obj.parsed_markdown_path.exists() else ""
        artifacts = {}
        if artifacts_obj and artifacts_obj.quality_path and artifacts_obj.quality_path.exists():
            artifacts["quality.json"] = json.loads(artifacts_obj.quality_path.read_text(encoding="utf-8"))
        if artifacts_obj and artifacts_obj.manifest_path and artifacts_obj.manifest_path.exists():
            manifest = json.loads(artifacts_obj.manifest_path.read_text(encoding="utf-8"))
            artifacts["manifest.json"] = manifest
            # Add interaction artifacts if they exist
            interaction_artifacts_path = manifest.get("interaction_artifacts_path")
            if interaction_artifacts_path:
                interaction_path = pathlib.Path(interaction_artifacts_path)
                if interaction_path.exists():
                    artifacts["interaction_artifacts.json"] = json.loads(interaction_path.read_text(encoding="utf-8"))

        generate_html_report(args.source, chunks, markdown, artifacts, output_path)

    except Exception as e:
        print(f"Error processing URL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()