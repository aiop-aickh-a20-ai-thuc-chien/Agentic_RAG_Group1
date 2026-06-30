"""Data contracts for the KG pipeline.

Uses stdlib dataclasses (not pydantic) on purpose: this package is self-contained
and must run with zero heavy imports. In production you would back these with the
project's pydantic models, but the shapes are identical.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Input
# --------------------------------------------------------------------------- #
@dataclass
class Chunk:
    """One unit of text fed to the extractor (already chunked upstream)."""

    doc_id: str
    chunk_id: str
    text: str
    section_path: tuple[str, ...] = ()
    heading: str | None = None


@dataclass
class Document:
    doc_id: str
    title: str
    chunks: list[Chunk] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# [1] Extract — open triple straight from the LLM (free-form predicate/type)
# --------------------------------------------------------------------------- #
@dataclass
class OpenTriple:
    subject: str
    predicate: str
    object: str
    subject_type: str = ""
    object_type: str = ""
    evidence: str = ""


# --------------------------------------------------------------------------- #
# [2] Stage — raw triple + provenance, append-only
# --------------------------------------------------------------------------- #
@dataclass
class StagedTriple:
    triple_id: str
    doc_id: str
    chunk_id: str
    subject: str
    predicate: str
    object: str
    subject_type: str = ""
    object_type: str = ""
    evidence: str = ""


# --------------------------------------------------------------------------- #
# [3] Canonicalize — outputs
# --------------------------------------------------------------------------- #
@dataclass
class CanonicalEntity:
    canonical_id: str
    canonical_name: str
    type: str = ""
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    frequency: int = 0


@dataclass
class CanonicalPredicate:
    canonical: str
    definition: str = ""
    direction: str = ""  # e.g. "product->org": canonical subject type -> object type
    members: list[str] = field(default_factory=list)
    frequency: int = 0


@dataclass
class CleanTriple:
    subj_id: str
    predicate: str  # canonical predicate
    obj_id: str
    evidence: str = ""
    evidence_offset: tuple[int, int] | None = None
    doc_id: str = ""
    chunk_id: str = ""
    strength: int = 1
    flipped: bool = False  # direction was straightened in stage [4]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def content_id(prefix: str, normalized: str) -> str:
    """Content-addressed id: same normalized form -> same id (idempotent, race-safe)."""

    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"
