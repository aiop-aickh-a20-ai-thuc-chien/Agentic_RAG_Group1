# URL Sample Data Structure

Recommended sample data should separate domains, source pages, and generated chunks.

## Concepts

- `domain`: website root used for grouping and crawl policy.
- `source`: one ingested document/page. For URL ingestion, this should be the final canonical page URL.
- `url`: original/final page URL stored in each chunk metadata for citation.
- `chunk`: normalized text segment generated from one source page.

## Recommended Layout

```text
data/samples/url/
  sources.jsonl
  vintechvietnam.com/
    homepage.md
    gioi-thieu.md
    thuong-hieu.md
    giai-phap.md
    du-an.md
  vinfastauto.com/
    vf-mpv7.md
```

## Source Manifest

Use `sources.jsonl` as the source-of-truth allowlist:

```json
{"source_id":"vintech_home","domain":"vintechvietnam.com","url":"https://vintechvietnam.com/","source_type":"url","group":"company_site","expected_focus":"homepage overview"}
{"source_id":"vintech_gioi_thieu","domain":"vintechvietnam.com","url":"https://vintechvietnam.com/gioi-thieu/","source_type":"url","group":"company_site","expected_focus":"company introduction"}
{"source_id":"vintech_thuong_hieu","domain":"vintechvietnam.com","url":"https://vintechvietnam.com/thuong-hieu/","source_type":"url","group":"company_site","expected_focus":"brands"}
{"source_id":"vintech_giai_phap","domain":"vintechvietnam.com","url":"https://vintechvietnam.com/giai-phap/","source_type":"url","group":"company_site","expected_focus":"solutions"}
{"source_id":"vintech_du_an","domain":"vintechvietnam.com","url":"https://vintechvietnam.com/du-an/","source_type":"url","group":"company_site","expected_focus":"projects"}
{"source_id":"vinfast_vf_mpv7","domain":"vinfastauto.com","url":"https://vinfastauto.com/vn_vi/dat-coc-xe-vf-mpv7","source_type":"url","group":"product_page","expected_focus":"vehicle specs and offer"}
```

## Chunk Metadata

Each chunk should keep page-level source metadata:

```json
{
  "source": "https://vintechvietnam.com/giai-phap/",
  "source_type": "url",
  "file_name": null,
  "url": "https://vintechvietnam.com/giai-phap/",
  "page": null,
  "section": "Giải pháp tổng đài IP",
  "domain": "vintechvietnam.com",
  "source_id": "vintech_giai_phap",
  "title": "Vintech Việt Nam",
  "content_hash": "...",
  "chunk_index": 1
}
```

## Recommendation

For sample tests, include more than the homepage when a domain has important child pages. The
homepage often contains only previews, while child pages reveal real parser behavior, duplicated
navigation/footer noise, section headings, and chunk quality.
