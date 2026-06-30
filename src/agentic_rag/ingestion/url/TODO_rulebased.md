# URL Ingestion TODO - Rule-Based JS Interaction Capture

Use this TODO for pages where important facts change after JavaScript
interaction, for example:

```text
https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9
```

On this page class, a user can choose buttons/options such as color or variant.
The selected button may change image URLs, visible price, deposit/booking text,
and product summary. Static HTML extraction is not enough because the facts are
stateful.

Rule-based extraction is the preferred solution when selectors, API responses,
or state objects are stable enough to validate deterministically.

## Goal

Capture every important UI state as evidence:

- selected model, for example from `modelId`;
- selected color / variant / trim / battery option;
- visible price and currency;
- image URL or image asset associated with the selected state;
- disabled/unavailable states;
- source URL, query params, final URL, and captured timestamp;
- DOM/network evidence proving where each fact came from.

Do not trust one rendered default state when buttons can change facts.

## Rule-Based Strategy

Implementation folder:

- `interactions/profile.py`: detects booking/configurator interaction needs and
  preserves query params such as `modelId`.
- `interactions/extractor.py`: extracts option-state records from rendered HTML,
  data attributes, embedded JSON state, and supplied network payloads.
- `interactions/playwright.py`: optional live browser runner that clicks safe
  option controls and captures DOM/network evidence.
- `interactions/artifacts.py`: persists `interaction_states.json`,
  `image_snapshots.json`, `network_payloads.jsonl`, `chunks.jsonl`, and
  `manifest.json`.
- `interactions/models.py`: Pydantic contracts for profiles, controls, state
  records, and interaction artifacts.
- `interactions/runner.py`: one-call helper that captures safe UI states,
  creates chunks, and writes artifacts.

1. Detect configurator or booking pages.
   - Use URL path markers such as `dat-coc`, `booking`, `configurator`.
   - Preserve query params such as `modelId=Products-Car-VF9`.
   - Set `page_type = "booking_flow"` or `vehicle_configurator`.

2. Render with Playwright.
   - Wait for page load and network quiet enough for product data.
   - Save `source.html`, `cleaned.html`, screenshots, and network payload
     summaries as artifacts.

3. Discover option controls.
   - Prefer semantic selectors: `button`, `[role=button]`, radio inputs,
     tab controls, color swatches, variant cards.
   - Read labels from visible text, `aria-label`, `title`, `alt`, and nearby
     text.
   - Ignore nav/header/footer buttons.

4. Enumerate safe interaction states.
   - Click one option group at a time.
   - After each click, wait for DOM/image/price changes.
   - Record the selected option label, selected DOM attribute, image source,
     price text, and any changed product-spec text.
   - Stop on loops and cap combinations to avoid exploding runtime.

5. Capture network/API data.
   - Intercept JSON responses during render and option clicks.
   - Look for product, price, color, image, SKU, variant, and availability
     fields.
   - Prefer API/state data when it matches visible DOM text.
   - Store raw snippets in artifacts, but keep only normalized facts in chunk
     metadata.

6. Build variant records.
   - Each selected state should produce a structured record:

```json
{
  "model_id": "Products-Car-VF9",
  "model_name": "VF 9",
  "option_group": "color",
  "option_label": "Red",
  "price": "raw visible price",
  "currency": "VND",
  "image_url": "https://...",
  "availability": "available|disabled|unknown",
  "evidence_source": "dom|network|dom+network",
  "captured_at": "ISO datetime"
}
```

7. Convert records to chunks.
   - Keep readable text for retrieval:
     `VF 9 - color Red - price ... - image ...`.
   - Attach structured metadata:
     `product_model`, `product_price`, `product_specs`, `variant_options`,
     `variant_id`, `image_url`, `evidence_source`, `captured_at`.
   - Set `attribute_group = "pricing_specs"` when price is present.

## Metadata TODO

Add or standardize these metadata keys:

- `requested_url`: exact URL passed to ingestion, including query params.
- `url_query_params`: parsed query params, including `modelId`.
- `interaction_required`: `true` for pages where option clicks change facts.
- `interaction_states`: list of captured option states.
- `variant_id`: stable hash of model + selected options.
- `variant_options`: selected option labels by group.
- `image_url`: selected image URL.
- `price_source`: `dom`, `network`, `json_state`, or `mixed`.
- `interaction_artifact_dir`: artifact path for screenshots/network snippets.

## Artifact TODO

For each interaction run, persist:

- `source.html`: selected final rendered DOM.
- `cleaned.html`: cleaned semantic HTML from final Markdown.
- `interaction_states.json`: normalized state records.
- `network_payloads.jsonl`: filtered JSON payload metadata, not secrets.
- `image_snapshots.json`: selected image URL references per captured state,
  plus optional screenshot paths if the browser runner captures them.
- `screenshots/`: optional state screenshots for visual review.
- `chunks.jsonl`: generated chunks with variant metadata.
- `manifest.json`: selector version, state count, errors, and caps.

## Safety / Runtime Rules

- Never click submit/payment/checkout confirmation buttons.
- Do not enter user data.
- Do not bypass authentication or anti-bot controls.
- Use allowlisted selectors for option-like controls.
- Cap state combinations, for example max 30 states per URL.
- Treat hidden prices as `price_state = "not_visible"` unless an official API
  response exposes the price.

## Tests

Create deterministic HTML fixtures for:

1. Color buttons changing image URL.
2. Variant buttons changing price.
3. Disabled option buttons.
4. Price only in JSON state/API response.
5. Query param choosing initial model.
6. No visible price after all safe interactions.

## Pass Criteria

- The selected default state is captured.
- Every safe color/variant button produces either a variant record or a clear
  skipped reason.
- Price and image facts are backed by DOM or network evidence.
- Generated chunks include readable text and structured metadata.
- Golden/demo output can show whether interaction states created valuable
  chunks.
