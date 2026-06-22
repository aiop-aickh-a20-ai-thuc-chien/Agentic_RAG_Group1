from agentic_rag.ingestion.url.extractor import normalize_extracted_markdown


def test_normalize_extracted_markdown_adds_space_after_link() -> None:
    markdown = "[World Wide Web](https://en.wikipedia.org/wiki/World_Wide_Web)using"

    assert normalize_extracted_markdown(markdown) == (
        "[World Wide Web](https://en.wikipedia.org/wiki/World_Wide_Web) using"
    )


def test_normalize_extracted_markdown_joins_inline_link_continuation() -> None:
    markdown = (
        "using the\n\n"
        "[Hypertext Transfer Protocol](https://en.wikipedia.org/wiki/"
        "Hypertext_Transfer_Protocol)or a web browser."
    )

    assert normalize_extracted_markdown(markdown) == (
        "using the [Hypertext Transfer Protocol](https://en.wikipedia.org/wiki/"
        "Hypertext_Transfer_Protocol) or a web browser."
    )


def test_normalize_extracted_markdown_preserves_heading_breaks() -> None:
    markdown = "# Heading\n\n[Link](https://example.edu)text"

    assert normalize_extracted_markdown(markdown) == (
        "# Heading\n\n[Link](https://example.edu) text"
    )


def test_normalize_extracted_markdown_handles_link_urls_with_parentheses() -> None:
    markdown = (
        "[honeypot](https://en.wikipedia.org/wiki/Honeypot_(computing))or "
        "[Python](https://en.wikipedia.org/wiki/Python_(programming_language))script"
    )

    assert normalize_extracted_markdown(markdown) == (
        "[honeypot](https://en.wikipedia.org/wiki/Honeypot_(computing)) or "
        "[Python](https://en.wikipedia.org/wiki/Python_(programming_language)) script"
    )


def test_build_product_markdown_dynamic_model() -> None:
    from agentic_rag.ingestion.url.extractor import build_product_markdown

    product_data = {
        "is_vinfast": True,
        "model_name": "VF 7",
        "model_id": "Products-Car-VF7",
        "deposit_amount": "15.000.000 VNĐ",
        "specs": [
            ["Phân khúc", "C-SUV – SUV điện 5 chỗ"],
            ["Quãng đường (WLTP)", "430 km"],
            ["Công suất", "349 hp / 500 Nm"],
            ["Bảo hành xe", "10 năm hoặc 200.000 km"]
        ],
        "editions": {
            "VF7-Base": {
                "label": "Base",
                "price": "850.000.000",
                "priceValue": 850000000
            },
            "VF7-Plus": {
                "label": "Plus",
                "price": "999.000.000",
                "priceValue": 999000000
            }
        },
        "colors_config": {
            "defaultColor": "C_VF7_RED",
            "C_VF7_RED": {
                "label": "Red",
                "price": 0
            },
            "C_VF7_BLUE": {
                "label": "Blue",
                "price": 10000000
            }
        },
        "edition_details": {
            "VF7-Base": {
                "listColor": ["C_VF7_RED", "C_VF7_BLUE"],
                "listInterior": ["INT_VF7_DARK"],
                "C_VF7_RED": {
                    "INT_VF7_DARK": {
                        "label": "Dark Interior",
                        "pid": "VF-ZVEH-PE_VF7-VF7-Base-C_VF7_RED-INT_VF7_DARK"
                    }
                },
                "C_VF7_BLUE": {
                    "INT_VF7_DARK": {
                        "label": "Dark Interior",
                        "pid": "VF-ZVEH-PE_VF7-VF7-Base-C_VF7_BLUE-INT_VF7_DARK"
                    }
                }
            }
        },
        "rolling_cost_details": [
            ["Lệ phí trước bạ (0%)", "0 VNĐ"],
            ["Phí đăng kiểm", "340.000 VNĐ"],
            ["Tổng chi phí lăn bánh", "870.340.000 VNĐ"]
        ],
        "anchors": [
            {"text": "Giới thiệu", "href": "#section-intro"},
            {"text": "Ngoại thất", "href": "#section-product-exterior"},
            {"text": "Nội thất", "href": "#section-product-interior"}
        ],
        "title": "Xe điện VinFast VF 7 - Phong cách thiết kế tương lai"
    }

    markdown = build_product_markdown(product_data)
    
    assert "## 1. Thông tin xe" in markdown
    assert "Tên xe | VF 7" in markdown
    assert "Phân khúc | C-SUV – SUV điện 5 chỗ" in markdown
    assert "Quãng đường (WLTP) | 430 km" in markdown
    
    assert "## 2. Phiên bản & Giá niêm yết" in markdown
    assert "`VF7-Base` | Base | **850.000.000**" in markdown
    assert "`VF7-Plus` | Plus | **999.000.000**" in markdown
    
    assert "## 3. Đặt cọc" in markdown
    assert "Số tiền đặt cọc | **15.000.000 VNĐ**" in markdown
    assert 'CTA Label | "Đặt cọc 15.000.000 VNĐ"' in markdown
    assert "modelId=Products-Car-VF7" in markdown
    
    assert "## 4. Chi phí lăn bánh – Popup \"Chi tiết\"" in markdown
    assert "### Bảng chi tiết chi phí lăn bánh dự tính" in markdown
    assert "| Lệ phí trước bạ (0%) | 0 VNĐ |" in markdown
    assert "| Phí đăng kiểm | 340.000 VNĐ |" in markdown
    assert "| Tổng chi phí lăn bánh | 870.340.000 VNĐ |" in markdown
    
    assert "## 5. Màu ngoại thất (Exterior Colors)" in markdown
    assert "Hiển thị cho edition `VF7-Base` (Base). Màu đang chọn mặc định: **Red**." in markdown
    assert "| `C_VF7_RED` | Red ✅ *(mặc định đang chọn)* |" in markdown
    assert "| `C_VF7_BLUE` | Blue |" in markdown
    assert "### 5.2 Màu nâng cao (+10.000.000 VNĐ so với giá niêm yết phiên bản)" in markdown
    
    assert "## 6. Màu nội thất (Interior Colors)" in markdown
    assert "| Red | `C_VF7_RED` | Dark Interior (`INT_VF7_DARK`) |" in markdown
    assert "| Blue | `C_VF7_BLUE` | Dark Interior (`INT_VF7_DARK`) |" in markdown
    
    assert "## 7. Cấu trúc Product ID" in markdown
    assert "Model code: `PE_VF7`" in markdown
    assert "VF-ZVEH-PE_VF7-VF7-Base-C_VF7_RED-INT_VF7_DARK" in markdown
    
    assert "## 8. Điều hướng trang PDP" in markdown
    assert "1. Giới thiệu (`#section-intro`)" in markdown
    assert "2. Ngoại thất (`#section-product-exterior`)" in markdown
    assert "3. Nội thất (`#section-product-interior`)" in markdown
    
    assert "## 9. Ghi chú cho Scoring" in markdown
    assert "| Tiền đặt cọc | 15.000.000 VNĐ |" in markdown
    assert "| Số màu ngoại thất | 2 tổng (1 cơ bản, 1 nâng cao) |" in markdown
    
    assert "## 10. Tài liệu tham khảo & Ghi chú kỹ thuật" in markdown
    assert "Tiêu đề trang (page.title):** Xe điện VinFast VF 7 - Phong cách thiết kế tương lai" in markdown


def test_build_product_markdown_color_surcharge_from_label_and_total_price() -> None:
    from agentic_rag.ingestion.url.extractor import build_product_markdown

    product_data_total_prices = {
        "is_vinfast": True,
        "model_name": "VF 9",
        "model_id": "Products-Car-VF9",
        "deposit_amount": "50.000.000 VNĐ",
        "editions": {
            "NE3NV": {
                "label": "Plus",
                "price": "1.699.000.000",
                "priceValue": 1699000000
            }
        },
        "colors_config": {
            "defaultColor": "CE18",
            "CE18": {
                "label": "Infinity Blanc",
                "price": "1.731.000.000"
            },
            "CE22": {
                "label": "Ivy Green",
                "price": "1.743.000.000"
            }
        },
        "edition_details": {
            "NE3NV": {
                "listColor": ["CE18", "CE22"],
                "listInterior": ["CI11"],
                "CE18": {
                    "CI11": {
                        "label": "Dark",
                        "pid": "VF-ZVEH-PE1U_2023-NE3NV-CE18-CI11"
                    }
                },
                "CE22": {
                    "CI11": {
                        "label": "Dark",
                        "pid": "VF-ZVEH-PE1U_2023-NE3NV-CE22-CI11"
                    }
                }
            }
        }
    }

    markdown_total = build_product_markdown(product_data_total_prices)
    assert "### 5.1 Màu cơ bản – Theo xe (không phụ thu)" in markdown_total
    assert "| `CE18` | Infinity Blanc ✅" in markdown_total
    assert "### 5.2 Màu nâng cao (+12.000.000 VNĐ so với giá niêm yết phiên bản)" in markdown_total
    assert "| `CE22` | Ivy Green |" in markdown_total

    product_data_label_surcharge = {
        "is_vinfast": True,
        "model_name": "VF 9",
        "model_id": "Products-Car-VF9",
        "deposit_amount": "50.000.000 VNĐ",
        "editions": {
            "NE3NV": {
                "label": "Plus",
                "price": "1.699.000.000",
                "priceValue": 1699000000
            }
        },
        "colors_config": {
            "defaultColor": "CE18",
            "CE18": {
                "label": "Infinity Blanc"
            },
            "CE22": {
                "label": "Ivy Green (+12.000.000 VNĐ so với giá niêm yết phiên bản)"
            }
        },
        "edition_details": {
            "NE3NV": {
                "listColor": ["CE18", "CE22"],
                "listInterior": ["CI11"],
                "CE18": {
                    "CI11": {
                        "label": "Dark",
                        "pid": "VF-ZVEH-PE1U_2023-NE3NV-CE18-CI11"
                    }
                },
                "CE22": {
                    "CI11": {
                        "label": "Dark",
                        "pid": "VF-ZVEH-PE1U_2023-NE3NV-CE22-CI11"
                    }
                }
            }
        }
    }

    markdown_label = build_product_markdown(product_data_label_surcharge)
    assert "### 5.1 Màu cơ bản – Theo xe (không phụ thu)" in markdown_label
    assert "| `CE18` | Infinity Blanc ✅" in markdown_label
    assert "### 5.2 Màu nâng cao (+12.000.000 VNĐ so với giá niêm yết phiên bản)" in markdown_label
    # Parenthesized surcharge suffix should be cleaned/removed in the table
    assert "| `CE22` | Ivy Green |" in markdown_label


def test_build_product_markdown_vf9_premium_color_override() -> None:
    from agentic_rag.ingestion.url.extractor import build_product_markdown

    product_data = {
        "is_vinfast": True,
        "model_name": "VF 9",
        "model_id": "Products-Car-VF9",
        "deposit_amount": "50.000.000 VNĐ",
        "editions": {
            "NE3NV": {
                "label": "Plus",
                "price": "1.699.000.000",
                "priceValue": 1699000000
            }
        },
        "colors_config": {
            "defaultColor": "CE18",
            "CE18": {
                "label": "Infinity Blanc"
            },
            "CE22": {
                "label": "Ivy Green"
            },
            "CE17": {
                "label": "Desat Silver"
            }
        },
        "edition_details": {
            "NE3NV": {
                "listColor": ["CE18", "CE22", "CE17"],
                "listInterior": ["CI11"],
                "CE18": {
                    "CI11": {
                        "label": "Dark",
                        "pid": "VF-ZVEH-PE1U_2023-NE3NV-CE18-CI11"
                    }
                },
                "CE22": {
                    "CI11": {
                        "label": "Dark",
                        "pid": "VF-ZVEH-PE1U_2023-NE3NV-CE22-CI11"
                    }
                },
                "CE17": {
                    "CI11": {
                        "label": "Dark",
                        "pid": "VF-ZVEH-PE1U_2023-NE3NV-CE17-CI11"
                    }
                }
            }
        }
    }

    markdown = build_product_markdown(product_data)
    assert "### 5.1 Màu cơ bản – Theo xe (không phụ thu)" in markdown
    assert "| `CE18` | Infinity Blanc ✅" in markdown
    assert "### 5.2 Màu nâng cao (+12.000.000 VNĐ so với giá niêm yết phiên bản)" in markdown
    assert "| `CE22` | Ivy Green |" in markdown
    assert "| `CE17` | Desat Silver |" in markdown



