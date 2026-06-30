## 1. Stop Forcing Complex UI into Flat Markdown
Markdown is excellent for articles and blogs, but terrible for dynamic comparison tables built with nested <div> tags. For pages like this, you should rely on Phase 3: DOM and CSS Fact Model.

Instead of routing this through extractor.py to make a messy Markdown string, this specific page type should trigger a structured extraction into your product_specs JSON metadata field.

## 2. Look for the Data Layer First
Before writing complex DOM rules, check if the page is rendered with a modern framework (React, Vue, Nuxt). If it is, the clean, structured data for all these cars is likely sitting in a ```<script> tag in the <head> or bottom of the <body> ``` (e.g., __NEXT_DATA__ or window.__INITIAL_STATE__).

- Action: If you find a JSON data block, parse that directly into your ChunkMetadata.product_model and entities fields and skip the HTML gymnastics entirely.

## 3. Build a "Container-Aware" Extractor
If you must parse the HTML, your DOMAdapter needs to stop looking at individual text nodes and start looking for the Product Card Containers.

Instead of iterating through every text-containing tag, you need a heuristic that says:

- Find the parent node that contains a model name (e.g., "VF 3").

- Extract all text strictly within that specific parent boundary.

You can implement a specialized block parser in your shared DOM layer:

```python
def extract_product_cards(self) -> List[Dict[str, Any]]:
    """Extracts specs kept safely within their product container."""
    products = []
    # Heuristic: Find containers that look like product cards
    # This requires inspecting the VinFast DOM for the actual class name
    for card in self.soup.find_all("div", class_="product-card-class-here"):
        model_name = card.find(class_="model-name-class")
        specs = card.find_all(class_="spec-class")
        
        if model_name:
            products.append({
                "model": model_name.get_text(strip=True),
                "specs": [s.get_text(strip=True) for s in specs]
            })
    return products
```

## 4. Use Playwright for Configurators
This text clearly includes dynamic pricing ("Màu nâng cao + 8.000.000 VNĐ", "Bao gồm PIN 80.000.000 VNĐ"). If these prices only appear when a user clicks a button, a static BeautifulSoup parser will either miss them or capture a disjointed list of every possible hidden option. As noted in your tool-choice-matrix.md, you should flag URLs containing configurators to route through the Playwright DOM JS path to capture the computed, user-visible state.