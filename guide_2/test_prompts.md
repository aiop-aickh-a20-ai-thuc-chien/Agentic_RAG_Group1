# Test Prompts for Dynamic and Structured Data Ingestion (VinFast)

This test prompt suite is designed to verify if the ingestion pipeline and the knowledge extraction prompts can correctly identify, preserve, and represent complex web structures, hidden lists, and dynamic states (such as changing prices based on chosen options, color select, model selection, or VinClub discount checkboxes).

---

## 1. User Retrieval Test Prompts (Q&A Evaluation Queries)

These queries can be run against the RAG system to test if the ingested chunks contain the correct dynamic facts.

### 1.1. Model & Edition Selection
*   **Query (VI):** "So sánh giá bán, công suất động cơ và tầm hoạt động của xe VinFast VF 9 phiên bản Eco và Plus khi mua đứt pin và thuê pin."
*   **Expected Target Facts:** 
    *   Price distinction between Eco and Plus.
    *   Price distinction between battery purchase vs. battery subscription (thuê pin).
    *   Correct mapping of specs (horsepower: 402 hp, range: ~400-420 km depending on edition) without mixing them up.

### 1.2. Interactive Color Option Pricing & Assets
*   **Query (VI):** "Giá xe VF 8 thay đổi như thế nào khi chọn màu sơn cao cấp (như Xám kim loại hoặc Đỏ) so với màu sơn tiêu chuẩn? Tìm đường dẫn hình ảnh tương ứng của từng màu nếu có."
*   **Expected Target Facts:**
    *   Presence of color options (Màu ngoại thất: Trắng, Đen, Xám, Đỏ, Xanh).
    *   Option pricing surcharge for premium colors (nếu có).
    *   Association of correct image URLs or color codes with color names.

### 1.3. VinClub Membership Discounts (Checkbox options)
*   **Query (VI):** "Chính sách chiết khấu thành viên VinClub áp dụng thế nào cho xe điện VinFast? Giá ưu đãi của VF 7 Eco sau khi tích chọn chiết khấu VinClub (hạng Vàng, Bạch Kim, Kim Cương) là bao nhiêu?"
*   **Expected Target Facts:**
    *   Tiers of VinClub discounts (Vàng: 1%, Bạch Kim: 1.5%, Kim Cương: 2% hoặc tương đương).
    *   The dynamic price calculation (e.g., Base Price - Discount).
    *   Clear indication that this is an option chosen via checkbox during booking.

### 1.4. Hidden Collapsible Lists & Accordions
*   **Query (VI):** "Liệt kê đầy đủ các tính năng trong gói hỗ trợ lái nâng cao ADAS của xe VF 6. Các thông số này nằm ở phần nào trên trang thông số kỹ thuật?"
*   **Expected Target Facts:**
    *   Detailed list of ADAS features (cảnh báo chệch làn, hỗ trợ giữ làn, phanh tự động khẩn cấp, v.v.).
    *   These facts must be fully extracted even if they are placed inside a collapsible accordion/tab labeled "Tính năng an toàn / ADAS".

### 1.5. VF 9 Colors & Configurations
*   **Query (VI):** "Có bao nhiêu màu cho các loại xe VF 9 Eco, Plus 7 chỗ, Plus cơ trưởng?"
*   **Expected Target Facts:**
    *   Color swatches and availability for each specific model trim (Eco vs. Plus 7-seat vs. Plus 6-seat/Captain chairs/Cơ trưởng).
    *   Dynamic price changes (surcharges) for premium colors (if applicable).
    *   Association of correct color names (e.g. Trắng, Đen, Xám, Xanh) with their specific trim configurations.

### 1.6. VF 9 Rolling Cost & Dynamic Surcharges
*   **Query (VI):** "Thống kê các khoản chi và chi phí lăn bánh cuối cùng là bao nhiêu khi tôi chọn VF 9 với các quyền lợi của mình?"
*   **Expected Target Facts:**
    *   Itemized registration fees (lệ phí trước bạ), plate fees (phí biển số), inspection fees, road maintenance fees, and insurance.
    *   Dynamic calculation of the final total on-road price (chi phí lăn bánh cuối cùng) grouped by selected configuration and province.
    *   Separation of base price, battery ownership cost (nếu mua đứt pin), and any membership/promotional voucher credits applied.

### 1.7. VF 9 Installment Calculation
*   **Query (VI):** "Dự toán trả góp hàng tháng cho xe VF 9 Plus khi vay 70% giá trị xe tại ngân hàng BIDV trong thời hạn 60 tháng là bao nhiêu?"
*   **Expected Target Facts:**
    *   Dynamic payment matrices based on Bank selection (e.g., BIDV, VietinBank), down payment (30% down / 70% loan), and duration (60 months).
    *   Expected monthly payment calculations (dynamic output from the installment calculator).
    *   Interest rate assumptions and total interest paid over the duration of the loan.

---

## 2. LLM Evaluation Prompts (System Prompts for Ingestion Verifier)

These prompts are used with the evaluation LLM (e.g. by enabling `--use-llm` in `verify_url_ingestion.py`) to systematically grade the quality of the ingested Markdown against the ground truth.

### 2.1. Structural & Formatting Verification Prompt
Use this prompt to check if tables and headings are preserved instead of being flattened into unreadable paragraphs.

```text
You are an expert auditor for RAG web-scraping pipelines.
Your task is to evaluate the structural integrity of the 'Actual Output' Markdown compared to the 'Ground Truth'.

Assert the following structural rules:
1. Data tables (such as specifications, editions, and color variants) must be formatted as clean Markdown tables.
2. Section headings (H1, H2, H3) must define distinct boundaries for each product model.
3. Pricing options must not be flattened into a single comma-separated line.

Input Actual Output:
{actual_md}

Input Ground Truth:
{ground_truth_md}

Provide a report listing:
- [ ] Pass/Fail on table preservation
- [ ] List of sections that lost hierarchy
- [ ] Suggested fixes for structural gaps
```

### 2.2. Hidden List & Accordion Completeness Prompt
Use this prompt to check if dynamic crawler elements (tabs, spec tables) were lost.

```text
You are an expert evaluator for RAG ingestion.
Analyze the 'Actual Output' to verify if collapsible accordions, specifications, and hidden dropdown options were fully extracted.

Check for the presence of:
1. Fully listed specifications (e.g. dimensions, battery capacity, suspension type, tire size).
2. Equipment detail lists that are usually hidden behind tabs (e.g., Exterior, Interior, Safety).

Identify if the actual output:
- Missed any hidden categories present in the Ground Truth.
- Flattened tab titles but omitted the tab bodies.

Provide a completeness score (0-100%) and list any missing specifications.
```

### 2.3. State-Aware Dynamic Pricing Prompt
Use this prompt to verify if interactive configuration states (colors, models, VinClub discount checkboxes) are accurately modeled.

```text
You are a Quality Assurance LLM evaluating a VinFast configurator crawler.
The crawler should capture different price states resulting from interactive options (changing colors, checking the VinClub discount checkbox, choosing buying vs. renting battery).

Analyze the 'Actual Output' and 'Evidence Corpus' for the following states:
1. VINCLUB DISCOUNT: Does the document specify the final discounted price when the VinClub discount checkbox is selected? Is the discount percentage associated with the member tier (Gold/Platinum/Diamond)?
2. EXTERIOR COLOR OPTION: Does the document capture that pricing or images change when selecting different color options (e.g. optional premium paint)?
3. BATTERY STATUS: Are the price options for "Mua xe kèm pin" (battery purchased) vs. "Mua xe thuê pin" (battery rented) clearly separated and not conflated?

Verify if these values are correctly grouped by state to prevent "cross-talk" (e.g., attributing a VinClub discounted price as the base MSRP, or attributing a renting-battery price to a purchasing-battery model).

Format your output as:
- VINCLUB CHECKBOX STATUS: [Captured / Missed / Conflated] (with details)
- COLOR PRICING STATUS: [Captured / Missed / Conflated] (with details)
- BATTERY PRICING STATUS: [Captured / Missed / Conflated] (with details)
```

---

## 3. Integration Guide

To run these checks, you can point your local verifier scripts in `guide_2/` to use these evaluation criteria.

1.  **Run Ingestion with Interactions Enabled**:
    ```bash
    uv run python guide_2/verify_url_ingestion.py \
      --url "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9" \
      --ground-truth-dir "guide_2/ground_truth/https-shop-vinfastauto-com-vn-vi-dat-coc-o-to-dien-vinfast-html-modelid-products-car-VF9" \
      --output-dir "guide_2/demo/verify_ingestion/output" \
      --use-llm
    ```

2.  **Verify local chunks directly**:
    Inspect `guide_2/demo/verify_ingestion/output/comparison_summary.json` to check the `text_similarity_ratio` and coverage of structured terms extracted from dynamic payloads.
