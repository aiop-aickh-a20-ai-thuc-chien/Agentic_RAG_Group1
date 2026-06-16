"""URL-specific metadata enrichment."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.chunking import short_hash
from agentic_rag.ingestion.url.dom import DomBlock, dom_blocks_summary
from agentic_rag.ingestion.url.entities import (
    UrlEntity,
    entities_summary,
    extract_product_specs,
)
from agentic_rag.ingestion.url.parser import ParsedHtml


def enrich_chunks_with_url_metadata(
    chunks: list[Chunk],
    *,
    source_url: str | None,
    original_url: str | None,
    final_url: str | None,
    canonical_url: str | None,
    parsed: ParsedHtml,
    dom_blocks: list[DomBlock] | None = None,
    entities: list[UrlEntity] | None = None,
) -> list[Chunk]:
    """Attach URL-owned page, DOM, and entity metadata to chunks."""

    best_url = canonical_url or final_url or source_url or original_url
    blocks = dom_blocks or []
    entity_list = entities or []
    block_summary = dom_blocks_summary(blocks)
    entity_summary = entities_summary(entity_list)
    page_type = _infer_page_type(block_summary, entity_summary)
    source_hash = short_hash(best_url or "")
    page_specs = extract_product_specs(
        "\n\n".join(chunk.text for chunk in chunks),
        title=parsed.title,
        url=best_url,
    )
    enriched_chunks: list[Chunk] = []
    for chunk in chunks:
        matched_entity = _best_entity_for_chunk(chunk, entity_list)
        product_specs = _product_specs_for_chunk(
            chunk,
            entity=matched_entity,
            page_specs=page_specs,
            title=parsed.title,
            url=best_url,
        )
        attribute_group = _infer_attribute_group(
            chunk.text,
            matched_entity,
            product_specs=product_specs,
        )
        is_noise = _is_noise_chunk(chunk)
        schema_metadata = _general_schema_metadata(
            chunk,
            page_type=page_type,
            parsed=parsed,
            entity_summary=entity_summary,
        )
        enriched_chunks.append(
            chunk.model_copy(
                update={
                    "metadata": {
                        **chunk.metadata,
                        **schema_metadata,
                        "url": best_url,
                        "domain": _extract_domain(best_url),
                        "original_url": original_url,
                        "canonical_url": canonical_url,
                        "language": parsed.metadata.language,
                        "author": parsed.metadata.author,
                        "published_at": parsed.metadata.published_at,
                        "captured_at": chunk.metadata.get("fetched_at"),
                        "page_type": page_type,
                        "url_source_hash": source_hash,
                        "semantic_block_count": block_summary["semantic_block_count"],
                        "semantic_block_types": block_summary["semantic_block_types"],
                        "entity_count": entity_summary["entity_count"],
                        "entity_types": entity_summary["entity_types"],
                        "entity_names": entity_summary["entity_names"],
                        "entity_type": matched_entity.entity_type if matched_entity else None,
                        "entity_name": matched_entity.entity_name if matched_entity else None,
                        "entity_hash": _entity_hash(matched_entity),
                        "product_specs": product_specs,
                        "product_spec_fields": sorted(product_specs),
                        "product_model": product_specs.get("model_name"),
                        "product_price": product_specs.get("price"),
                        "driving_range": product_specs.get("driving_range"),
                        "battery_capacity": product_specs.get("battery_capacity"),
                        "charging_time": product_specs.get("charging_time"),
                        "vehicle_segment": _infer_vehicle_segment(chunk.text, matched_entity),
                        "attribute_group": attribute_group,
                        "is_noise": is_noise,
                        "retrieval_weight": _retrieval_weight(
                            is_noise=is_noise,
                            entity=matched_entity,
                            attribute_group=attribute_group,
                        ),
                    }
                }
            )
        )
    return enriched_chunks


def _general_schema_metadata(
    chunk: Chunk,
    *,
    page_type: str,
    parsed: ParsedHtml,
    entity_summary: dict[str, object],
) -> dict[str, object]:
    """Return Agentic RAG shared metadata aliases proven by URL ingestion."""

    section_path = chunk.metadata.get("section_path")
    entity_names = entity_summary.get("entity_names")
    metadata: dict[str, object] = {
        "document_type": page_type,
        "heading": chunk.metadata.get("section"),
        "breadcrumb": list(section_path) if isinstance(section_path, list) else [],
        "entities": list(entity_names) if isinstance(entity_names, list) else [],
    }
    token_count = chunk.metadata.get("chunk_token_count")
    if isinstance(token_count, int):
        metadata["token_count"] = token_count
    chunk_index = chunk.metadata.get("chunk_part_index")
    if isinstance(chunk_index, int):
        metadata["chunk_index"] = chunk_index
    if parsed.metadata.modified_at:
        metadata["created_date"] = parsed.metadata.modified_at
        metadata["created_date_source"] = "page_modified_metadata"
    metadata["updated_date"] = chunk.metadata.get("updated_date")
    metadata["updated_date_source"] = chunk.metadata.get("updated_date_source")
    return metadata


def _infer_page_type(
    block_summary: dict[str, object],
    entity_summary: dict[str, object],
) -> str:
    entity_types = entity_summary.get("entity_types")
    if isinstance(entity_types, dict):
        if entity_types.get("vehicle"):
            return "vehicle_or_product_page"
        if entity_types.get("product"):
            return "product_page"
        if entity_types.get("faq_item"):
            return "faq_page"
    block_types = block_summary.get("semantic_block_types")
    if isinstance(block_types, dict):
        if block_types.get("comparison_table") or block_types.get("comparison_row"):
            return "comparison_table_page"
        if block_types.get("policy_section"):
            return "policy_page"
    return "generic"


def _extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(url).netloc or None


def _best_entity_for_chunk(chunk: Chunk, entities: list[UrlEntity]) -> UrlEntity | None:
    if not entities:
        return None
    chunk_text = chunk.text.casefold()
    for entity in entities:
        if entity.entity_name.casefold() in chunk_text:
            return entity
    if len(entities) == 1:
        return entities[0]
    return None


def _entity_hash(entity: UrlEntity | None) -> str | None:
    if entity is None:
        return None
    return short_hash(f"{entity.entity_type}|{entity.entity_name.casefold()}")


def _product_specs_for_chunk(
    chunk: Chunk,
    *,
    entity: UrlEntity | None,
    page_specs: dict[str, str],
    title: str | None,
    url: str | None,
) -> dict[str, str]:
    specs: dict[str, str] = {}
    if _should_apply_page_specs(page_specs, entity=entity, url=url):
        specs.update(page_specs)
    if entity is not None:
        specs.update(entity.structured_data)
    specs.update(extract_product_specs(chunk.text, title=title, url=url))
    if not _should_keep_product_specs(specs, entity=entity, url=url):
        return {}
    return specs


def _should_apply_page_specs(
    specs: dict[str, str],
    *,
    entity: UrlEntity | None,
    url: str | None,
) -> bool:
    if not specs:
        return False
    if entity is not None and entity.entity_type in {"vehicle", "product"}:
        return True
    if specs.get("model_name"):
        return True
    domain = _extract_domain(url)
    return domain == "shop.vinfastauto.com"


def _should_keep_product_specs(
    specs: dict[str, str],
    *,
    entity: UrlEntity | None,
    url: str | None,
) -> bool:
    if not specs:
        return False
    if entity is not None and entity.entity_type in {"vehicle", "product"}:
        return True
    if specs.get("model_name"):
        return True
    domain = _extract_domain(url)
    if domain == "shop.vinfastauto.com":
        return bool({"price", "driving_range", "battery_capacity"} & set(specs))
    return len(specs) >= 2 and bool({"price", "driving_range"} & set(specs))


def _infer_vehicle_segment(text: str, entity: UrlEntity | None) -> str | None:
    combined_text = text
    if entity is not None:
        combined_text = f"{combined_text} {entity.retrieval_text}"
    segment_match = re.search(
        r"\b(?:[A-D]-SUV|MPV|MiniCar|SUV|Sedan|Hatchback)\b", combined_text, re.I
    )
    return segment_match.group(0) if segment_match else None


def _infer_attribute_group(
    text: str,
    entity: UrlEntity | None,
    *,
    product_specs: dict[str, str] | None = None,
) -> str:
    combined_text = text.casefold()
    if entity is not None:
        combined_text = f"{combined_text} {entity.retrieval_text.casefold()}"
    specs = product_specs or {}
    if specs.get("price"):
        return "pricing_specs"
    if any(specs.get(key) for key in ("driving_range", "battery_capacity", "charging_time")):
        return "battery_range"
    if any(specs.get(key) for key in ("power", "torque", "max_speed", "dimensions")):
        return "technical_specs"
    if specs.get("warranty"):
        return "warranty_service"
    if re.search(
        r"\b(?:price|gia|vnd|vn\u0111|\u20ab|dong|deposit|dat coc)\b", combined_text, re.I
    ):
        return "pricing_specs"
    if re.search(r"\b(?:battery|pin|charging|sac|range|km)\b", combined_text, re.I):
        return "battery_range"
    if re.search(r"\b(?:warranty|bao hanh|service|maintenance)\b", combined_text, re.I):
        return "warranty_service"
    if "?" in text or "faq" in combined_text:
        return "faq"
    if re.search(r"\b(?:policy|terms|privacy|chinh sach|dieu khoan)\b", combined_text, re.I):
        return "policy_terms"
    return "general"


def _is_noise_chunk(chunk: Chunk) -> bool:
    section = str(chunk.metadata.get("section") or "").casefold()
    text = chunk.text.casefold()
    word_count = len(re.findall(r"\w+", chunk.text))
    if word_count < 5:
        return True
    if any(marker in section for marker in ("footer", "navigation", "cookie", "related")):
        return True
    return bool(
        re.search(
            r"\b(cookie|copyright|all rights reserved|newsletter|hotline|follow us)\b",
            text,
            re.I,
        )
    )


def _retrieval_weight(
    *,
    is_noise: bool,
    entity: UrlEntity | None,
    attribute_group: str,
) -> float:
    if is_noise:
        return 0.2
    if entity is not None and attribute_group != "general":
        return 1.2
    if entity is not None:
        return 1.1
    return 1.0


__all__ = ["enrich_chunks_with_url_metadata"]
