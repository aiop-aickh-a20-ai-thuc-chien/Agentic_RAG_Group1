# 🌐 VinFast Homepage & Portal Crawler Specification

This document details the crawling and extraction strategy for the **VinFast Main Portal / Homepage**.

- **Target URL**: `https://vinfastauto.com/vn_vi`
- **Objective**: Crawl static and dynamic portal components, including menus, promotional announcements, press releases/news articles, showroom/dealer networks, charging station specifications, and brochures.

---

## 1. Target Entities

The portal behaves as a distribution hub containing diverse content types:

```text
Portal Home
  ├── News Article (Title, Publish Date, Content Markdown, Tags)
  ├── Promotion Event (Discounts, Validity Dates, Applied Models)
  ├── Showroom/Dealer Node (Name, Address, Hotline, Services Available)
  ├── Charging Station Node (Location, Charger Types, Count, Status)
  └── Brochure/Catalog Link (Document URL, Vehicle Model, Language)
```

---

## 2. Interaction Flow & State Tree

Unlike booking sites, portal crawling is divided into navigation traversal, article pagination, and locator form selection:

### Interaction Modes
```
1. Menu Navigation: Scrape header/footer links to build site index map.
2. News Scraper:
   └── Visit news listing -> Paginate (Click Next) -> Scrape article content
3. Locator Scraper (Showrooms & Charging Stations):
   └── Select Province (select#province)
           └── Select District (select#district)
                   └── Capture: List of Showrooms & Chargers (.showroom-card)
```

---

## 3. Extraction Rules & Target Selectors

### A. News & Article Scraper
- **List Selectors**: Article cards `.news-item-card`, links `a.news-detail-link`
- **Article Details Selectors**:
  - Title: `h1.news-title`, `.article-detail__title`
  - Date: `.news-date`, `.article-detail__date`
  - Body Content (Convert to Markdown): `.news-content-body`, `.article-detail__content`
- **Output Schema**:
  ```json
  {
    "title": "VinFast Bàn Giao Xe VF 3 Đầu Tiên...",
    "published_date": "2024-08-01T10:00:00Z",
    "url": "https://vinfastauto.com/vn_vi/tin-tuc/...",
    "content_markdown": "# VinFast Bàn Giao Xe VF 3...\n\nNội dung bài viết...",
    "tags": ["VF3", "Bàn giao", "Sự kiện"]
  }
  ```

### B. Showroom & Dealer Locator
- **Locator Form Selectors**:
  - Province Select: `select.select-province`, `[data-placeholder="Chọn Tỉnh/Thành"]`
  - District Select: `select.select-district`
- **Card Selectors**: `.showroom-item`, `.dealer-card`
- **Scraped Fields per Card**:
  - Name, address, phone number, operating hours, coordinates (lat/lng from Google Maps link or data attributes), and type (3S, 1S, Authorized Dealer).
- **Output Schema**:
  ```json
  {
    "name": "VinFast Showroom Smart City",
    "address": "Tây Mỗ, Nam Từ Liêm, Hà Nội",
    "telephone": "1900 232389",
    "type": "3S",
    "lat": 21.0028,
    "lng": 105.7423
  }
  ```

### C. Charging Station Locator
- **Path**: Navigate to `Hệ thống trạm sạc` page.
- **Interactions**:
  - Select City/Province and Filter by Charger Type.
- **Scraped Fields**:
  - Location name, address, charger power (e.g. AC 11kW, DC 30kW, DC 60kW, DC 150kW, Supercharger DC 250kW), plug count, and status (Active/Maintenance).
- **Output Schema**:
  ```json
  {
    "station_name": "Trạm sạc Vinhomes Smart City S1.02",
    "address": "Tây Mỗ, Nam Từ Liêm, Hà Nội",
    "chargers": [
      { "type": "DC 60kW", "plugs": 4 },
      { "type": "AC 11kW", "plugs": 10 }
    ],
    "status": "active"
  }
  ```

---

## 4. Crawl Pacing & Sync Rules

- **Locator Dropdown Selection**: After choosing a province, delay `0.5 - 1.2 sec` before selecting a district, allowing AJAX responses to populate the sub-menu.
- **Page Pagination**: Wait `1.5 - 2.5 sec` after clicking "Next" page in news directory. Use `wait_for_selector` for the new page cards to avoid stale DOM exceptions.
- **API First Fallback**: Intercept and parse background REST requests (e.g., `/api/v1/showrooms`, `/api/v1/charging-stations`) to download showroom and charger locations in bulk instead of selecting dropdown options sequentially.
