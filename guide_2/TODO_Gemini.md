# Gemini TODO: Capturing Dynamic Model Selection on Configurator Pages

This is a minor fix and follow-up based on the observation from reviewing the `parsed.md` artifact for the VinFast configurator page:
`guide_2/demo/output/artifacts/artifacts/https-shop-vinfastauto-com-vn-vi-dat-coc-o-to-dien-vinfast-html-modelid-products_2a7cf685fe11/url-ingestion/parsed.md`

## Observation

As noted during the review, on the VinFast configurator page, the initially selected model (e.g., VF 9) is presented more clearly in the left panel than the other vehicle options. This visual distinction is a crucial semantic signal that indicates which vehicle's specifications are currently being displayed.

## Problem

The current static ingestion process, which generates the `parsed.md` file, only captures the default state of the page. It cannot see the specifications for other models (like the VF 8 or VF 7) because that would require clicking on them. This means we are missing important product data.

## Solution

To address this, we must enhance the ingestion pipeline to be "container-aware" and "state-aware," moving beyond flat Markdown extraction for complex pages. This involves implementing the strategies outlined in `guide/url-css-html-dynamic-markdown-guide.md` and `src/agentic_rag/ingestion/url/TODO.md`.

The goal is to capture the page's structure and state changes to extract accurate, structured data for each product entity.

### Action Items

1.  **Prioritize the Data Layer**: Before parsing HTML, the extractor should first inspect the page for a framework-provided JSON data layer (e.g., `<script id="__NEXT_DATA__">`). If found, parse this structured data directly to populate `product_specs` and `entities` metadata, which is faster and more reliable than DOM traversal.

2.  **Implement Container-Aware DOM Extraction**: If a data layer is absent, the DOM parser must be enhanced to be "container-aware." Instead of extracting all text, it should:
    -   Identify the parent DOM nodes that act as containers for each product (e.g., a `div` for "VF 9", another for "VF 8").
    -   Extract text and data *only within* the boundaries of each container.
    -   This prevents facts from different products from being mixed into a single, confusing chunk. This aligns with the "Preserve entity boundaries before chunking" goal in `src/agentic_rag/ingestion/url/TODO.md`.

3.  **Enable and Verify Dynamic Interaction Capture**: For configurator pages, static rendering is insufficient.
    -   **Enhance the Review Script**: Add a command-line flag (e.g., `--include-interactions`) to the `guide_2/demo/review.py` script to trigger the dynamic interaction runner.
    -   **Update the Loader**: Modify `load_url_with_artifacts` to accept and pass down the `include_interactions` flag.
    -   **Simulate Clicks**: Programmatically click on each vehicle model selector (`VF 9`, `VF 8`, etc.) and capture the resulting page state (e.g., updated price, specs, and images) for each one, as described in `guide/url-css-html-dynamic-markdown-guide.md`.

4.  **Improve the HTML Report**:
    -   Visually distinguish chunks that were generated from dynamic interactions in the `review.html` report. A different background color or a "Dynamic" badge would be effective.
    -   Add a new debug section to display raw interaction artifacts, such as `interaction_debug` chunks and panel snapshots (`left_panel`, `center_visual`, `right_panel`).

5.  **Verify the Fix**: Run the updated review script on the VinFast configurator URL with the new flag enabled. The final report should contain distinct, accurate chunks for each vehicle model (VF 9, VF 8, etc.), with structured `product_specs` in the metadata, proving that the container-aware and state-aware extraction was successful.

6.  **Create Ground Truth and Verify with LLM**: Manually create an ideal `parsed.md` ground truth file that captures all vehicle models. Then, use the `guide_2/demo/verify_ingestion/verify_ingestion.py` script to compare the dynamic ingestion output against this ground truth, generating a detailed evaluation report.