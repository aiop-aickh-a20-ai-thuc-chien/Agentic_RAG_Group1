# URL Ingestion TODO - LLM-Assisted JS Interaction Review

Use this TODO when rule-based selectors or state extraction are too brittle for
dynamic pages, such as booking/configurator pages where clicking buttons changes
color, image, price, or availability.

LLM can help inspect and classify page states, but it must not be the source of
truth for price, model, or image facts. Facts must come from DOM text, network
payloads, screenshots with OCR, or persisted artifacts.

## When LLM Helps

- Label ambiguous buttons, for example color swatches with no text.
- Decide which controls are safe option controls and which are checkout/login
  actions.
- Compare screenshots before/after a click and describe what changed.
- Map visible labels to structured option groups: `color`, `trim`, `battery`,
  `package`, `deposit`, `warranty`.
- Suggest selector repairs when deterministic extraction returns zero states.
- Review generated chunks and explain whether they are useful for retrieval.

## When LLM Should Not Be Used Alone

- Do not ask LLM to invent or infer price.
- Do not accept LLM-only image/color mappings without DOM, network, or screenshot
  evidence.
- Do not let LLM click arbitrary buttons.
- Do not let LLM decide duplicate/conflict resolution; send facts to
  `dedup_detect` or `knowledge_quality`.

## Evidence-First Flow

1. Run rule-based render and safe interaction capture first.
2. Persist artifacts:
   - rendered DOM,
   - cleaned HTML,
   - screenshots,
   - network payload summaries,
   - interaction state records,
   - chunks.
3. Send only the relevant artifact slices to LLM:
   - visible text around controls,
   - control attributes,
   - before/after screenshot paths or OCR text,
   - candidate state JSON.
4. Ask LLM to return structured JSON with confidence and evidence references.
5. Validate every proposed fact against DOM/network/artifact text.
6. Keep unvalidated LLM output as review notes, not chunk metadata.

## Proposed LLM Output Schema

```json
{
  "page_type": "booking_flow",
  "safe_controls": [
    {
      "selector_hint": "button[data-color='red']",
      "option_group": "color",
      "option_label": "red",
      "safe_to_click": true,
      "reason": "changes product color only"
    }
  ],
  "state_reviews": [
    {
      "state_id": "vf9-color-red",
      "observed_changes": ["image changed", "price unchanged"],
      "facts_validated": ["image_url"],
      "facts_needing_rule_validation": ["price"],
      "confidence": 0.82,
      "evidence": ["screenshot:state-red.png", "dom:price-block"]
    }
  ],
  "chunk_review": {
    "valuable": true,
    "missing_facts": ["battery option"],
    "noise_risk": "low"
  }
}
```

## TODO

1. Add an optional review stage after rule-based interaction capture.
2. Create a compact artifact bundle for LLM review:
   - selected control text/attributes,
   - state diffs,
   - screenshot filenames,
   - candidate JSON records.
3. Add a strict JSON schema for LLM output.
4. Add validators:
   - fact must appear in DOM text, network payload, OCR text, or existing
     metadata;
   - price must match currency/number regex;
   - image URL must appear in DOM/network payload;
   - option labels must map to clicked controls.
5. Store LLM review under `interaction_review.llm_notes`, not as trusted facts.
6. Add an evaluation column:
   - `rule_based_state_count`,
   - `llm_suggested_state_count`,
   - `validated_state_count`,
   - `unvalidated_llm_fact_count`.

## Prompt Guardrails

Use prompts like:

```text
You are reviewing URL ingestion artifacts. Return only JSON.
Do not invent price, model, image URL, or availability.
If a fact is not present in the provided evidence, mark it as unknown.
Only classify controls that are safe option selectors.
Do not suggest clicking checkout, payment, login, submit, or personal-data forms.
```

## Pass Criteria

- LLM can improve control labeling or review notes without changing trusted
  facts directly.
- Every metadata fact used for retrieval has deterministic evidence.
- Unvalidated LLM outputs are visible in artifacts but excluded from chunks.
- The demo can show whether LLM review found missing interaction states.

