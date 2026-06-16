from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url import (
    LoadedUrlDocument,
    load_html_chunks,
    load_html_with_artifacts,
    load_text_chunks,
    load_url_chunks,
)
from agentic_rag.ingestion.url import loader as loader_module
from agentic_rag.ingestion.url.chunking import normalize_for_content_hash, short_hash
from agentic_rag.ingestion.url.extractor import ExtractedMarkdown


def test_load_html_chunks_removes_noise_and_preserves_section_metadata() -> None:
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
    assert [chunk.metadata["section"] for chunk in chunks] == ["Admissions"]
    assert chunks[0].metadata["chunk_id"] == chunks[0].chunk_id
    assert chunks[0].metadata["source_type"] == "url"
    assert chunks[0].metadata["url"] == "https://example.edu/admissions"
    assert chunks[0].metadata["domain"] == "example.edu"
    assert chunks[0].metadata["title"] == "Admissions Page"
    assert chunks[0].metadata["section_level"] == 1
    assert chunks[0].metadata["section_path"] == ["Admissions Page", "Admissions"]
    assert chunks[0].metadata["chunk_part_index"] == 1
    assert chunks[0].metadata["chunk_part_total"] == 1
    assert "chunking_method" not in chunks[0].metadata
    assert "semantic_unit" not in chunks[0].metadata
    assert "Applications require transcripts." in chunks[0].text
    assert "Shortlisted applicants join one interview." in chunks[0].text
    assert "Home Login Pricing" not in chunks[0].text
    assert "tracking" not in chunks[0].text


def test_load_html_chunks_adds_dom_entity_metadata() -> None:
    chunks = load_html_chunks(
        """
        <html lang="vi">
          <head>
            <title>VinFast Shop</title>
            <link rel="canonical" href="https://shop.vinfastauto.com/vn_vi/vf8" />
            <meta property="article:published_time" content="2026-06-01" />
            <meta property="article:modified_time" content="2026-06-15" />
          </head>
          <body>
            <main>
              <h1>Bang gia xe</h1>
              <article class="vehicle-card">
                <h2>VF 8</h2>
                <p>Gia 849.000.000 VND</p>
                <p>Range 480 km</p>
                <p>5 seats</p>
              </article>
            </main>
          </body>
        </html>
        """,
        source="https://shop.vinfastauto.com/vn_vi/vf8",
        source_url="https://shop.vinfastauto.com/vn_vi/vf8",
    )

    assert chunks
    metadata = chunks[0].metadata
    assert metadata["canonical_url"] == "https://shop.vinfastauto.com/vn_vi/vf8"
    assert metadata["captured_at"]
    assert metadata["published_at"] == "2026-06-01"
    assert metadata["created_date"] == "2026-06-15"
    assert metadata["created_date_source"] == "page_modified_metadata"
    assert metadata["updated_date"] == metadata["captured_at"]
    assert metadata["updated_date_source"] == "ingestion_start"
    assert metadata["language"] == "vi"
    assert metadata["heading"] == "Bang gia xe"
    assert metadata["breadcrumb"] == ["VinFast Shop", "Bang gia xe"]
    assert metadata["document_type"] == "vehicle_or_product_page"
    assert metadata["token_count"] == metadata["chunk_token_count"]
    assert metadata["chunk_index"] == metadata["chunk_part_index"]
    assert metadata["semantic_block_count"] >= 1
    assert metadata["semantic_block_types"]["vehicle_card"] >= 1
    assert metadata["entity_count"] >= 1
    assert metadata["entity_types"]["vehicle"] >= 1
    assert "VF 8" in metadata["entity_names"]
    assert "VF 8" in metadata["entities"]
    assert metadata["page_type"] == "vehicle_or_product_page"
    assert metadata["extractor_page_type"]
    assert metadata["entity_type"] == "vehicle"
    assert metadata["entity_name"] == "VF 8"
    assert metadata["attribute_group"] == "pricing_specs"
    assert metadata["is_noise"] is False
    assert metadata["retrieval_weight"] > 1.0
    assert metadata["product_model"] == "VF 8"
    assert metadata["product_price"] == "849.000.000 VND"
    assert metadata["driving_range"] == "480 km"
    assert metadata["product_specs"]["seats"] == "5 seats"


def test_load_html_chunks_adds_product_spec_metadata_from_detail_text() -> None:
    chunks = load_html_chunks(
        """
        <html lang="vi">
          <head><title>VF 8 | VinFast</title></head>
          <body>
            <main>
              <h1>VF 8</h1>
              <section class="specifications">
                <h2>Thong so ky thuat</h2>
                <p>Gia niem yet 1.019.000.000 VND</p>
                <p>Quang duong di chuyen 471 km</p>
                <p>Dung luong pin 87,7 kWh</p>
                <p>Thoi gian sac nhanh 31 phut</p>
                <p>Cong suat toi da 300 kW</p>
                <p>Mo men xoan cuc dai 500 Nm</p>
                <p>Toc do toi da 200 km/h</p>
                <p>Bao hanh 10 nam</p>
              </section>
            </main>
          </body>
        </html>
        """,
        source="https://vinfastauto.com/vn_vi/vf-8",
        source_url="https://vinfastauto.com/vn_vi/vf-8",
    )

    metadata = chunks[0].metadata
    specs = metadata["product_specs"]

    assert metadata["product_model"] == "VF 8"
    assert metadata["product_price"] == "1.019.000.000 VND"
    assert metadata["driving_range"] == "471 km"
    assert metadata["battery_capacity"] == "87,7 kWh"
    assert metadata["charging_time"] == "31 phut"
    assert specs["power"] == "300 kW"
    assert specs["torque"] == "500 Nm"
    assert specs["max_speed"] == "200 km/h"
    assert specs["warranty"] == "10 nam"
    assert metadata["attribute_group"] == "pricing_specs"


def test_load_html_chunks_uses_page_hash_and_chunk_level_content_hash() -> None:
    first_text = " ".join(f"first{i}" for i in range(180))
    second_text = " ".join(f"second{i}" for i in range(180))
    chunks = load_html_chunks(
        f"""
        <html>
          <head><title>Hash Page</title></head>
          <body>
            <main>
              <h1>First</h1>
              <p>{first_text}</p>
              <h1>Second</h1>
              <p>{second_text}</p>
            </main>
          </body>
        </html>
        """,
        source="https://example.edu/hash",
        source_url="https://example.edu/hash",
    )

    assert len(chunks) >= 2
    page_hashes = {chunk.metadata["page_hash"] for chunk in chunks}
    content_hashes = {chunk.metadata["content_hash"] for chunk in chunks}

    assert len(page_hashes) == 1
    assert len(content_hashes) > 1
    assert chunks[0].metadata["content_hash"] == short_hash(
        normalize_for_content_hash(chunks[0].text)
    )
    assert chunks[0].metadata["dedupe_hash"]
    assert chunks[0].metadata["normalized_text"] == normalize_for_content_hash(chunks[0].text)


def test_load_html_chunks_writes_debug_artifacts(tmp_path: Path) -> None:
    chunks = load_html_chunks(
        "<html><body><h1>Overview</h1>"
        "<p>Debug content with enough detail for chunk review.</p></body></html>",
        source="https://example.edu/debug",
        source_url="https://example.edu/debug",
        debug_artifact_dir=tmp_path,
    )

    artifact_names = {path.name for path in tmp_path.iterdir()}

    assert chunks
    assert any(name.endswith("_raw.html") for name in artifact_names)
    assert any(name.endswith("_parsed.txt") for name in artifact_names)


def test_load_html_with_artifacts_uses_crawl_link_markdown_cleanup() -> None:
    loaded = load_html_with_artifacts(
        """
        <html>
          <head><title>VF 8 | VinFast</title></head>
          <body>
            <nav>Menu noise</nav>
            <main>
              <h1>VF 8</h1>
              <p>Dong SUV dien voi noi dung mo ta du dai cho RAG.</p>
              <h2>Thong so</h2>
              <p>Kich thuoc</p>
              <p>4545</p>
              <p>1890</p>
              <div role="tabpanel" hidden>
                <h3>Pin va sac</h3>
                <p>Thong tin pin trong tab an van duoc giu lai.</p>
              </div>
              <h4>Cookie Policy</h4>
              <p>Cookie consent noise should be removed.</p>
              <p>Support</p>
              <p>Hotline 1900 0000</p>
              <h2>Dang ky tu van</h2>
              <p>Nhan thong tin chinh thuc tu VinFast.</p>
            </main>
          </body>
        </html>
        """,
        source="https://example.edu/vf8",
        source_url="https://example.edu/vf8",
    )

    assert loaded.markdown.startswith("# VF 8")
    assert "Kich thuoc: 4545 / 1890" in loaded.markdown
    assert "### Pin va sac" in loaded.markdown
    assert "Thong tin pin trong tab an van duoc giu lai." in loaded.markdown
    assert "Menu noise" not in loaded.markdown
    assert "Cookie consent noise" not in loaded.markdown
    assert "Support" not in loaded.markdown
    assert "Hotline" not in loaded.markdown
    assert "Dang ky tu van" not in loaded.markdown
    assert loaded.chunks
    assert "parser" not in loaded.chunks[0].metadata


def test_load_html_chunks_uses_metadata_and_image_alt_for_title_only_pages() -> None:
    loaded = load_html_with_artifacts(
        """
        <html lang="vi">
          <head>
            <title>About VinFast</title>
            <meta
              name="description"
              content="VinFast is a Vietnamese EV brand with global manufacturing ambitions."
            />
          </head>
          <body>
            <main>
              <h1>About VinFast</h1>
              <img
                src="/factory.jpg"
                alt="VinFast Hai Phong factory supports electric vehicle production."
              />
              <img
                src="/timeline.jpg"
                alt="VinFast grows from Vietnam to global EV markets with VF 8 and VF 9."
              />
              <img src="/logo.png" alt="VinFast" />
            </main>
          </body>
        </html>
        """,
        source="https://vinfastauto.com/vn_vi/ve-chung-toi",
        source_url="https://vinfastauto.com/vn_vi/ve-chung-toi",
    )

    assert loaded.chunks
    assert "## Page Summary" in loaded.markdown
    assert "## Visual Content" in loaded.markdown
    assert "Vietnamese EV brand" in loaded.markdown
    assert "Hai Phong factory" in loaded.markdown
    assert "VF 8 and VF 9" in loaded.markdown
    assert "- VinFast\n" not in loaded.markdown


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
              <p>Stored content with enough detail for artifact chunk review.</p>
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
    source_html_path = run_dir / "source.html"
    cleaned_html_path = run_dir / "cleaned.html"
    parsed_sections_path = run_dir / "parsed_sections.txt"
    extracted_markdown_path = run_dir / "extracted.md"
    quality_path = run_dir / "quality.json"

    assert markdown_path.read_text(encoding="utf-8") == (
        "# Overview\n\nStored content with enough detail for artifact chunk review.\n"
    )
    assert "Stored content with enough detail" in source_html_path.read_text(encoding="utf-8")
    cleaned_html = cleaned_html_path.read_text(encoding="utf-8")
    assert '<body data-artifact-stage="cleaned_html">' in cleaned_html
    assert "<h1>Overview</h1>" in cleaned_html
    assert "<p>Stored content with enough detail for artifact chunk review.</p>" in cleaned_html
    assert "Stored content with enough detail" in parsed_sections_path.read_text(encoding="utf-8")
    assert "Stored content with enough detail" in extracted_markdown_path.read_text(
        encoding="utf-8"
    )
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    assert quality["chunk_count"] == len(chunks)
    assert quality["url_quality"]["verdict"] in {"useful", "low_signal"}

    chunk_lines = chunks_path.read_text(encoding="utf-8").splitlines()
    assert len(chunk_lines) == len(chunks)
    assert json.loads(chunk_lines[0])["chunk_id"] == chunks[0].chunk_id

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifact_schema_version"] == 2
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
    assert manifest["parser"] == "crawl-link-dom-markdown+normalizer"
    assert manifest["run_id"] == "sample_run"
    assert manifest["source_html_stage"] == "static_html"
    assert manifest["source_html_path"].endswith("/source.html")
    assert manifest["cleaned_html_path"].endswith("/cleaned.html")
    assert manifest["parsed_sections_path"].endswith("/parsed_sections.txt")
    assert manifest["extracted_markdown_path"].endswith("/extracted.md")
    assert manifest["quality_path"].endswith("/quality.json")
    assert manifest["markdown_path"].endswith("/parsed.md")
    assert manifest["chunks_path"].endswith("/chunks.jsonl")
    assert manifest["manifest_path"].endswith("/manifest.json")
    assert manifest["stage_paths"]["source_html"].endswith("/source.html")
    assert manifest["stage_paths"]["cleaned_html"].endswith("/cleaned.html")
    assert manifest["stage_paths"]["parsed_sections"].endswith("/parsed_sections.txt")
    assert manifest["stage_paths"]["extracted_markdown"].endswith("/extracted.md")
    assert manifest["stage_paths"]["cleaned_markdown"].endswith("/parsed.md")
    assert manifest["stage_paths"]["quality"].endswith("/quality.json")
    assert manifest["stage_paths"]["chunks"].endswith("/chunks.jsonl")
    assert manifest["chunk_count"] == len(chunks)


def test_load_html_with_artifacts_returns_markdown_and_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    loaded = load_html_with_artifacts(
        "<html><head><title>Artifact Page</title></head>"
        "<body><main><h1>Intro</h1>"
        "<p>Artifact content with enough detail for chunk review.</p></main></body></html>",
        source="https://example.edu/artifact",
        source_url="https://example.edu/artifact",
        data_artifact_dir=tmp_path,
        run_id="artifact-run",
    )

    assert loaded.markdown == "# Intro\n\nArtifact content with enough detail for chunk review."
    assert len(loaded.chunks) == 1
    assert loaded.chunks[0].text == (
        "# Intro\n\nArtifact content with enough detail for chunk review."
    )
    assert loaded.artifacts is not None
    assert loaded.artifacts.markdown_path.read_text(encoding="utf-8") == f"{loaded.markdown}\n"
    assert loaded.artifacts.chunks_path.exists()
    assert loaded.artifacts.source_html_path is not None
    assert loaded.artifacts.source_html_path.exists()
    assert loaded.artifacts.cleaned_html_path is not None
    assert loaded.artifacts.cleaned_html_path.exists()
    assert "<h1>Intro</h1>" in loaded.artifacts.cleaned_html_path.read_text(encoding="utf-8")
    assert loaded.artifacts.parsed_sections_path is not None
    assert loaded.artifacts.parsed_sections_path.exists()
    assert loaded.artifacts.extracted_markdown_path is not None
    assert loaded.artifacts.extracted_markdown_path.exists()
    assert loaded.artifacts.quality_path is not None
    assert loaded.artifacts.quality_path.exists()


def test_loaded_url_document_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        LoadedUrlDocument.model_validate(
            {
                "markdown": "# Intro",
                "chunks": [],
                "artifacts": None,
                "unexpected": True,
            }
        )


def test_load_html_chunks_prefers_crawl_link_dom_markdown_for_artifacts(
    tmp_path: Path,
) -> None:
    load_html_chunks(
        "<html><body><h1>Raw</h1><p>Raw content.</p><footer>Footer noise</footer></body></html>",
        source="https://example.edu/article",
        source_url="https://example.edu/article",
        data_artifact_dir=tmp_path,
        run_id="dom_run",
    )

    run_dirs = list((tmp_path / "artifacts").glob("*/dom-run"))
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "parsed.md").read_text(encoding="utf-8") == "# Raw\n\nRaw content.\n"

    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["parser"] == "crawl-link-dom-markdown+normalizer"


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
    monkeypatch.setattr(
        loader_module,
        "extract_markdown_with_playwright",
        lambda *_: (_ for _ in ()).throw(RuntimeError("browser disabled")),
    )

    def fake_fetch_url(url: str) -> loader_module._FetchedPage:
        assert url == "https://example.edu"
        return loader_module._FetchedPage(
            html=(
                "<html><body><h1>Overview</h1>"
                "<p>Fetched content with enough detail for chunk review.</p></body></html>"
            ),
            url="https://example.edu/final",
        )

    monkeypatch.setattr(loader_module, "_fetch_url", fake_fetch_url)

    chunks = load_url_chunks("https://example.edu")

    assert len(chunks) == 1
    assert chunks[0].text == "# Overview\n\nFetched content with enough detail for chunk review."
    assert chunks[0].metadata["source"] == "https://example.edu/final"
    assert chunks[0].metadata["url"] == "https://example.edu/final"
    assert chunks[0].metadata["domain"] == "example.edu"
    assert chunks[0].metadata["original_url"] == "https://example.edu"
    assert "final_url" not in chunks[0].metadata
    assert chunks[0].metadata["section"] == "Overview"
    assert chunks[0].metadata["section_path"] == ["Overview"]


def test_load_url_chunks_prefers_rendered_output_for_dynamic_product_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_render_options: dict[str, object] = {}

    def fake_fetch_url(url: str) -> loader_module._FetchedPage:
        assert url == "https://shop.vinfastauto.com/vn_vi/VF8.html"
        return loader_module._FetchedPage(
            html=(
                "<html><head><title>VF 8</title>"
                '<script id="__NEXT_DATA__">{}</script></head>'
                '<body><div id="__next"></div></body></html>'
            ),
            url=url,
        )

    def fake_render(url: str, **kwargs: object) -> ExtractedMarkdown:
        assert url == "https://shop.vinfastauto.com/vn_vi/VF8.html"
        captured_render_options.update(kwargs)
        return ExtractedMarkdown(
            markdown=(
                "# VF 8\n\n"
                "Gia 849.000.000 VND cho mau SUV dien voi noi dung mo ta chinh thuc "
                "du dai de nguoi dung hieu diem manh san pham.\n\n"
                "## Thong so\n\n"
                "Range 480 km.\n\n"
                "5 seats.\n\n"
                "Khoang sang gam cao, khoang noi that rong, va cong nghe an toan "
                "ho tro hanh trinh hang ngay."
            ),
            parser_name="fake-rendered",
            title="VF 8",
            final_url=url,
            rendered_html=(
                '<html><body><main><article class="vehicle-card">'
                "<h1>VF 8</h1><p>Gia 849.000.000 VND</p>"
                "<p>Range 480 km</p><p>5 seats</p>"
                "</article></main></body></html>"
            ),
        )

    monkeypatch.setattr(loader_module, "_fetch_url", fake_fetch_url)
    monkeypatch.setattr(loader_module, "extract_markdown_with_playwright", fake_render)

    chunks = load_url_chunks("https://shop.vinfastauto.com/vn_vi/VF8.html")

    assert chunks
    assert "849.000.000 VND" in chunks[0].text
    metadata = chunks[0].metadata
    assert metadata["url_quality_gate"]["parser"] == "rendered"
    assert metadata["url_quality_gate"]["status"] == "accepted"
    assert metadata["url_quality_gate"]["latency_budget_seconds"] == 20
    assert metadata["page_type"] == "product_detail"
    assert metadata["document_type"] == "product_detail"
    assert metadata["url_status"] == "accepted"
    assert metadata["render_required"] is True
    assert metadata["entity_name"] == "VF 8"
    assert captured_render_options["timeout_seconds"] == 20
    assert captured_render_options["wait_until"] == "load"


def test_load_url_chunks_uses_browser_when_static_fetch_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_render_options: dict[str, object] = {}

    def fake_fetch_url(url: str) -> loader_module._FetchedPage:
        assert url == "https://vinfastauto.com/vn_vi/limo-green"
        raise RuntimeError("Failed to fetch URL https://vinfastauto.com/vn_vi/limo-green: HTTP 403")

    def fake_render(url: str, **kwargs: object) -> ExtractedMarkdown:
        assert url == "https://vinfastauto.com/vn_vi/limo-green"
        captured_render_options.update(kwargs)
        return ExtractedMarkdown(
            markdown=(
                "# Limo Green\n\n"
                "Limo Green la mau xe dich vu dien cua VinFast voi noi dung "
                "mo ta chinh thuc du dai cho ingestion.\n\n"
                "## Gia va thong so\n\n"
                "Gia 749.000.000 VND.\n\n"
                "Range 450 km va 7 seats."
            ),
            parser_name="fake-rendered",
            title="Limo Green",
            final_url=url,
            rendered_html=(
                '<html><body><main><article class="vehicle-card">'
                "<h1>Limo Green</h1><p>Gia 749.000.000 VND</p>"
                "<p>Range 450 km</p><p>7 seats</p>"
                "</article></main></body></html>"
            ),
        )

    monkeypatch.setattr(loader_module, "_fetch_url", fake_fetch_url)
    monkeypatch.setattr(loader_module, "extract_markdown_with_playwright", fake_render)

    chunks = load_url_chunks("https://vinfastauto.com/vn_vi/limo-green")

    assert chunks
    assert "Limo Green" in chunks[0].text
    gate = chunks[0].metadata["url_quality_gate"]
    assert gate["parser"] == "rendered"
    assert gate["page_type"] == "product_detail"
    assert "static_fetch_failed" in gate["browser_error"]
    assert captured_render_options["timeout_seconds"] == 20


def test_load_url_chunks_marks_dynamic_static_fallback_when_browser_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch_url(url: str) -> loader_module._FetchedPage:
        assert url == "https://shop.vinfastauto.com/vn_vi/VF8.html"
        return loader_module._FetchedPage(
            html=(
                "<html><head><title>Product Shell</title></head>"
                "<body><main><h1>Product Shell</h1>"
                "<p>This page is still loading and does not expose useful vehicle "
                "details yet.</p></main></body></html>"
            ),
            url=url,
        )

    monkeypatch.setattr(loader_module, "_fetch_url", fake_fetch_url)

    chunks = load_url_chunks(
        "https://shop.vinfastauto.com/vn_vi/VF8.html",
        use_browser_extractor=False,
    )

    assert chunks
    gate = chunks[0].metadata["url_quality_gate"]
    assert gate["parser"] == "static"
    assert gate["status"] == "rejected"
    assert gate["accepted"] is False
    assert gate["requires_rendered_parser"] is True
    assert "browser_extractor_disabled" in gate["reason"]


def test_load_url_chunks_rejects_non_http_url() -> None:
    with pytest.raises(ValueError, match="absolute http or https URL"):
        load_url_chunks("file:///tmp/example.html")


def test_load_url_chunks_rejects_direct_pdf_url() -> None:
    with pytest.raises(ValueError, match="PDF URL"):
        load_url_chunks("https://example.edu/file.pdf")


def test_load_url_chunks_rejects_pdf_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        loader_module,
        "extract_markdown_with_playwright",
        lambda *_: (_ for _ in ()).throw(RuntimeError("browser disabled")),
    )

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
