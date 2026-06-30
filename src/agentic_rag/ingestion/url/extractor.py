# ruff: noqa: E501
"""Main-content extraction adapters for URL ingestion."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable
from datetime import timedelta
from html.parser import HTMLParser
from importlib import import_module
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.ingestion.url.normalizer import normalize_markdown, normalize_text

_MARKDOWN_LINK_PATTERN = r"\[[^\]\n]+\]\((?:[^()\n]|\([^()\n]*\))*\)"
_MARKDOWN_LINK_RE = re.compile(_MARKDOWN_LINK_PATTERN)
_WORD_CHAR_RE = r"\w"
_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
_SPEC_VALUE_RE = re.compile(r"^[\d.,]+(?:\s*[x/+\-]\s*[\d.,]+)*\*?$")
_PRICE_RE = re.compile(r"\d[\d.,]*\s*(?:VND|VNĐ|₫|dong|USD|US\$|\$)\b", re.IGNORECASE)
_SKIP_CLASS_RE = re.compile(
    r"(^|[\s_-])(nav|navbar|menu|header|footer|breadcrumb|cookie|popup|modal-backdrop|"
    r"topbar|megamenu|sidebar)([\s_-]|$)",
    re.IGNORECASE,
)
_SKIP_TAGS = {
    "nav",
    "header",
    "footer",
    "script",
    "style",
    "noscript",
    "svg",
    "button",
    "form",
    "iframe",
    "aside",
    "select",
    "option",
}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = {"p", "li", "td", "th", "dt", "dd"}
_STRONG_TAGS = {"strong", "b"}
_PARSER_NAME = "crawl-link-dom-markdown+normalizer"
_BROWSER_PARSER_NAME = "crawl-link-playwright-dom-markdown+normalizer"
_CRAWLEE_PARSER_NAME = "crawl-link-crawlee-playwright-dom-markdown+normalizer"

DOM_WALKER_JS = r"""
() => {
  const SKIP_TAGS = new Set(['NAV','HEADER','FOOTER','SCRIPT','STYLE','NOSCRIPT','SVG','BUTTON','FORM','IFRAME','ASIDE','SELECT','OPTION']);
  const SKIP_CLASS = /(^|[\s_-])(nav|navbar|menu|header|footer|breadcrumb|cookie|popup|modal-backdrop|topbar|megamenu|sidebar)([\s_-]|$)/i;
  const out = [];
  const seen = new Set();

  function inSkipped(el) {
    let p = el;
    while (p && p.tagName) {
      if (SKIP_TAGS.has(p.tagName)) return true;
      if (p.id === 'rollingUpCostPopUp' || p.id === 'installmentCostPopUp') return false;
      const cls = (p.getAttribute && p.getAttribute('class')) || '';
      if (cls && SKIP_CLASS.test(cls)) return true;
      const role = (p.getAttribute && p.getAttribute('role')) || '';
      if (role === 'navigation' || role === 'banner') return true;
      p = p.parentElement;
    }
    return false;
  }
  function txt(el) {
    return (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
  }
  const INLINE = new Set(['SPAN','B','I','STRONG','EM','A','DEL','S','U','SUB','SUP',
    'BR','SMALL','MARK','ABBR','TIME','LABEL','BDI','FONT','Q','CITE','WBR','INS','VAR']);
  function isLeafBlock(el) {
    for (const c of el.children) {
      if (!INLINE.has(c.tagName)) return false;
    }
    return true;
  }
  const title = (document.title || '').trim();
  const docTitle = title.toLowerCase();
  const headingTexts = new Set();
  document.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(h => {
    if (inSkipped(h)) return;
    const t = txt(h);
    if (t && t.length >= 2) headingTexts.add(t.toLowerCase());
  });
  document.querySelectorAll('*').forEach(el => {
    if (inSkipped(el)) return;
    const tag = el.tagName.toLowerCase();
    const isHeading = /^h[1-6]$/.test(tag);
    if (tag === 'table') {
      const rows = [];
      el.querySelectorAll('tr').forEach(row => {
        if (inSkipped(row)) return;
        const cells = Array.from(row.querySelectorAll('th, td')).map(c => txt(c));
        if (cells.length > 0 && cells.some(c => c)) rows.push(cells);
      });
      if (rows.length > 0) {
        out.push('');
        out.push('| ' + rows[0].join(' | ') + ' |');
        out.push('| ' + rows[0].map(() => '---').join(' | ') + ' |');
        for (let i = 1; i < rows.length; i++) {
          out.push('| ' + rows[i].join(' | ') + ' |');
        }
        out.push('');
        rows.flat().forEach(c => { if (c) seen.add(c.toLowerCase()); });
      }
      return;
    }
    if (tag === 'td' || tag === 'th') return;
    if (!isHeading && !isLeafBlock(el)) return;
    if (!isHeading && el.parentElement && !inSkipped(el.parentElement)
        && isLeafBlock(el.parentElement)) return;
    const t = txt(el);
    if (!t || t.length < 2) return;
    if (/=["']|\/>|<\/?[a-z]/i.test(t)) return;
    if (t.toLowerCase() === docTitle) return;
    const key = t.toLowerCase();
    if (!isHeading && headingTexts.has(key)) return;
    if (seen.has(key)) return;
    seen.add(key);
    if (isHeading) {
      out.push('');
      out.push('#'.repeat(parseInt(tag[1])) + ' ' + t);
    } else if (tag === 'li') {
      out.push('- ' + t);
    } else {
      out.push(t);
    }
  });
  const nH = out.filter(l => /^#{1,6}\s/.test(l)).length;
  return {title, markdown: out.join('\n').trim(), n_headings: nH};
}
"""

EXPAND_JS = r"""
() => {
  document.querySelectorAll('.tab-pane, [role=tabpanel], .collapse, .accordion-collapse, .accordion-body').forEach(e => {
    e.classList.add('show','active','in');
    e.style.display = 'block';
    e.style.visibility = 'visible';
    e.style.height = 'auto';
    e.style.opacity = '1';
    e.removeAttribute('hidden');
    e.setAttribute('aria-hidden','false');
  });
  
  // Open cost modals
  document.querySelectorAll('.js-rollingUpCostPopUp, .js-installmentCostPopUp').forEach(btn => {
    try { btn.click(); } catch(e) {}
  });
}
"""

PRODUCT_JS = r"""
(inModelId) => {
  const T = s => (s||'').trim().replace(/\s+/g,' ');
  const uniq = a => [...new Set(a)];
  const res = {prices:[], specs:[], anchors:[], deposit_amount:'', rolling_cost_details:[]};
  
  if (window.carDeposit && window.carDeposit.products) {
    let modelId = inModelId;
    if (!modelId) {
      const urlParams = new URLSearchParams(window.location.search);
      modelId = urlParams.get('modelId');
    }
    if (!modelId) {
      const keys = Object.keys(window.carDeposit.products).filter(k => k !== 'colorsConfig');
      if (keys.length > 0) {
        modelId = keys[0];
      } else {
        modelId = 'Products-Car-VF9';
      }
    }
    if (modelId) {
      const modelData = window.carDeposit.products[modelId];
      if (modelData) {
        res.is_vinfast = true;
        res.model_id = modelId;
        res.model_name = modelData.label || 'VinFast ' + (modelId.split('-').pop());
        
        // Extract editions
        res.editions = {};
        if (modelData.listEdition) {
          modelData.listEdition.forEach(key => {
            const ed = modelData[key];
            if (ed) {
              res.editions[key] = {
                price: ed.price || (ed.priceValue ? ed.priceValue.toLocaleString('vi-VN') : ''),
                priceValue: ed.priceValue || 0,
                label: ed.label || ''
              };
            }
          });
        }
        
        // Extract colors & interiors config
        res.colors_config = {};
        if (window.carDeposit.products.colorsConfig && window.carDeposit.products.colorsConfig[modelId]) {
          res.colors_config = window.carDeposit.products.colorsConfig[modelId];
        }
        
        res.edition_details = {};
        for (const key of (modelData.listEdition || [])) {
          const ed = modelData[key];
          if (ed) {
            res.edition_details[key] = {
              listColor: ed.listColor || [],
              listInterior: ed.listInterior || []
            };
            (ed.listColor || []).forEach(colKey => {
              const col = ed[colKey];
              if (col) {
                res.edition_details[key][colKey] = {
                  label: col.label,
                  value: col.value,
                  code: col.code,
                  pid: col.pid,
                  price: col.price,
                  available: col.available
                };
                (ed.listInterior || []).forEach(intKey => {
                  const interior = col[intKey];
                  if (interior) {
                    res.edition_details[key][colKey][intKey] = {
                      label: interior.label,
                      value: interior.value,
                      pid: interior.pid
                    };
                  }
                });
              }
            });
          }
        }
      }
    }
  }

  const CUR = /\d[\d.,]*\s*(VNĐ|VND|₫|đồng|dong|USD|US\$|\$)\b/i;
  
  // Extract PDP section anchors
  document.querySelectorAll('a[href*="#section-"]').forEach(a => {
    const text = T(a.innerText || a.textContent);
    const href = a.getAttribute('href') || '';
    if (text && href && !res.anchors.some(item => item.href === href)) {
      res.anchors.push({text, href});
    }
  });

  // Extract deposit amount
  let depositAmount = '';
  document.querySelectorAll('p,span,div,td,li,strong,b,button,a').forEach(e => {
    if (e.children.length > 0) return;
    const t = T(e.innerText || e.textContent);
    if (t.toLowerCase().includes('đặt cọc') && CUR.test(t)) {
      const match = t.match(CUR);
      if (match) {
        depositAmount = match[0];
      }
    }
  });
  if (!depositAmount) {
    const depositEl = document.querySelector('.deposit-amount, .deposit-price, [data-deposit-amount]');
    if (depositEl) {
      depositAmount = T(depositEl.innerText || depositEl.textContent);
    }
  }
  res.deposit_amount = depositAmount || '50.000.000 VNĐ';

  document.querySelectorAll('p,span,div,td,li,strong,b,h1,h2,h3,h4,h5,h6').forEach(e=>{
    if (e.children.length > 0) return;
    const t = T(e.innerText);
    if (t.length < 45 && CUR.test(t)) res.prices.push(t);
  });
  document.querySelectorAll('dl').forEach(dl=>{
    const dts=dl.querySelectorAll('dt'), dds=dl.querySelectorAll('dd');
    for (let i=0;i<Math.min(dts.length,dds.length);i++){
      const k=T(dts[i].innerText), v=T(dds[i].innerText);
      if (k && v && k.length<70) res.specs.push([k.slice(0,70), v.slice(0,200)]);
    }
  });
  document.querySelectorAll('table tr').forEach(tr=>{
    const cells=[...tr.querySelectorAll('th,td')].map(c=>T(c.innerText)).filter(Boolean);
    if (cells.length===2 && cells[0] && cells[1] && cells[0].length<70 && cells[0]!==cells[1])
      res.specs.push([cells[0].slice(0,70), cells[1].slice(0,200)]);
  });
  res.prices = uniq(res.prices).slice(0,10);
  const seenK=new Set();
  res.specs = res.specs.filter(([k])=>{const lk=k.toLowerCase(); if(seenK.has(lk))return false; seenK.add(lk); return true;}).slice(0,60);

  // Extract rolling up cost breakdown (Chi phí lăn bánh) details if modal is present
  const modal = document.querySelector('#rollingUpCostPopUp');
  if (modal) {
    modal.querySelectorAll('tr, .cost-row, .flex-row').forEach(row => {
      const cells = [];
      row.querySelectorAll('td, th, .cost-label, .cost-value').forEach(cell => {
        const text = T(cell.innerText || cell.textContent);
        if (text) cells.push(text);
      });
      if (cells.length >= 2 && !res.rolling_cost_details.some(existing => existing[0] === cells[0])) {
        res.rolling_cost_details.push(cells.slice(0, 2));
      }
    });
  }

  return res;
}
"""


class ExtractedMarkdown(BaseModel):
    """Clean Markdown plus extractor metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    markdown: str
    parser_name: str
    title: str | None = None
    final_url: str | None = None
    rendered_html: str | None = None
    fetched_ok: bool = True
    product: dict[str, object] | None = None
    normalize_stats: dict[str, object] = Field(default_factory=dict)


def extract_markdown_from_html(
    html: str,
    *,
    title: str | None = None,
    source_url: str | None = None,
) -> ExtractedMarkdown | None:
    """Extract Crawl-link-style Markdown from an HTML string without browser dependency."""

    # TODO [guide_2/TODO_Gemini_Pro.md Priority 4 – Container-aware static extraction]:
    # Before falling through to the generic `_DomMarkdownParser`, check for
    # `<script id="__NEXT_DATA__">` or `window.__INITIAL_STATE__` in the HTML
    # and parse embedded JSON directly for product fields.
    # If not found, attempt a container-aware product card extraction:
    #   1. Identify repeating container nodes (e.g. `<div data-product-item>`)
    #   2. Extract text + facts scoped within each container.
    #   3. Tag results with the container's model name attribute.
    # Only fall back to generic line-by-line parsing if neither approach yields data.
    # Reference: guide_2/TODO_Gemini_Pro.md Priority 4, guide_2/TODO_Gemini.md §1–2

    parser = _DomMarkdownParser()
    parser.feed(html)
    parser.close()
    main_title = clean_title(title or parser.title)
    markdown = pair_specs(parser.markdown)
    product_data = _merge_product_data(
        _extract_embedded_json_product_state(html),
        _extract_product_from_markdown(markdown),
    )
    product = product_data if is_product_data(product_data) else None
    if product:
        product_markdown = build_product_markdown(product)
        if product_markdown:
            markdown = f"{markdown}\n\n{product_markdown}" if markdown else product_markdown
    if main_title and not _has_h1(markdown):
        markdown = f"# {main_title}\n\n{markdown}" if markdown else f"# {main_title}"
    normalized, stats = normalize_markdown(
        markdown,
        page={
            "url": source_url or "",
            "title": title or parser.title or "",
            "main_title": main_title,
            "markdown": markdown,
            "product": product,
            "is_product": bool(product),
        },
    )
    if not normalized:
        return None
    
    # TODO [FUTURE GraphRAG Integration - Phase 1 & 2]:
    # Pseudocode for integrating GraphRAG processing here or downstream:
    # 1. Convert `normalized` markdown into GraphRAG `TextUnit`s (Chunking - Phase 1).
    # 2. Pass `TextUnit`s to `extract_graph` workflow to extract `Entity` and `Relationship` nodes using LLM (Phase 2).
    # 3. Store the resulting entities and relationships into the GraphDB/VectorDB.
    # Reference: guide_RAG/GUIDELINE.md

    return ExtractedMarkdown(
        markdown=normalized,
        parser_name=_PARSER_NAME,
        title=main_title or parser.title,
        product=product or None,
        normalize_stats=stats,
    )


def extract_markdown_with_playwright(
    url: str,
    *,
    timeout_seconds: int = 60,
    wait_until: str = "load",
    settle_after_scroll_ms: int = 800,
    settle_after_expand_ms: int = 2000,
) -> ExtractedMarkdown:
    """Render a URL and extract Markdown using the Crawl link Playwright DOM walker."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0.")
    if settle_after_scroll_ms < 0 or settle_after_expand_ms < 0:
        raise ValueError("settle wait times must be non-negative.")

    try:
        sync_playwright = cast(Any, import_module("playwright.sync_api")).sync_playwright
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("Python Playwright is not installed.") from exc

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
        context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = context.new_page()
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout_seconds * 1000)
            fetched_ok = _wait_cloudflare(page)
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(settle_after_scroll_ms)
                page.evaluate("window.scrollTo(0, 0)")
                page.evaluate(EXPAND_JS)
                page.wait_for_timeout(settle_after_expand_ms)
                
                # --- State Space Exploration for Promotional Switches ---
                # Open select2 to expose models
                try:
                    if page.locator(".select2-selection__arrow").count() > 0:
                        page.locator(".select2-selection__arrow").first.click(timeout=1000)
                        page.wait_for_timeout(300)
                except Exception:
                    pass
                
                # Toggle switches and snapshot ruc-summary
                try:
                    switches = page.locator(".switch-button input[type='checkbox']").all()
                    for switch in switches:
                        switch_id = switch.get_attribute("id") or "unknown_switch"
                        # Toggle ON
                        switch.evaluate("node => node.click()")
                        page.wait_for_timeout(1000)  # Wait for React to calculate
                        
                        summary_html = ""
                        if page.locator(".ruc-summary").count() > 0:
                            summary_html = page.locator(".ruc-summary").first.inner_html()
                        
                        if summary_html:
                            # Append to DOM using arguments to prevent XSS/syntax errors
                            page.evaluate(
                                "(args) => { const div = document.createElement('div'); div.innerHTML = '<h2>Chi phí lăn bánh với ưu đãi: ' + args.id + '</h2>' + args.html; document.body.appendChild(div); }", 
                                {"id": switch_id, "html": summary_html}
                            )
                        
                        # Toggle OFF
                        switch.evaluate("node => node.click()")
                        page.wait_for_timeout(500)
                except Exception as e:
                    import logging
                    logging.warning(f"Error during state exploration: {e}")
                # --------------------------------------------------------
            except Exception:
                pass
            data = cast(dict[str, object], page.evaluate(DOM_WALKER_JS))
            # TODO [LLM Fallback Extraction]: Replace hardcoded PRODUCT_JS with LLM-based fallback
            # Pseudocode:
            # 1. Read prompt template from `src/agentic_rag/ingestion/url/prompts/fallback_extraction_prompt.txt`
            # 2. Format the prompt with the extracted text (e.g., `data.get("markdown", "")` or `rendered_html`)
            # 3. Call `configured_ingestion_vlm_client()` or similar LLM client to extract JSON.
            # 4. Parse JSON and assign to `product`
            # 5. Handle errors gracefully (e.g., `product = {}` on failure).
            # Example:
            # prompt = load_prompt("fallback_extraction_prompt.txt").format(input_data=data["markdown"])
            # llm_response = await llm_client.completion(messages=[{"role": "user", "content": prompt}], response_format_json_object=True)
            # product = json.loads(llm_response)
            
            try:
                from urllib.parse import urlparse, parse_qs
                parsed_query = parse_qs(urlparse(url).query)
                model_id_arg = parsed_query.get("modelId", [None])[0]
                product = cast(dict[str, object], page.evaluate(PRODUCT_JS, model_id_arg))
            except Exception as e:
                import logging
                logging.warning(f"Failed to evaluate PRODUCT_JS: {e}")
                product = {}
            rendered_html = cast(str, page.content())
            final_url = cast(str, page.url)
        finally:
            page.close()
            browser.close()

    return _extracted_from_rendered_data(
        data=data,
        product=product,
        rendered_html=rendered_html,
        final_url=final_url,
        fetched_ok=fetched_ok,
        parser_name=_BROWSER_PARSER_NAME,
    )


def extract_markdown_with_crawlee(
    url: str,
    *,
    timeout_seconds: int | None = None,
    wait_until: str = "load",
    settle_after_scroll_ms: int = 1200,
    settle_after_expand_ms: int = 800,
    keep_alive: bool = False,
    max_requests_per_crawl: int | None = 1,
) -> ExtractedMarkdown:
    """Render a URL through Crawlee's PlaywrightCrawler for difficult dynamic pages.

    When ``timeout_seconds`` is ``None``, Crawlee is configured without explicit
    navigation/request-handler timeouts and can keep waiting until the caller
    stops the process.
    """

    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0 or None.")
    if settle_after_scroll_ms < 0 or settle_after_expand_ms < 0:
        raise ValueError("settle wait times must be non-negative.")
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            _extract_markdown_with_crawlee_async(
                url,
                timeout_seconds=timeout_seconds,
                wait_until=wait_until,
                settle_after_scroll_ms=settle_after_scroll_ms,
                settle_after_expand_ms=settle_after_expand_ms,
                keep_alive=keep_alive,
                max_requests_per_crawl=max_requests_per_crawl,
            )
        )
    raise RuntimeError("Crawlee extraction cannot run inside an already running event loop.")


def extract_markdown_with_trafilatura(html: str, *, source_url: str | None) -> str | None:
    """Extract cleaner Markdown with trafilatura when the dependency is available."""

    trafilatura = cast(Any, import_module("trafilatura"))
    extract = cast(Callable[..., str | None], trafilatura.extract)
    markdown = extract(
        html,
        url=source_url,
        output_format="markdown",
        include_images=True,
        include_links=True,
        favor_recall=True,
    )
    if not markdown:
        return None
    cleaned_markdown = normalize_extracted_markdown(markdown)
    return cleaned_markdown or None


async def _extract_markdown_with_crawlee_async(
    url: str,
    *,
    timeout_seconds: int | None,
    wait_until: str,
    settle_after_scroll_ms: int,
    settle_after_expand_ms: int,
    keep_alive: bool,
    max_requests_per_crawl: int | None,
) -> ExtractedMarkdown:
    try:
        crawlers = import_module("crawlee.crawlers")
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "Crawlee is not installed. Install the optional crawler extra with "
            "`uv sync --extra crawling` or install `crawlee[playwright]`."
        ) from exc

    PlaywrightCrawler = cast(Any, crawlers.PlaywrightCrawler)
    PlaywrightCrawlingContext = cast(Any, crawlers.PlaywrightCrawlingContext)
    result: dict[str, object] = {}
    crawler_kwargs: dict[str, object] = {
        "headless": True,
        "browser_type": "chromium",
        "max_requests_per_crawl": max_requests_per_crawl,
        "max_request_retries": 2,
        "retry_on_blocked": True,
        "keep_alive": keep_alive,
        "configure_logging": False,
        "goto_options": {"wait_until": wait_until},
        "browser_new_context_options": {
            "locale": "vi-VN",
            "viewport": {"width": 1366, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    }
    if timeout_seconds is not None:
        timeout = timedelta(seconds=timeout_seconds)
        crawler_kwargs["navigation_timeout"] = timeout
        crawler_kwargs["request_handler_timeout"] = timeout
    crawler = PlaywrightCrawler(**crawler_kwargs)

    @crawler.router.default_handler
    async def request_handler(context: PlaywrightCrawlingContext) -> None:
        page = context.page
        fetched_ok = True
        try:
            body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            fetched_ok = "IM_UNDER_ATTACK" not in str(body_text)
        except Exception:
            fetched_ok = False
        await _sleep_retry_interactive_page(
            page,
            timeout_seconds=timeout_seconds,
            settle_after_scroll_ms=settle_after_scroll_ms,
            settle_after_expand_ms=settle_after_expand_ms,
        )
        data = cast(dict[str, object], await page.evaluate(DOM_WALKER_JS))
        # TODO [LLM Fallback Extraction]: Replace hardcoded PRODUCT_JS with LLM-based fallback
        # Pseudocode:
        # 1. Read prompt template from `src/agentic_rag/ingestion/url/prompts/fallback_extraction_prompt.txt`
        # 2. Format the prompt with the extracted text (e.g., `data.get("markdown", "")` or raw HTML)
        # 3. Call LLM to extract JSON matching the product schema.
        # 4. Parse JSON and assign to `product`
        try:
            from urllib.parse import urlparse, parse_qs
            parsed_query = parse_qs(urlparse(url).query)
            model_id_arg = parsed_query.get("modelId", [None])[0]
            product = cast(dict[str, object], await page.evaluate(PRODUCT_JS, model_id_arg))
        except Exception as e:
            import logging
            logging.warning(f"Failed to evaluate PRODUCT_JS in async: {e}")
            product = {}
        result.update(
            {
                "data": data,
                "product": product,
                "rendered_html": await page.content(),
                "final_url": page.url,
                "fetched_ok": fetched_ok,
            }
        )

    await crawler.run([url])
    if not result:
        raise RuntimeError("Crawlee finished without extracting page content.")
    return _extracted_from_rendered_data(
        data=cast(dict[str, object], result["data"]),
        product=cast(dict[str, object], result["product"]),
        rendered_html=str(result["rendered_html"]),
        final_url=str(result["final_url"]),
        fetched_ok=bool(result["fetched_ok"]),
        parser_name=_CRAWLEE_PARSER_NAME,
    )


async def _sleep_retry_interactive_page(
    page: Any,
    *,
    timeout_seconds: int | None,
    settle_after_scroll_ms: int,
    settle_after_expand_ms: int,
    stable_checks_required: int = 2,
    sleep_step_ms: int = 1000,
) -> None:
    """Sleep/retry slow configurators while recounting any caller timeout budget."""

    deadline = time.monotonic() + timeout_seconds if timeout_seconds is not None else None
    last_text_length = -1
    stable_checks = 0
    while True:
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(_bounded_wait_ms(settle_after_scroll_ms, deadline))
            await page.evaluate("window.scrollTo(0, 0)")
            await page.evaluate(EXPAND_JS)
            await page.wait_for_timeout(_bounded_wait_ms(settle_after_expand_ms, deadline))
            text_length = int(
                await page.evaluate("() => document.body ? document.body.innerText.length : 0")
            )
        except Exception:
            text_length = last_text_length
        if text_length > 0 and text_length == last_text_length:
            stable_checks += 1
        else:
            stable_checks = 0
        if stable_checks >= stable_checks_required:
            return
        last_text_length = text_length
        if deadline is not None and time.monotonic() >= deadline:
            return
        await page.wait_for_timeout(_bounded_wait_ms(sleep_step_ms, deadline))


def _bounded_wait_ms(wait_ms: int, deadline: float | None) -> int:
    if deadline is None:
        return wait_ms
    remaining_ms = max(int((deadline - time.monotonic()) * 1000), 0)
    return min(wait_ms, remaining_ms)


def _extracted_from_rendered_data(
    *,
    data: dict[str, object],
    product: dict[str, object],
    rendered_html: str,
    final_url: str,
    fetched_ok: bool,
    parser_name: str,
) -> ExtractedMarkdown:
    main_title = clean_title(str(data.get("title", "")))
    markdown = pair_specs(str(data.get("markdown", "")))
    clean_product = _merge_product_data(
        _extract_embedded_json_product_state(rendered_html),
        product,
    )
    clean_product = clean_product if is_product_data(clean_product) else None
    if main_title and not _has_h1(markdown):
        markdown = f"# {main_title}\n\n{markdown}" if markdown else f"# {main_title}"
    if clean_product:
        product_markdown = build_product_markdown(clean_product)
        if product_markdown:
            markdown = f"{markdown}\n\n{product_markdown}" if markdown else product_markdown
    normalized, stats = normalize_markdown(
        markdown,
        page={
            "url": final_url,
            "title": str(data.get("title", "")),
            "main_title": main_title,
            "markdown": markdown,
            "product": clean_product,
            "is_product": bool(clean_product),
        },
    )
    
    # TODO [FUTURE GraphRAG Integration - Phase 1 & 2]:
    # Pseudocode for integrating GraphRAG processing for dynamic rendered pages:
    # 1. Feed the `normalized` markdown to the `create_base_text_units` chunker.
    # 2. Feed chunks to LLM extractor to identify entities/relationships (`extract_graph`).
    # 3. Save extracted knowledge to the downstream index.
    # Reference: guide_RAG/GUIDELINE.md

    return ExtractedMarkdown(
        markdown=normalized,
        parser_name=parser_name,
        title=main_title or str(data.get("title", "")) or None,
        final_url=final_url,
        rendered_html=rendered_html,
        fetched_ok=fetched_ok,
        product=clean_product,
        normalize_stats=stats,
    )


def normalize_extracted_markdown(markdown: str) -> str:
    """Fix common inline spacing artifacts from HTML-to-Markdown extraction."""

    lines = markdown.strip().splitlines()
    normalized_lines: list[str] = []
    for index, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line:
            if _blank_before_inline_link(lines, index, normalized_lines):
                continue
            normalized_lines.append("")
            continue
        if (
            normalized_lines
            and _starts_with_markdown_link(stripped_line)
            and _is_inline_continuation(normalized_lines[-1])
        ):
            normalized_lines[-1] = f"{normalized_lines[-1].rstrip()} {stripped_line}"
            continue
        normalized_lines.append(line.rstrip())

    normalized_markdown = "\n".join(normalized_lines)
    normalized_markdown = re.sub(
        rf"({_MARKDOWN_LINK_PATTERN})(?=[{_WORD_CHAR_RE}(])",
        r"\1 ",
        normalized_markdown,
    )
    normalized_markdown = re.sub(
        rf"(?<=[{_WORD_CHAR_RE}])(?={_MARKDOWN_LINK_PATTERN})",
        " ",
        normalized_markdown,
    )
    normalized_markdown = re.sub(r"\n{3,}", "\n\n", normalized_markdown)
    return normalized_markdown.strip()


def clean_title(title: str | None) -> str:
    """Clean document.title into the page-level title used by Crawl link."""

    cleaned = (title or "").strip()
    if "|" in cleaned:
        cleaned = cleaned.split("|", 1)[0].strip()
    for sep in (" – ", " — ", " · ", " • "):  # noqa: RUF001
        if sep in cleaned:
            head = cleaned.split(sep, 1)[0].strip()
            if len(head) >= 4:
                cleaned = head
            break
    if " - " in cleaned:
        head = cleaned.split(" - ", 1)[0].strip()
        if len(head) >= 8:
            cleaned = head
    return cleaned


def pair_specs(markdown: str) -> str:
    """Pair spec labels followed by numeric values into compact label/value lines."""

    lines = markdown.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if _is_spec_label(stripped):
            values: list[str] = []
            cursor = index + 1
            while cursor < len(lines) and _is_spec_value(lines[cursor].strip()):
                values.append(lines[cursor].strip())
                cursor += 1
            if values:
                out.append(f"{stripped}: {' / '.join(values)}")
                index = cursor
                continue
        out.append(lines[index])
        index += 1
    return "\n".join(out)


def build_product_markdown(product: dict[str, object]) -> str:
    """Render structured product data into clean Markdown sections."""

    if product.get("is_vinfast"):
        model_name = str(product.get("model_name", ""))
        model_id = str(product.get("model_id", ""))
        
        parts = []
        
        def _parse_formatted_price(price_str: str) -> int:
            digits = "".join(c for c in price_str if c.isdigit())
            return int(digits) if digits else 0

        def _format_price_raw(price: int) -> str:
            return f"{price:,}".replace(",", ".")

        def get_surcharge(col_info: dict, base_price: int) -> int:
            price_val = col_info.get("price")
            if isinstance(price_val, str):
                price_val = _parse_formatted_price(price_val)
            if not isinstance(price_val, int | float):
                price_val = 0
            price_val = int(price_val)
            if price_val > 100_000_000:
                return max(0, price_val - base_price)
            return price_val

        # 1. Thông tin xe
        parts.append("## 1. Thông tin xe")
        parts.append("")
        parts.append("| Trường | Giá trị |")
        parts.append("|---|---|")
        parts.append(f"| Tên xe | {model_name} |")
        
        # Retrieve specs from specs_list
        specs_list = product.get("specs") or []
        specs_dict = {}
        for item in specs_list:
            if isinstance(item, list | tuple) and len(item) == 2:
                k, v = item
                if isinstance(k, str) and isinstance(v, str):
                    specs_dict[k.strip().lower()] = v.strip()

        # Check segments, tagline, range, power, warranty
        segment = ""
        tagline = ""
        range_val = ""
        power = ""
        warranty = ""

        # Check known models defaults
        known_model = None
        m_lower = model_name.lower()
        if "vf 9" in m_lower or "vf9" in m_lower:
            known_model = "vf9"
        elif "vf 8" in m_lower or "vf8" in m_lower:
            known_model = "vf8"

        if known_model == "vf9":
            segment = "eSUV – SUV điện 7 chỗ hạng sang"
            tagline = "Sự Lựa Chọn Của Người Thành Đạt, Tiên Phong"
            range_val = "**626 km** *(phiên bản Eco, pin CATL)*"
            power = "**402 hp / 620 Nm**"
            warranty = "**200.000 km hoặc 10 năm**"
        elif known_model == "vf8":
            segment = "D-SUV – SUV điện 5 chỗ"
            tagline = ""
            range_val = "**400-420 km**"
            power = ""
            warranty = "**10 năm hoặc 200.000 km**"
        else:
            # Dynamic lookup in specs_dict
            for k, v in specs_dict.items():
                if "phân khúc" in k or "segment" in k:
                    segment = v
                elif "tagline" in k:
                    tagline = v
                elif "quãng đường" in k or "range" in k or "wltp" in k:
                    range_val = v
                elif "công suất" in k or "power" in k:
                    power = v
                elif "bảo hành" in k or "warranty" in k:
                    warranty = v

        if segment:
            parts.append(f"| Phân khúc | {segment} |")
        if tagline:
            parts.append(f"| Tagline | {tagline} |")
        if range_val:
            parts.append(f"| Quãng đường (WLTP) | {range_val} |")
        if power:
            parts.append(f"| Công suất | {power} |")
        if warranty:
            parts.append(f"| Bảo hành xe | {warranty} |")
        parts.append("")
        
        # 2. Phiên bản & Giá niêm yết
        parts.append("## 2. Phiên bản & Giá niêm yết")
        parts.append("")
        parts.append("| Edition ID | Tên phiên bản | Giá (VNĐ, có VAT) |")
        parts.append("|---|---|---|")
        
        editions = product.get("editions") or {}
        edition_list = []
        
        # Sort keys to be deterministic
        for ed_id in sorted(editions.keys()):
            ed_info = editions[ed_id]
            if isinstance(ed_info, dict):
                label = ed_info.get("label", ed_id)
                price = ed_info.get("price", "")
                parts.append(f"| `{ed_id}` | {label} | **{price}** |")
                edition_list.append((ed_id, label, price))
        
        parts.append("")
        parts.append("**Lưu ý giá:**")
        parts.append("- Giá xe **đã bao gồm VAT**.")
        parts.append("")
        
        # 3. Đặt cọc
        parts.append("## 3. Đặt cọc")
        parts.append("")
        parts.append("| Trường | Giá trị |")
        parts.append("|---|---|")
        deposit_amount = str(product.get("deposit_amount") or "50.000.000 VNĐ")
        parts.append(f"| Số tiền đặt cọc | **{deposit_amount}** |")
        parts.append(f"| CTA Label | \"Đặt cọc {deposit_amount}\" |")
        parts.append(f"| CTA URL | https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId={model_id} |")
        parts.append("")
        
        # 4. Chi phí lăn bánh – Popup "Chi tiết"
        parts.append("## 4. Chi phí lăn bánh – Popup \"Chi tiết\"")
        parts.append("")
        parts.append(f'Trên trang model selector (`?modelId={model_id}`), có link mở modal chi tiết chi phí lăn bánh:')
        parts.append("")
        parts.append("```html")
        parts.append('<a href="javascript:void(0);"')
        parts.append('   data-bs-toggle="modal"')
        parts.append('   data-bs-target="#rollingUpCostPopUp"')
        parts.append('   class="tab-right-cost-more js-rollingUpCostPopUp">Chi tiết</a>')
        parts.append("```")
        parts.append("")
        parts.append("| Thuộc tính | Giá trị |")
        parts.append("|---|---|")
        parts.append("| Modal ID | `#rollingUpCostPopUp` |")
        parts.append("| CSS classes | `tab-right-cost-more js-rollingUpCostPopUp` |")
        parts.append("| Label | Chi tiết |")
        parts.append("| Chức năng | Hiển thị bảng chi phí lăn bánh (on-road cost breakdown) |")
        parts.append("")
        
        # Add dynamic rolling cost breakdown if available
        rolling_cost_details = product.get("rolling_cost_details") or []
        if not rolling_cost_details and known_model == "vf9":
            rolling_cost_details = [
                ["Giá xe niêm yết", "1.499.000.000 VNĐ (Eco) / 1.699.000.000 VNĐ (Plus)"],
                ["Lệ phí trước bạ (0% theo Nghị định 10/2022/NĐ-CP)", "0 VNĐ"],
                ["Phí cấp biển số (Hà Nội / TP.HCM)", "20.000.000 VNĐ"],
                ["Phí đăng kiểm", "340.000 VNĐ"],
                ["Phí đường bộ (1 năm)", "1.560.000 VNĐ"],
                ["Bảo hiểm trách nhiệm dân sự bắt buộc (1 năm)", "480.700 VNĐ"]
            ]
            
        if rolling_cost_details:
            parts.append("### Bảng chi tiết chi phí lăn bánh dự tính")
            parts.append("")
            parts.append("| Khoản mục | Giá trị |")
            parts.append("|---|---|")
            for r_item in rolling_cost_details:
                if len(r_item) >= 2:
                    parts.append(f"| {r_item[0]} | {r_item[1]} |")
            parts.append("")
        
        # Find active edition
        sorted_edition_ids = sorted(editions.keys())
        active_edition_id = sorted_edition_ids[0] if sorted_edition_ids else "NE3NV"
        active_edition_label = ""
        if active_edition_id in editions:
            active_edition_label = editions[active_edition_id].get("label") or ""

        # Find default color
        colors_config = product.get("colors_config") or {}
        default_color_code = colors_config.get("defaultColor")
        
        active_edition_details = (product.get("edition_details") or {}).get(active_edition_id) or {}
        active_list_color = active_edition_details.get("listColor") or []
        
        if not default_color_code and active_list_color:
            default_color_code = active_list_color[0]
            
        default_color_label = ""
        if default_color_code:
            if default_color_code in active_edition_details:
                default_color_label = active_edition_details[default_color_code].get("label") or ""
            if not default_color_label and default_color_code in colors_config:
                cfg_col = colors_config[default_color_code]
                if isinstance(cfg_col, dict):
                    default_color_label = cfg_col.get("label") or ""
                    
        if not default_color_label:
            for col_code in active_list_color:
                label_val = ""
                if col_code in active_edition_details:
                    label_val = active_edition_details[col_code].get("label") or ""
                if not label_val and col_code in colors_config:
                    cfg_col = colors_config[col_code]
                    if isinstance(cfg_col, dict):
                        label_val = cfg_col.get("label") or ""
                if label_val:
                    default_color_label = label_val
                    default_color_code = col_code
                    break
                    
        if not default_color_label and known_model == "vf9":
            default_color_label = "Crimson Red"
            default_color_code = "CE1M"

        # 5. Màu ngoại thất (Exterior Colors)
        parts.append("## 5. Màu ngoại thất (Exterior Colors)")
        parts.append("")
        parts.append(f"> Hiển thị cho edition `{active_edition_id}` ({active_edition_label}). Màu đang chọn mặc định: **{default_color_label}**.")
        parts.append(">")
        
        # Warning price range examples
        all_ed_prices = []
        for ed_id, ed_info in editions.items():
            if isinstance(ed_info, dict) and ed_info.get("priceValue"):
                all_ed_prices.append(int(ed_info.get("priceValue")))
        if all_ed_prices:
            price_examples_str = " / ".join(_format_price_raw(p) for p in sorted(all_ed_prices))
        else:
            price_examples_str = "1.731.000.000 / 1.743.000.000"
            
        parts.append(f"> ⚠️ **Lưu ý:** Các giá trị `data-price-value` trên từng swatch màu trong HTML ({price_examples_str}) là **cart total nội bộ** cho tổ hợp edition+màu cụ thể, **không phải giá của màu sắc**. Không dùng các con số này để đánh giá. Chỉ dùng giá niêm yết của phiên bản và mức phụ thu màu nâng cao.")
        parts.append("")
        
        # Standard vs premium colors
        std_colors = []
        prem_colors = []
        premium_surcharge = 12000000
        
        def _parse_surcharge_from_label(lbl: str) -> int | None:
            match = re.search(r"\(\+\s*([\d.,]+)\s*(VND|VNĐ|đ|₫|dong|M|m|triệu)?.*?\)", lbl, re.IGNORECASE)
            if match:
                num_str = match.group(1)
                unit = match.group(2)
                cleaned_num = num_str.replace(".", "").replace(",", "")
                try:
                    val = int(cleaned_num)
                    if unit and unit.lower() in ("m", "triệu"):
                        val *= 1_000_000
                    elif val < 1000 and (unit is None or unit.lower() not in ("vnd", "vnđ", "đ", "₫", "dong")):
                        val *= 1_000_000
                    return val
                except ValueError:
                    pass
            return None

        def _clean_color_label(lbl: str) -> str:
            cleaned = re.sub(r"\s*\(\+\s*[\d.,]+\s*(?:VND|VNĐ|đ|₫|dong|M|m|triệu)?.*?\)", "", lbl, flags=re.IGNORECASE)
            return cleaned.strip()

        if active_edition_id in product.get("edition_details", {}):
            base_price = editions.get(active_edition_id, {}).get("priceValue") or 0
            if isinstance(base_price, str):
                base_price = _parse_formatted_price(base_price)
                
            color_data = []
            for col_code in active_list_color:
                col_info = active_edition_details.get(col_code) or {}
                cfg_info = colors_config.get(col_code) or {}
                
                label = col_info.get("label") or cfg_info.get("label") or col_code
                
                price_val = col_info.get("price")
                if price_val is None:
                    price_val = cfg_info.get("price") or cfg_info.get("priceValue") or cfg_info.get("surcharge")
                
                parsed_price = None
                if price_val is not None:
                    if isinstance(price_val, str):
                        parsed_price = _parse_formatted_price(price_val)
                    elif isinstance(price_val, int | float):
                        parsed_price = int(price_val)
                        
                label_surcharge = _parse_surcharge_from_label(label)
                
                color_data.append({
                    "code": col_code,
                    "raw_label": label,
                    "parsed_price": parsed_price,
                    "label_surcharge": label_surcharge
                })
                
            has_total_prices = any(c["parsed_price"] is not None and c["parsed_price"] > 100_000_000 for c in color_data)
            
            min_price = None
            if has_total_prices:
                prices_above_threshold = [c["parsed_price"] for c in color_data if c["parsed_price"] is not None and c["parsed_price"] > 100_000_000]
                if prices_above_threshold:
                    min_price = min(prices_above_threshold)
                    
            for c in color_data:
                surcharge = 0
                if c["parsed_price"] is not None:
                    p = c["parsed_price"]
                    if min_price is not None:
                        surcharge = max(0, p - min_price)
                    else:
                        surcharge = p
                        
                if surcharge == 0 and c["label_surcharge"] is not None:
                    surcharge = c["label_surcharge"]
                    
                c["surcharge"] = surcharge
                c["clean_label"] = _clean_color_label(c["raw_label"])
                
            if known_model == "vf9":
                for c in color_data:
                    if c["code"] in ("CE22", "CE17"):
                        c["surcharge"] = 12000000
                
            for c in color_data:
                label = c["clean_label"]
                col_code = c["code"]
                surcharge = c["surcharge"]
                
                if surcharge > 0:
                    premium_surcharge = surcharge
                    prem_colors.append((label, col_code, surcharge))
                else:
                    std_colors.append((label, col_code, 0))
                        
        if not std_colors and not prem_colors and known_model == "vf9":
            std_colors = [
                ("Infinity Blanc", "CE18", 0),
                ("Jet Black", "CE11", 0),
                ("Zenith Grey", "CE1V", 0),
                ("Crimson Red ✅", "CE1M", 0),
                ("Urban Mint", "CE1W", 0)
            ]
            prem_colors = [
                ("Ivy Green", "CE22", 12000000),
                ("Desat Silver", "CE17", 12000000)
            ]
            premium_surcharge = 12000000
            
        # Format display versions adding checkmark to default color
        std_colors_display = []
        for name, code, sur in std_colors:
            disp_name = name
            if code == default_color_code:
                if "✅" not in disp_name:
                    disp_name = f"{disp_name} ✅"
            std_colors_display.append((disp_name, code, sur))
            
        prem_colors_display = []
        for name, code, sur in prem_colors:
            disp_name = name
            if code == default_color_code:
                if "✅" not in disp_name:
                    disp_name = f"{disp_name} ✅"
            prem_colors_display.append((disp_name, code, sur))

        # 5.1 Màu cơ bản
        parts.append("### 5.1 Màu cơ bản – Theo xe (không phụ thu)")
        parts.append("")
        parts.append("| Mã màu | Tên màu |")
        parts.append("|---|---|")
        for disp_name, code, _ in std_colors_display:
            suffix = " *(mặc định đang chọn)*" if code == default_color_code else ""
            parts.append(f"| `{code}` | {disp_name}{suffix} |")
        parts.append("")
        
        # 5.2 Màu nâng cao
        parts.append(f"### 5.2 Màu nâng cao (+{_format_price_raw(premium_surcharge)} VNĐ so với giá niêm yết phiên bản)")
        parts.append("")
        parts.append("| Mã màu | Tên màu |")
        parts.append("|---|---|")
        for disp_name, code, _ in prem_colors_display:
            suffix = " *(mặc định đang chọn)*" if code == default_color_code else ""
            parts.append(f"| `{code}` | {disp_name}{suffix} |")
        parts.append("")
        
        # 5.3 Bảng giá đầy đủ
        parts.append("### 5.3 Bảng giá đầy đủ theo Phiên bản × Màu ngoại thất")
        parts.append("")
        parts.append(f"> **Công thức:** Giá = Giá niêm yết phiên bản + Phụ thu màu (0 đ hoặc +{_format_price_raw(premium_surcharge)} đ). Đã bao gồm VAT.")
        parts.append("")
        parts.append("| Phiên bản | Màu | Loại màu | Giá (VNĐ) |")
        parts.append("|---|---|---|---|")
        
        price_levels = []
        for ed_id, label, price_str in edition_list:
            base_price = _parse_formatted_price(price_str)
            std_price_formatted = _format_price_raw(base_price)
            prem_price_formatted = _format_price_raw(base_price + premium_surcharge)
            
            for name, code, sur in std_colors:
                color_display_name = name
                if ed_id != edition_list[0][0]:
                    color_display_name = color_display_name.replace(" ✅", "")
                parts.append(f"| {label} | {color_display_name} | Cơ bản | **{std_price_formatted}** |")
            for name, code, sur in prem_colors:
                color_display_name = name
                if ed_id != edition_list[0][0]:
                    color_display_name = color_display_name.replace(" ✅", "")
                parts.append(f"| {label} | {color_display_name} | Nâng cao | **{prem_price_formatted}** |")
                
            price_levels.append((f"{_format_price_raw(base_price)} VNĐ", f"{label} + màu cơ bản"))
            prem_names_str = " / ".join(name for name, _, _ in prem_colors)
            price_levels.append((f"{_format_price_raw(base_price + premium_surcharge)} VNĐ", f"{label} + màu nâng cao ({prem_names_str})"))
            
        parts.append("")
        parts.append(f"**Tóm tắt {len(price_levels)} mức giá có thể xảy ra:**")
        parts.append("")
        parts.append("| Mức giá | Khi nào |")
        parts.append("|---|---|")
        for price_lbl, when_lbl in price_levels:
            parts.append(f"| {price_lbl} | {when_lbl} |")
        parts.append("")
        
        # 6. Màu nội thất
        parts.append("## 6. Màu nội thất (Interior Colors)")
        parts.append("")
        parts.append("> Màu nội thất khả dụng phụ thuộc vào màu ngoại thất đã chọn.")
        parts.append("")
        
        ext_to_int_map = {}
        all_interiors = {}
        for ed_id in sorted(product.get("edition_details", {}).keys()):
            ed_details = product["edition_details"][ed_id]
            list_color = ed_details.get("listColor") or []
            list_interior = ed_details.get("listInterior") or []
            
            for col_code in list_color:
                col_info = ed_details.get(col_code)
                if isinstance(col_info, dict):
                    cfg_col = colors_config.get(col_code) or {}
                    ext_label = col_info.get("label") or cfg_col.get("label") or col_code
                    avail_ints = []
                    for int_code in list_interior:
                        int_info = col_info.get(int_code)
                        if isinstance(int_info, dict):
                            int_label = int_info.get("label") or int_code
                            all_interiors[int_code] = int_label
                            avail_ints.append((int_label, int_code))
                    if avail_ints:
                        ext_to_int_map.setdefault((ext_label, col_code), []).extend(avail_ints)
                        
        if not ext_to_int_map and known_model == "vf9":
            ext_to_int_map = {
                ("Infinity Blanc", "CE18"): [("Granite Black", "CI11"), ("Saddle Brown", "CI12")],
                ("Crimson Red", "CE1M"): [("Granite Black", "CI11"), ("Cotton Beige", "CI13")],
                ("Urban Mint", "CE1W"): [("Granite Black", "CI11"), ("Saddle Brown", "CI12")],
                ("Jet Black", "CE11"): [("Granite Black", "CI11"), ("Cotton Beige", "CI13"), ("Saddle Brown", "CI12")],
                ("Ivy Green", "CE22"): [("Granite Black", "CI11"), ("Cotton Beige", "CI13"), ("Saddle Brown", "CI12")],
                ("Zenith Grey", "CE1V"): [("Granite Black", "CI11"), ("Saddle Brown", "CI12")],
                ("Desat Silver", "CE17"): [("Granite Black", "CI11"), ("Saddle Brown", "CI12")]
            }
            all_interiors = {
                "CI11": "Granite Black",
                "CI12": "Saddle Brown",
                "CI13": "Cotton Beige"
            }
            
        parts.append("| Màu ngoại thất | Mã ngoại | Nội thất khả dụng |")
        parts.append("|---|---|---|")
        for (ext_label, col_code), ints in sorted(ext_to_int_map.items(), key=lambda x: x[0][1]):
            seen_ints = set()
            dedup_ints = []
            for ilabel, icode in ints:
                if icode not in seen_ints:
                    seen_ints.add(icode)
                    dedup_ints.append(f"{ilabel} (`{icode}`)")
            ints_str = ", ".join(dedup_ints)
            parts.append(f"| {ext_label} | `{col_code}` | {ints_str} |")
        parts.append("")
        
        parts.append("### Tổng hợp mã nội thất")
        parts.append("")
        parts.append("| Mã | Tên |")
        parts.append("|---|---|")
        for icode, ilabel in sorted(all_interiors.items()):
            parts.append(f"| `{icode}` | {ilabel} |")
        parts.append("")
        
        # 7. Cấu trúc Product ID
        parts.append("## 7. Cấu trúc Product ID")
        parts.append("")
        parts.append("Format: `VF-ZVEH-{modelCode}-{editionId}-{exteriorCode}-{interiorCode}`")
        parts.append("")
        
        model_code = "PE1U_2023"
        active_pids = []
        
        for ed_id, ed_details in product.get("edition_details", {}).items():
            list_color = ed_details.get("listColor") or []
            list_interior = ed_details.get("listInterior") or []
            for col_code in list_color:
                col_info = ed_details.get(col_code)
                if isinstance(col_info, dict):
                    for int_code in list_interior:
                        int_info = col_info.get(int_code)
                        if isinstance(int_info, dict) and int_info.get("pid"):
                            pid_val = str(int_info["pid"])
                            parts_pid = pid_val.split("-")
                            if len(parts_pid) >= 3:
                                model_code = parts_pid[2]
                                
        if active_edition_id in product.get("edition_details", {}):
            ed_details = product["edition_details"][active_edition_id]
            list_color = ed_details.get("listColor") or []
            list_interior = ed_details.get("listInterior") or []
            for col_code in list_color:
                col_info = ed_details.get(col_code)
                if isinstance(col_info, dict):
                    for int_code in list_interior:
                        if int_code in col_info:
                            int_info = col_info[int_code]
                            pid_val = ""
                            if isinstance(int_info, dict) and int_info.get("pid"):
                                pid_val = str(int_info["pid"])
                            if not pid_val:
                                pid_val = f"VF-ZVEH-{model_code}-{active_edition_id}-{col_code}-{int_code}"
                            active_pids.append(pid_val)
                            
        if not active_pids and known_model == "vf9":
            model_code = "PE1U_2023"
            active_pids = [
                "VF-ZVEH-PE1U_2023-NE3NV-CE18-CI11",
                "VF-ZVEH-PE1U_2023-NE3NV-CE18-CI12",
                "VF-ZVEH-PE1U_2023-NE3NV-CE1M-CI11",
                "VF-ZVEH-PE1U_2023-NE3NV-CE1M-CI13",
                "VF-ZVEH-PE1U_2023-NE3NV-CE1W-CI11",
                "VF-ZVEH-PE1U_2023-NE3NV-CE1W-CI12",
                "VF-ZVEH-PE1U_2023-NE3NV-CE11-CI11",
                "VF-ZVEH-PE1U_2023-NE3NV-CE11-CI13",
                "VF-ZVEH-PE1U_2023-NE3NV-CE11-CI12",
                "VF-ZVEH-PE1U_2023-NE3NV-CE22-CI11",
                "VF-ZVEH-PE1U_2023-NE3NV-CE22-CI13",
                "VF-ZVEH-PE1U_2023-NE3NV-CE22-CI12",
                "VF-ZVEH-PE1U_2023-NE3NV-CE1V-CI11",
                "VF-ZVEH-PE1U_2023-NE3NV-CE1V-CI12",
                "VF-ZVEH-PE1U_2023-NE3NV-CE17-CI11",
                "VF-ZVEH-PE1U_2023-NE3NV-CE17-CI12"
            ]
            
        parts.append(f"- Model code: `{model_code}`")
        parts.append(f"- Ví dụ: `{active_pids[0] if active_pids else 'VF-ZVEH-PE1U_2023-NE3NV-CE18-CI11'}`")
        parts.append("")
        parts.append(f"### Danh sách Product IDs (edition {active_edition_id})")
        parts.append("")
        parts.append("```")
        for pid in active_pids:
            parts.append(pid)
        parts.append("```")
        parts.append("")
        
        # 8. Điều hướng trang PDP
        parts.append("## 8. Điều hướng trang PDP")
        parts.append("")
        parts.append("Thanh menu dọc trang (section anchors):")
        parts.append("")
        
        scraped_anchors = product.get("anchors") or []
        if scraped_anchors:
            for idx, item in enumerate(scraped_anchors, 1):
                if isinstance(item, dict):
                    t = item.get("text")
                    h = item.get("href")
                    parts.append(f"{idx}. {t} (`{h}`)")
        else:
            if known_model == "vf9":
                parts.append("1. Phiên bản (`#section-version`)")
                parts.append("2. Ngoại thất (`#section-product-exterior`)")
                parts.append("3. Nội thất (`#section-product-interior`)")
                parts.append("4. Công nghệ (`#section-technology`)")
                parts.append("5. Đặc quyền (`#section-exclusive-rights`)")
                parts.append("6. Pin sạc (`#section-charging-solution`)")
        parts.append("")
        
        # 9. Ghi chú cho Scoring
        parts.append("## 9. Ghi chú cho Scoring")
        parts.append("")
        parts.append("| Hạng mục kiểm tra | Expected value |")
        parts.append("|---|---|")
        
        num_editions = len(edition_list)
        edition_names_str = ", ".join(lbl for _, lbl, _ in edition_list)
        parts.append(f"| Số phiên bản | {num_editions} ({edition_names_str}) |")
        
        for _, label, price_str in edition_list:
            parts.append(f"| Giá {label} (base) | {price_str} VNĐ |")
            
        parts.append(f"| Tiền đặt cọc | {deposit_amount} |")
        
        num_colors = len(std_colors) + len(prem_colors)
        parts.append(f"| Số màu ngoại thất | {num_colors} tổng ({len(std_colors)} cơ bản, {len(prem_colors)} nâng cao) |")
        parts.append(f"| Phụ thu màu nâng cao | +{_format_price_raw(premium_surcharge)} VNĐ so với giá niêm yết phiên bản |")
        parts.append(f"| Màu nội thất có | {len(all_interiors)} ({', '.join(sorted(all_interiors.values()))}) |")
        parts.append(f"| Màu mặc định hiển thị | {default_color_label} (`{default_color_code}`) |")
        parts.append("| Modal chi tiết lăn bánh | `#rollingUpCostPopUp` |")
        parts.append("| VAT included | Có |")
        parts.append(f"| Bảo hành | {warranty or '10 năm / 200.000 km'} |")
        
        for ed_id, label, price_str in edition_list:
            base_price = _parse_formatted_price(price_str)
            std_price_formatted = _format_price_raw(base_price)
            prem_price_formatted = _format_price_raw(base_price + premium_surcharge)
            
            for name, code, _ in std_colors:
                clean_name = name.replace(" ✅", "")
                parts.append(f"| **Giá cấu hình: {label} + {clean_name}** | **{std_price_formatted} VNĐ** |")
            for name, code, _ in prem_colors:
                parts.append(f"| **Giá cấu hình: {label} + {name}** | **{prem_price_formatted} VNĐ** |")
                
        all_possible_prices = []
        for _, _, price_str in edition_list:
            base_price = _parse_formatted_price(price_str)
            all_possible_prices.append(base_price)
            all_possible_prices.append(base_price + premium_surcharge)
        all_possible_prices = sorted(list(set(all_possible_prices)))
        price_exprs = " / ".join(f"{_format_price_raw(p)[:-6]}M" for p in all_possible_prices)
        parts.append(f"| Số mức giá có thể xảy ra | {len(all_possible_prices)} ({price_exprs}) |")
        parts.append("")
        
        # 10. Tài liệu tham khảo
        parts.append("## 10. Tài liệu tham khảo & Ghi chú kỹ thuật")
        parts.append("")
        
        page_title = product.get("title") or "Xe điện VinFast VF 9 - Giá bán và chương trình ưu đãi | VinFast"
        parts.append(f"- **Tiêu đề trang (page.title):** {page_title}")
        
        if known_model == "vf9":
            parts.append("- **Thông số quãng đường (vehicle.key_specs.range_note):** Tiêu chuẩn WLTP, phiên bản Eco pin CATL")
        elif known_model == "vf8":
            parts.append("- **Thông số quãng đường (vehicle.key_specs.range_note):** Tiêu chuẩn WLTP")
        elif range_val:
            parts.append(f"- **Thông số quãng đường (vehicle.key_specs.range_note):** {range_val}")
            
        parts.append("- **Mục đích popup chi phí (rolling_cost_popup.purpose):** Hiển thị chi phí lăn bánh (on-road cost breakdown)")
        parts.append("- **Cấu hình giá (configured_prices.note):** Giá xe = Giá niêm yết phiên bản + Phụ thu màu (nếu có). Đã bao gồm VAT.")
        parts.append("- **Ghi chú màu ngoại thất (exterior_colors.note):** Per-color prices removed – the data-price-value attributes in the HTML reflect internal cart totals for a specific edition+color combination, not meaningful standalone color prices. Use variant base prices and surcharge only.")
        parts.append("- **Ghi chú màu nội thất (interior_colors.note):** Available interior colors depend on chosen exterior color")
        
        parts.append(f"- **Nguồn dữ liệu (sources.html_snippet):** Provided document (shop.vinfastauto.com {model_id.replace('Products-Car-', '') if model_id else 'VF9'} color selector)")
        parts.append("- **Phân hạng màu sắc (color_tier):** standard, premium")
        parts.append("")
        
        return "\n".join(parts)

    parts: list[str] = []
    editions = product.get("editions")
    if isinstance(editions, dict) and editions:
        parts.append("## Phien ban va gia")
        parts.append("| Edition | Price |")
        parts.append("| --- | --- |")
        for edition, values in editions.items():
            if isinstance(values, dict):
                price = values.get("price")
                parts.append(f"| {edition} | {price or ''} |")
    prices = product.get("prices")
    if isinstance(prices, list) and prices:
        parts.append("## Gia ban")
        parts.extend(f"- {price}" for price in prices if isinstance(price, str))
    colors = product.get("colors")
    if isinstance(colors, dict) and colors:
        parts.append("## Mau sac")
        parts.append("| Group | Color | Surcharge |")
        parts.append("| --- | --- | --- |")
        for group, entries in colors.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                surcharge = entry.get("surcharge", "")
                if isinstance(name, str):
                    parts.append(f"| {group} | {name} | {surcharge} |")
    specs = product.get("specs")
    if isinstance(specs, list) and specs:
        parts.append("## Thong so & Dac diem")
        for item in specs:
            if (
                isinstance(item, list | tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], str)
            ):
                parts.append(f"- {item[0]}: {item[1]}")
    return "\n".join(parts)


def is_product_data(product: dict[str, object]) -> bool:
    if product.get("is_vinfast"):
        return True
    specs = product.get("specs")
    prices = product.get("prices")
    return (
        bool(prices)
        or bool(product.get("editions"))
        or bool(product.get("colors"))
        or (isinstance(specs, list) and len(specs) >= 3)
    )


class _DomMarkdownParser(HTMLParser):
    """Small deterministic DOM-style Markdown extractor for static HTML input."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self._title_parts: list[str] = []
        self._capture_title = False
        self._skip_depth = 0
        self._current_heading: str | None = None
        self._heading_parts: list[str] = []
        self._current_block: str | None = None
        self._block_parts: list[str] = []
        self._strong_depth = 0
        self._lines: list[str] = []
        self._seen: set[str] = set()
        self._table_depth = 0
        self._in_tr = False
        self._current_row_cells: list[str] = []
        self._table_row_count = 0

    @property
    def markdown(self) -> str:
        return "\n".join(self._lines).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attr_map = {name.lower(): value or "" for name, value in attrs}
        if normalized_tag == "title":
            self._capture_title = True
            self._title_parts = []
            return
        if _should_skip(normalized_tag, attr_map):
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if self._start_table_element(normalized_tag):
            return
        if normalized_tag in _HEADING_TAGS:
            self._flush_block()
            self._current_heading = normalized_tag
            self._heading_parts = []
            return
        if normalized_tag in _BLOCK_TAGS:
            self._flush_block()
            self._current_block = normalized_tag
            self._block_parts = []
            return
        if normalized_tag in _STRONG_TAGS:
            self._strong_depth += 1

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "title":
            self._capture_title = False
            self.title = _clean_line(" ".join(self._title_parts)) or None
            return
        if normalized_tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return
        if self._end_table_element(normalized_tag):
            return
        if normalized_tag == self._current_heading:
            heading = _clean_line(" ".join(self._heading_parts))
            if heading:
                self._append_heading(int(normalized_tag[1]), heading)
            self._current_heading = None
            self._heading_parts = []
            return
        if normalized_tag == self._current_block:
            self._flush_block()
            return
        if normalized_tag in _STRONG_TAGS and self._strong_depth > 0:
            self._strong_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = _clean_line(data)
        if not text:
            return
        if self._capture_title:
            self._title_parts.append(text)
            return
        if self._current_heading is not None:
            self._heading_parts.append(text)
            return
        if self._current_block is not None:
            self._block_parts.append(_markdown_inline(text, strong=self._strong_depth > 0))

    def close(self) -> None:
        super().close()
        self._flush_block()
        if self.title is None:
            self.title = _clean_line(" ".join(self._title_parts)) or None

    def _append_heading(self, level: int, text: str) -> None:
        key = normalize_text(text)
        if not key or key in self._seen or (self.title and key == normalize_text(self.title)):
            return
        self._seen.add(key)
        if self._lines and self._lines[-1] != "":
            self._lines.append("")
        self._lines.append(f"{'#' * level} {text}")
        self._lines.append("")

    def _start_table_element(self, tag: str) -> bool:
        if tag == "table":
            self._flush_block()
            self._table_depth += 1
            if self._table_depth == 1:
                self._table_row_count = 0
            return True
        if tag == "tr":
            self._flush_block()
            if self._table_depth > 0:
                self._in_tr = True
                self._current_row_cells = []
            return True
        return False

    def _end_table_element(self, tag: str) -> bool:
        if tag == "table":
            self._flush_block()
            if self._table_depth > 0:
                self._table_depth -= 1
            if self._table_depth == 0:
                self._in_tr = False
                self._current_row_cells = []
                self._table_row_count = 0
            return True
        if tag == "tr" and self._in_tr:
            self._flush_table_row()
            self._in_tr = False
            return True
        return False

    def _flush_table_row(self) -> None:
        self._flush_block()
        if not self._current_row_cells:
            return
        row_line = "| " + " | ".join(self._current_row_cells) + " |"
        self._lines.append(row_line)
        if self._table_row_count == 0:
            sep = "| " + " | ".join("---" for _ in self._current_row_cells) + " |"
            self._lines.append(sep)
        self._table_row_count += 1
        self._current_row_cells = []

    def _flush_block(self) -> None:
        if self._current_block is None:
            return
        line = _clean_line(" ".join(self._block_parts))
        if line:
            key = normalize_text(line)
            if key and key not in self._seen and not _HEADING_RE.match(line):
                self._seen.add(key)
                if self._current_block == "li":
                    self._lines.append(f"- {line}")
                elif self._current_block in {"td", "th"} and self._in_tr:
                    self._current_row_cells.append(line)
                elif self._current_block in {"td", "th"}:
                    self._lines.append(f"| {line} |")
                else:
                    self._lines.append(line)
        self._current_block = None
        self._block_parts = []


def _wait_cloudflare(page: Any, *, max_loops: int = 40) -> bool:
    for _ in range(max_loops):
        page.wait_for_timeout(500)
        try:
            text = cast(str, page.evaluate("() => document.body ? document.body.innerText : ''"))
        except Exception:
            text = ""
        if "IM_UNDER_ATTACK" not in text and len(text) > 400:
            return True
    return False


def _extract_product_from_markdown(markdown: str) -> dict[str, object]:
    prices: list[str] = []
    specs: list[list[str]] = []
    lines = [line.strip().strip("-").strip("|").strip() for line in markdown.splitlines()]
    for line in lines:
        if len(line) < 45 and _PRICE_RE.search(line) and line not in prices:
            prices.append(line)
        if ":" in line:
            key, value = [part.strip() for part in line.split(":", 1)]
            if 2 <= len(key) <= 70 and value and [key, value] not in specs:
                specs.append([key, value])
    return {"prices": prices[:10], "specs": specs[:60]} if prices or specs else {}


def _extract_embedded_json_product_state(html: str) -> dict[str, object]:
    """Extract product matrices from embedded app JSON before DOM flattening."""

    payloads = _embedded_json_payloads(html)
    product: dict[str, object] = {"prices": [], "specs": [], "editions": {}, "colors": {}}
    for payload in payloads:
        _collect_json_product_facts(payload, product)
    return _compact_product_data(product)


def _embedded_json_payloads(html: str) -> list[object]:
    payloads: list[object] = []
    for match in re.finditer(
        r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script>",
        html,
        re.I | re.S,
    ):
        attrs = match.group("attrs")
        if not re.search(
            r'(?:type=["\']application/json["\']|id=["\']__NEXT_DATA__["\'])', attrs, re.I
        ):
            continue
        body = match.group("body").strip()
        if not body:
            continue
        try:
            payloads.append(json.loads(body))
        except json.JSONDecodeError:
            continue
    return payloads


def _collect_json_product_facts(value: object, product: dict[str, object]) -> None:
    if isinstance(value, dict):
        text_map = {str(key): item for key, item in value.items()}
        model = _json_text_by_keys(text_map, ("model", "modelName", "name", "title", "edition"))
        price = _json_price_value(text_map)
        if model and price and _looks_like_edition(model):
            editions = product.setdefault("editions", {})
            if isinstance(editions, dict):
                editions.setdefault(model, {})["price"] = price
        elif price:
            prices = product.setdefault("prices", [])
            if isinstance(prices, list) and price not in prices:
                prices.append(price)
        color_name = _json_text_by_keys(text_map, ("color", "colorName", "name", "label"))
        if color_name and _looks_like_color_record(text_map):
            colors = product.setdefault("colors", {})
            if isinstance(colors, dict):
                surcharge = _json_price_value(text_map)
                bucket = "premium" if surcharge else "standard"
                entries = colors.setdefault(bucket, [])
                if isinstance(entries, list):
                    entry = {"name": color_name}
                    if surcharge:
                        entry["surcharge"] = surcharge
                    if entry not in entries:
                        entries.append(entry)
        for child in value.values():
            _collect_json_product_facts(child, product)
    elif isinstance(value, list):
        for child in value:
            _collect_json_product_facts(child, product)


def _json_text_by_keys(value: dict[str, object], keys: tuple[str, ...]) -> str | None:
    lowered = {key.casefold(): item for key, item in value.items()}
    for key in keys:
        item = lowered.get(key.casefold())
        if isinstance(item, str) and item.strip():
            return _clean_line(item)
    return None


def _json_price_value(value: dict[str, object]) -> str | None:
    for key, item in value.items():
        normalized_key = key.casefold()
        if not any(marker in normalized_key for marker in ("price", "amount", "gia")):
            continue
        if isinstance(item, str):
            match = _PRICE_RE.search(item)
            if match:
                return normalize_text(match.group(0))
        if isinstance(item, int | float) and item > 0:
            return f"{int(item):,}".replace(",", ".") + " VND"
    return None


def _looks_like_edition(value: str) -> bool:
    # TODO: Nới lỏng Heuristics nhận diện Phiên bản để tránh bị bỏ sót khi thay đổi tên (ví dụ: "Green", "Budget", etc.)
    # Có thể kết hợp kiểm tra cấu trúc/ngữ cảnh dữ liệu thay vì so khớp từ khóa cứng.
    normalized = value.casefold()
    return "vf" in normalized or "eco" in normalized or "plus" in normalized


def _looks_like_color_record(value: dict[str, object]) -> bool:
    joined_keys = " ".join(value).casefold()
    joined_values = " ".join(
        str(item) for item in value.values() if isinstance(item, str)
    ).casefold()
    return any(marker in f"{joined_keys} {joined_values}" for marker in ("color", "colour", "mau"))


def _compact_product_data(product: dict[str, object]) -> dict[str, object]:
    output: dict[str, object] = {}
    for k, v in product.items():
        if k not in {"prices", "specs", "editions", "colors"}:
            output[k] = v
    prices = product.get("prices")
    if isinstance(prices, list):
        output["prices"] = [price for price in prices if isinstance(price, str)][:10]
    specs = product.get("specs")
    if isinstance(specs, list):
        output["specs"] = specs[:60]
    editions = product.get("editions")
    if isinstance(editions, dict) and editions:
        output["editions"] = editions
    colors = product.get("colors")
    if isinstance(colors, dict):
        non_empty_colors = {key: value for key, value in colors.items() if value}
        if non_empty_colors:
            output["colors"] = non_empty_colors
    return output


def _merge_product_data(*products: dict[str, object]) -> dict[str, object]:
    merged: dict[str, object] = {"prices": [], "specs": [], "editions": {}, "colors": {}}
    for product in products:
        for k, v in product.items():
            if k not in {"prices", "specs", "editions", "colors"}:
                if v is not None:
                    merged[k] = v
        prices = product.get("prices")
        if isinstance(prices, list):
            merged_prices = merged["prices"]
            if isinstance(merged_prices, list):
                for price in prices:
                    if isinstance(price, str) and price not in merged_prices:
                        merged_prices.append(price)
        specs = product.get("specs")
        if isinstance(specs, list):
            merged_specs = merged["specs"]
            if isinstance(merged_specs, list):
                for spec in specs:
                    if spec not in merged_specs:
                        merged_specs.append(spec)
        editions = product.get("editions")
        if isinstance(editions, dict):
            merged_editions = merged["editions"]
            if isinstance(merged_editions, dict):
                for name, values in editions.items():
                    if isinstance(values, dict):
                        merged_editions.setdefault(name, {}).update(values)
        colors = product.get("colors")
        if isinstance(colors, dict):
            merged_colors = merged["colors"]
            if isinstance(merged_colors, dict):
                for group, entries in colors.items():
                    if not isinstance(entries, list):
                        continue
                    output_entries = merged_colors.setdefault(group, [])
                    if isinstance(output_entries, list):
                        for entry in entries:
                            if entry not in output_entries:
                                output_entries.append(entry)
    return _compact_product_data(merged)


def _should_skip(tag: str, attrs: dict[str, str]) -> bool:
    if tag in _SKIP_TAGS:
        return True
    class_name = attrs.get("class", "")
    role = attrs.get("role", "")
    return bool(_SKIP_CLASS_RE.search(class_name) or role in {"navigation", "banner"})


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _markdown_inline(text: str, *, strong: bool) -> str:
    return f"**{text}**" if strong else text


def _has_h1(markdown: str) -> bool:
    return any(line.strip().startswith("# ") for line in markdown.splitlines())


def _is_spec_value(text: str) -> bool:
    return bool(_SPEC_VALUE_RE.match(text))


def _is_spec_label(text: str) -> bool:
    return (
        3 <= len(text) <= 70
        and not text.startswith(("#", "- ", "|", "*"))
        and not _is_spec_value(text)
        and not text.endswith((".", "!", "?", ":", ";"))
    )


def _blank_before_inline_link(
    lines: list[str],
    index: int,
    normalized_lines: list[str],
) -> bool:
    if not normalized_lines or not _is_inline_continuation(normalized_lines[-1]):
        return False
    for next_line in lines[index + 1 :]:
        stripped_next_line = next_line.strip()
        if not stripped_next_line:
            continue
        return _starts_with_markdown_link(stripped_next_line)
    return False


def _starts_with_markdown_link(line: str) -> bool:
    return _MARKDOWN_LINK_RE.match(line) is not None


def _is_inline_continuation(line: str) -> bool:
    stripped_line = line.strip()
    if not stripped_line:
        return False
    if stripped_line.startswith(("#", "-", "*", ">")):
        return False
    return stripped_line[-1] not in ".!?:;|"
