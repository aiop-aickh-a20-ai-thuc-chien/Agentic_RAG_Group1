from agentic_rag.ingestion.url.parser import Asset, parse_html


def test_parse_html_extracts_title_sections_and_removes_noise() -> None:
    parsed = parse_html(
        """
        <html>
          <head><title>Example Page</title></head>
          <body>
            <header>Top navigation</header>
            <main>
              <h1>Overview</h1>
              <p>Main content.</p>
              <h2>Details</h2>
              <p>Detailed content.</p>
            </main>
            <aside>Related links</aside>
          </body>
        </html>
        """
    )

    assert parsed.title == "Example Page"
    section_summaries = [
        (section.heading, section.text, section.heading_level, section.markdown)
        for section in parsed.sections
    ]
    assert section_summaries == [
        ("Overview", "Overview Main content.", 1, "# Overview\n\nMain content."),
        ("Details", "Details Detailed content.", 2, "## Details\n\nDetailed content."),
    ]
    assert all("navigation" not in section.text for section in parsed.sections)
    assert all("Related links" not in section.text for section in parsed.sections)


def test_parse_html_uses_main_section_without_headings() -> None:
    parsed = parse_html("<html><body><p>Plain page content.</p></body></html>")

    assert len(parsed.sections) == 1
    assert parsed.sections[0].heading == "main"
    assert parsed.sections[0].text == "Plain page content."
    assert parsed.sections[0].markdown == "Plain page content."


def test_parse_html_preserves_markdown_lists_and_strong_text() -> None:
    parsed = parse_html(
        """
        <html>
          <body>
            <h1>Parent</h1>
            <p><strong>Important</strong> overview.</p>
            <h2>Child</h2>
            <ul>
              <li>First benefit</li>
              <li><strong>Second</strong> benefit</li>
            </ul>
          </body>
        </html>
        """
    )

    assert parsed.sections[0].heading == "Parent"
    assert parsed.sections[0].heading_level == 1
    assert parsed.sections[0].markdown == "# Parent\n\n**Important** overview."
    assert parsed.sections[1].heading == "Child"
    assert parsed.sections[1].heading_level == 2
    assert parsed.sections[1].markdown == ("## Child\n\n- First benefit\n\n- **Second** benefit")


def test_parse_html_marks_duplicate_and_conflicting_section_evidence() -> None:
    parsed = parse_html(
        """
        <html>
          <body>
            <h1>Pricing</h1>
            <p>VF 9 Eco: giÃ¡ bÃ¡n 1.229.180.000 VNÄ</p>
            <p>VF 9 Eco: giÃ¡ bÃ¡n 1.499.000.000 VNÄ</p>
            <p>VinFast electric vehicle battery warranty policy lasts 10 years</p>
            <p>VinFast electric vehicle battery warranty policy lasts 10 years</p>
          </body>
        </html>
        """
    )

    diagnostics = parsed.sections[0].evidence_diagnostics

    assert diagnostics["has_duplicate_evidence"] is True
    assert diagnostics["has_possible_conflict"] is True


def test_parse_html_strips_utm_banners_and_promotes_anchor_sections() -> None:
    parsed = parse_html(
        """
        <html>
          <body>
            <main>
              <h1>VinFast</h1>
              <a href="/promo?utm_source=banner"><p>Promotional campaign noise</p></a>
              <a id="dong_co_dien_content"></a>
              <p>D-SUV electric vehicle details.</p>
            </main>
          </body>
        </html>
        """,
        base_url="https://vinfastauto.com/vn_vi",
    )

    markdown = "\n\n".join(section.markdown or "" for section in parsed.sections)

    assert "Promotional campaign noise" not in markdown
    assert any(section.heading == "O to dien" for section in parsed.sections)
    assert "D-SUV electric vehicle details." in markdown


def test_parse_html_extracts_canonical_open_graph_and_article_metadata() -> None:
    parsed = parse_html(
        """
        <html lang="vi">
          <head>
            <link rel="canonical" href="/canonical-page" />
            <meta property="og:url" content="/og-page" />
            <meta property="og:title" content="OG Title" />
            <meta property="og:description" content="OG description." />
            <meta name="description" content="Meta description." />
            <meta name="author" content="Editorial Team" />
            <meta property="article:published_time" content="2026-06-01T00:00:00+07:00" />
          </head>
          <body><h1>Article</h1><p>Content.</p></body>
        </html>
        """,
        base_url="https://example.edu/root/",
    )

    assert parsed.metadata.language == "vi"
    assert parsed.metadata.canonical_url == "https://example.edu/canonical-page"
    assert parsed.metadata.og_url == "https://example.edu/og-page"
    assert parsed.metadata.og_title == "OG Title"
    assert parsed.metadata.og_description == "OG description."
    assert parsed.metadata.description == "Meta description."
    assert parsed.metadata.author == "Editorial Team"
    assert parsed.metadata.published_at == "2026-06-01T00:00:00+07:00"


def test_parse_html_discovers_related_assets() -> None:
    parsed = parse_html(
        """
        <html>
          <body>
            <a href="/product">
              <img src="/image.jpg" alt="Product photo" title="Main product" />
            </a>
            <a href="/brochure.pdf" title="Brochure">Download</a>
            <iframe src="/embed"></iframe>
            <object data="/catalog.pdf"></object>
          </body>
        </html>
        """,
        base_url="https://example.edu/shop/",
    )

    assert parsed.assets == (
        Asset(
            kind="image",
            url="https://example.edu/image.jpg",
            alt="Product photo",
            title="Main product",
            target_url="https://example.edu/product",
        ),
        Asset(kind="pdf", url="https://example.edu/brochure.pdf", title="Brochure"),
        Asset(kind="iframe", url="https://example.edu/embed"),
        Asset(kind="object", url="https://example.edu/catalog.pdf"),
    )
