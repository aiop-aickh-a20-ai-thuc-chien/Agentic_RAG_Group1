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
from agentic_rag.ingestion.url.crawler import Crawl4AIPage


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
    assert [chunk.metadata["section"] for chunk in chunks] == ["Admissions", "Interview"]
    assert chunks[0].metadata["source_type"] == "url"
    assert chunks[0].metadata["url"] == "https://example.edu/admissions"
    assert chunks[0].metadata["title"] == "Admissions Page"
    assert chunks[0].metadata["chunking_method"] == "hierarchical-markdown-probe-aware-overlap"
    assert chunks[0].metadata["section_level"] == 1
    assert chunks[0].metadata["section_path"] == ["Admissions"]
    assert chunks[0].metadata["semantic_unit"] == "url_markdown_section_paragraph"
    assert "Applications require transcripts." in chunks[0].text
    assert "Home Login Pricing" not in chunks[0].text
    assert "tracking" not in chunks[0].text


def test_load_html_chunks_stores_search_aliases_in_metadata_not_text() -> None:
    chunks = load_html_chunks(
        """
        <html>
          <head><title>VinFast VF 9</title></head>
          <body>
            <main>
              <h1>VF 9</h1>
              <p>Thong tin xe VF 9.</p>
            </main>
          </body>
        </html>
        """,
        source="https://example.edu/vf9",
        source_url="https://example.edu/vf9",
    )

    assert len(chunks) == 1
    assert "Search aliases:" not in chunks[0].text
    assert "VF9" in chunks[0].metadata["search_aliases"]
    assert "VinFast VF 9" in chunks[0].metadata["search_aliases"]


def test_load_html_chunks_records_chunk_adjacency_for_split_sections() -> None:
    long_markdown = "# Long Section\n\n" + "\n\n".join(
        f"Paragraph {index} " + ("retrieval evidence " * 70) for index in range(12)
    )

    loaded = load_html_with_artifacts(
        "<html><head><title>Long Page</title></head><body><h1>Long Section</h1></body></html>",
        source="https://example.edu/long",
        source_url="https://example.edu/long",
        preferred_markdown=long_markdown,
    )

    assert len(loaded.chunks) > 1
    first_chunk = loaded.chunks[0]
    second_chunk = loaded.chunks[1]
    assert first_chunk.metadata["chunk_group_size"] == len(loaded.chunks)
    assert first_chunk.metadata["previous_chunk_id"] is None
    assert first_chunk.metadata["next_chunk_id"] == second_chunk.chunk_id
    assert first_chunk.metadata["continues_to_next"] is True
    assert second_chunk.metadata["previous_chunk_id"] == first_chunk.chunk_id
    assert second_chunk.metadata["is_continuation"] is True


def test_load_html_chunks_adds_image_references_to_related_chunks() -> None:
    chunks = load_html_chunks(
        """
        <html>
          <body>
            <main>
              <h1>VF 9 Exterior</h1>
              <p>VF 9 exterior image shows the vehicle body.</p>
              <a href="/vf9-detail">
                <img src="/vf9-exterior.jpg" alt="VF 9 exterior" title="VF 9 body image" />
              </a>
            </main>
          </body>
        </html>
        """,
        source="https://example.edu/vf9",
        source_url="https://example.edu/vf9",
    )

    assert len(chunks) == 1
    assert chunks[0].metadata["image_reference_count"] == 1
    assert chunks[0].metadata["image_references"] == [
        {
            "kind": "image",
            "url": "https://example.edu/vf9-exterior.jpg",
            "alt": "VF 9 exterior",
            "title": "VF 9 body image",
            "target_url": "https://example.edu/vf9-detail",
            "reference_reason": "alt_or_title_overlap",
        }
    ]


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

    assert loaded.markdown == "# Artifact Page\n\n# Intro\n\nArtifact content."
    assert len(loaded.chunks) == 1
    assert loaded.chunks[0].text == "# Intro\n\nArtifact content."
    assert loaded.artifacts is not None
    assert loaded.artifacts.markdown_path.read_text(encoding="utf-8").rstrip() == loaded.markdown
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

    load_html_chunks(
        "<html><body><h1>Raw</h1><p>Raw content.</p></body></html>",
        source="https://example.edu/article",
        source_url="https://example.edu/article",
        data_artifact_dir=tmp_path,
        run_id="trafilatura_run",
    )

    run_dirs = list((tmp_path / "artifacts").glob("*/trafilatura-run"))
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "parsed.md").read_text(encoding="utf-8") == (
        "# Clean Article\n\nClean extracted content.\n"
    )

    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["parser"] == "trafilatura-markdown+builtin-html-parser"


def test_load_html_with_artifacts_normalizes_vehicle_price_cards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    loaded = load_html_with_artifacts(
        "<html><head><title>Xe điện VinFast VF 9</title></head><body><h1>VF9</h1></body></html>",
        source="https://shop.example/vf9",
        source_url="https://shop.example/vf9",
        preferred_markdown=(
            "# Xe điện VinFast VF 9\n\n"
            "VF 9 Eco\n\n"
            "Giá bán từ\n\n"
            "1.229.180.000\n\n"
            "VNĐ\n\n"
            "1.499.000.000\n\n"
            "VNĐ\n\n"
            "VF 9 Plus\n\n"
            "Giá bán từ\n\n"
            "1.393.180.000\n\n"
            "VNĐ\n\n"
            "1.699.000.000\n\n"
            "VNĐ"
        ),
    )

    assert (
        "- VF 9 Eco: Giá bán từ 1.229.180.000 VNĐ; giá niêm yết cũ ~~1.499.000.000 VNĐ~~."
    ) in loaded.markdown
    assert (
        "- VF 9 Plus: Giá bán từ 1.393.180.000 VNĐ; giá niêm yết cũ ~~1.699.000.000 VNĐ~~."
    ) in loaded.markdown
    assert "~~1.499.000.000 VNĐ~~" in loaded.chunks[0].text
    assert "~~1.699.000.000 VNĐ~~" in loaded.chunks[0].text


def test_load_html_with_artifacts_normalizes_product_price_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    loaded = load_html_with_artifacts(
        "<html><head><title>Phu kien</title></head><body><h1>Products</h1></body></html>",
        source="https://shop.example/parts",
        source_url="https://shop.example/parts",
        preferred_markdown=(
            "### DANH MUC SAN PHAM\n\n"
            '[ Tham Cop 3D VF 6 990.000 VND  ](https://shop.example/p1.html "Tham Cop")\n'
            '[ VF 7 Tam Che Pin Cao Ap 6.881.001 VNĐ  ](https://shop.example/p2.html "Tam Che")'
        ),
    )

    assert (
        "- Tham Cop 3D VF 6: giá bán hiện tại / current price 990.000 VND. "
        "Link: https://shop.example/p1.html"
    ) in loaded.markdown
    assert (
        "- VF 7 Tam Che Pin Cao Ap: giá bán hiện tại / current price 6.881.001 VNĐ. "
        "Link: https://shop.example/p2.html"
    ) in loaded.markdown


def test_load_html_with_artifacts_prefers_cleaner_trafilatura_over_image_heavy_crawl4ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_extract_markdown_with_trafilatura(
        html: str,
        *,
        source_url: str | None,
    ) -> str:
        assert "Rendered shell" in html
        assert source_url == "https://example.edu/listing"
        return (
            "# VF 9 price summary\n\n"
            "VF 9 Plus current price 1.699.000.000 VND. "
            "VF 9 Eco current price 1.499.000.000 VND. "
            "Battery warranty and vehicle specification summary for review. "
            "The clean article text keeps model, edition, price, warranty, range, "
            "charging, safety, and technical specification terms without gallery images."
        )

    monkeypatch.setattr(
        loader_module,
        "extract_markdown_with_trafilatura",
        fake_extract_markdown_with_trafilatura,
    )
    image_spam = "\n".join(
        f"![VF 9](https://example.edu/vf9-{index}.png) VF 9 {index}" for index in range(35)
    )

    loaded = load_html_with_artifacts(
        "<html><body><h1>Rendered shell</h1><p>Loading.</p></body></html>",
        source="https://example.edu/listing",
        source_url="https://example.edu/listing",
        preferred_markdown=(
            "# Vehicle gallery\n\n"
            f"{image_spam}\n\n"
            "VF 9 Plus 1.699.000.000 VND\n\n"
            "VF 9 Eco 1.499.000.000 VND"
        ),
        preferred_parser="crawl4ai-markdown+builtin-html-parser",
    )

    assert loaded.chunks[0].metadata["parser"] == "trafilatura-markdown+builtin-html-parser"
    assert loaded.chunks[0].metadata["markdown_quality"]["fallback_reason"] == (
        "trafilatura_quality_check_selected_for_lower_noise"
    )
    candidates = loaded.chunks[0].metadata["markdown_quality"]["candidates"]
    assert any(candidate["image_count"] >= 35 for candidate in candidates)


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

    chunks = load_url_chunks("https://example.edu")

    assert len(chunks) == 1
    assert chunks[0].text == "# Overview\n\nFetched content."
    assert chunks[0].metadata["source"] == "https://example.edu/final"
    assert chunks[0].metadata["url"] == "https://example.edu/final"
    assert chunks[0].metadata["original_url"] == "https://example.edu"
    assert chunks[0].metadata["final_url"] == "https://example.edu/final"
    assert chunks[0].metadata["section"] == "Overview"
    assert chunks[0].metadata["section_path"] == ["Overview"]


def test_load_url_chunks_prefers_crawl4ai_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_crawl_url_with_crawl4ai(url: str) -> Crawl4AIPage:
        assert url == "https://example.edu/dynamic"
        return Crawl4AIPage(
            html="<html><body><h1>Server Shell</h1><p>Hydrated later.</p></body></html>",
            markdown="# Rendered Product\n\n## Card A\n\nDynamic card content.",
            url="https://example.edu/dynamic",
            links=(),
        )

    monkeypatch.setattr(loader_module, "crawl_url_with_crawl4ai", fake_crawl_url_with_crawl4ai)

    chunks = load_url_chunks("https://example.edu/dynamic")

    assert len(chunks) == 1
    assert chunks[0].text == "## Card A\n\nDynamic card content."
    assert chunks[0].metadata["section_path"] == ["Rendered Product", "Card A"]
    assert chunks[0].metadata["crawler"] == "crawl4ai"
    assert chunks[0].metadata["parser"] == "crawl4ai-markdown+builtin-html-parser"
    assert chunks[0].metadata["markdown_quality"]["selected_role"] == "crawl4ai_primary"


def test_load_html_with_artifacts_uses_trafilatura_as_quality_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_extract_markdown_with_trafilatura(
        html: str,
        *,
        source_url: str | None,
    ) -> str:
        assert "Rendered shell" in html
        assert source_url == "https://example.edu/product"
        return (
            "# Product Specs\n\n"
            "This product page contains battery warranty, vehicle range, charging, "
            "price, edition, safety, and technical specification details for retrieval."
        )

    monkeypatch.setattr(
        loader_module,
        "extract_markdown_with_trafilatura",
        fake_extract_markdown_with_trafilatura,
    )

    loaded = load_html_with_artifacts(
        "<html><body><h1>Rendered shell</h1><p>Loading.</p></body></html>",
        source="https://example.edu/product",
        source_url="https://example.edu/product",
        preferred_markdown="Cookie Login Cart",
        preferred_parser="crawl4ai-markdown+builtin-html-parser",
    )

    assert loaded.chunks[0].metadata["parser"] == "trafilatura-markdown+builtin-html-parser"
    assert loaded.chunks[0].metadata["markdown_quality"]["selected_role"] == (
        "trafilatura_quality_check"
    )
    assert loaded.chunks[0].metadata["markdown_quality"]["fallback_reason"] == (
        "trafilatura_quality_check_selected_as_fallback"
    )


def test_load_html_with_artifacts_can_use_crawl4ai_bm25_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    loaded = load_html_with_artifacts(
        "<html><body><h1>Shell</h1><p>Loading.</p></body></html>",
        source="https://example.edu/vf9",
        source_url="https://example.edu/vf9",
        preferred_markdown="Loading",
        preferred_parser="crawl4ai-markdown+builtin-html-parser",
        bm25_markdown=(
            "# VF 9 price and specs\n\n"
            "VF 9 Eco price 1.499.000.000 VND with battery warranty and range details."
        ),
    )

    assert loaded.chunks[0].metadata["parser"] == "crawl4ai-bm25-markdown+builtin-html-parser"
    assert loaded.chunks[0].metadata["markdown_quality"]["selected_role"] == (
        "crawl4ai_bm25_filter"
    )
    assert loaded.chunks[0].metadata["markdown_quality"]["fallback_reason"] == (
        "crawl4ai_bm25_filter_selected_as_fallback"
    )


def test_load_html_with_artifacts_appends_structured_parse_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    loaded = load_html_with_artifacts(
        "<html><body><h1>VF 9</h1><p>Overview.</p></body></html>",
        source="https://example.edu/vf9",
        source_url="https://example.edu/vf9",
        preferred_markdown="# VF 9\n\nOverview.",
        preferred_parser="crawl4ai-markdown+builtin-html-parser",
        structured_markdown=(
            "# Structured Page Data\n\n"
            "## Table 1\n\n"
            "| Edition | Price |\n"
            "| --- | --- |\n"
            "| Eco | 1.499.000.000 VND |"
        ),
    )

    assert "Structured Page Data" in loaded.markdown
    structured_chunk = next(
        chunk for chunk in loaded.chunks if chunk.metadata["section"] == "Table 1"
    )
    assert structured_chunk.metadata["content_origin"] == "structured_parse"
    assert "1.499.000.000" in structured_chunk.text


def test_load_url_chunks_includes_interactive_probe_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_crawl_url_with_crawl4ai(url: str) -> Crawl4AIPage:
        assert (
            url
            == "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9"
        )
        return Crawl4AIPage(
            html=(
                "<html><body><h1>VF 9 Configurator</h1><p>Default visible state.</p></body></html>"
            ),
            markdown="# VF 9 Configurator\n\nDefault visible state.",
            url=url,
            links=(),
            probe_markdown=(
                "# Probed Interactive State\n\n"
                "## VinFast configurator price options\n\n"
                "### VF 9 Plus tuy chon 7 cho\n\n"
                "- Probe source: window.carDeposit.products.Products-Car-VF9.NE3MV.\n"
                "- Probe relation: this record represents one selectable configurator state.\n"
                "- VF 9 Plus tuy chon 7 cho: Gia xe kem pin 1.699.000.000 VND.\n"
                "- VF 9 Plus tuy chon 7 cho + Mau nang cao: Gia xe kem pin "
                "1.711.000.000 VND (mau nang cao + 12.000.000 VND).\n"
                "\n### VF 9 Eco\n\n"
                "- Probe source: window.carDeposit.products.Products-Car-VF9.NE3LV.\n"
                "- Probe relation: this record represents one selectable configurator state.\n"
                "- VF 9 Eco: Gia xe kem pin 1.499.000.000 VND.\n\n"
                "## VinFast configurator notes\n\n"
                "- Quang duong di chuyen duoc tinh toan dua tren ket qua kiem dinh NEDC."
            ),
        )

    monkeypatch.setattr(loader_module, "crawl_url_with_crawl4ai", fake_crawl_url_with_crawl4ai)

    loaded = loader_module.load_url_with_artifacts(
        "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9"
    )

    assert "Probed Interactive State" in loaded.markdown
    assert "1.699.000.000" in loaded.markdown
    assert "1.499.000.000" in loaded.markdown
    assert "12.000.000" in loaded.markdown
    assert "NEDC" in loaded.markdown
    assert any("1.699.000.000" in chunk.text for chunk in loaded.chunks)
    assert any("12.000.000" in chunk.text for chunk in loaded.chunks)
    vf9_plus_chunk = next(
        chunk for chunk in loaded.chunks if chunk.metadata["section"] == "VF 9 Plus tuy chon 7 cho"
    )
    notes_chunk = next(
        chunk
        for chunk in loaded.chunks
        if chunk.metadata["section"] == "VinFast configurator notes"
    )
    assert vf9_plus_chunk.metadata["content_origin"] == "interactive_probe"
    assert vf9_plus_chunk.metadata["probe_state_label"] == "VF 9 Plus tuy chon 7 cho"
    assert "interactive-probe" in vf9_plus_chunk.metadata["parser"]
    assert notes_chunk.metadata["content_origin"] == "interactive_probe"
    question_citations = {
        "VF 9 Plus tuy chon 7 cho co gia xe kem pin bao nhieu?": _chunk_id_with_terms(
            loaded.chunks,
            ("VF 9 Plus tuy chon 7 cho", "1.699.000.000"),
        ),
        "VF 9 Eco co gia xe kem pin bao nhieu?": _chunk_id_with_terms(
            loaded.chunks,
            ("VF 9 Eco", "1.499.000.000"),
        ),
        "Mau nang cao cong them bao nhieu tien?": _chunk_id_with_terms(
            loaded.chunks,
            ("Mau nang cao", "12.000.000"),
        ),
        "Quang duong di chuyen duoc tinh theo quy chuan nao?": _chunk_id_with_terms(
            loaded.chunks,
            ("NEDC",),
        ),
    }
    assert all(question_citations.values())
    assert (
        question_citations["VF 9 Plus tuy chon 7 cho co gia xe kem pin bao nhieu?"]
        == vf9_plus_chunk.chunk_id
    )
    assert (
        question_citations["Quang duong di chuyen duoc tinh theo quy chuan nao?"]
        == notes_chunk.chunk_id
    )


def test_load_url_chunks_falls_back_to_urllib_when_crawl4ai_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_crawl_url_with_crawl4ai(url: str) -> Crawl4AIPage:
        raise RuntimeError("browser is unavailable")

    def fake_fetch_url_urllib(
        url: str,
        *,
        crawler_error: str | None = None,
    ) -> loader_module._FetchedPage:
        assert url == "https://example.edu/static"
        assert crawler_error == (
            "RuntimeError: browser is unavailable; trafilatura fetch failed: RuntimeError: "
            "trafilatura returned empty HTML"
        )
        return loader_module._FetchedPage(
            html="<html><body><h1>Static</h1><p>Fallback content.</p></body></html>",
            url="https://example.edu/static",
            crawler="urllib",
            crawler_error=crawler_error,
        )

    monkeypatch.setattr(loader_module, "crawl_url_with_crawl4ai", fake_crawl_url_with_crawl4ai)
    monkeypatch.setattr(loader_module, "fetch_html_with_trafilatura", lambda _: None)
    monkeypatch.setattr(loader_module, "_fetch_url_urllib", fake_fetch_url_urllib)

    chunks = load_url_chunks("https://example.edu/static")

    assert len(chunks) == 1
    assert chunks[0].text == "# Static\n\nFallback content."
    assert chunks[0].metadata["crawler"] == "urllib"
    assert chunks[0].metadata["crawler_error"] == (
        "RuntimeError: browser is unavailable; trafilatura fetch failed: RuntimeError: "
        "trafilatura returned empty HTML"
    )


def test_load_url_chunks_uses_trafilatura_fetch_before_urllib_when_crawl4ai_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_crawl_url_with_crawl4ai(url: str) -> Crawl4AIPage:
        raise RuntimeError("browser is unavailable")

    def fake_fetch_html_with_trafilatura(url: str) -> str:
        assert url == "https://example.edu/article"
        return (
            "<html><head><title>Article</title></head>"
            "<body><main><h1>Article</h1><p>Fetched by trafilatura.</p></main></body></html>"
        )

    monkeypatch.setattr(loader_module, "crawl_url_with_crawl4ai", fake_crawl_url_with_crawl4ai)
    monkeypatch.setattr(
        loader_module,
        "fetch_html_with_trafilatura",
        fake_fetch_html_with_trafilatura,
    )
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    chunks = load_url_chunks("https://example.edu/article")

    assert len(chunks) == 1
    assert chunks[0].text == "# Article\n\nFetched by trafilatura."
    assert chunks[0].metadata["crawler"] == "trafilatura"
    assert chunks[0].metadata["crawler_error"] == "RuntimeError: browser is unavailable"


def test_load_url_chunks_uses_trafilatura_when_crawl4ai_returns_title_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_crawl_url_with_crawl4ai(url: str) -> Crawl4AIPage:
        assert url == "https://example.edu/title-only"
        return Crawl4AIPage(
            html="<html><head><title>Title Only</title></head></html>",
            markdown=None,
            url=url,
            links=(),
        )

    def fake_fetch_html_with_trafilatura(url: str) -> str:
        assert url == "https://example.edu/title-only"
        return (
            "<html><head><title>Title Only</title></head>"
            "<body><main><h1>Recovered Body</h1><p>Recovered evidence.</p></main></body></html>"
        )

    monkeypatch.setattr(loader_module, "crawl_url_with_crawl4ai", fake_crawl_url_with_crawl4ai)
    monkeypatch.setattr(
        loader_module,
        "fetch_html_with_trafilatura",
        fake_fetch_html_with_trafilatura,
    )
    monkeypatch.setattr(loader_module, "extract_markdown_with_trafilatura", lambda *_, **__: None)

    chunks = load_url_chunks("https://example.edu/title-only")

    assert len(chunks) == 1
    assert "Recovered evidence." in chunks[0].text
    assert chunks[0].metadata["crawler"] == "trafilatura"
    assert chunks[0].metadata["crawler_error"] == "Crawl4AI returned title-only content"


def test_load_url_chunks_can_crawl_child_pages_and_dedupe_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_crawl_url_with_crawl4ai(url: str) -> Crawl4AIPage:
        if url == "https://example.edu/products":
            return Crawl4AIPage(
                html="<html><body><h1>Products</h1></body></html>",
                markdown="# Products\n\nShared product card.",
                url=url,
                links=("https://example.edu/products/card-a", "https://other.edu/out"),
            )
        return Crawl4AIPage(
            html="<html><body><h1>Products</h1></body></html>",
            markdown="# Products\n\nShared product card.",
            url=url,
            links=(),
        )

    monkeypatch.setattr(loader_module, "crawl_url_with_crawl4ai", fake_crawl_url_with_crawl4ai)

    chunks = load_url_chunks("https://example.edu/products", max_child_pages=1)

    assert len(chunks) == 1
    assert chunks[0].metadata["source"] == "https://example.edu/products"


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


def _chunk_id_with_terms(chunks: list[Chunk], terms: tuple[str, ...]) -> str | None:
    for chunk in chunks:
        text = chunk.text.lower()
        if all(term.lower() in text for term in terms):
            return chunk.chunk_id
    return None
