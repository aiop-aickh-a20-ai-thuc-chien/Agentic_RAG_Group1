from agentic_rag.ingestion.url.parser import ParsedHtml, Section, parse_html


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

    assert parsed == ParsedHtml(
        title="Example Page",
        sections=(
            Section(heading="Overview", text="Overview Main content."),
            Section(heading="Details", text="Details Detailed content."),
        ),
    )
    assert all("navigation" not in section.text for section in parsed.sections)
    assert all("Related links" not in section.text for section in parsed.sections)


def test_parse_html_uses_main_section_without_headings() -> None:
    parsed = parse_html("<html><body><p>Plain page content.</p></body></html>")

    assert parsed.sections == (Section(heading="main", text="Plain page content."),)
