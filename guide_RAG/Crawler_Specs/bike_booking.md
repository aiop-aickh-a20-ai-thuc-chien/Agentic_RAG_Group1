# 🛵 VinFast Electric Motorbike Booking Crawler Specification

This document details the crawling and data extraction strategy for the **VinFast Electric Motorbike Booking Page**.

- **Target URL**: `https://shop.vinfastauto.com/vn_vi/xe-may-dien-vinfast.html`
- **Objective**: Scrape comprehensive electric motorbike information, including models, battery procurement schemes, variant options, color swatches, dynamic pricing, and technical specifications.

---

## 1. Target Entities

Electric motorbike pricing and data models are heavily structured around battery options:

```text
Motorbike Model (Evo200, Feliz S, Klara S, Vento S, Theon S)
  ├── Variant Options (e.g., Evo200 vs. Evo200 Lite, Vento vs. Vento S)
  ├── Battery Plan Option
  │     ├── Option A: Battery Rental (Thuê pin) -> Lower upfront cost + monthly subscription
  │     └── Option B: Battery Included (Mua pin) -> Higher upfront cost, battery ownership
  ├── Color Swatch (Color Name, Code, Price Delta, Image List)
  └── Technical Specifications (Top Speed, Range, Battery Chemistry, Motor Power)
```

---

## 2. Interaction Flow & State Tree

To enumerate motorbike prices accurately, the crawler must cycle through variants, colors, and battery plans:

### State Transition Diagram
```
[Start: Motorbike Landing Page]
       │
       ▼
1. Enumerate & Click Motorbike Model (.bike-model-card / .swiper-slide)
       │
       ▼
2. Toggle Battery Option (Rental vs. Purchase)
       │
       ▼
3. Enumerate & Select Variant Option (.variant-choice)
       │
       ▼
4. Enumerate & Click Color Swatch (.color-circle / .swatch-item)
       ├── Capture: Dynamic Price for state Combination
       └── Capture: Vehicle Image Assets & Technical Specs
```

---

## 3. Extraction Rules & Target Selectors

### A. Motorbike Model Enumeration
- **Selector**: `.bike-model-card`, `.swiper-slide[data-modelid]`, `.product-item-link`
- **Expected Models**: `Evo200`, `Evo200 Lite`, `Feliz S`, `Klara S (2024)`, `Vento S`, `Theon S`
- **Output Schema**:
  ```json
  {
    "model_id": "Products-Bike-Evo200",
    "name": "Evo200"
  }
  ```

### B. Battery Procurement Toggle
- **Selector**: `.battery-option-card`, `input[type="radio"][value="rent"]`, `input[type="radio"][value="buy"]`
- **Action**: Toggle between battery rental (Thuê pin) and battery purchase (Mua pin).
- **Rule**: Changing this option updates the base vehicle price instantly. Extract both states for complete pricing.

### C. Variant Selection
- **Selector**: `.variant-option-item`, `.variant-choice`
- **Action**: Click to toggle between performance/range configurations (e.g., Lite speed-locked at 49 km/h vs. Standard at 70 km/h).

### D. Color Swatches
- **Selector**: `.color-circle`, `.swatch-item`, `.color-select`
- **Action**: Iterate over all available color swatches. Extract:
  - Color name (e.g., "Vàng", "Đỏ", "Xanh")
  - Dynamic image URLs
  - Price delta (if some premium colors carry additional charges)

### E. Price & Specification Capture
- **Price Selector**: `.price-amount`, `.final-price`
- **Specifications Table**: `.specifications-table`, `dl.specs-list`
- **Output Schema**:
  ```json
  {
    "model_name": "Evo200",
    "variant": "Standard",
    "battery_option": "rental",
    "color": "Vàng",
    "price": 18000000,
    "specifications": {
      "top_speed_kmh": 70,
      "range_km": 203,
      "battery_type": "LFP",
      "motor_power_w": 1500
    }
  }
  ```

---

## 4. Crawl Pacing & Sync Rules

- **Battery Toggle Sync**: Toggling the battery plan triggers dynamic DOM recalculation. Wait `0.5 - 1.2 sec` for the price tag selector content to update.
- **Verification Hook**: Verify that the selected battery option styling matches the active CSS class (e.g., `.is-selected`, `.active`) before capturing pricing data.
- **Pacing**: Apply a pacing delay of `0.5 - 1.5 sec` between color/variant clicks to emulate human browsing speeds and prevent rate limits.
