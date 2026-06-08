# ruff: noqa: E501
"""Main-content extraction adapters for URL ingestion."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from importlib import import_module
from typing import Any, cast

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
}
"""

PRODUCT_JS = r"""
() => {
  const T = s => (s||'').trim().replace(/\s+/g,' ');
  const uniq = a => [...new Set(a)];
  const res = {prices:[], specs:[]};
  const CUR = /\d[\d.,]*\s*(VNĐ|VND|₫|đồng|dong|USD|US\$|\$)\b/i;
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
  return res;
}
"""


@dataclass(frozen=True)
class ExtractedMarkdown:
    """Clean Markdown plus extractor metadata."""

    markdown: str
    parser_name: str
    title: str | None = None
    final_url: str | None = None
    rendered_html: str | None = None
    fetched_ok: bool = True
    product: dict[str, object] | None = None
    normalize_stats: dict[str, object] = field(default_factory=dict)


def extract_markdown_from_html(
    html: str,
    *,
    title: str | None = None,
    source_url: str | None = None,
) -> ExtractedMarkdown | None:
    """Extract Crawl-link-style Markdown from an HTML string without browser dependency."""

    parser = _DomMarkdownParser()
    parser.feed(html)
    parser.close()
    main_title = clean_title(title or parser.title)
    markdown = pair_specs(parser.markdown)
    product_data = _extract_product_from_markdown(markdown)
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
    return ExtractedMarkdown(
        markdown=normalized,
        parser_name=_PARSER_NAME,
        title=main_title or parser.title,
        product=product or None,
        normalize_stats=stats,
    )


def extract_markdown_with_playwright(url: str) -> ExtractedMarkdown:
    """Render a URL and extract Markdown using the Crawl link Playwright DOM walker."""

    try:
        sync_playwright = cast(Any, import_module("playwright.sync_api")).sync_playwright
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("Python Playwright is not installed.") from exc

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
        context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = context.new_page()
        try:
            page.goto(url, wait_until="load", timeout=60_000)
            fetched_ok = _wait_cloudflare(page)
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(800)
                page.evaluate("window.scrollTo(0, 0)")
                page.evaluate(EXPAND_JS)
                page.wait_for_timeout(400)
            except Exception:
                pass
            data = cast(dict[str, object], page.evaluate(DOM_WALKER_JS))
            try:
                product = cast(dict[str, object], page.evaluate(PRODUCT_JS))
            except Exception:
                product = {}
            rendered_html = cast(str, page.content())
            final_url = cast(str, page.url)
        finally:
            page.close()
            browser.close()

    main_title = clean_title(str(data.get("title", "")))
    markdown = pair_specs(str(data.get("markdown", "")))
    clean_product = product if is_product_data(product) else None
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
    return ExtractedMarkdown(
        markdown=normalized,
        parser_name=_BROWSER_PARSER_NAME,
        title=main_title or str(data.get("title", "")) or None,
        final_url=final_url,
        rendered_html=rendered_html,
        fetched_ok=fetched_ok,
        product=clean_product,
        normalize_stats=stats,
    )


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


def fetch_html_with_trafilatura(url: str) -> str | None:
    """Fetch raw HTML with trafilatura when browser crawling is unavailable."""

    trafilatura = cast(Any, import_module("trafilatura"))
    fetch_url = cast(Callable[..., str | None], trafilatura.fetch_url)
    html = fetch_url(url)
    if not html:
        return None
    return html.strip() or None


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

    parts: list[str] = []
    prices = product.get("prices")
    if isinstance(prices, list) and prices:
        parts.append("## Gia ban")
        parts.extend(f"- {price}" for price in prices if isinstance(price, str))
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
    specs = product.get("specs")
    prices = product.get("prices")
    return bool(prices) or (isinstance(specs, list) and len(specs) >= 3)


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
