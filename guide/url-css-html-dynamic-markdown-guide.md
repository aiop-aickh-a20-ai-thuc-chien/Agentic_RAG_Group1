# CSS, HTML, And Dynamic Markdown Guide

This guide defines how URL ingestion should convert visual HTML, CSS, and
JavaScript behavior into meaningful Markdown and source-backed metadata.

Use this guide when a page contains visual meaning that plain text extraction
can miss, such as old prices, highlighted prices, selected colors, CSS-based
tables, generated labels, or JavaScript option controls.

## Core Rule

URL ingestion should preserve meaning, not decoration.

Markdown is the readable retrieval representation. `Chunk.metadata` is the
traceable evidence representation. Do not add new top-level `Chunk` fields for
URL-only details.

Visual evidence must be applied to retrievable chunks, not left only in
standalone visual-review chunks. BM25 and dense retrieval primarily see
`Chunk.text`, so the useful semantic fact should appear in the same text chunk
as the product, policy, model, or section it describes.

Every trusted product fact should be backed by deterministic evidence:

```text
raw HTML
  -> rendered DOM
  -> computed CSS / accessibility evidence
  -> dynamic interaction DOM
  -> network or JSON state
  -> screenshot or OCR review
  -> LLM review notes
```

LLM output is the lowest-trust layer. It can help classify evidence, but it
must not become the only source for price, model, image, availability, warranty,
range, or other product facts.

## Applying Visual Facts To RAG Chunks

Use this priority when visual extraction finds a fact:

1. Rewrite in place when the fact already appears in the relevant Markdown.
   Example: if raw Markdown has `Original price 1.699.000.000 VND` and CSS shows
   line-through, rewrite the same chunk to
   `Original price ~~1.699.000.000 VND~~`.
2. Attach metadata to that same relevant chunk:
   `visual_semantics`, `original_price`, `css_evidence`, `evidence_source`,
   `section_origin`, and `trusted_for_retrieval`.
3. If the visual fact does not appear in extracted Markdown, create a small
   fallback evidence line, but still make it self-contained with the page title,
   product/model, or nearest section name.
4. Mark fallback visual chunks as debug-only:
   `chunk_type=visual_debug`, `retrieval_visibility=debug_only`,
   `metadata_prefilter_exclude=true`, and `trusted_for_retrieval=false`.
5. Keep artifact-only visual facts for review, debugging, or future expansion.
   Do not rely on artifact-only facts for normal RAG answers.

Good retrievable chunk text:

```markdown
VF 9 current price: 1.393.180.000 VND. Original price: ~~1.699.000.000 VND~~.
```

Weak visual-only chunk:

```markdown
Visual Pricing Evidence
- Original price from strike-through text: ~~1.699.000.000 VND~~.
```

The weak form is acceptable only as a fallback when the extractor cannot map the
visual fact back into a nearby semantic chunk. It should remain available in
artifacts and demos, but normal metadata pre-filter should exclude it before
vector search.

Pre-filter rule:

```text
exclude chunk where metadata_prefilter_exclude == true
exclude chunk where retrieval_visibility == "debug_only"
unless the query explicitly asks for ingestion/debug/review artifacts
```

## HTML And CSS To Markdown Rules

### Headings

Use Markdown headings for real page structure:

- HTML `h1` to `h6`.
- Stable ARIA or DOM sections that act as source-backed headings.
- Page titles when no visible heading exists.

Do not turn visually large isolated values into headings. For example, a price
such as `1.699.000.000 VND` should stay attached to its product or pricing
section, not become:

```markdown
# 1.699.000.000 VND
```

Prefer:

```markdown
VF 9 listed price: 1.699.000.000 VND.
```

### Tables And Table-Like Layouts

Use Markdown tables when the source is a real data table or when CSS layout
clearly forms recoverable rows and columns.

HTML `table`, `tr`, `th`, and `td` are strong evidence for a Markdown table.
CSS `display: grid`, `display: flex`, or `display: table` is weaker evidence.
Only convert CSS layout to a Markdown table when the extractor can recover:

- stable headers or labels,
- repeated rows or cards,
- label-value pairs,
- row/entity identity,
- units or currency attached to values.

Good Markdown table:

```markdown
| Model | Range | Listed price |
| --- | --- | --- |
| VF 8 Eco | 471 km | 849.150.000 VND |
| VF 9 Plus | 626 km | 1.699.000.000 VND |
```

If headers or rows are uncertain, prefer self-contained bullets:

```markdown
- VF 8 Eco driving range: 471 km.
- VF 8 Eco listed price: 849.150.000 VND.
```

### Old Price, Current Price, And Strike-Through

Treat old or superseded prices as semantic facts when the source uses:

- HTML `s`,
- HTML `del`,
- CSS `text-decoration: line-through`,
- visible labels such as `old price`, `original price`, or `was`.

Use Markdown strike-through for the old value and keep structured metadata for
both values:

```markdown
VF 9 current price: 1.393.180.000 VND; original price: ~~1.699.000.000 VND~~.
```

Recommended metadata:

```json
{
  "chunk_type": "spec_fact",
  "attribute_group": "pricing_specs",
  "product_model": "VF 9",
  "product_price": "1.393.180.000",
  "product_currency": "VND",
  "original_price": "1.699.000.000",
  "price_source": "rendered_dom",
  "css_evidence": ["text-decoration: line-through"]
}
```

### Color, Weight, Badges, And Visual Emphasis

Do not preserve arbitrary colors as Markdown. Preserve visual style only when it
changes meaning.

Use Markdown emphasis for source-backed meaning:

- selected state,
- promotion,
- warning,
- availability,
- required action,
- active package, model, color, or trim.

Example:

```markdown
VF 9 selected exterior color: **Deep Ocean**.
```

Recommended metadata:

```json
{
  "section_kind": "dynamic",
  "attribute_group": "visual_variant",
  "variant_options": {"exterior_color": "Deep Ocean"},
  "evidence_source": "dom_after_interaction"
}
```

### Hidden Content

Do not trust hidden content as visible user-facing text when it is hidden by:

- `display: none`,
- `visibility: hidden`,
- `hidden`,
- `aria-hidden="true"`,
- off-screen or collapsed UI before safe expansion.

Hidden content can still be useful as evidence, but it should be marked as
state or payload evidence instead of normal visible Markdown:

```json
{
  "section_origin": "dynamic_state_payload",
  "evidence_source": "json_state",
  "visible_in_markdown": false
}
```

### Generated CSS Content

CSS `::before` and `::after` can add visible labels that are not present in raw
HTML. Include generated labels only when rendered or computed-style artifacts
prove they are visible and meaningful.

Example:

```css
.price::before { content: "Price:"; }
```

Acceptable Markdown after rendered verification:

```markdown
VF 9 price: 1.699.000.000 VND.
```

Recommended metadata:

```json
{
  "evidence_source": "computed_style",
  "css_generated_content": true,
  "selector": ".price::before"
}
```

## Dynamic JavaScript Rules

Dynamic pages should separate static facts from interaction-dependent facts.
Raw interaction capture chunks are debug artifacts by default. They record what
the crawler saw after JavaScript/button/state extraction, but normal RAG
retrieval should filter them out unless the query asks for ingestion/debug
evidence.

### Panel-Aware Interaction Capture

For configurator pages, treat the rendered page as review regions:

- `left_panel`: option controls such as model, trim, color, battery, package,
  financing, or deposit selectors.
- `center_visual`: product image, carousel, gallery, selected visual preview,
  or image URL evidence.
- `right_panel`: price, payment/deposit summary, selected-option summary,
  availability, or checkout-adjacent information.
- `unknown`: visible evidence that cannot be mapped confidently.

Each safe click should capture:

- baseline panel snapshots,
- before/after snapshots for the clicked control,
- changed panels,
- changed fields such as `price`, `image`, `availability`, or `visible_text`,
- artifact references for before snapshot, after snapshot, and state diff.

Raw click records remain debug-only:

```json
{
  "chunk_type": "interaction_debug",
  "retrieval_visibility": "debug_only",
  "metadata_prefilter_exclude": true,
  "trusted_for_retrieval": false,
  "semantic_application_status": "unmapped",
  "panel_role": "left_panel",
  "changed_panels": ["center_visual", "right_panel"],
  "changed_fields": ["price", "image"],
  "before_snapshot_ref": "panel_snapshot_before",
  "after_snapshot_ref": "panel_snapshot_after",
  "state_diff_ref": "panel_diff_trim_plus"
}
```

Only promote deterministic changed facts into normal retrieval:

```json
{
  "chunk_type": "dynamic_state",
  "retrieval_visibility": "normal",
  "metadata_prefilter_exclude": false,
  "trusted_for_retrieval": true,
  "semantic_application_status": "applied_to_semantic_chunk",
  "panel_role": "left_panel",
  "changed_panels": ["center_visual", "right_panel"],
  "changed_fields": ["price", "image"]
}
```

Example promoted text:

```markdown
VF 9 selected trim Plus changes across center visual, right panel:
right-panel visible price to 1.699.000.000 VND, center product image to
https://example.com/vf9-plus.png.
```

Panel snapshots and raw interaction debug chunks are useful for the review UI,
but metadata pre-filter should remove them from normal retrieval. RAG should see
only the promoted, self-contained semantic dynamic chunk.

Safe interaction capture may click controls that only change product state:

- model,
- color,
- trim,
- battery,
- package,
- deposit option,
- accordion or tab disclosure.

Do not click actions that can mutate state or start real workflows:

- checkout,
- payment,
- login,
- submit,
- add to cart when it changes account/cart state,
- personal-data forms.

Dynamic chunks should include provenance:

```json
{
  "chunk_type": "interaction_debug",
  "section_kind": "dynamic",
  "section_origin": "dynamic_interaction",
  "dynamic_state_id": "vf9-plus-deep-ocean",
  "interaction_step": "select-color-deep-ocean",
  "evidence_source": "dom_after_interaction",
  "artifact_ref": "artifacts/vf9-plus-deep-ocean/state.json",
  "retrieval_visibility": "debug_only",
  "metadata_prefilter_exclude": true,
  "trusted_for_retrieval": false,
  "semantic_application_status": "unmapped"
}
```

If the value comes from JSON or network data instead of visible DOM, use:

```json
{
  "chunk_type": "interaction_debug",
  "section_origin": "dynamic_state_payload",
  "evidence_source": "network_payload",
  "state_path": "$.product.variants[0].price",
  "retrieval_visibility": "debug_only",
  "metadata_prefilter_exclude": true,
  "trusted_for_retrieval": false
}
```

Only promote an interaction fact into normal retrieval when it is applied to a
semantic chunk that answers a real user-facing question.

Promoted semantic dynamic chunk:

```markdown
VF 9 selected trim Plus has visible price 1.699.000.000 VND after selecting the
Plus option. Evidence: dynamic interaction state.
```

Promoted metadata:

```json
{
  "chunk_type": "dynamic_state",
  "section_kind": "dynamic",
  "section_origin": "dynamic_interaction",
  "product_model": "VF 9",
  "variant_options": {"trim": "Plus"},
  "product_price": "1.699.000.000 VND",
  "retrieval_visibility": "normal",
  "metadata_prefilter_exclude": false,
  "trusted_for_retrieval": true,
  "semantic_application_status": "applied_to_semantic_chunk"
}
```

Pre-filter rule for interaction chunks:

```text
exclude chunk where chunk_type == "interaction_debug"
exclude chunk where semantic_application_status == "unmapped"
exclude chunk where metadata_prefilter_exclude == true
unless debug/review mode is explicitly requested
```

### Why Interaction Chunks May Be Missing

Interaction chunks will not appear just because a page is dynamic. They require
the interaction capture path to run and successfully identify safe controls.

Common reasons they are absent:

- The caller used `load_url_with_artifacts()` without
  `include_interactions=True`, so only rendered/static chunks were produced.
- The demo did not enable **Capture dynamic interactions when needed**, so it
  never invoked the interaction runner.
- The page is detected as a booking/configurator URL, but the rendered controls
  do not expose stable selectors such as `button`, `role=button`,
  `data-option-group`, `data-option-label`, `.color-swatch`, `.variant-card`,
  or `.option-card`.
- The useful state appears as static text, hidden JSON, framework state, or
  network payload instead of safe clickable controls.
- Controls are skipped because they look unsafe: checkout, payment, login,
  submit, deposit, support, or hotline actions.
- The page requires extra wait/scroll/accordion expansion before controls are
  available in the DOM.

For pages like VinFast booking/configurator pages, the correct flow is:

```text
normal URL ingestion
  -> static/rendered semantic chunks
interaction capture
  -> debug-only interaction chunks and state artifacts
state-to-semantic promotion
  -> trusted dynamic_state chunks appended to the review/ingestion chunk set
metadata pre-filter
  -> exclude raw interaction_debug chunks from normal RAG
```

If interaction capture sees only raw button inventory or unstable framework
state, keep it as debug-only. Promote only validated facts such as selected
trim, selected color, price, image, availability, or bounded visible text
changes into semantic chunks.

### Visual Buttons And Option Groups

Visual buttons under a text label should be parsed as option controls first,
not as headings and not automatically as a table.

Use bullets when the page shows one option group under a label:

```markdown
VF 9 configurable option group: exterior color.
- option: Deep Ocean; state: selected; changes: product image.
- option: Crimson Red; state: available; changes: product image.
- option: Jet Black; state: available; changes: product image.
```

Use a table only when captured states have stable comparable columns:

```markdown
| Option group | Option | Selected | Price | Image changes |
| --- | --- | --- | --- | --- |
| Exterior color | Deep Ocean | yes | unchanged | yes |
| Exterior color | Crimson Red | no | unchanged | yes |
| Trim | Plus | yes | 1.699.000.000 VND | yes |
| Trim | Eco | no | 1.499.000.000 VND | yes |
```

Use self-contained dynamic fact chunks for the selected or captured state:

```markdown
VF 9 selected exterior color: Deep Ocean. Selecting this color changes the
product image. The visible price remains 1.699.000.000 VND.
```

Recommended button metadata:

```json
{
  "chunk_type": "dynamic_state",
  "section_kind": "dynamic",
  "section_origin": "dynamic_interaction",
  "option_group": "exterior_color",
  "option_label": "Deep Ocean",
  "selected": true,
  "changes_detected": ["image"],
  "dynamic_state_id": "vf9-color-deep-ocean",
  "interaction_step": "select-exterior-color-deep-ocean",
  "trusted_for_retrieval": true
}
```

Rule of thumb:

- button inventory alone -> bullets;
- repeated captured states with the same fields -> table;
- selected state or changed result -> self-contained semantic chunk;
- unsafe checkout/payment/login buttons -> excluded or debug-only metadata.

## Markdown Syntax Contract

Use Markdown that remains useful after chunking and retrieval.

### Exact Spec Fact

```markdown
VF 9 Plus driving range: 626 km under the listed standard.
```

Metadata:

```json
{
  "chunk_type": "spec_fact",
  "product_model": "VF 9 Plus",
  "attribute_group": "driving_range",
  "product_specs": {"driving_range": "626 km"}
}
```

### Recoverable Comparison Table

```markdown
| Model | Battery capacity | Driving range |
| --- | --- | --- |
| VF 8 Eco | 87.7 kWh | 471 km |
| VF 9 Plus | 123 kWh | 626 km |
```

### Current And Old Price

```markdown
VF 9 current price: 1.393.180.000 VND; original price: ~~1.699.000.000 VND~~.
```

### Image Reference

Use image Markdown only when the image is useful retrieval or review evidence:

```markdown
![VF 9 Deep Ocean exterior](https://example.com/vf9-deep-ocean.png)
```

Metadata should keep the traceable reference:

```json
{
  "chunk_type": "asset_reference",
  "image_url": "https://example.com/vf9-deep-ocean.png",
  "image_snapshot_ref": "artifacts/images/vf9-deep-ocean.json",
  "attribute_group": "visual_variant"
}
```

### Dynamic Variant Block

```markdown
VF 9 Plus selected color: Deep Ocean. Price after selection:
1.393.180.000 VND. Selected image:
https://example.com/vf9-deep-ocean.png.
```

Metadata:

```json
{
  "chunk_type": "dynamic_state",
  "product_model": "VF 9 Plus",
  "variant_options": {"color": "Deep Ocean"},
  "product_price": "1.393.180.000",
  "product_currency": "VND",
  "image_url": "https://example.com/vf9-deep-ocean.png"
}
```

## LLM Fallback Contract

LLM fallback is optional and evidence-first.

Trigger it only when rule-based extraction found evidence but cannot confidently
map that evidence into Markdown or metadata. Good reasons include:

- ambiguous color swatches without text,
- CSS table layout with unclear columns,
- generated labels that need semantic naming,
- before/after dynamic diffs that are hard to classify,
- selector repair suggestions after rule-based extraction found zero states.

Inputs should be bounded artifact slices:

- DOM snippet,
- computed styles,
- selector path or DOM path,
- accessibility or visible text,
- before/after diffs,
- network or JSON excerpts,
- screenshot or OCR references,
- current rule-based extraction result.

Require strict JSON output:

```json
{
  "proposed_markdown": "VF 9 selected color: Deep Ocean.",
  "semantic_role": "dynamic_state",
  "field_mapping": {
    "variant_options.color": "Deep Ocean"
  },
  "evidence_refs": [
    "dom:#color-option-deep-ocean",
    "screenshot:state-deep-ocean.png"
  ],
  "confidence": 0.82,
  "needs_human_review": false,
  "unvalidated_facts": []
}
```

Validation rule:

```text
No price, model, image, availability, warranty, range, or product fact enters
trusted Markdown or Chunk.metadata unless it appears in deterministic DOM,
network, JSON, OCR, or artifact evidence.
```

Unvalidated LLM output should stay in review notes or generated artifacts:

```json
{
  "section_origin": "generated_artifact",
  "llm_fallback_used": true,
  "llm_confidence": 0.64,
  "trusted_for_retrieval": false
}
```

## Acceptance Scenarios

Use these scenarios when implementing or reviewing extraction changes:

| Scenario | Expected behavior |
| --- | --- |
| Old price/current price with strike-through | Current price stays normal; old price becomes `~~old price~~`; both values appear in metadata. |
| Color swatch changes image but not price | Dynamic state captures selected color and image; price remains unchanged or omitted from that state. |
| Color or trim changes price and image | Dynamic state records selected options, price, image URL, and evidence refs. |
| CSS grid/flex acts like a table | Convert to Markdown table only when headers and rows are recoverable; otherwise use bullets/spec facts. |
| `::before { content: "Price:" }` adds a label | Include the label only when computed/rendered evidence proves it is visible. |
| Hidden JSON price not visible in DOM | Store as `dynamic_state_payload`; do not present as visible Markdown unless policy allows payload-backed facts. |
| LLM proposes a mapping with evidence | Accept only after deterministic validation succeeds. |
| LLM invents a price | Reject from trusted Markdown and metadata; keep only in review notes. |

## References

- WHATWG HTML table element:
  <https://html.spec.whatwg.org/multipage/tables.html#the-table-element>
- WHATWG HTML `s` element:
  <https://html.spec.whatwg.org/multipage/text-level-semantics.html#the-s-element>
- WHATWG HTML `del` element:
  <https://html.spec.whatwg.org/multipage/edits.html#the-del-element>
- W3C CSS Text Decoration:
  <https://www.w3.org/TR/css-text-decor-3/>
- W3C CSS Pseudo-Elements:
  <https://www.w3.org/TR/css-pseudo-4/>
- W3C CSS Display:
  <https://www.w3.org/TR/css-display-3/>
- CommonMark:
  <https://spec.commonmark.org/0.31.2/>
- Playwright actionability:
  <https://playwright.dev/python/docs/actionability>
- Playwright network monitoring:
  <https://playwright.dev/python/docs/network>
