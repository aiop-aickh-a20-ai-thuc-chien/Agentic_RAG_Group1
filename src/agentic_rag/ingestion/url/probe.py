"""Interactive page probes for URL ingestion.

These probes extract important page state that is not reliably visible in static
HTML or default rendered Markdown. They are intentionally narrow and optional:
if probing fails, normal URL ingestion still works.
"""

from __future__ import annotations

import re
from importlib import import_module
from typing import Any
from urllib.parse import parse_qs, urlparse

VINFAST_CONFIGURATOR_STATE_SCRIPT = """
() => {
  const products = window.carDeposit?.products || {};
  const requestedModelId = new URL(window.location.href).searchParams.get('modelId');
  const modelId = requestedModelId || 'Products-Car-VF9';
  const model = products[modelId] || {};
  const editions = Object.entries(model)
    .filter(([, value]) => value && typeof value === 'object' && value.priceValue)
    .map(([editionCode, edition]) => {
      const basePrice = Number(edition.priceValue || 0);
      const colors = Object.entries(edition)
        .filter(([, value]) => value && typeof value === 'object' && value.price)
        .map(([colorCode, color]) => {
          const priceValue = Number(color.price?.value || 0);
          return {
            colorCode,
            colorLabel: color.label || color.name || colorCode,
            priceFormatted: color.price?.formatted || '',
            priceValue,
            priceDelta: priceValue > basePrice ? priceValue - basePrice : 0,
            available: color.available,
          };
        });
      return {
        editionCode,
        label: edition.label || edition.optionsName || editionCode,
        optionName: edition.optionsName || '',
        basePriceFormatted: edition.price || '',
        basePriceValue: basePrice,
        colors,
      };
    });
  const notes = Array.from(new Set((document.body?.innerText || '')
    .split(/\\n+/)
    .map((line) => line.trim())
    .filter((line) => line && /NEDC|quãng đường|quang duong/i.test(line))
  ));
  return {
    kind: 'vinfast_car_deposit_configurator',
    modelId,
    pageUrl: window.location.href,
    notes,
    editions,
  };
}
"""


def should_probe_interactive_state(url: str) -> bool:
    """Return whether this URL should attempt an interactive state probe."""

    parsed_url = urlparse(url)
    if parsed_url.netloc.lower() != "shop.vinfastauto.com":
        return False
    if not parsed_url.path.endswith("/dat-coc-o-to-dien-vinfast.html"):
        return False
    return bool(parse_qs(parsed_url.query).get("modelId"))


async def probe_interactive_markdown(url: str) -> str | None:
    """Probe dynamic page state and return Markdown records when available."""

    if not should_probe_interactive_state(url):
        return None
    state = await _probe_vinfast_configurator_state(url)
    return vinfast_configurator_state_to_markdown(state)


async def _probe_vinfast_configurator_state(url: str) -> dict[str, Any]:
    playwright_async_api = import_module("playwright.async_api")
    async_playwright = playwright_async_api.async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1200}, locale="vi-VN")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            state = await page.evaluate(VINFAST_CONFIGURATOR_STATE_SCRIPT)
        finally:
            await browser.close()

    if not isinstance(state, dict):
        raise RuntimeError("VinFast configurator probe returned invalid state.")
    return state


def vinfast_configurator_state_to_markdown(state: dict[str, Any]) -> str | None:
    """Convert VinFast configurator state into chunkable Markdown."""

    editions = state.get("editions")
    if not isinstance(editions, list) or not editions:
        return None

    lines = [
        "# Probed Interactive State",
        "",
        "## VinFast configurator price options",
        "",
    ]
    model_id = _text(state.get("modelId"))
    page_url = _text(state.get("pageUrl"))
    if model_id:
        lines.extend([f"- Model ID: {model_id}", ""])
    if page_url:
        lines.extend([f"- Page URL: {page_url}", ""])

    for edition in editions:
        if isinstance(edition, dict):
            lines.extend(_edition_markdown_lines(edition, model_id=model_id))

    notes = _unique_texts(state.get("notes"))
    if notes:
        lines.extend(["## VinFast configurator notes", ""])
        for note in notes:
            lines.append(f"- {note}")

    markdown = "\n".join(lines).strip()
    if markdown.count("Gia xe kem pin") == 0:
        return None
    return markdown


def _edition_markdown_lines(edition: dict[str, Any], *, model_id: str) -> list[str]:
    edition_code = _text(edition.get("editionCode"))
    label = _configurator_label(_text(edition.get("label")) or edition_code, model_id=model_id)
    base_price = _price_text(edition.get("basePriceFormatted"), edition.get("basePriceValue"))
    if not label or not base_price:
        return []

    lines = [f"### {label}", ""]
    if model_id and edition_code:
        lines.append(f"- Probe source: window.carDeposit.products.{model_id}.{edition_code}.")
    elif edition_code:
        lines.append(f"- Probe source edition code: {edition_code}.")
    lines.append("- Probe relation: this record represents one selectable configurator state.")
    lines.append(
        "- Price rule: final price / gia cuoi cung = base price of this exact "
        "variant + selected option delta; do not reuse a price from another variant."
    )
    lines.append(f"- {label}: base price / gia co ban / Gia xe kem pin {base_price}.")
    for color in _advanced_colors(edition):
        color_label = _text(color.get("colorLabel")) or _text(color.get("colorCode"))
        color_price = _price_text(color.get("priceFormatted"), color.get("priceValue"))
        price_delta = _price_text(None, color.get("priceDelta"))
        if not color_label or not color_price or not price_delta:
            continue
        lines.append(
            f"- {label} + {color_label}: final price / gia cuoi cung / Gia xe kem pin "
            f"{base_price} + {price_delta} = {color_price} "
            f"(option delta / phu phi mau nang cao + {price_delta})."
        )
    lines.append("")
    return lines


def _configurator_label(label: str, *, model_id: str) -> str:
    if not label:
        return ""
    if re.search(r"\bVF\s*-?\s*\d{1,2}\b", label, flags=re.IGNORECASE):
        return label
    model_label = _model_label_from_model_id(model_id)
    return f"{model_label} {label}".strip() if model_label else label


def _model_label_from_model_id(model_id: str) -> str:
    match = re.search(r"Products-Car-VF(\d{1,2})", model_id, flags=re.IGNORECASE)
    return f"VF {match.group(1)}" if match is not None else ""


def _advanced_colors(edition: dict[str, Any]) -> list[dict[str, Any]]:
    colors = edition.get("colors")
    if not isinstance(colors, list):
        return []
    advanced_colors = [
        color
        for color in colors
        if isinstance(color, dict) and _number(color.get("priceDelta")) > 0
    ]
    return advanced_colors[:6]


def _price_text(formatted: object, raw_value: object) -> str:
    formatted_text = _text(formatted)
    if formatted_text:
        return _normalize_vnd(formatted_text)
    value = _number(raw_value)
    if value <= 0:
        return ""
    return f"{value:,}".replace(",", ".") + " VND"


def _normalize_vnd(value: str) -> str:
    normalized = " ".join(value.replace("\xa0", " ").split())
    normalized = normalized.replace("VNĐ", "VND")
    if normalized.endswith("VND"):
        return normalized
    return f"{normalized} VND"


def _number(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _unique_texts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    texts: list[str] = []
    for item in value:
        text = _text(item)
        normalized = " ".join(text.split()).lower()
        if not text or normalized in seen:
            continue
        seen.add(normalized)
        texts.append(text)
    return texts
