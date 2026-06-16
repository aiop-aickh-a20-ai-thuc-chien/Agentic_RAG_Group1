"""Optional Playwright-backed rule-based interaction capture."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, cast

from agentic_rag.ingestion.url.interactions.extractor import (
    extract_interaction_states_from_html,
)
from agentic_rag.ingestion.url.interactions.models import (
    InteractionCaptureResult,
    InteractionControl,
    InteractionOptions,
    InteractionStateRecord,
)

_MAX_NETWORK_PAYLOADS = 50
_MAX_PAYLOAD_CHARS = 20_000

_DISCOVER_CONTROLS_JS = r"""
() => {
  const BLOCK_LABEL = new RegExp([
    'dat\\s*coc',
    'thanh\\s*toan',
    'checkout',
    'payment',
    'submit',
    'buy\\s*now',
    'mua\\s*ngay',
    'login',
    'dang\\s*nhap',
    'support',
    'hotline'
  ].join('|'), 'i');
  const OPTION_CLASS = new RegExp([
    '(^|[\\s_-])',
    '(color|colour|swatch|variant|option|trim|battery|model|package)',
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
    'button',
    '[role="button"]',
    '[role="radio"]',
    '[role="tab"]',
    'input[type="radio"]',
    '[data-option-group]',
    '[data-option-label]',
    '.color-swatch',
    '.variant-card',
    '.option-card'
  ].join(',')));
  const controls = [];
  let index = 0;
  for (const el of candidates) {
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
    if (!label || BLOCK_LABEL.test(label)) continue;
    if (
      !hasOptionAttr &&
      !OPTION_CLASS.test(cls) &&
      !['button','radio','tab'].includes(role)
    ) continue;
    const disabled = (
      el.disabled ||
      el.getAttribute('aria-disabled') === 'true' ||
      el.getAttribute('data-disabled') === 'true'
    );
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
      disabled,
      attributes: {
        class: cls,
        role,
        'aria-label': el.getAttribute('aria-label') || '',
        'data-option-group': el.getAttribute('data-option-group') || '',
        'data-option-label': el.getAttribute('data-option-label') || '',
        'data-price': el.getAttribute('data-price') || '',
        'data-image': el.getAttribute('data-image') || '',
        'data-model-name': el.getAttribute('data-model-name') || ''
      }
    });
  }
  function inferGroup(label, cls) {
    const text = `${label} ${cls}`.toLowerCase();
    if (/(color|colour|swatch|mau)/.test(text)) return 'color';
    if (/(battery|pin)/.test(text)) return 'battery';
    if (/(trim|variant|version|phien ban)/.test(text)) return 'variant';
    return 'option';
  }
  return controls;
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
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="vi-VN",
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
            states = list(result.states)
            skipped_controls = list(result.skipped_controls)
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
                try:
                    page.locator(control.selector).click(timeout=3000)
                    page.wait_for_timeout(capture_options.settle_after_click_ms)
                except Exception as exc:
                    skipped_controls.append(
                        control.model_copy(update={"skipped_reason": f"click_failed:{exc}"})
                    )
                    continue
                state_html = cast(str, page.content())
                state_result = extract_interaction_states_from_html(
                    state_html,
                    requested_url=url,
                    final_url=cast(str, page.url),
                    captured_at=_utc_now(),
                    network_payloads=captured_payloads,
                    options=InteractionOptions(max_states=1),
                )
                if state_result.states:
                    states.extend(state_result.states)
                else:
                    skipped_controls.append(
                        control.model_copy(update={"skipped_reason": "no_state_extracted"})
                    )
            result = result.model_copy(
                update={
                    "states": _dedupe_states_by_id(states)[: capture_options.max_states],
                    "controls": _dedupe_controls(all_controls),
                    "skipped_controls": skipped_controls,
                    "network_payloads": captured_payloads,
                    "source_html": captured_html,
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
        payloads.append(_redact_payload(payload))


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
