# Metadata

Target home for URL-specific metadata enrichment.

Responsibilities:

- Attach source URL, final URL, canonical URL, title, language, and section path.
- Add DOM path and entity metadata once DOM-aware chunking exists.
- Add stable content, DOM, and entity hashes after tests define stability.

URL-specific fields should stay inside `Chunk.metadata`.
