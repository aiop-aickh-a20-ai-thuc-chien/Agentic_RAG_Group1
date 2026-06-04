import argparse
import json
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def parse_url(url: str) -> list[dict[str, str]]:
    from agentic_rag.ingestion.url.loader import load_url_chunks  # type: ignore[import-untyped]

    chunks = load_url_chunks(url)
    # Returns list of Chunk objects which have chunk_id, text, metadata
    result = []
    for c in chunks:
        result.append(
            {
                "id": c.chunk_id,
                "url": url,
                "title": c.metadata.get("section", "") or c.metadata.get("title", ""),
                "text": c.text,
            }
        )
    return result


def parse_pdf(path: str) -> list[dict[str, str]]:
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
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="URL to parse")
    parser.add_argument("--pdf", help="Path to PDF to parse")

    args = parser.parse_args()

    try:
        if args.url:
            chunks = parse_url(args.url)
            print(json.dumps({"success": True, "chunks": chunks}, ensure_ascii=False))
        elif args.pdf:
            chunks = parse_pdf(args.pdf)
            print(json.dumps({"success": True, "chunks": chunks}, ensure_ascii=False))
        else:
            print(json.dumps({"success": False, "error": "No input provided"}))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e), "trace": traceback.format_exc()}))


if __name__ == "__main__":
    main()
