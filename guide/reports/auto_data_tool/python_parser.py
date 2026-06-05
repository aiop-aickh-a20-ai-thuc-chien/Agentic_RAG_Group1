import argparse
import json
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def parse_url(url: str) -> dict[str, object]:
    from agentic_rag.ingestion.url.loader import (  # type: ignore[import-untyped]
        load_url_with_artifacts,
    )

    document = load_url_with_artifacts(url)
    # Returns list of Chunk objects which have chunk_id, text, metadata
    result = []
    for c in document.chunks:
        result.append(
            {
                "id": c.chunk_id,
                "url": url,
                "title": c.metadata.get("section", "") or c.metadata.get("title", ""),
                "text": c.text,
            }
        )
    return {"chunks": result, "markdown": document.markdown}


def parse_pdf(path: str) -> dict[str, object]:
    from agentic_rag.ingestion.pdf.loader import load_pdf_chunks  # type: ignore[import-untyped]

    chunks = load_pdf_chunks(path)
    result = []
    for c in chunks:
        result.append(
            {
                "id": c.chunk_id,
                "url": path,
                "title": c.metadata.get("section", "") or c.metadata.get("title", ""),
                "text": c.text,
            }
        )
    return {"chunks": result, "markdown": "\n\n".join(item["text"] for item in result)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="URL to parse")
    parser.add_argument("--pdf", help="Path to PDF to parse")

    args = parser.parse_args()

    try:
        if args.url:
            parsed = parse_url(args.url)
            print(json.dumps({"success": True, **parsed}, ensure_ascii=False))
        elif args.pdf:
            parsed = parse_pdf(args.pdf)
            print(json.dumps({"success": True, **parsed}, ensure_ascii=False))
        else:
            print(json.dumps({"success": False, "error": "No input provided"}))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e), "trace": traceback.format_exc()}))


if __name__ == "__main__":
    main()
