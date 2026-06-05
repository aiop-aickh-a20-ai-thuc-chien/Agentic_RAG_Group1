"""Markdown cleanup adapted from the local Crawl link ingestion prototype."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

PRICE_RE = re.compile(
    r"(?:\d[\d.,]*\s*(?:VNĐ|VND|₫|đồng|dong|USD|US\$|\$|EUR|€|GBP|£|JPY|¥|KRW|₩|CNY|RMB|AUD|CAD|SGD|THB)\b"
    r"|(?:VNĐ|VND|₫|đồng|dong|USD|US\$|\$|EUR|€|GBP|£|JPY|¥|KRW|₩|CNY|RMB|AUD|CAD|SGD|THB)\s*\d[\d.,]*)",
    re.IGNORECASE,
)
PRICE_LINE_RE = re.compile(
    r"^\s*(?:(?:giá|gia)\s*(?:bán|ban|từ|tu|niêm yết|niem yet)?\s*:?\s*)?"
    r"(?:\d[\d.,]*\s*(?:VNĐ|VND|₫|đồng|dong|USD|US\$|\$|EUR|€|GBP|£|JPY|¥|KRW|₩|CNY|RMB|AUD|CAD|SGD|THB)\b"
    r"|(?:VNĐ|VND|₫|đồng|dong|USD|US\$|\$|EUR|€|GBP|£|JPY|¥|KRW|₩|CNY|RMB|AUD|CAD|SGD|THB)\s*\d[\d.,]*)\s*$",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
BREADCRUMB_SEP_RE = re.compile(r"\s[/›»>·•]\s|\s\|\s")
RELATED_SECTION_RE = re.compile(
    r"\b("
    r"san pham tuong tu|sản phẩm tương tự|related|similar|recommended|"
    r"you may also like|customers also|san pham lien quan|sản phẩm liên quan|"
    r"kham pha them|khám phá thêm|de xuat|đề xuất|goi y|gợi ý|"
    r"also viewed|also bought|ban cung co the thich|bạn cũng có thể thích|"
    r"xem them san pham|xem thêm sản phẩm"
    r")\b",
    re.IGNORECASE,
)
COOKIE_OR_PRIVACY_RE = re.compile(
    r"\b(cookie|cookies|privacy|quyen rieng tu|quyền riêng tư|consent|leg\.interest)\b",
    re.IGNORECASE,
)
UI_NOISE_RE = re.compile(
    r"^("
    r"minus|plus|label|checkbox label|start as guest|new topic|"
    r"tiep tuc|tiếp tục|ve dau trang|về đầu trang|xem them|xem thêm|"
    r"hien thi them|hiển thị thêm|doc them|đọc thêm|xem chi tiet|xem chi tiết|"
    r"show more|load more|xem tat ca|xem tất cả|back to top|scroll to top|"
    r"the maximum allowed file size is .+|trai nghiem cua ban the nao\??|"
    r"trải nghiệm của bạn thế nào\??"
    r")$",
    re.IGNORECASE,
)
CTA_RE = re.compile(
    r"\b("
    r"dang ky tu van|đăng ký tư vấn|dang ky lai thu|đăng ký lái thử|"
    r"dang ky ngay|đăng ký ngay|dat lich|đặt lịch|dat coc|đặt cọc|"
    r"mua ngay|lien he tu van|liên hệ tư vấn|nhan tu van|nhận tư vấn|"
    r"subscribe|sign up|contact us|request (?:a )?(?:quote|consultation|demo)|"
    r"book (?:now|a|an)"
    r")\b",
    re.IGNORECASE,
)
CHAT_NOISE_RE = re.compile(
    r"\b("
    r"tro ly ao|trợ lý ảo|chatbot|live chat|chat voi|chat với|"
    r"xin chao|xin chào|toi co the giup|tôi có thể giúp|"
    r"new topic|start as guest"
    r")\b",
    re.IGNORECASE,
)
CTA_FOLLOWUP_RE = re.compile(
    r"\b("
    r"nhan thong tin|nhận thông tin|thong tin chinh thuc|thông tin chính thức|"
    r"tu van tu|tư vấn từ|de duoc tu van|để được tư vấn|"
    r"our team|we will contact|learn more|get updates"
    r")\b",
    re.IGNORECASE,
)
DIALOG_NOISE_RE = re.compile(
    r"("
    r"dang tao don tren nhieu trinh duyet|đang tạo đơn trên nhiều trình duyệt|"
    r"dong bo don|đồng bộ đơn|"
    r"chi co the thanh toan cho don hang duoc tao gan nhat|"
    r"chỉ có thể thanh toán cho đơn hàng được tạo gần nhất|"
    r"xin loi vi su bat tien|xin lỗi vì sự bất tiện|"
    r"vui long thuc hien lai thao tac|vui lòng thực hiện lại thao tác|"
    r"evoucher chi ap dung|evoucher chỉ áp dụng|"
    r"da thanh toan mot so san pham trong gio hang|"
    r"đã thanh toán một số sản phẩm trong giỏ hàng|"
    r"gio hang .* cap nhap lai|giỏ hàng .* cập nhập lại"
    r")",
    re.IGNORECASE,
)
STATUS_PHRASE_RE = re.compile(
    r"("
    r"tam het hang|tạm hết hàng|het hang|hết hàng|sold out|out of stock|"
    r"unavailable|available|con hang|còn hàng|nhan tai showroom|nhận tại showroom|"
    r"co lap dat|có lắp đặt"
    r")",
    re.IGNORECASE,
)
NAV_SECTION_WORDS = {
    "tien ich",
    "utilities",
    "mua sam",
    "shopping",
    "shop",
    "tin tuc",
    "news",
    "ho tro",
    "support",
    "help",
    "thao luan",
    "discussion",
    "ve chung toi",
    "about us",
    "ket noi",
    "connect",
}
ARTICLE_WORDS = ("tin tuc", "news", "article", "press", "blog", "cong ty", "community")
FAQ_WORDS = ("faq", "cau hoi", "hoi dap", "thuong gap", "questions", "answers")
POLICY_WORDS = (
    "dieu khoan",
    "phap ly",
    "chinh sach",
    "policy",
    "privacy",
    "terms",
    "quy che",
    "bao mat",
)
SERVICE_WORDS = (
    "dich vu",
    "bao duong",
    "bao hanh",
    "cuu ho",
    "service",
    "maintenance",
    "warranty",
    "repair",
)
PRODUCT_WORDS = (
    "san pham",
    "product",
    "chi tiet san pham",
    "gia ban",
    "thong so",
    "dat coc",
    "mua ngay",
    "cart",
    "checkout",
)
SPEC_WORDS = (
    "cong suat",
    "quang duong",
    "toc do",
    "kich thuoc",
    "dung luong",
    "thoi gian sac",
    "mo men",
    "dan dong",
    "he thong phanh",
    "pin",
    "hp",
    "kw",
    "kwh",
    "km/h",
    "mm",
    "inch",
)
PRODUCT_UI_SECTION_WORDS = {
    "dat san pham",
    "order product",
    "add to cart",
    "tong tien",
    "total",
    "thong bao",
    "notification",
    "notice",
}

_INLINE_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((?:[^()\n]|\([^()\n]*\))*\)")


def normalize_text(text: str) -> str:
    """Collapse whitespace and lowercase a value for matching."""

    return re.sub(r"\s+", " ", text or "").strip().lower()


def fold_text(text: str) -> str:
    """Fold Vietnamese accents for tolerant rule matching."""

    normalized = (text or "").replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFKD", normalized)
    return normalize_text("".join(ch for ch in normalized if not unicodedata.combining(ch)))


def normalize_markdown(
    markdown: str,
    *,
    page: Mapping[str, object] | None = None,
    page_type: str | None = None,
) -> tuple[str, dict[str, object]]:
    """Remove obvious UI/noise lines and compact repeated product cards."""

    inferred_page_type = page_type or classify_page(page or {"markdown": markdown})[0]
    markdown = _INLINE_LINK_RE.sub(r"\1", markdown)
    lines = markdown.split("\n")
    out: list[str] = []
    removed = {
        "breadcrumb": 0,
        "ui_noise": 0,
        "cookie_privacy": 0,
        "nav_section": 0,
        "aggregate": 0,
    }
    mapped_cards = 0
    first_h1_seen = False
    skip_section_level: int | None = None
    skip_section_reason: str | None = None
    skip_cta_followup = False
    related_depth: int | None = None
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        level = heading_level(stripped)

        if level:
            if skip_section_level is not None and level <= skip_section_level:
                skip_section_level = None
                skip_section_reason = None
            skip_cta_followup = False
            if related_depth is not None and level <= related_depth:
                related_depth = None
            if stripped.startswith("# "):
                first_h1_seen = True
            if is_cookie_or_privacy_heading(stripped):
                skip_section_level = level
                skip_section_reason = "cookie_privacy"
                removed["cookie_privacy"] += 1
                index += 1
                continue
            if is_nav_section_heading(stripped):
                skip_section_level = level
                skip_section_reason = "nav_section"
                removed["nav_section"] += 1
                index += 1
                continue
            if inferred_page_type in {"product", "listing"} and is_product_ui_section_heading(
                stripped
            ):
                skip_section_level = level
                skip_section_reason = "ui_noise"
                removed["ui_noise"] += 1
                index += 1
                continue
            if is_cta_noise(stripped):
                removed["ui_noise"] += 1
                skip_cta_followup = True
                index += 1
                continue
            if RELATED_SECTION_RE.search(heading_text(stripped)):
                related_depth = level

        if skip_section_level is not None:
            if skip_section_reason in removed:
                removed[skip_section_reason] += int(bool(stripped))
            index += 1
            continue
        if stripped and not first_h1_seen and looks_like_breadcrumb(stripped):
            removed["breadcrumb"] += 1
            index += 1
            continue
        if stripped and COOKIE_OR_PRIVACY_RE.search(stripped) and len(stripped) > 80:
            removed["cookie_privacy"] += 1
            index += 1
            continue
        if stripped and is_ui_noise(stripped):
            removed["ui_noise"] += 1
            index += 1
            continue
        if stripped and is_cta_noise(stripped):
            removed["ui_noise"] += 1
            skip_cta_followup = True
            index += 1
            continue
        if skip_cta_followup:
            if not stripped:
                index += 1
                continue
            if is_cta_followup(stripped):
                removed["ui_noise"] += 1
                index += 1
                continue
            skip_cta_followup = False
        if stripped and is_aggregate_of_following(lines, index):
            removed["aggregate"] += 1
            index += 1
            continue
        if (
            related_depth is not None
            and stripped
            and not level
            and inferred_page_type in {"product", "listing", "generic"}
        ):
            mapped, consumed = map_related_card(lines, index)
            if mapped:
                out.append(mapped)
                mapped_cards += 1
                index += consumed
                continue

        out.append(line)
        index += 1

    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return text, {
        "content_type": inferred_page_type,
        "removed": removed,
        "mapped_cards": mapped_cards,
        "n_chars_before": len(markdown or ""),
        "n_chars_after": len(text),
    }


def classify_page(row: Mapping[str, object]) -> tuple[str, dict[str, int]]:
    """Infer broad page type to make cleanup less aggressive on non-product pages."""

    url = str(row.get("url", ""))
    title = str(row.get("main_title") or row.get("title") or "")
    markdown = str(row.get("markdown", ""))
    haystack = "\n".join([url, title, markdown[:4000]])
    title_url = "\n".join([url, title])
    scores = {"product": 0, "faq": 0, "policy": 0, "service": 0, "article": 0, "listing": 0}

    if bool(row.get("is_product")) or bool(row.get("product")):
        scores["product"] += 4
    if PRICE_RE.search(markdown[:2500]):
        scores["product"] += 2
    if RELATED_SECTION_RE.search(markdown):
        scores["product"] += 2
    if contains_any(haystack, PRODUCT_WORDS):
        scores["product"] += 1
    if contains_any(haystack, SPEC_WORDS):
        scores["product"] += 2
    spec_like_lines = 0
    for line in markdown.split("\n")[:80]:
        folded = fold_text(line)
        if any(word in folded for word in SPEC_WORDS) or re.search(
            r"\b\d+(?:[.,]\d+)?\s*(?:kw|kwh|km/h|mm|inch|hp|nm)\b",
            folded,
        ):
            spec_like_lines += 1
    if spec_like_lines >= 6:
        scores["product"] += 2
    if contains_any(haystack, FAQ_WORDS):
        scores["faq"] += 3
    if contains_any(title_url, FAQ_WORDS):
        scores["faq"] += 3
    if len(re.findall(r"\?", markdown[:5000])) >= 3:
        scores["faq"] += 1
    if contains_any(haystack, POLICY_WORDS):
        scores["policy"] += 3
    if contains_any(title_url, POLICY_WORDS):
        scores["policy"] += 3
    if len(re.findall(r"(?m)^\s*(?:\d+\.){1,3}\s+", markdown)) >= 8:
        scores["policy"] += 1
    if contains_any(haystack, SERVICE_WORDS):
        scores["service"] += 3
    if contains_any(title_url, SERVICE_WORDS):
        scores["service"] += 3
    if contains_any(haystack, ARTICLE_WORDS):
        scores["article"] += 2
    if contains_any(title_url, ARTICLE_WORDS):
        scores["article"] += 3
    if re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", markdown[:8000]):
        scores["article"] += 1
    if len(re.findall(r"^-\s+", markdown, flags=re.MULTILINE)) >= 20 and PRICE_RE.search(markdown):
        scores["listing"] += 2
    if scores["product"] >= 3:
        scores["policy"] = max(0, scores["policy"] - 1)
        scores["article"] = max(0, scores["article"] - 1)
        scores["faq"] = max(0, scores["faq"] - 2)
    if (
        scores["service"] >= 3
        and not PRICE_RE.search(markdown[:2500])
        and not RELATED_SECTION_RE.search(markdown)
    ):
        scores["product"] = max(0, scores["product"] - 3)
    elif scores["service"] >= 3 and scores["product"] <= 3:
        scores["product"] = max(0, scores["product"] - 2)

    priority = {"faq": 5, "service": 4, "policy": 3, "article": 2, "product": 1, "listing": 0}
    page_type = max(scores, key=lambda key: (scores[key], priority.get(key, 0)))
    return (page_type if scores[page_type] > 0 else "generic"), scores


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    folded = fold_text(text)
    return any(word in folded for word in words)


def heading(line: str) -> re.Match[str] | None:
    return HEADING_RE.match(line or "")


def heading_level(line: str) -> int:
    match = heading(line)
    return len(match.group(1)) if match else 0


def heading_text(line: str) -> str:
    match = heading(line)
    return match.group(2).strip() if match else ""


def is_price(line: str) -> bool:
    return PRICE_RE.search(line or "") is not None


def is_price_line(line: str) -> bool:
    return PRICE_LINE_RE.match(line or "") is not None


def is_status(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    rest = STATUS_PHRASE_RE.sub("", stripped)
    rest = re.sub(r"[\s/|,;:\-]+", "", rest)
    return rest == ""


def is_ui_noise(line: str) -> bool:
    stripped = (line or "").strip()
    return (
        UI_NOISE_RE.match(stripped) is not None
        or DIALOG_NOISE_RE.search(stripped) is not None
        or CHAT_NOISE_RE.search(stripped) is not None
    )


def is_cta_noise(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    text = heading_text(stripped) if heading(stripped) else stripped
    return len(text) <= 180 and CTA_RE.search(text) is not None


def is_cta_followup(line: str) -> bool:
    stripped = (line or "").strip()
    return bool(
        stripped
        and not heading(stripped)
        and len(stripped) <= 180
        and CTA_FOLLOWUP_RE.search(stripped)
    )


def is_cookie_or_privacy_heading(line: str) -> bool:
    text = heading_text(line) if heading(line) else line
    return COOKIE_OR_PRIVACY_RE.search(text or "") is not None


def is_nav_section_heading(line: str) -> bool:
    level = heading_level(line)
    return bool(level and level >= 4 and fold_text(heading_text(line)) in NAV_SECTION_WORDS)


def is_product_ui_section_heading(line: str) -> bool:
    level = heading_level(line)
    return bool(level and fold_text(heading_text(line)) in PRODUCT_UI_SECTION_WORDS)


def looks_like_breadcrumb(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped or heading(stripped) or stripped.startswith(("- ", "|")):
        return False
    if len(stripped) > 180 or BREADCRUMB_SEP_RE.search(stripped) is None:
        return False
    parts = [part.strip() for part in BREADCRUMB_SEP_RE.split(stripped) if part.strip()]
    return 2 <= len(parts) <= 8 and all(len(part) <= 80 for part in parts)


def is_aggregate_of_following(lines: list[str], index: int) -> bool:
    current = normalize_text(lines[index])
    if not current or heading(lines[index]):
        return False
    for count in range(2, 5):
        if index + count >= len(lines):
            break
        window = [lines[index + offset].strip() for offset in range(1, count + 1)]
        if any(not item or heading(item) for item in window):
            continue
        joined = normalize_text(" ".join(window))
        has_card_signal = any(is_price(item) or is_status(item) for item in window)
        if has_card_signal and joined == current:
            return True
    return False


def is_probable_title(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped or heading(stripped) or stripped.startswith(("- ", "|")):
        return False
    if is_price(stripped) or is_status(stripped) or is_ui_noise(stripped):
        return False
    return 2 <= len(stripped) <= 120


def split_title_price(line: str) -> tuple[str, str]:
    match = PRICE_RE.search(line or "")
    if not match:
        return "", ""
    title = ((line or "")[: match.start()] + " " + (line or "")[match.end() :]).strip()
    title = re.sub(r"\s+", " ", title).strip(" -:|")
    price = match.group(0).strip()
    if not title or not is_probable_title(title):
        return "", ""
    return title, price


def split_title_status(line: str) -> tuple[str, str]:
    matches = list(STATUS_PHRASE_RE.finditer(line or ""))
    if not matches:
        return "", ""
    first = matches[0]
    title = (line or "")[: first.start()].strip(" -:|")
    status = (line or "")[first.start() :].strip(" -:|")
    if not title or not is_probable_title(title) or not is_status(status):
        return "", ""
    return title, status


def map_related_card(lines: list[str], index: int) -> tuple[str | None, int]:
    current = lines[index].strip()
    title_from_price, price = split_title_price(current)
    if title_from_price:
        consumed = 1
        if index + 1 < len(lines) and normalize_text(lines[index + 1]) == normalize_text(
            title_from_price
        ):
            consumed = 2
        return f"- {title_from_price}: {price}", consumed

    title_from_status, status = split_title_status(current)
    if title_from_status:
        consumed = 1
        if index + 1 < len(lines) and normalize_text(lines[index + 1]) == normalize_text(
            title_from_status
        ):
            consumed = 2
            if index + 2 < len(lines) and is_status(lines[index + 2]):
                consumed = 3
        return f"- {title_from_status}: {status}", consumed

    title = current
    if not is_probable_title(title):
        return None, 0
    fields: list[str] = []
    cursor = index + 1
    while cursor < len(lines) and len(fields) < 3:
        item = lines[cursor].strip()
        if not item or heading(item):
            break
        if is_price_line(item) or is_status(item):
            fields.append(item)
            cursor += 1
            continue
        break
    if fields:
        return f"- {title}: {' / '.join(fields)}", 1 + len(fields)
    return None, 0
