Follow-up về sample data cho phần URL/Text ingestion:

Mình nghĩ nên tách rõ `domain`, `source URL`, và `chunk metadata` để test ingestion thực tế hơn, đặc biệt với các website có nhiều page con như Vintech.

## Đề xuất cấu trúc sample data

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

## Source manifest

`sources.jsonl` nên là allowlist chính cho URL ingestion:

```json
{"source_id":"vintech_home","domain":"vintechvietnam.com","url":"https://vintechvietnam.com/","source_type":"url","group":"company_site","expected_focus":"homepage overview"}
{"source_id":"vintech_gioi_thieu","domain":"vintechvietnam.com","url":"https://vintechvietnam.com/gioi-thieu/","source_type":"url","group":"company_site","expected_focus":"company introduction"}
{"source_id":"vintech_thuong_hieu","domain":"vintechvietnam.com","url":"https://vintechvietnam.com/thuong-hieu/","source_type":"url","group":"company_site","expected_focus":"brands"}
{"source_id":"vintech_giai_phap","domain":"vintechvietnam.com","url":"https://vintechvietnam.com/giai-phap/","source_type":"url","group":"company_site","expected_focus":"solutions"}
{"source_id":"vintech_du_an","domain":"vintechvietnam.com","url":"https://vintechvietnam.com/du-an/","source_type":"url","group":"company_site","expected_focus":"projects"}
{"source_id":"vinfast_vf_mpv7","domain":"vinfastauto.com","url":"https://vinfastauto.com/vn_vi/dat-coc-xe-vf-mpv7","source_type":"url","group":"product_page","expected_focus":"vehicle specs and offer"}
```

## Metadata trong mỗi chunk

`source` nên là URL thật của page được ingest, không chỉ là domain root. Ví dụ chunk từ trang `giai-phap`:

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

## Vì sao nên include các URL con?

Homepage `https://vintechvietnam.com/` chỉ test được landing page và một số preview. Các page con như:

- `https://vintechvietnam.com/gioi-thieu/`
- `https://vintechvietnam.com/thuong-hieu/`
- `https://vintechvietnam.com/giai-phap/`
- `https://vintechvietnam.com/du-an/`

sẽ giúp test parser/chunker tốt hơn vì có layout, heading, nội dung dài/ngắn, duplicate menu/footer noise và section metadata khác nhau.

Recommendation: với mỗi domain, chọn 1 homepage + 3-5 page con quan trọng. Khi tạo chunk, giữ citation theo page URL thật để retrieval/generation trả nguồn chính xác hơn.
