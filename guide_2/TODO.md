# TODO: URL Ingestion Evaluation Follow-up

Source evaluation:
`guide_2/demo/verify_ingestion/output/evaluation_report.md`

Tested URL:
`https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9`

Ground truth:
`guide_2/ground_truth/https-shop-vinfastauto-com-vn-vi-dat-coc-o-to-dien-vinfast-html-modelid-products-car-VF9/vf9_ground_truth.md`

Current score: **3/10**

## Evaluation Summary

- Actual output is incomplete for the target VF 9 page.
- Output mixes VF 9 with unrelated VinFast models such as VF 3, VF 5, and VF 6.
- Important structured data is missing: edition pricing, color options, deposit amount,
  CTA URL, warranty details, and product-specific sections.
- Output structure is weak: missing headings, missing tables, and poor separation of
  product details.
- Boilerplate and irrelevant promotional/service content still leaks into the parsed
  Markdown.

## Priority 1: Preserve VF 9 Product-Specific Content

- [x] Ensure the selected URL query parameter `modelId=Products-Car-VF9` is preserved
  through fetch, render, and interaction capture.
- [ ] Add a regression fixture for the VF 9 deposit page that asserts the parsed
  Markdown contains only VF 9-focused product data.
- [ ] Extract and preserve the VF 9 tagline and summary content.
- [ ] Extract and preserve VF 9 warranty information.
- [x] Extract and preserve VF 9 Eco and Plus edition prices.
- [x] Extract and preserve the deposit amount from model-scoped network payloads.
- [x] Append promoted interaction chunks into the main verifier output or merged
  parsed Markdown so LLM evaluation sees `deposit_amount=50.000.000 VND`.
- [ ] Extract and preserve the CTA URL for placing a deposit.

## Priority 2: Restore Structured Tables

- [x] Convert edition pricing into a stable Markdown table.
- [ ] Convert exterior color options into a stable Markdown table.
- [ ] Convert interior color options into a stable Markdown table.
- [ ] Preserve color names, color codes, and option pricing.
- [x] Add structure-aware parser tests for DOM product/table blocks and generated
  structure metadata.
- [ ] Add parser tests that compare expected VF 9 table headers and required rows.

## Priority 3: Reduce Cross-Model Noise

- [x] Detect when a VinFast page is scoped to a single selected model.
- [x] Filter or demote unrelated model cards and specifications when a selected model
  is present.
- [x] Add a metadata flag for selected model context, such as
  `selected_product_model=VF 9`.
- [ ] Add a retrieval/debug-only flag for non-selected model content captured from
  shared product navigation.
- [ ] Add tests proving VF 3, VF 5, VF 6, and other unrelated model facts are excluded
  from the VF 9 parsed Markdown.
- [ ] Ensure `url-ingestion/chunks.jsonl` no longer assigns primary
  `product_model` values such as `VF 3`, `VF 7`, or `VF 8 PLUS` for a
  `Products-Car-VF9` run.

## Priority 4: Improve DOM and Interaction Extraction

- [ ] Inspect generated artifacts:
  `guide_2/demo/verify_ingestion/output/ingestion_artifacts`.
- [x] Compare `source.html`, `parsed_sections.txt`, `interaction_states.json`, and
  `network_payloads.jsonl` to locate where VF 9 details exist before cleanup.
- [x] Prefer structured product state from interaction/network artifacts when static
  Markdown extraction loses model-specific fields.
- [x] Add a structure-aware DOM mapper that turns semantic DOM blocks into generated
  Markdown sections before chunking.
- [x] Attach structure-aware chunk metadata:
  `section_origin`, `structure_aware`, `structure_block_types`,
  `structure_block_ids`, and `structure_dedupe_hashes`.
- [x] Add a product-detail mapper that turns captured interaction/network state into
  promoted dynamic product chunks.
- [x] Merge promoted dynamic product chunks from `url-ingestion-interactions` into
  the primary `LoadedUrlDocument.markdown` or verification report input.
- [x] Integrate optional Crawlee/Apify Playwright rendering for ill-structured
  dynamic pages before falling back to the direct Playwright extractor.
- [x] Add Crawlee sleep/retry settling that recounts `timeout_seconds` when a
  timeout is provided and allows an explicit unbounded wait mode with
  `timeout_seconds=None`.
- [ ] Keep interaction/debug artifacts out of retrieval unless they are promoted into
  clean product facts.

## Priority 5: Boilerplate and Relevance Filtering

- [ ] Expand URL cleanup rules for VinFast navigation, generic model listings,
  promotions, support text, and unrelated services.
- [ ] Keep legitimate product CTAs while removing repeated global CTAs.
- [ ] Add a quality check that fails when the parsed page contains too many unrelated
  model names.
- [ ] Add a quality check that fails when required VF 9 fields are absent.

## Priority 6: Evaluation Workflow

- [x] Rerun `guide_2/verify_ingestion.py` after each extraction change.
- [x] Track score changes in this TODO with date, score, and short notes.
- [ ] Keep generated output under `guide_2/demo/verify_ingestion/output` for local
  review only unless intentionally committed.

## Score Log

- [ ] 2026-06-19: Initial verifier run scored **3/10**. Main failures:
  incomplete VF 9 details, cross-model contamination, missing tables, weak structure,
  and boilerplate leakage.
- [x] 2026-06-19: Implemented first structure-aware URL ingestion pass. DOM semantic
  blocks now append generated Markdown sections with dedupe hashes before chunking,
  and generated chunks carry structure metadata for downstream filtering/dedup.
- [x] 2026-06-19: Promoted model-scoped deposit network payloads. The
  `CarsDeposit-BankInfo` payload with `modelID=Products-Car-VF9` now produces a
  normal dynamic chunk with `selected_product_model=VF 9` and
  `deposit_amount=50.000.000 VND`.
- [ ] 2026-06-19 rerun: Verifier score remains **3/10**. Interaction artifacts now
  contain 2 chunks, including 1 normal promoted VF 9 deposit chunk, but
  `url-ingestion/chunks.jsonl` still has 4 static chunks, no deposit hits, no
  promoted chunks, and primary product models `VF 3`, `VF 7`, and `VF 8 PLUS`.
- [x] 2026-06-19: Main URL ingestion now merges promoted interaction chunks into
  `LoadedUrlDocument.markdown`, rewrites primary `parsed.md`, rewrites primary
  `chunks.jsonl`, and annotates `manifest.json` with promoted interaction chunk
  IDs. The verifier should now see the VF 9 deposit fact in the main parsed
  Markdown instead of only in `url-ingestion-interactions`.
- [x] 2026-06-19: Added primary page entity enforcement and nested product spec
  extraction. URL/query-scoped models such as `modelId=Products-Car-VF9` now
  filter cross-sell DOM blocks, `data-*` configurator attributes are preserved,
  embedded JSON state can hydrate edition/color facts, and Eco/Plus prices render
  as stable Markdown tables plus nested `product_specs["editions"]`.
- [x] 2026-06-19: Added optional Crawlee/Apify rendering for dynamic pages. The
  loader now tries Crawlee first for render-required profiles with
  `timeout_seconds=None`, then falls back to direct Playwright. The Crawlee path
  sleeps/retries slow or inactive configurators and recounts the remaining
  timeout budget when a bounded timeout is supplied.
