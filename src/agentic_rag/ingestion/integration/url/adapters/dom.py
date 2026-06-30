import json
import re
from typing import Any
from bs4 import BeautifulSoup

from agentic_rag.ingestion.integration.url.models import (
    UrlAcquisitionResult,
    UrlEvidenceFact,
    UrlIntegrationInput,
    UrlStrategyOutput,
    UrlStructuredSection,
)
from agentic_rag.ingestion.url.extractor import extract_markdown_from_html
from agentic_rag.ingestion.url.parser import parse_html


def _traverse_json_facts(data: Any, results: dict | None = None) -> dict:
    if results is None:
        results = {
            "model_name": None,
            "editions": {},
            "colors": {"standard": [], "premium": []},
            "prices": {}
        }
    if isinstance(data, dict):
        model_val = data.get("modelName") or data.get("model_name") or data.get("modelCode")
        if isinstance(model_val, str) and not results["model_name"]:
            from agentic_rag.ingestion.url.entities.extractor import _MODEL_RE
            if _MODEL_RE.search(model_val):
                results["model_name"] = model_val
        
        price_val = data.get("price") or data.get("basePrice") or data.get("priceVnd") or data.get("sellingPrice")
        if price_val and model_val:
            results["prices"][str(model_val)] = str(price_val)
            
        variant_val = data.get("variant") or data.get("edition") or data.get("trim")
        if variant_val and model_val:
            results["editions"][str(model_val)] = {"price": str(price_val)} if price_val else {}

        color_list = data.get("colors") or data.get("colorList") or data.get("optionColors")
        if isinstance(color_list, list):
            for c in color_list:
                if isinstance(c, dict):
                    color_name = c.get("name") or c.get("colorName") or c.get("title")
                    if color_name:
                        surcharge = c.get("surcharge") or c.get("extraPrice") or c.get("price")
                        try:
                            surcharge_int = int(str(surcharge).replace(".", "").replace(",", "").strip() or 0)
                        except Exception:
                            surcharge_int = 0
                        bucket = "premium" if surcharge_int > 0 else "standard"
                        entry = {"name": str(color_name)}
                        if surcharge:
                            entry["surcharge"] = str(surcharge)
                        if entry not in results["colors"][bucket]:
                            results["colors"][bucket].append(entry)

        for k, v in data.items():
            _traverse_json_facts(v, results)
    elif isinstance(data, list):
        for item in data:
            _traverse_json_facts(item, results)
            
    return results


def _extract_product_cards_bs4(soup: BeautifulSoup) -> list[dict[str, Any]]:
    products = []
    from agentic_rag.ingestion.url.entities.extractor import _MODEL_RE
    for card in soup.find_all("div"):
        class_str = " ".join(card.get("class") or []).lower()
        if any(marker in class_str for marker in ("product-card", "car-card", "vehicle-card", "spec-grid", "configurator")):
            text = card.get_text(" ", strip=True)
            model_match = _MODEL_RE.search(text)
            if model_match:
                model_name = model_match.group(0)
                specs = []
                for s in card.find_all(class_=lambda c: c and any(m in str(c).lower() for m in ("spec", "price", "range", "battery", "color"))):
                    s_text = s.get_text(strip=True)
                    if s_text and s_text not in specs:
                        specs.append(s_text)
                products.append({
                    "model": model_name,
                    "text": text,
                    "specs": specs
                })
    return products


def extract_dom(
    request: UrlIntegrationInput, acquisition: UrlAcquisitionResult
) -> UrlStrategyOutput:
    html = acquisition.rendered_html or acquisition.raw_html or ""
    if not html:
        return UrlStrategyOutput(
            strategy="beautifulsoup",
            unresolved_gaps=("html_missing",),
            warnings=("No HTML was available for deterministic parsing.",),
        )

    # Prioritize the frameworks JSON data layer (e.g. Next.js, Nuxt.js)
    next_data = None
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html, re.DOTALL)
    if not match:
        match = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\});', html, re.DOTALL)
    if match:
        try:
            next_data = json.loads(match.group(1).strip())
        except Exception:
            pass

    facts: list[UrlEvidenceFact] = []
    source_ref = acquisition.evidence[0].evidence_id if acquisition.evidence else "dom_ref"

    if next_data:
        extracted = _traverse_json_facts(next_data)
        if extracted.get("model_name"):
            from agentic_rag.ingestion.url.entities.extractor import _format_model_name
            model_name = _format_model_name(extracted["model_name"])
            
            price_val = None
            if extracted.get("prices"):
                for m, p in extracted["prices"].items():
                    if m.casefold() == model_name.casefold():
                        price_val = p
                        break
            if price_val:
                facts.append(
                    UrlEvidenceFact(
                        subject=model_name,
                        attribute="price",
                        value=str(price_val),
                        evidence_refs=(source_ref,),
                        extraction_strategy="json_data_layer",
                        confidence=1.0,
                    )
                )
            if extracted.get("editions"):
                for ed_name, ed_data in extracted["editions"].items():
                    facts.append(
                        UrlEvidenceFact(
                            subject=model_name,
                            attribute="edition",
                            value=f"{ed_name}: {ed_data.get('price', 'N/A')}",
                            evidence_refs=(source_ref,),
                            extraction_strategy="json_data_layer",
                            confidence=1.0,
                        )
                    )
            if extracted.get("colors"):
                for bucket, col_list in extracted["colors"].items():
                    for col in col_list:
                        col_val = col.get("name", "")
                        if col.get("surcharge"):
                            col_val = f"{col_val} (+{col.get('surcharge')})"
                        facts.append(
                            UrlEvidenceFact(
                                subject=model_name,
                                attribute=f"{bucket}_color",
                                value=col_val,
                                evidence_refs=(source_ref,),
                                extraction_strategy="json_data_layer",
                                confidence=1.0,
                            )
                        )
    else:
        # Fallback to container-aware HTML parsing
        soup = BeautifulSoup(html, "html.parser")
        products = _extract_product_cards_bs4(soup)
        for prod in products:
            model_name = prod["model"]
            for spec in prod["specs"]:
                facts.append(
                    UrlEvidenceFact(
                        subject=model_name,
                        attribute="spec",
                        value=spec,
                        evidence_refs=(source_ref,),
                        extraction_strategy="container_aware_dom",
                        confidence=0.9,
                    )
                )

    parsed = parse_html(html, base_url=acquisition.final_url)
    extracted_md = extract_markdown_from_html(html, source_url=acquisition.final_url)
    markdown = extracted_md.markdown if extracted_md is not None else acquisition.parser_markdown or ""
    sections = tuple(
        UrlStructuredSection(
            section_id=f"section-{index:04d}",
            heading=section.heading,
            markdown=section.markdown or section.text,
            reading_order=index,
            evidence_refs=(source_ref,) if source_ref else (),
        )
        for index, section in enumerate(parsed.sections[: request.max_sections])
        if (section.markdown or section.text).strip()
    )
    gaps: list[str] = []
    lowered = html.casefold()
    if "<canvas" in lowered or "<svg" in lowered:
        gaps.append("visual_chart_or_canvas")
    if "<table" in lowered and "|" not in markdown:
        gaps.append("table_structure_missing")
    return UrlStrategyOutput(
        strategy="beautifulsoup",
        markdown=markdown,
        sections=sections,
        facts=tuple(facts),
        unresolved_gaps=tuple(gaps),
        metadata={
            "title": parsed.title,
            "canonical_url": parsed.metadata.canonical_url,
            "language": parsed.metadata.language,
        },
    )

