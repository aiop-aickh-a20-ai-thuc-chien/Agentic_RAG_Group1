# 🚗 VinFast Electric Car Booking Crawler Specification

This document details the crawling and data extraction strategy specifically for the **VinFast Electric Car Booking Page**.

- **Target URL**: `https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html`
- **Objective**: Scrape comprehensive electric vehicle data, including variants, pricing, specifications, promotions, colors, interactive rolling costs (chi phí lăn bánh), and installment schedules (dự toán trả góp).

---

## 1. Target Entities

The crawling process treats the booking interface as a graph of related entities:

```text
Vehicle (Car)
  ├─ Variant (Eco, Plus, etc.)
  │    ├─ Battery Option (Rent vs. Buy, if applicable)
  │    ├─ Color Options (Price / Swatch / Images)
  │    ├─ Specifications (Range, Battery Capacity, Motors, etc.)
  │    ├─ Rolling Cost Options (Province-based breakdown)
  │    └─ Installment Options (Bank-based monthly projections)
  └─ Promotion Events
```

---

## 2. Interaction Flow & State Tree

To extract all data, the crawler must enumerate the state tree by executing dynamic UI interactions.

### State Transition Diagram
```
[Start: Landing Page]
       │
       ▼
1. Enumerate & Click Vehicle Slide (.swiper-slide[data-modelid])
       │
       ▼
2. Enumerate & Click Variant Selector (.variant-option)
       │
       ▼
3. Enumerate & Click Color Swatch (.color-item / .swatch)
       ├── Capture: Variant Price & Specifications
       │
       ├─► 4a. Click "Chi phí lăn bánh" (Modal)
       │       └── For each Province in dropdown:
       │               └── Capture: Rolling Cost Breakdown JSON
       │
       └─► 4b. Click "Dự toán trả góp" (Modal)
               └── For each Bank, Down Payment %, and Loan Term:
                       └── Capture: Installment Breakdown JSON
```

---

## 3. Extraction Rules & Target Selectors

### A. Vehicle Enumeration
- **Selector**: `.swiper-slide[data-modelid]` (e.g., `<div data-modelid="Products-Car-VF8">`)
- **Expected Models**: `VF3`, `VF5`, `VF6`, `MPV7`, `VF7`, `VF8`, `VF8 The All New`, `VF9`
- **Output Schema**:
  ```json
  {
    "model_id": "Products-Car-VF8",
    "name": "VF 8"
  }
  ```

### B. Variant Selection
- **Selector**: `.variant-option`, `.variant-selector`, `select`
- **Action**: Iterate through each element and click to update page state.

### C. Color Selection
- **Selector**: `.color-item`, `.color-option`, `.swatch`
- **Action**: Click to update vehicle render images and pricing details.

### D. Rolling Cost (Chi phí lăn bánh)
- **Trigger**: Click element matching text `Chi phí lăn bánh` or selector `[data-bs-toggle="modal"]` associated with rolling costs.
- **Interactions**:
  1. Open the modal dialog.
  2. Locate the province/location selection dropdown.
  3. Loop through all option values (Provinces).
  4. Scrape the computed table.
- **Target Schema**:
  ```json
  {
    "province": "Hà Nội",
    "registration_fee": 0,
    "insurance": 0,
    "road_fee": 0,
    "plate_fee": 0,
    "inspection_fee": 0,
    "total_on_road": 1050000000
  }
  ```

### E. Installment Calculator (Dự toán trả góp)
- **Trigger**: Click element matching text `Dự toán trả góp`.
- **Interactions**:
  1. Open the installment modal.
  2. Select/Iterate through Bank options, Down Payment percentage sliders/dropdowns (e.g., 30%, 40%, 50%), and Loan Terms (e.g., 36, 48, 60 months).
  3. Scrape the dynamically calculated fields.
- **Target Schema**:
  ```json
  {
    "bank": "BIDV",
    "down_payment_percent": 50,
    "loan_term_months": 60,
    "monthly_payment": 12500000,
    "interest_rate": 7.5,
    "loan_amount": 450000000
  }
  ```

---

## 4. Crawl Pacing & Sync Rules

To avoid triggering rate-limiting and handle debounced dynamic inputs:
- **Vehicle Switch**: Delay `0.8 - 2.0 sec` after click.
- **Variant Switch**: Delay `0.5 - 1.2 sec` after click.
- **Calculator Interactions**: Delay `1.0 - 3.0 sec` for calculation API requests to settle.
- **Pacing Rule**: Use random pacing ranges coupled with verification of dynamic UI indicators (e.g. loader/spinner disappearances or text change events).
