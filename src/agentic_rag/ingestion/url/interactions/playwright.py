"""Optional Playwright-backed rule-based interaction capture."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, cast

from agentic_rag.ingestion.url.chunking import (
    normalize_for_content_hash,
    normalize_space,
    short_hash,
    slugify,
)
from agentic_rag.ingestion.url.interactions.extractor import (
    extract_interaction_states_from_html,
    extract_specifications_from_text,
)
from agentic_rag.ingestion.url.interactions.models import (
    InteractionCaptureResult,
    InteractionControl,
    InteractionOptions,
    InteractionPanelDiff,
    InteractionPanelSnapshot,
    InteractionProfile,
    InteractionStateRecord,
    PanelRole,
)

_MAX_NETWORK_PAYLOADS = 50
_MAX_PAYLOAD_CHARS = 20_000
_GAIN_ENTITY_RE = re.compile(
    r"\b(?:VinFast\s+)?VF\s*-?\s?\d{1,2}(?:\s+(?:Eco|Plus|Lux|S|Base|Premium))?\b",
    re.IGNORECASE,
)
_PANEL_ROLES: tuple[PanelRole, ...] = (
    "left_panel",
    "center_visual",
    "right_panel",
    "unknown",
)
_MODEL_NAME_RE = re.compile(r"\b(?:VinFast\s+)?VF\s*-?\s?\d{1,2}\b", re.IGNORECASE)

_DISCOVER_CONTROLS_JS = r"""
() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && style.opacity !== '0'
      && rect.width > 0
      && rect.height > 0;
  };
  const BLOCK_LABEL = new RegExp([
    'dat\\s*coc\\s*(ngay|xe)',
    'thanh\\s*toan',
    'checkout',
    'submit',
    'buy\\s*now',
    'mua\\s*ngay',
    'login',
    'dang\\s*nhap',
    'account',
    'cart',
    'gio\\s*hang',
    'support',
    'hotline'
  ].join('|'), 'i');
  const OPTION_CLASS = new RegExp([
    '(^|[\\s_-])',
    '(color|colour|swatch|variant|option|trim|battery|model|package)',
    '|(spec|specification|technical|detail|thong\\s*so|chi\\s*tiet)',
    '([\\s_-]|$)'
  ].join(''), 'i');
  const TEXT = el => (
    el.innerText ||
    el.textContent ||
    el.getAttribute('aria-label') ||
    el.getAttribute('title') ||
    ''
  ).trim().replace(/\s+/g, ' ');
  const SELECTOR_ATTR = 'data-url-ingestion-interaction-id';
  const candidates = Array.from(document.querySelectorAll([
    'a[data-bs-toggle="modal"]',
    'a[data-toggle="modal"]',
    'a[data-bs-target]',
    'a[data-target]',
    'button',
    '[role="button"]',
    '[role="radio"]',
    '[role="tab"]',
    '[aria-expanded]',
    '[data-bs-toggle="modal"]',
    '[data-toggle="modal"]',
    '[data-bs-target]',
    '[data-target]',
    'input[type="radio"]',
    '[data-option-group]',
    '[data-option-label]',
    '.color-swatch',
    '.variant-card',
    '.option-card',
    '[class*="spec"]',
    '[class*="technical"]',
    '[class*="detail"]',
    '[data-testid*="spec"]',
    '[data-testid*="technical"]',
    '[data-testid*="detail"]'
  ].join(',')));
  const controls = [];
  let index = 0;
  for (const el of candidates) {
    if (!visible(el)) continue;
    const tag = el.tagName.toLowerCase();
    const label = (
      TEXT(el) ||
      el.value ||
      el.getAttribute('data-option-label') ||
      el.getAttribute('aria-label') ||
      ''
    );
    const cls = el.getAttribute('class') || '';
    const role = el.getAttribute('role') || '';
    const hasOptionAttr = (
      el.hasAttribute('data-option-group') ||
      el.hasAttribute('data-option-label')
    );
    const hasModalAttr = (
      el.getAttribute('data-bs-toggle') === 'modal' ||
      el.getAttribute('data-toggle') === 'modal' ||
      el.hasAttribute('data-bs-target') ||
      el.hasAttribute('data-target')
    );
    if (!label || BLOCK_LABEL.test(label)) continue;
    if (
      !hasModalAttr &&
      !hasOptionAttr &&
      !OPTION_CLASS.test(cls) &&
      !['button','radio','tab'].includes(role)
    ) continue;
    const disabled = (
      el.disabled ||
      el.getAttribute('aria-disabled') === 'true' ||
      el.getAttribute('data-disabled') === 'true'
    );
    const panelRole = inferPanelRole(el);
    const panelId = nearestPanelId(el, panelRole);
    const rect = el.getBoundingClientRect();
    index += 1;
    const id = `url-interaction-${index}`;
    el.setAttribute(SELECTOR_ATTR, id);
    controls.push({
      control_id: id,
      label,
      group: (
        el.getAttribute('data-option-group') ||
        el.getAttribute('name') ||
        inferGroup(label, cls)
      ),
      selector: `[${SELECTOR_ATTR}="${id}"]`,
      panel_role: panelRole,
      panel_id: panelId,
      disabled,
      attributes: {
        class: cls,
        role,
        href: el.getAttribute('href') || '',
        'aria-expanded': el.getAttribute('aria-expanded') || '',
        'aria-label': el.getAttribute('aria-label') || '',
        'data-bs-toggle': el.getAttribute('data-bs-toggle') || '',
        'data-toggle': el.getAttribute('data-toggle') || '',
        'data-bs-target': el.getAttribute('data-bs-target') || '',
        'data-target': el.getAttribute('data-target') || '',
        'data-option-group': el.getAttribute('data-option-group') || '',
        'data-option-label': el.getAttribute('data-option-label') || '',
        'data-price': el.getAttribute('data-price') || '',
        'data-image': el.getAttribute('data-image') || '',
        'data-model-name': el.getAttribute('data-model-name') || '',
        'bbox': [
          Math.round(rect.left),
          Math.round(rect.top),
          Math.round(rect.width),
          Math.round(rect.height)
        ].join(',')
      }
    });
  }
  function inferGroup(label, cls) {
    const text = `${label} ${cls}`.toLowerCase();
    const specRe = /(spec|specification|technical|thong\s*so|chi\s*tiet|detail)/;
    if (
      /chi\s*tiet|detail/.test(text) ||
      cls.includes('modal') ||
      cls.includes('cost-more')
    ) return 'details';
    if (specRe.test(text)) return 'specifications';
    if (/(color|colour|swatch|mau)/.test(text)) return 'color';
    if (/(battery|pin)/.test(text)) return 'battery';
    if (/(trim|variant|version|phien ban)/.test(text)) return 'variant';
    return 'option';
  }
  function nearestPanelId(el, role) {
    const panel = el.closest([
      '[id]',
      '[data-panel]',
      '[data-section]',
      '[class*="panel"]',
      '[class*="summary"]',
      '[class*="option"]',
      '[class*="modal"]',
      '[role="dialog"]',
      'aside',
      'section',
      'form'
    ].join(','));
    if (!panel) return role;
    return panel.id ||
      panel.getAttribute('data-panel') ||
      panel.getAttribute('data-section') ||
      role;
  }
  function inferPanelRole(el) {
    const rect = el.getBoundingClientRect();
    const width = Math.max(window.innerWidth || 1366, 1);
    const centerX = rect.left + (rect.width / 2);
    const haystack = `${TEXT(el)} ${el.getAttribute('class') || ''} ${el.id || ''}`.toLowerCase();
    const rightPanelRe = new RegExp([
      'summary',
      'price',
      'payment',
      'finance',
      'deposit',
      'total',
      'right',
      'cart',
      'gio hang',
      'spec',
      'technical',
      'thong so',
      'chi tiet',
      'modal',
      'dialog',
      'popup'
    ].join('|'));
    if (rightPanelRe.test(haystack)) {
      return 'right_panel';
    }
    if (/(gallery|image|photo|media|visual|preview|carousel|slide)/.test(haystack)) {
      return 'center_visual';
    }
    if (/(option|control|config|variant|trim|color|swatch|battery|package|left)/.test(haystack)) {
      return 'left_panel';
    }
    if (centerX > width * 0.64) return 'right_panel';
    if (centerX < width * 0.38) return 'left_panel';
    if (centerX >= width * 0.38 && centerX <= width * 0.64) return 'center_visual';
    return 'unknown';
  }
  return controls;
}
"""

_CAPTURE_PANELS_JS = r"""
({ sourceControlId, interactionStep }) => {
  const PRICE_RE = /\b\d[\d.,]*(?:\s*(?:VND|VN\u0110|\u0111|dong|USD|US\$|\$)|\s*\u20ab)\b/ig;
  const roles = ['left_panel', 'center_visual', 'right_panel', 'unknown'];
  const buckets = Object.fromEntries(roles.map((role) => [role, {
    panel_role: role,
    panel_id: role,
    interaction_step: interactionStep,
    source_control_id: sourceControlId || null,
    text_parts: [],
    price_values: [],
    image_urls: [],
    table_count: 0,
    node_signatures: []
  }]));
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && style.opacity !== '0'
      && rect.width > 0
      && rect.height > 0;
  };
  const textOf = (el) => (
    el.innerText ||
    el.textContent ||
    el.getAttribute('aria-label') ||
    el.getAttribute('alt') ||
    el.getAttribute('title') ||
    ''
  ).trim().replace(/\s+/g, ' ');
  const addUnique = (items, value, maxItems) => {
    const clean = String(value || '').trim();
    if (!clean || items.includes(clean)) return;
    if (items.length < maxItems) items.push(clean);
  };
  const nodeSignature = (el, text) => {
    const tag = el.tagName.toLowerCase();
    const id = el.id || '';
    const cls = (el.getAttribute('class') || '').split(/\s+/).slice(0, 3).join('.');
    return `${tag}#${id}.${cls}:${text.slice(0, 120)}`;
  };
  const imageUrl = (el) => {
    const absolutize = (value) => {
      if (!value) return '';
      try {
        return new URL(value, document.baseURI).href;
      } catch {
        return String(value || '');
      }
    };
    if (el.currentSrc) return absolutize(el.currentSrc);
    if (el.src) return absolutize(el.src);
    if (el.getAttribute('data-src')) return absolutize(el.getAttribute('data-src'));
    const bg = window.getComputedStyle(el).backgroundImage || '';
    const match = bg.match(/url\(["']?([^"')]+)["']?\)/);
    return match ? absolutize(match[1]) : '';
  };
  const inferPanelRole = (el) => {
    const rect = el.getBoundingClientRect();
    const width = Math.max(window.innerWidth || 1366, 1);
    const centerX = rect.left + (rect.width / 2);
    const text = textOf(el).slice(0, 400);
    const haystack = `${text} ${el.getAttribute('class') || ''} ${el.id || ''}`.toLowerCase();
    const rightPanelRe = new RegExp([
      'summary',
      'price',
      'payment',
      'finance',
      'deposit',
      'total',
      'right',
      'cart',
      'gio hang',
      'tam tinh',
      'spec',
      'technical',
      'thong so',
      'chi tiet',
      'modal',
      'dialog',
      'popup'
    ].join('|'));
    const leftPanelRe = new RegExp([
      'option',
      'control',
      'config',
      'variant',
      'trim',
      'color',
      'swatch',
      'battery',
      'package',
      'left',
      'phien ban',
      'mau'
    ].join('|'));
    if (rightPanelRe.test(haystack)) {
      return 'right_panel';
    }
    if (
      /(gallery|image|photo|media|visual|preview|carousel|slide|swiper|img)/.test(haystack) ||
      el.tagName.toLowerCase() === 'img'
    ) {
      return 'center_visual';
    }
    if (leftPanelRe.test(haystack)) {
      return 'left_panel';
    }
    if (centerX > width * 0.64) return 'right_panel';
    if (centerX < width * 0.38) return 'left_panel';
    if (centerX >= width * 0.38 && centerX <= width * 0.64) return 'center_visual';
    return 'unknown';
  };
  const nodes = Array.from(document.querySelectorAll([
    'h1','h2','h3','h4','h5','h6','p','li','dt','dd','th','td',
    'tr','table','dl',
    'button','[role="button"]','[role="radio"]','[role="tab"]',
    '[role="dialog"]','dialog','.modal-body',
    'label','span','strong','em','img','picture','figure',
    '[class*="price"]','[class*="summary"]','[class*="option"]',
    '[class*="swatch"]','[class*="variant"]','[class*="image"]',
    '[class*="gallery"]','[class*="carousel"]',
    '[class*="modal"]','[class*="modal-body"]','[class*="popup"]','[class*="dialog"]',
    '[class*="spec"]','[class*="technical"]','[class*="detail"]'
  ].join(',')));
  for (const el of nodes) {
    if (!visible(el)) continue;
    const role = inferPanelRole(el);
    const bucket = buckets[role] || buckets.unknown;
    const text = textOf(el);
    if (el.tagName.toLowerCase() === 'table') bucket.table_count += 1;
    if (text) {
      addUnique(bucket.text_parts, text.slice(0, 240), 80);
      addUnique(bucket.node_signatures, nodeSignature(el, text), 120);
      const prices = text.match(PRICE_RE) || [];
      for (const price of prices) addUnique(bucket.price_values, price.replace(/\s+/g, ' '), 20);
    }
    const url = imageUrl(el);
    if (url) addUnique(bucket.image_urls, url, 30);
  }
  return roles.map((role) => {
    const bucket = buckets[role];
    return {
      panel_role: bucket.panel_role,
      panel_id: bucket.panel_id,
      interaction_step: bucket.interaction_step,
      source_control_id: bucket.source_control_id,
      text: bucket.text_parts.join('\n').slice(0, 6000),
      price_values: bucket.price_values,
      image_urls: bucket.image_urls,
      table_count: bucket.table_count,
      node_signatures: bucket.node_signatures
    };
  });
}
"""


def capture_interaction_states_with_playwright(
    url: str,
    *,
    options: InteractionOptions | None = None,
) -> InteractionCaptureResult:
    """Render a URL, click safe option controls, and extract state records."""

    capture_options = options or InteractionOptions()
    try:
        sync_playwright = cast(Any, import_module("playwright.sync_api")).sync_playwright
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("Python Playwright is not installed.") from exc

    captured_payloads: list[dict[str, object]] = []
    captured_html: str | None = None
    errors: list[str] = []
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ],
            )
        except Exception:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ],
            )
        import random
        width = random.randint(1280, 1920)
        height = random.randint(800, 1080)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": width, "height": height},
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
        )
        page = context.new_page()
        page.on("response", lambda response: _capture_json_response(response, captured_payloads))
        try:
            page.goto(
                url,
                wait_until=capture_options.wait_until,
                timeout=capture_options.timeout_seconds * 1000,
            )
            page.wait_for_timeout(capture_options.settle_after_click_ms)
            
            # Dismiss cookie consent/OneTrust banner if present
            try:
                for cookie_selector in (
                    "#onetrust-accept-btn-handler",
                    "#btn-accept-cookie",
                    ".cookie-agree",
                    "button:has-text('Accept')",
                    "button:has-text('Đồng ý')",
                ):
                    locator = page.locator(cookie_selector)
                    if locator.is_visible(timeout=1000):
                        locator.click(timeout=2000)
                        page.wait_for_timeout(500)
                        break
            except Exception:
                pass
            captured_html = cast(str, page.content())
            result = extract_interaction_states_from_html(
                captured_html,
                requested_url=url,
                final_url=cast(str, page.url),
                captured_at=_utc_now(),
                network_payloads=captured_payloads,
                options=capture_options,
            )
            controls = _discover_controls(page)
            all_controls = [*result.controls, *controls]
            fallback_states = list(result.states)
            clicked_states: list[InteractionStateRecord] = []
            skipped_controls = list(result.skipped_controls)
            panel_snapshots = _capture_panel_snapshots(
                page,
                interaction_step="baseline",
            )
            panel_diffs: list[InteractionPanelDiff] = []
            for control in controls[: capture_options.max_states]:
                if control.disabled:
                    skipped_controls.append(
                        control.model_copy(update={"skipped_reason": "disabled"})
                    )
                    continue
                if control.selector is None:
                    skipped_controls.append(
                        control.model_copy(update={"skipped_reason": "missing_selector"})
                    )
                    continue
                before_snapshots = _capture_panel_snapshots(
                    page,
                    interaction_step=f"before:{control.control_id}",
                    source_control_id=control.control_id,
                )
                before_payload_count = len(captured_payloads)
                try:
                    page.locator(control.selector).click(timeout=3000)
                    page.wait_for_timeout(capture_options.settle_after_click_ms)
                except Exception as exc:
                    skipped_controls.append(
                        control.model_copy(update={"skipped_reason": f"click_failed:{exc}"})
                    )
                    continue
                after_snapshots = _capture_panel_snapshots(
                    page,
                    interaction_step=f"after:{control.control_id}",
                    source_control_id=control.control_id,
                )
                panel_snapshots.extend([*before_snapshots, *after_snapshots])
                panel_diff = _build_panel_diff(
                    control=control,
                    before_snapshots=before_snapshots,
                    after_snapshots=after_snapshots,
                    before_network_payloads=captured_payloads[:before_payload_count],
                    new_network_payloads=captured_payloads[before_payload_count:],
                )
                if not panel_diff.changed_fields:
                    skipped_controls.append(
                        control.model_copy(update={"skipped_reason": "no_panel_change"})
                    )
                    continue
                panel_diffs.append(panel_diff)
                state = _state_from_panel_diff(
                    control=control,
                    profile=result.profile,
                    diff=panel_diff,
                    after_snapshots=after_snapshots,
                    requested_url=url,
                    final_url=cast(str, page.url),
                    captured_at=_utc_now(),
                )
                if state is None:
                    skipped_controls.append(
                        control.model_copy(update={"skipped_reason": "no_promotable_fact"})
                    )
                    continue
                clicked_states.append(state)
            from agentic_rag.ingestion.url.interactions.models import SectionVisit
            from agentic_rag.ingestion.url.interactions.traversal import DEFAULT_CONFIGURATOR_SECTIONS
            result = result.model_copy(
                update={
                    "states": _prioritize_states_by_gain(
                        _dedupe_states_by_id([*clicked_states, *fallback_states])
                    )[: capture_options.max_states],
                    "controls": _dedupe_controls(all_controls),
                    "skipped_controls": skipped_controls,
                    "network_payloads": captured_payloads,
                    "source_html": captured_html,
                    "panel_snapshots": _dedupe_panel_snapshots(panel_snapshots),
                    "panel_diffs": panel_diffs,
                    "section_visits": [
                        SectionVisit(section_id=sec, reached=True)
                        for sec in DEFAULT_CONFIGURATOR_SECTIONS
                    ],
                }
            )
        except Exception as exc:
            errors.append(str(exc))
            result = extract_interaction_states_from_html(
                captured_html or "",
                requested_url=url,
                final_url=cast(str, page.url),
                captured_at=_utc_now(),
                network_payloads=captured_payloads,
                options=capture_options,
            ).model_copy(update={"errors": errors})
        finally:
            page.close()
            context.close()
            browser.close()
    return result


def _discover_controls(page: Any) -> list[InteractionControl]:
    raw_controls = page.evaluate(_DISCOVER_CONTROLS_JS)
    if not isinstance(raw_controls, list):
        return []
    controls: list[InteractionControl] = []
    for item in raw_controls:
        if not isinstance(item, dict):
            continue
        try:
            controls.append(InteractionControl.model_validate(item))
        except Exception:
            continue
    return controls


def _capture_panel_snapshots(
    page: Any,
    *,
    interaction_step: str,
    source_control_id: str | None = None,
) -> list[InteractionPanelSnapshot]:
    try:
        raw_snapshots = page.evaluate(
            _CAPTURE_PANELS_JS,
            {
                "sourceControlId": source_control_id,
                "interactionStep": interaction_step,
            },
        )
    except Exception:
        return []
    if not isinstance(raw_snapshots, list):
        return []
    captured_at = _utc_now()
    snapshots: list[InteractionPanelSnapshot] = []
    for item in raw_snapshots:
        if not isinstance(item, dict):
            continue
        panel_role = _panel_role(item.get("panel_role"))
        panel_id = normalize_space(str(item.get("panel_id") or panel_role)) or panel_role
        text = normalize_space(str(item.get("text") or ""))[:6000]
        price_values = _string_list(item.get("price_values"), limit=20)
        image_urls = _string_list(item.get("image_urls"), limit=30)
        table_count = _non_negative_int(item.get("table_count"))
        node_signatures = _string_list(item.get("node_signatures"), limit=120)
        specifications = extract_specifications_from_text(text)
        if (
            not text
            and not price_values
            and not image_urls
            and not table_count
            and not node_signatures
        ):
            continue
        snapshot_key = "|".join(
            [
                panel_role,
                panel_id,
                interaction_step,
                source_control_id or "",
                text[:500],
                ",".join(price_values[:8]),
                ",".join(image_urls[:8]),
            ]
        )
        snapshots.append(
            InteractionPanelSnapshot(
                snapshot_id=f"panel_snapshot_{short_hash(snapshot_key)}",
                panel_role=panel_role,
                panel_id=panel_id,
                interaction_step=interaction_step,
                captured_at=captured_at,
                source_control_id=source_control_id,
                text=text,
                text_hash=short_hash(normalize_for_content_hash(text)) if text else None,
                price_values=price_values,
                specifications=specifications,
                image_urls=image_urls,
                table_count=table_count,
                node_signatures=node_signatures,
            )
        )
    return snapshots


def _build_panel_diff(
    *,
    control: InteractionControl,
    before_snapshots: list[InteractionPanelSnapshot],
    after_snapshots: list[InteractionPanelSnapshot],
    before_network_payloads: list[dict[str, object]] | None = None,
    new_network_payloads: list[dict[str, object]] | None = None,
) -> InteractionPanelDiff:
    before_by_role = _snapshot_by_role(before_snapshots)
    after_by_role = _snapshot_by_role(after_snapshots)
    changed_panels: list[PanelRole] = []
    changed_fields: list[str] = []
    panel_changes: dict[str, dict[str, list[str]]] = {}
    before_refs: list[str] = []
    after_refs: list[str] = []
    for role in _PANEL_ROLES:
        before = before_by_role.get(role)
        after = after_by_role.get(role)
        if before is None or after is None:
            continue
        changes: dict[str, list[str]] = {}
        price_added = _added_values(before.price_values, after.price_values)
        price_removed = _removed_values(before.price_values, after.price_values)
        image_added = _added_values(before.image_urls, after.image_urls)
        image_removed = _removed_values(before.image_urls, after.image_urls)
        specs_added = _added_specifications(before.specifications, after.specifications)
        table_delta = max(after.table_count - before.table_count, 0)
        node_added = _added_values(before.node_signatures, after.node_signatures)
        if price_added:
            changes["price_values_added"] = price_added
            _append_once(changed_fields, "price")
        if price_removed:
            changes["price_values_removed"] = price_removed
        if image_added:
            changes["image_urls_added"] = image_added
            _append_once(changed_fields, "image")
        if image_removed:
            changes["image_urls_removed"] = image_removed
        if specs_added:
            changes["specifications_added"] = [
                f"{key}: {value}" for key, value in specs_added.items()
            ]
            _append_once(changed_fields, "specifications")
        if table_delta:
            changes["table_count_added"] = [str(table_delta)]
            _append_once(changed_fields, "tables")
        if node_added:
            changes["nodes_added"] = node_added[:20]
            _append_once(changed_fields, "nodes")
        if before.text_hash != after.text_hash:
            changes["text_hash"] = [before.text_hash or "", after.text_hash or ""]
            _append_once(changed_fields, "visible_text")
        if not changes:
            continue
        changed_panels.append(role)
        before_refs.append(before.snapshot_id)
        after_refs.append(after.snapshot_id)
        panel_changes[role] = changes
    diff_key = "|".join(
        [
            control.control_id,
            control.group,
            control.label,
            ",".join(changed_panels),
            ",".join(changed_fields),
        ]
    )
    information_gain = _calculate_information_gain(
        before_snapshots=before_snapshots,
        after_snapshots=after_snapshots,
        before_network_payloads=before_network_payloads or [],
        new_network_payloads=new_network_payloads or [],
    )
    return InteractionPanelDiff(
        diff_id=f"panel_diff_{short_hash(diff_key)}",
        source_control_id=control.control_id,
        control_label=control.label,
        control_group=control.group,
        changed_panels=changed_panels,
        changed_fields=changed_fields,
        before_snapshot_refs=before_refs,
        after_snapshot_refs=after_refs,
        panel_changes=panel_changes,
        dom_gain=_object_to_int(information_gain["dom_gain"]),
        api_gain=_object_to_int(information_gain["api_gain"]),
        entity_gain=_object_to_int(information_gain["entity_gain"]),
        gain_score=_object_to_int(information_gain["gain_score"]),
        information_gain=information_gain,
    )


def _state_from_panel_diff(
    *,
    control: InteractionControl,
    profile: InteractionProfile,
    diff: InteractionPanelDiff,
    after_snapshots: list[InteractionPanelSnapshot],
    requested_url: str,
    final_url: str | None,
    captured_at: str,
) -> InteractionStateRecord | None:
    if not diff.changed_fields:
        return None
    price = _first_changed_value(diff, "price_values_added") or _first_after_price(
        after_snapshots,
        diff.changed_panels,
    )
    image_url = _first_changed_value(diff, "image_urls_added") or _first_after_image(
        after_snapshots,
        diff.changed_panels,
    )
    specifications = _specifications_from_snapshots(after_snapshots, diff.changed_panels)
    changed_fields = list(diff.changed_fields)
    if specifications and "specifications" not in changed_fields:
        changed_fields.append("specifications")
    if not price and not image_url and not specifications and "visible_text" not in changed_fields:
        return None
    after_text = _snapshot_text_summary(after_snapshots, diff.changed_panels)
    normalized_group = slugify(control.group) or "option"
    option_label = normalize_space(control.label) or "unknown"
    model_name = _model_name_from_snapshots(after_snapshots) or profile.model_id
    state_key = "|".join(
        [
            requested_url,
            final_url or "",
            control.control_id,
            diff.diff_id,
            price or "",
            json.dumps(specifications, sort_keys=True, ensure_ascii=True),
            image_url or "",
        ]
    )
    panel_role = control.panel_role if control.panel_role in _PANEL_ROLES else "unknown"
    panel_id = control.panel_id or panel_role
    return InteractionStateRecord(
        state_id=short_hash(state_key),
        requested_url=requested_url,
        final_url=final_url,
        model_id=profile.model_id,
        model_name=model_name,
        option_group=normalized_group,
        option_label=option_label,
        source_control_id=control.control_id,
        panel_role=panel_role,
        panel_id=panel_id,
        variant_options={normalized_group: option_label},
        price=price,
        currency=_currency_from_price(price),
        price_source="dom" if price else "not_visible",
        specifications=specifications,
        image_url=image_url,
        availability="disabled" if control.disabled else "available",
        evidence_source="dom",
        captured_at=captured_at,
        changed_panels=diff.changed_panels,
        changed_fields=changed_fields,
        before_snapshot_ref=diff.before_snapshot_refs[0] if diff.before_snapshot_refs else None,
        after_snapshot_ref=diff.after_snapshot_refs[0] if diff.after_snapshot_refs else None,
        state_diff_ref=diff.diff_id,
        gain_score=diff.gain_score,
        information_gain=diff.information_gain,
        dom_evidence={
            "control_id": control.control_id,
            "control_label": control.label,
            "control_group": control.group,
            "panel_role": panel_role,
            "panel_id": panel_id,
            "changed_panels": ",".join(diff.changed_panels),
            "changed_fields": ",".join(changed_fields),
            "before_snapshot_refs": ",".join(diff.before_snapshot_refs),
            "after_snapshot_refs": ",".join(diff.after_snapshot_refs),
            "state_diff_ref": diff.diff_id,
            "gain_score": str(diff.gain_score),
            "after_snapshot_text": after_text,
        },
    )


def _snapshot_text_summary(
    snapshots: list[InteractionPanelSnapshot],
    roles: list[PanelRole],
    *,
    limit: int = 500,
) -> str:
    wanted_roles = set(roles)
    values: list[str] = []
    for role in ("right_panel", "left_panel", "center_visual", "unknown"):
        if wanted_roles and role not in wanted_roles:
            continue
        for snapshot in snapshots:
            if snapshot.panel_role != role or not snapshot.text:
                continue
            text = normalize_space(snapshot.text)
            if text and text not in values:
                values.append(text)
    summary = " | ".join(values)
    if len(summary) <= limit:
        return summary
    return summary[:limit].rstrip() + "..."


def _specifications_from_snapshots(
    snapshots: list[InteractionPanelSnapshot],
    roles: list[PanelRole],
) -> dict[str, str]:
    wanted_roles = set(roles)
    ordered_roles: tuple[PanelRole, ...] = (
        "right_panel",
        "unknown",
        "left_panel",
        "center_visual",
    )
    combined_text: list[str] = []
    for role in ordered_roles:
        if wanted_roles and role not in wanted_roles:
            continue
        for snapshot in snapshots:
            if snapshot.panel_role == role and snapshot.text:
                combined_text.append(snapshot.text)
    return extract_specifications_from_text("\n".join(combined_text))


def _calculate_information_gain(
    *,
    before_snapshots: list[InteractionPanelSnapshot],
    after_snapshots: list[InteractionPanelSnapshot],
    before_network_payloads: list[dict[str, object]],
    new_network_payloads: list[dict[str, object]],
) -> dict[str, object]:
    before_text = _snapshot_text(before_snapshots)
    after_text = _snapshot_text(after_snapshots)
    before_tokens = set(normalize_for_content_hash(before_text).split())
    after_tokens = set(normalize_for_content_hash(after_text).split())
    new_text_tokens = sorted(after_tokens - before_tokens)
    before_nodes = _snapshot_node_signatures(before_snapshots)
    after_nodes = _snapshot_node_signatures(after_snapshots)
    changed_nodes = sorted(after_nodes - before_nodes)
    new_tables = max(_table_count(after_snapshots) - _table_count(before_snapshots), 0)
    new_prices = sorted(
        _snapshot_price_values(after_snapshots) - _snapshot_price_values(before_snapshots)
    )
    before_specs = _snapshot_specifications(before_snapshots)
    after_specs = _snapshot_specifications(after_snapshots)
    new_specs = {
        key: value for key, value in sorted(after_specs.items()) if before_specs.get(key) != value
    }
    before_json_fields = _json_field_paths(before_network_payloads)
    new_json_fields = sorted(_json_field_paths(new_network_payloads) - before_json_fields)
    new_endpoints = sorted(_payload_endpoints(new_network_payloads))
    before_entities = _payload_entities(before_network_payloads) | _text_entities(before_text)
    after_entities = _payload_entities(
        [*before_network_payloads, *new_network_payloads]
    ) | _text_entities(after_text)
    new_entities = sorted(after_entities - before_entities)
    new_models = [entity for entity in new_entities if _is_model_entity(entity)]
    new_variants = [entity for entity in new_entities if not _is_model_entity(entity)]
    dom_gain = (
        len(new_text_tokens)
        + (len(changed_nodes) * 2)
        + (new_tables * 10)
        + (len(new_prices) * 5)
        + (len(new_specs) * 8)
    )
    api_gain = (len(new_endpoints) * 10) + (len(new_json_fields) * 2) + (len(new_entities) * 5)
    entity_gain = (len(new_models) * 6) + (len(new_variants) * 4)
    gain_score = dom_gain + api_gain + entity_gain
    return {
        "dom_gain": dom_gain,
        "api_gain": api_gain,
        "entity_gain": entity_gain,
        "gain_score": gain_score,
        "dom": {
            "new_text_token_count": len(new_text_tokens),
            "new_text_tokens": new_text_tokens[:80],
            "changed_node_count": len(changed_nodes),
            "changed_nodes": changed_nodes[:40],
            "new_tables": new_tables,
            "new_prices": new_prices,
            "new_specs": new_specs,
        },
        "api": {
            "new_endpoints": new_endpoints,
            "new_json_field_count": len(new_json_fields),
            "new_json_fields": new_json_fields[:80],
            "new_entities": new_entities,
        },
        "entity": {
            "new_models": new_models,
            "new_variants": new_variants,
        },
    }


def _snapshot_text(snapshots: list[InteractionPanelSnapshot]) -> str:
    return "\n".join(snapshot.text for snapshot in snapshots if snapshot.text)


def _snapshot_node_signatures(snapshots: list[InteractionPanelSnapshot]) -> set[str]:
    return {
        signature for snapshot in snapshots for signature in snapshot.node_signatures if signature
    }


def _snapshot_price_values(snapshots: list[InteractionPanelSnapshot]) -> set[str]:
    return {price for snapshot in snapshots for price in snapshot.price_values if price}


def _snapshot_specifications(
    snapshots: list[InteractionPanelSnapshot],
) -> dict[str, str]:
    specs: dict[str, str] = {}
    for snapshot in snapshots:
        specs.update(snapshot.specifications)
    return specs


def _table_count(snapshots: list[InteractionPanelSnapshot]) -> int:
    return sum(snapshot.table_count for snapshot in snapshots)


def _added_specifications(
    before: dict[str, str],
    after: dict[str, str],
) -> dict[str, str]:
    return {key: value for key, value in sorted(after.items()) if before.get(key) != value}


def _payload_endpoints(payloads: list[dict[str, object]]) -> set[str]:
    endpoints: set[str] = set()
    for payload in payloads:
        endpoint = payload.get("__endpoint") or payload.get("endpoint") or payload.get("action")
        if isinstance(endpoint, str) and endpoint:
            endpoints.add(endpoint)
    return endpoints


def _json_field_paths(payloads: list[dict[str, object]]) -> set[str]:
    fields: set[str] = set()
    for payload in payloads:
        fields.update(_json_field_paths_for_value(payload))
    return fields


def _json_field_paths_for_value(value: object, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        fields: set[str] = set()
        for key, item in value.items():
            if str(key).startswith("__"):
                continue
            path = f"{prefix}.{key}" if prefix else str(key)
            fields.add(path)
            fields.update(_json_field_paths_for_value(item, path))
        return fields
    if isinstance(value, list | tuple):
        list_fields: set[str] = set()
        for item in value[:20]:
            list_fields.update(_json_field_paths_for_value(item, f"{prefix}[]"))
        return list_fields
    return set()


def _payload_entities(payloads: list[dict[str, object]]) -> set[str]:
    entities: set[str] = set()
    for payload in payloads:
        entities.update(_text_entities(json.dumps(payload, ensure_ascii=False)))
        for key in ("modelId", "modelID", "productId", "sku", "variantName", "colorName"):
            value = _nested_value_by_key(payload, key)
            if isinstance(value, str) and value:
                entities.add(normalize_space(value))
    return entities


def _nested_value_by_key(value: object, wanted_key: str) -> object | None:
    if isinstance(value, dict):
        lowered = {str(key).lower(): key for key in value}
        actual_key = lowered.get(wanted_key.lower())
        if actual_key is not None:
            return value.get(actual_key)
        for item in value.values():
            found = _nested_value_by_key(item, wanted_key)
            if found is not None:
                return found
    elif isinstance(value, list | tuple):
        for item in value:
            found = _nested_value_by_key(item, wanted_key)
            if found is not None:
                return found
    return None


def _text_entities(text: str) -> set[str]:
    return {normalize_space(match.group(0)) for match in _GAIN_ENTITY_RE.finditer(text)}


def _is_model_entity(value: str) -> bool:
    return bool(re.search(r"\bVF\s*-?\s?\d{1,2}\b", value, re.IGNORECASE))


def _snapshot_by_role(
    snapshots: list[InteractionPanelSnapshot],
) -> dict[PanelRole, InteractionPanelSnapshot]:
    output: dict[PanelRole, InteractionPanelSnapshot] = {}
    for snapshot in snapshots:
        output.setdefault(snapshot.panel_role, snapshot)
    return output


def _first_changed_value(diff: InteractionPanelDiff, field: str) -> str | None:
    for role in ("right_panel", "center_visual", "left_panel", "unknown"):
        changes = diff.panel_changes.get(role)
        if not changes:
            continue
        values = changes.get(field)
        if values:
            return values[0]
    return None


def _first_after_price(
    snapshots: list[InteractionPanelSnapshot],
    roles: list[PanelRole],
) -> str | None:
    return _first_after_value(
        snapshots,
        roles,
        "price_values",
        priority_roles=("right_panel", "left_panel", "center_visual", "unknown"),
    )


def _first_after_image(
    snapshots: list[InteractionPanelSnapshot],
    roles: list[PanelRole],
) -> str | None:
    return _first_after_value(
        snapshots,
        roles,
        "image_urls",
        priority_roles=("center_visual", "right_panel", "left_panel", "unknown"),
    )


def _first_after_value(
    snapshots: list[InteractionPanelSnapshot],
    roles: list[PanelRole],
    attr_name: str,
    *,
    priority_roles: tuple[PanelRole, ...],
) -> str | None:
    wanted_roles = set(roles)
    ordered_roles = [role for role in priority_roles if role in wanted_roles] or list(
        priority_roles
    )
    for role in ordered_roles:
        for snapshot in snapshots:
            if snapshot.panel_role != role:
                continue
            values = getattr(snapshot, attr_name)
            if isinstance(values, list) and values and isinstance(values[0], str):
                return values[0]
    return None


def _model_name_from_snapshots(
    snapshots: list[InteractionPanelSnapshot],
) -> str | None:
    for snapshot in snapshots:
        match = _MODEL_NAME_RE.search(snapshot.text)
        if match:
            return normalize_space(match.group(0))
    return None


def _dedupe_panel_snapshots(
    snapshots: list[InteractionPanelSnapshot],
) -> list[InteractionPanelSnapshot]:
    seen: set[str] = set()
    output: list[InteractionPanelSnapshot] = []
    for snapshot in snapshots:
        if snapshot.snapshot_id in seen:
            continue
        seen.add(snapshot.snapshot_id)
        output.append(snapshot)
    return output


def _added_values(before: list[str], after: list[str]) -> list[str]:
    before_set = set(before)
    return [value for value in after if value not in before_set]


def _removed_values(before: list[str], after: list[str]) -> list[str]:
    after_set = set(after)
    return [value for value in before if value not in after_set]


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _string_list(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    output: list[str] = []
    for item in value:
        text = normalize_space(str(item))
        if text and text not in output:
            output.append(text)
        if len(output) >= limit:
            break
    return output


def _non_negative_int(value: object) -> int:
    return max(_object_to_int(value), 0)


def _object_to_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _panel_role(value: object) -> PanelRole:
    if value in _PANEL_ROLES:
        return value
    return "unknown"


def _currency_from_price(price: str | None) -> str | None:
    if not price:
        return None
    lowered = price.lower()
    if "$" in price or "usd" in lowered:
        return "USD"
    if "vnd" in lowered or "vn\u0111" in lowered or "\u0111" in lowered or "\u20ab" in price:
        return "VND"
    return None


def _capture_json_response(response: Any, payloads: list[dict[str, object]]) -> None:
    if len(payloads) >= _MAX_NETWORK_PAYLOADS:
        return
    try:
        content_type = str(response.headers.get("content-type", "")).lower()
        request_url = str(response.url)
    except Exception:
        return
    if "json" not in content_type and not re.search(
        r"/api/|graphql|product|price",
        request_url,
        re.I,
    ):
        return
    try:
        text = str(response.text())
    except Exception:
        return
    if len(text) > _MAX_PAYLOAD_CHARS:
        text = text[:_MAX_PAYLOAD_CHARS]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return
    if isinstance(payload, dict):
        redacted_payload = _redact_payload(payload)
        redacted_payload["__endpoint"] = request_url
        payloads.append(redacted_payload)


def _redact_payload(payload: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, value in payload.items():
        lowered = key.lower()
        if any(secret in lowered for secret in ("token", "secret", "cookie", "auth")):
            redacted[key] = "[redacted]"
            continue
        if isinstance(value, dict):
            redacted[key] = _redact_payload(value)
        elif isinstance(value, list):
            redacted[key] = value[:20]
        else:
            redacted[key] = value
    return redacted


def _dedupe_states_by_id(
    states: list[InteractionStateRecord],
) -> list[InteractionStateRecord]:
    seen: set[str] = set()
    output: list[InteractionStateRecord] = []
    for state in states:
        state_id = getattr(state, "state_id", "")
        if not state_id or state_id in seen:
            continue
        seen.add(state_id)
        output.append(state)
    return output


def _prioritize_states_by_gain(
    states: list[InteractionStateRecord],
) -> list[InteractionStateRecord]:
    return sorted(
        states,
        key=lambda state: (
            state.gain_score,
            bool(state.specifications),
            bool(state.price),
            bool(state.image_url),
        ),
        reverse=True,
    )


def _dedupe_controls(controls: list[InteractionControl]) -> list[InteractionControl]:
    seen: set[tuple[str, str]] = set()
    output: list[InteractionControl] = []
    for control in controls:
        key = (control.group, control.label)
        if key in seen:
            continue
        seen.add(key)
        output.append(control)
    return output


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = ["capture_interaction_states_with_playwright"]
