# URL Interaction Capture

This folder implements the rule-based plan from `TODO_rulebased.md` for pages
where product facts change after safe JavaScript interactions.

Use it for booking/configurator pages such as:

```text
https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9
```

## What It Captures

- option controls such as color, variant, trim, battery, and package buttons;
- selected option labels;
- visible or JSON-backed prices;
- selected image URLs;
- disabled/unavailable options;
- query params such as `modelId`;
- evidence metadata showing whether facts came from DOM or network JSON.

## Entry Points

```python
from agentic_rag.ingestion.url.interactions import (
    build_interaction_chunks,
    capture_interaction_states_with_playwright,
    extract_interaction_states_from_html,
    load_url_interactions_with_artifacts,
    persist_interaction_artifacts,
)
```

- `extract_interaction_states_from_html()` is deterministic and test-friendly.
  Use it with rendered HTML snapshots, fixtures, or known JSON state payloads.
- `capture_interaction_states_with_playwright()` renders a live URL, discovers
  safe option controls, clicks them within caps, captures DOM/network evidence,
  and returns normalized state records.
- `build_interaction_chunks()` converts records into shared `Chunk` objects with
  URL metadata.
- `persist_interaction_artifacts()` writes `interaction_states.json`,
  `image_snapshots.json`, `network_payloads.jsonl`, `chunks.jsonl`, and
  `manifest.json`.
- `load_url_interactions_with_artifacts()` is the one-call helper for demos or
  future loader integration.

## Safety Rules

The browser path avoids submit/payment/checkout/login/support actions, does not
enter user data, redacts token-like network keys, and caps state capture with
`InteractionOptions.max_states`.

`image_snapshots.json` stores review references only. It points to the selected
product image URL and optional screenshot paths when a browser runner supplies
them; it does not download remote image binaries.

LLM review may read these artifacts later, but price/image/model facts should
only be trusted when backed by DOM or network evidence.
