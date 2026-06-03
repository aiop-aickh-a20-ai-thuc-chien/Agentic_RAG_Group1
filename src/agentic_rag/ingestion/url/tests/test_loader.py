from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url import (
    load_html_chunks,
    load_html_with_artifacts,
    load_text_chunks,
    load_url_chunks,
)
from agentic_rag.ingestion.url import loader as loader_module


def test_load_html_chunks_removes_noise_and_preserves_section_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    chunks = load_html_chunks(
        """
        <html>
          <head><title>Admissions Page</title></head>
          <body>
            <nav>Home Login Pricing</nav>
            <main>
              <h1>Admissions</h1>
              <p>Applications require transcripts.</p>
              <h2>Interview</h2>
              <p>Shortlisted applicants join one interview.</p>
            </main>
            <footer>Contact links</footer>
            <script>console.log("tracking")</script>
          </body>
        </html>
        """,
        source="https://example.edu/admissions",
        source_url="https://example.edu/admissions",
    )

    assert all(isinstance(chunk, Chunk) for chunk in chunks)
    assert [chunk.metadata["section"] for chunk in chunks] == ["Admissions", "Interview"]
    assert chunks[0].metadata["source_type"] == "url"
    assert chunks[0].metadata["url"] == "https://example.edu/admissions"
    assert chunks[0].metadata["title"] == "Admissions Page"
    assert "Applications require transcripts." in chunks[0].text
    assert "Home Login Pricing" not in chunks[0].text
    assert "tracking" not in chunks[0].text


def test_load_html_chunks_writes_debug_artifacts(tmp_path: Path) -> None:
    chunks = load_html_chunks(
        "<html><body><h1>Overview</h1><p>Debug content.</p></body></html>",
        source="https://example.edu/debug",
        source_url="https://example.edu/debug",
        debug_artifact_dir=tmp_path,
    )

    artifact_names = {path.name for path in tmp_path.iterdir()}

    assert chunks
    assert any(name.endswith("_raw.html") for name in artifact_names)
    assert any(name.endswith("_parsed.txt") for name in artifact_names)


def test_load_html_chunks_writes_data_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    chunks = load_html_chunks(
        """
        <html>
          <head>
            <title>Example Page</title>
            <link rel="canonical" href="https://example.edu/canonical" />
            <meta name="description" content="Example description." />
          </head>
          <body>
            <main>
              <h1>Overview</h1>
              <p>Stored content.</p>
              <a href="/asset.pdf" title="Asset PDF">PDF</a>
            </main>
          </body>
        </html>
        """,
        source="https://example.edu/page",
        source_url="https://example.edu/page",
        original_url="https://example.edu/original",
        final_url="https://example.edu/page",
        data_artifact_dir=tmp_path,
        run_id="sample_run",
    )

    run_dirs = list((tmp_path / "artifacts").glob("*/sample-run"))
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    markdown_path = run_dir / "parsed.md"
    chunks_path = run_dir / "chunks.jsonl"
    manifest_path = run_dir / "manifest.json"

    assert markdown_path.read_text(encoding="utf-8") == (
        "# Example Page\n\n# Overview\n\nStored content.\n"
    )
    chunk_lines = chunks_path.read_text(encoding="utf-8").splitlines()
    assert len(chunk_lines) == len(chunks)
    assert json.loads(chunk_lines[0])["chunk_id"] == chunks[0].chunk_id

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifact_schema_version"] == 1
    assert manifest["input_type"] == "url"
    assert manifest["input_source"] == "https://example.edu/page"
    assert manifest["input_url"] == "https://example.edu/page"
    assert manifest["original_url"] == "https://example.edu/original"
    assert manifest["final_url"] == "https://example.edu/page"
    assert manifest["canonical_url"] == "https://example.edu/canonical"
    assert manifest["page_metadata"]["description"] == "Example description."
    assert manifest["assets"] == [
        {
            "kind": "pdf",
            "url": "https://example.edu/asset.pdf",
            "alt": None,
            "title": "Asset PDF",
            "target_url": None,
        }
    ]
    assert manifest["parser"] == "builtin-html-parser"
    assert manifest["run_id"] == "sample_run"
    assert manifest["markdown_path"].endswith("/parsed.md")
    assert manifest["chunks_path"].endswith("/chunks.jsonl")
    assert manifest["manifest_path"].endswith("/manifest.json")
    assert manifest["chunk_count"] == len(chunks)


def test_load_html_with_artifacts_returns_markdown_and_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    loaded = load_html_with_artifacts(
        "<html><head><title>Artifact Page</title></head>"
        "<body><main><h1>Intro</h1><p>Artifact content.</p></main></body></html>",
        source="https://example.edu/artifact",
        source_url="https://example.edu/artifact",
        data_artifact_dir=tmp_path,
        run_id="artifact-run",
    )

    assert loaded.markdown == "# Artifact Page\n\n# Intro\n\nArtifact content.\n"
    assert len(loaded.chunks) == 1
    assert loaded.artifacts is not None
    assert loaded.artifacts.markdown_path.read_text(encoding="utf-8") == loaded.markdown
    assert loaded.artifacts.chunks_path.exists()


def test_load_html_chunks_prefers_trafilatura_markdown_for_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_extract_markdown_with_trafilatura(
        html: str,
        *,
        source_url: str | None,
    ) -> str:
        assert "Raw content" in html
        assert source_url == "https://example.edu/article"
        return "# Clean Article\n\nClean extracted content."

    monkeypatch.setattr(
        loader_module,
        "extract_markdown_with_trafilatura",
        fake_extract_markdown_with_trafilatura,
    )

    loaded = load_html_with_artifacts(
        "<html><body><h1>Raw</h1><p>Raw content.</p></body></html>",
        source="https://example.edu/article",
        source_url="https://example.edu/article",
        data_artifact_dir=tmp_path,
        run_id="trafilatura_run",
    )

    assert loaded.chunks[0].text == "Raw Raw content."
    assert loaded.chunks[0].metadata["section"] == "Raw"
    assert loaded.chunks[0].metadata["chunking_method"] == "deterministic-character-overlap"

    run_dirs = list((tmp_path / "artifacts").glob("*/trafilatura-run"))
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "parsed.md").read_text(encoding="utf-8") == (
        "# Clean Article\n\nClean extracted content.\n"
    )

    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["parser"] == "trafilatura-markdown+builtin-html-parser"


def test_load_text_chunks_returns_text_source_metadata() -> None:
    chunks = load_text_chunks(" Plain text content for ingestion. ", source="manual-note")

    assert len(chunks) == 1
    assert chunks[0].text == "Plain text content for ingestion."
    assert chunks[0].metadata["source"] == "manual-note"
    assert chunks[0].metadata["source_type"] == "text"
    assert chunks[0].metadata["url"] is None
    assert chunks[0].metadata["section"] == "main"


def test_load_text_chunks_returns_empty_list_for_blank_text() -> None:
    assert load_text_chunks(" \n\t ", source="blank") == []


def test_load_url_chunks_uses_fetched_final_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch_url(url: str) -> loader_module._FetchedPage:
        assert url == "https://example.edu"
        return loader_module._FetchedPage(
            html="<html><body><h1>Overview</h1><p>Fetched content.</p></body></html>",
            url="https://example.edu/final",
        )

    monkeypatch.setattr(loader_module, "_fetch_url", fake_fetch_url)
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    chunks = load_url_chunks("https://example.edu")

    assert len(chunks) == 1
    assert chunks[0].text == "Overview Fetched content."
    assert chunks[0].metadata["source"] == "https://example.edu/final"
    assert chunks[0].metadata["url"] == "https://example.edu/final"
    assert chunks[0].metadata["original_url"] == "https://example.edu"
    assert chunks[0].metadata["final_url"] == "https://example.edu/final"
    assert chunks[0].metadata["section"] == "Overview"
    assert chunks[0].metadata["chunking_library"] == "agentic_rag.ingestion.chunking"
    assert chunks[0].metadata["chunking_input_type"] == "parsed_section"


def test_load_url_chunks_rejects_non_http_url() -> None:
    with pytest.raises(ValueError, match="absolute http or https URL"):
        load_url_chunks("file:///tmp/example.html")


def test_load_url_chunks_rejects_direct_pdf_url() -> None:
    with pytest.raises(ValueError, match="PDF URL"):
        load_url_chunks("https://example.edu/file.pdf")


def test_load_url_chunks_rejects_pdf_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch_url(url: str) -> loader_module._FetchedPage:
        assert url == "https://example.edu/download"
        return loader_module._FetchedPage(
            html="%PDF-1.7",
            url="https://example.edu/download",
            content_type="application/pdf",
        )

    monkeypatch.setattr(loader_module, "_fetch_url", fake_fetch_url)

    with pytest.raises(ValueError, match="PDF response"):
        load_url_chunks("https://example.edu/download")
