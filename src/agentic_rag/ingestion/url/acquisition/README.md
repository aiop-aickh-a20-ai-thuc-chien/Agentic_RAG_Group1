# Acquisition

Target home for URL acquisition concerns.

Responsibilities:

- Validate HTTP and HTTPS URLs.
- Reject PDF URLs and PDF responses before URL parsing.
- Manage deterministic request headers and redirects.
- Expose fetched HTML, final URL, and content-type diagnostics.

Current code: `src/agentic_rag/ingestion/url/loader.py`.
