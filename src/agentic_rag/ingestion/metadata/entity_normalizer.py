"""Runtime entity normalization — looks up the LLM-built ``entity_map.json``.

PHASE 2 of entity normalization. Pure lookup, NO LLM at runtime:

- :func:`normalize` / :func:`normalize_all` — map a raw surface form to its
  canonical (used by the backfill and at ingestion to fill ``entities_canonical``).
- :func:`detect_in_query` — scan a user query for known entities and return
  their canonicals (used by the query-time pre-filter). Only entities of a
  *filterable* type (car/ebike model, location) are returned — generic terms
  like "VinFast" or "pin" are never used as filters.

The map (``entity_map.json``) is loaded once and cached. If it is missing or
malformed, every function degrades to a no-op (normalize returns the input,
detect returns nothing) so the pipeline never breaks on a missing map.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

_MAP_PATH = Path(__file__).with_name("entity_map.json")
_ALLOWLIST_PATH = Path(__file__).with_name("entity_filter_allowlist.json")

# Only these types are worth filtering on; brand/generic/etc. are too broad.
FILTERABLE_TYPES = frozenset({"car_model", "ebike_model", "location"})

# Surface forms shorter than this are skipped in query detection — single/double
# character forms (e.g. location "Mỹ") false-match inside unrelated Vietnamese
# words ("thẩm mỹ", "mỹ phẩm"). normalize() still maps them; only detection skips.
_MIN_DETECT_LEN = 3

_WORD_CHARS = "0-9a-zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"


@lru_cache(maxsize=1)
def _load_map() -> dict[str, dict[str, str]]:
    """Load entity_map.json once. Returns {} if missing/malformed (no-op mode)."""
    try:
        data = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    raw_map = data.get("map", {})
    return raw_map if isinstance(raw_map, dict) else {}


@lru_cache(maxsize=1)
def _coverage_map() -> dict[str, int]:
    """Per-canonical chunk coverage recorded in the allowlist ({} if absent)."""
    try:
        data = json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    coverage = data.get("coverage")
    if not isinstance(coverage, dict):
        return {}
    return {str(k): int(v) for k, v in coverage.items()}


def allowlisted_canonicals() -> frozenset[str]:
    """The set of canonicals allowed as filters (allowlist, or all filterable)."""
    allowlist = _filter_allowlist()
    if allowlist is not None:
        return allowlist
    return frozenset(
        str(entry["canonical"])
        for entry in _load_map().values()
        if entry.get("type") in FILTERABLE_TYPES and entry.get("canonical")
    )


def filter_coverage(canonicals: Iterable[str]) -> dict[str, int]:
    """Map each canonical to the number of chunks it pre-filters to.

    Lets a caller trace the candidate-pool size the entity filter narrows to
    (e.g. ``{"VF 8": 202}`` — searched within 202 chunks instead of the corpus).
    """
    coverage = _coverage_map()
    return {c: coverage.get(c, 0) for c in canonicals}


@lru_cache(maxsize=1)
def _filter_allowlist() -> frozenset[str] | None:
    """Canonicals worth pre-filtering on (coverage above threshold).

    Returns None when the allowlist file is absent — callers then fall back to
    *all* filterable canonicals (no coverage gating).
    """
    try:
        data = json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    canonicals = data.get("canonicals")
    return frozenset(canonicals) if isinstance(canonicals, list) else None


def normalize(raw: str) -> str:
    """Map a raw entity surface form to its canonical, or return it unchanged."""
    key = (raw or "").strip()
    entry = _load_map().get(key)
    if entry and entry.get("canonical"):
        return str(entry["canonical"])
    return key


def normalize_all(raws: Iterable[str]) -> list[str]:
    """Normalize a list of raw entities to canonicals (deduped, order-preserving)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in raws:
        canonical = normalize(raw)
        if canonical and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def normalize_filterable(raws: Iterable[str]) -> list[str]:
    """Canonical forms of raws whose type is filterable (deduped, order-preserving).

    This is what the backfill stores in ``entities_canonical`` and what the query
    pre-filter matches against — generic/brand entities are dropped.
    """
    entity_map = _load_map()
    out: list[str] = []
    seen: set[str] = set()
    for raw in raws:
        entry = entity_map.get((raw or "").strip())
        if not entry or entry.get("type") not in FILTERABLE_TYPES:
            continue
        canonical = str(entry.get("canonical") or "")
        if canonical and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def entity_type(raw: str) -> str | None:
    """Return the type of a raw/canonical entity, or None if unknown."""
    entry = _load_map().get((raw or "").strip())
    return entry.get("type") if entry else None


@lru_cache(maxsize=1)
def filterable_canonicals() -> dict[str, list[str]]:
    """Canonical entities grouped by filterable type (for menus / debugging)."""
    grouped: dict[str, set[str]] = {t: set() for t in FILTERABLE_TYPES}
    for entry in _load_map().values():
        etype = entry.get("type")
        if etype in FILTERABLE_TYPES and entry.get("canonical"):
            grouped[etype].add(str(entry["canonical"]))
    return {t: sorted(values) for t, values in grouped.items()}


@lru_cache(maxsize=1)
def _detect_index() -> list[tuple[re.Pattern[str], str]]:
    """Compiled (word-boundary pattern, canonical) for every filterable surface form.

    Both variants and canonicals are indexed so a query can use either. Sorted
    longest-first so "VF 8 Plus" is tried before "VF 8" (both → "VF 8" anyway).
    """
    allowlist = _filter_allowlist()
    forms: dict[str, str] = {}
    for raw, entry in _load_map().items():
        if entry.get("type") not in FILTERABLE_TYPES:
            continue
        canonical = str(entry.get("canonical") or "")
        if not canonical:
            continue
        # Gate by coverage allowlist: only pre-filter on canonicals worth it.
        if allowlist is not None and canonical not in allowlist:
            continue
        for surface in (raw, canonical):
            key = surface.strip().casefold()
            if len(key) >= _MIN_DETECT_LEN:
                forms[key] = canonical

    index: list[tuple[re.Pattern[str], str]] = []
    for surface, canonical in sorted(forms.items(), key=lambda kv: -len(kv[0])):
        # Match the form only when not flanked by other word characters, so
        # "vf 8" hits "pin vf 8 kwh" but not "vf 80", and "mỹ" won't hit "thẩm mỹ".
        pattern = re.compile(
            rf"(?<![{_WORD_CHARS}]){re.escape(surface)}(?![{_WORD_CHARS}])",
            re.IGNORECASE,
        )
        index.append((pattern, canonical))
    return index


def detect_in_query(text: str) -> list[str]:
    """Return canonical filterable entities mentioned in a user query.

    Pure dictionary lookup (no LLM), restricted to the coverage allowlist.
    Returns [] when nothing matches — the caller should then search without an
    entity filter.
    """
    if not text:
        return []
    haystack = re.sub(r"\s+", " ", text)
    found: list[str] = []
    seen: set[str] = set()
    for pattern, canonical in _detect_index():
        if canonical in seen:
            continue
        if pattern.search(haystack):
            seen.add(canonical)
            found.append(canonical)
    return found


@lru_cache(maxsize=1)
def build_entity_menu() -> str:
    """Render the filter-worthy canonicals as a typed menu for an LLM prompt.

    Lists only allowlisted (high-coverage) canonicals grouped by type, so an LLM
    can map a paraphrased query onto a closed set without hallucinating filters.
    """
    allowlist = _filter_allowlist()
    by_type: dict[str, set[str]] = {t: set() for t in FILTERABLE_TYPES}
    for entry in _load_map().values():
        etype = entry.get("type")
        canonical = str(entry.get("canonical") or "")
        if etype not in FILTERABLE_TYPES or not canonical:
            continue
        if allowlist is not None and canonical not in allowlist:
            continue
        by_type[etype].add(canonical)

    lines: list[str] = []
    for etype in ("car_model", "ebike_model", "location"):
        values = sorted(by_type.get(etype, set()))
        if values:
            lines.append(f"{etype}: {', '.join(values)}")
    return "\n".join(lines)
