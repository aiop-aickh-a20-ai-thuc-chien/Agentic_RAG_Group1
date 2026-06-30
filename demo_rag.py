#!/usr/bin/env python
"""
Standalone in-process CLI demo for Agentic RAG.
Allows you to ingest PDFs, URLs, or custom text, and query the RAG pipeline directly.

Usage:
    # Run the interactive menu:
    uv run python demo_rag.py

    # Or use command line arguments:
    uv run python demo_rag.py list
    uv run python demo_rag.py ingest-pdf --path data/lux_manual.pdf
    uv run python demo_rag.py ingest-url --url "https://example.com"
    uv run python demo_rag.py ingest-text --title "Warranty" --text "Warranty is 8 years."
    uv run python demo_rag.py search "How long is the warranty?"
    uv run python demo_rag.py delete-all
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Add the src folder to system path so we can import agentic_rag packages
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from agentic_rag.runtime_env import load_local_env
from agentic_rag.generation.evidence import source_provider_from_env
from agentic_rag.core.contracts import RetrievalInput


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(f" {title} ".center(60, "="))
    print("=" * 60)


def show_config(provider) -> None:
    print_header("RAG Configuration")
    print(f"Active Provider class : {provider.__class__.__name__}")
    print(f"EVIDENCE_PROVIDER      : {os.getenv('EVIDENCE_PROVIDER')}")
    print(f"LOCAL_PDF_STORE_DIR    : {os.getenv('LOCAL_PDF_STORE_DIR')}")
    print(f"LOCAL_PDF_STRATEGY     : {os.getenv('LOCAL_PDF_STRATEGY')}")
    print(f"LOCAL_PDF_CHUNKER      : {os.getenv('LOCAL_PDF_CHUNKER')}")
    print(f"VECTOR_STORE_PROVIDER  : {os.getenv('VECTOR_STORE_PROVIDER')}")
    print(f"EMBEDDING_PROVIDER     : {os.getenv('EMBEDDING_PROVIDER')}")
    print(f"EMBEDDING_MODEL        : {os.getenv('EMBEDDING_MODEL')}")
    print("=" * 60)


def list_docs(provider) -> None:
    print_header("Ingested Source Documents")
    try:
        docs = provider.list_documents(include_chunks=False)
        if not docs:
            print("No documents ingested yet. Database is empty.")
        else:
            for idx, d in enumerate(docs, 1):
                print(f"{idx}. Name: {d.name}")
                print(f"   ID: {d.document_id}")
                print(f"   Type: {d.source_type} | Total Chunks: {d.total_chunks}")
                print("-" * 60)
    except Exception as e:
        print(f"Error listing documents: {e}", file=sys.stderr)


def ingest_pdf(provider, pdf_path_str: str) -> None:
    print_header("Ingesting PDF File")
    pdf_path = Path(pdf_path_str.strip('"').strip("'"))
    if not pdf_path.exists():
        print(f"Error: File not found at '{pdf_path}'", file=sys.stderr)
        return

    try:
        print(f"Reading file: {pdf_path.name}...")
        content = pdf_path.read_bytes()
        print(f"Ingesting PDF (size: {len(content)} bytes). Parsing and chunking in progress...")
        
        start_time = time.perf_counter()
        res = provider.upload_document(filename=pdf_path.name, content=content)
        latency = time.perf_counter() - start_time
        
        print(f"\n✓ Successfully Ingested!")
        print(f"  - Document ID: {res.document_id}")
        print(f"  - Latency: {latency:.2f} seconds")
    except Exception as e:
        print(f"Error ingesting PDF: {e}", file=sys.stderr)


def ingest_url(provider, url: str) -> None:
    print_header("Ingesting URL Content")
    try:
        print(f"Scraping and chunking URL: {url}...")
        
        start_time = time.perf_counter()
        res = provider.upload_url(url=url)
        latency = time.perf_counter() - start_time
        
        print(f"\n✓ Successfully Ingested!")
        print(f"  - Document ID: {res.document_id}")
        print(f"  - Latency: {latency:.2f} seconds")
    except Exception as e:
        print(f"Error ingesting URL: {e}", file=sys.stderr)


def ingest_text(provider, title: str, text: str) -> None:
    print_header("Ingesting Custom Text")
    try:
        title = title or "Custom Text"
        print(f"Uploading text titled '{title}'...")
        
        start_time = time.perf_counter()
        res = provider.upload_text(title=title, text=text)
        latency = time.perf_counter() - start_time
        
        print(f"\n✓ Successfully Ingested!")
        print(f"  - Document ID: {res.document_id}")
        print(f"  - Latency: {latency:.2f} seconds")
    except Exception as e:
        print(f"Error ingesting text: {e}", file=sys.stderr)


def search_query(provider, question: str) -> None:
    print_header(f"Query Retrieval Search: '{question}'")
    try:
        print("Retrieving and fusing matched chunks...")
        start_time = time.perf_counter()
        res = provider.retrieve(RetrievalInput(question=question))
        latency = time.perf_counter() - start_time
        
        results = res.results
        print(f"Search complete in {latency:.4f} seconds.")
        print(f"Found {len(results)} chunks.")
        
        if not results:
            print("\nNo matching chunks found.")
            return

        for i, r in enumerate(results, 1):
            meta = r.chunk.metadata
            src = meta.get("source") or meta.get("file_name") or "unknown"
            page = meta.get("page_number")
            page_str = f" | Page {page}" if page else ""
            score_str = f"Score: {r.score:.4f}"
            retriever_str = f"Retriever: {r.retriever}"
            
            print("\n" + "-" * 60)
            print(f"[{i}] {src}{page_str} ({score_str} | {retriever_str})")
            print("-" * 60)
            print(r.chunk.text.strip())
        print("\n" + "=" * 60)
    except Exception as e:
        print(f"Error during search: {e}", file=sys.stderr)


def delete_all(provider) -> None:
    print_header("Delete All Documents")
    try:
        count = provider.delete_all_documents()
        print(f"✓ All documents, chunks, and dense vector indexes have been deleted. (Status count: {count})")
    except Exception as e:
        print(f"Error deleting documents: {e}", file=sys.stderr)


def interactive_menu(provider) -> None:
    while True:
        print_header("Agentic RAG CLI Interactive Menu")
        print("1. Show current configuration")
        print("2. List all ingested documents")
        print("3. Ingest a local PDF file")
        print("4. Ingest a URL (webpage)")
        print("5. Ingest custom text")
        print("6. Run search/retrieval query")
        print("7. Clear database (Delete all documents)")
        print("8. Exit")
        
        try:
            choice = input("\nSelect an option (1-8): ").strip()
            if not choice:
                continue
                
            if choice == "1":
                show_config(provider)
            elif choice == "2":
                list_docs(provider)
            elif choice == "3":
                path_str = input("Enter path to PDF file: ").strip()
                if path_str:
                    ingest_pdf(provider, path_str)
            elif choice == "4":
                url = input("Enter URL: ").strip()
                if url:
                    ingest_url(provider, url)
            elif choice == "5":
                title = input("Enter title/source name: ").strip()
                print("Enter text content (Press Enter when done, then Ctrl+D / Ctrl+Z + Enter to finish, or enter a single line):")
                lines = []
                while True:
                    try:
                        line = input()
                        lines.append(line)
                    except EOFError:
                        break
                text = "\n".join(lines)
                if not text.strip() and len(lines) == 1:
                    # Fallback for simple single-line inputs if they didn't do EOF
                    text = lines[0]
                if text.strip():
                    ingest_text(provider, title, text)
            elif choice == "6":
                question = input("Enter search query/question: ").strip()
                if question:
                    search_query(provider, question)
            elif choice == "7":
                confirm = input("Are you sure you want to delete ALL documents? (y/N): ").strip().lower()
                if confirm == "y":
                    delete_all(provider)
            elif choice == "8":
                print("\nExiting. Goodbye!")
                break
            else:
                print("Invalid selection. Please choose 1-8.")
        except KeyboardInterrupt:
            print("\nExiting. Goodbye!")
            break
        
        input("\nPress Enter to return to the menu...")


def main() -> None:
    # Load env files
    load_dotenv()
    load_local_env()

    # Set up stdout/stderr encoding for Windows console to handle Vietnamese characters
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

    # Initialize the provider
    try:
        provider = source_provider_from_env()
    except Exception as e:
        print(f"Error: Failed to initialize source evidence provider. Details: {e}", file=sys.stderr)
        print("Please check your .env configurations.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Agentic RAG Standalone Demo CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: list
    subparsers.add_parser("list", help="List all ingested documents")

    # Command: config
    subparsers.add_parser("config", help="Show current RAG configurations")

    # Command: ingest-pdf
    pdf_parser = subparsers.add_parser("ingest-pdf", help="Ingest a PDF file")
    pdf_parser.add_argument("--path", required=True, help="Path to the PDF file")

    # Command: ingest-url
    url_parser = subparsers.add_parser("ingest-url", help="Ingest content from a URL")
    url_parser.add_argument("--url", required=True, help="URL to ingest")

    # Command: ingest-text
    text_parser = subparsers.add_parser("ingest-text", help="Ingest custom text")
    text_parser.add_argument("--title", default="Custom Text", help="Title of the source")
    text_parser.add_argument("--text", required=True, help="Raw text content to ingest")

    # Command: search
    search_parser = subparsers.add_parser("search", help="Query the RAG pipeline")
    search_parser.add_argument("query", help="Question to query the index with")

    # Command: delete-all
    subparsers.add_parser("delete-all", help="Delete all ingested documents")

    args = parser.parse_args()

    if not args.command:
        # No command line arguments, drop into interactive mode
        interactive_menu(provider)
    else:
        if args.command == "list":
            list_docs(provider)
        elif args.command == "config":
            show_config(provider)
        elif args.command == "ingest-pdf":
            ingest_pdf(provider, args.path)
        elif args.command == "ingest-url":
            ingest_url(provider, args.url)
        elif args.command == "ingest-text":
            ingest_text(provider, args.title, args.text)
        elif args.command == "search":
            search_query(provider, args.query)
        elif args.command == "delete-all":
            delete_all(provider)


if __name__ == "__main__":
    main()
