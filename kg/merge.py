"""[4] MERGE — turn canonical triples into graph edges.

Applies the quality gates, straightens edge direction using the predicate's
canonical direction + the resolved entity types (so Vietnamese passive voice does
not invert relations), maps surface forms -> canonical ids, then aggregates
duplicate edges (weight + multi-source evidence + provenance).
"""

from __future__ import annotations

from collections import defaultdict

from kg.embeddings import norm_text
from kg.gates import gate_triple, length_fences
from kg.schema import (
    CanonicalEntity,
    CanonicalPredicate,
    CleanTriple,
    OpenTriple,
    StagedTriple,
)


def _should_flip(subj_type: str, obj_type: str, direction: str) -> bool:
    if not direction or "->" not in direction:
        return False
    left, right = (x.strip() for x in direction.split("->"))
    if subj_type == left and obj_type == right:
        return False
    return bool(subj_type == right and obj_type == left)


def build_clean_triples(
    staged: list[StagedTriple],
    key_to_id: dict[str, str],
    canon_entities: dict[str, CanonicalEntity],
    surface_to_canon: dict[str, str],
    registry: dict[str, CanonicalPredicate],
    chunk_text: dict[str, str],
) -> tuple[list[CleanTriple], list[tuple[StagedTriple, str]]]:
    clean: list[CleanTriple] = []
    dropped: list[tuple[StagedTriple, str]] = []
    endpoint_max, predicate_max = length_fences(staged)  # adaptive clause fences

    for t in staged:
        ot = OpenTriple(t.subject, t.predicate, t.object, t.subject_type, t.object_type, t.evidence)
        keep, reason, offset = gate_triple(
            ot, chunk_text.get(t.chunk_id, ""), endpoint_max, predicate_max
        )
        if not keep:
            dropped.append((t, reason))
            continue

        subj_id = key_to_id.get(norm_text(t.subject))
        obj_id = key_to_id.get(norm_text(t.object))
        if not subj_id or not obj_id:
            dropped.append((t, "unresolved_entity"))
            continue

        canon_pred = surface_to_canon.get(t.predicate, "related_to")
        direction = registry[canon_pred].direction if canon_pred in registry else ""
        st = canon_entities[subj_id].type
        ott = canon_entities[obj_id].type
        flipped = _should_flip(st, ott, direction)
        if flipped:
            subj_id, obj_id = obj_id, subj_id

        clean.append(
            CleanTriple(
                subj_id=subj_id,
                predicate=canon_pred,
                obj_id=obj_id,
                evidence=t.evidence,
                evidence_offset=offset,
                doc_id=t.doc_id,
                chunk_id=t.chunk_id,
                strength=1,
                flipped=flipped,
            )
        )
    return clean, dropped


def build_graph(clean: list[CleanTriple], canon_entities: dict[str, CanonicalEntity]):
    import networkx as nx

    g = nx.MultiDiGraph()

    used: set[str] = set()
    for c in clean:
        used.add(c.subj_id)
        used.add(c.obj_id)
    for cid in used:
        e = canon_entities[cid]
        g.add_node(cid, label=e.canonical_name, type=e.type, aliases=e.aliases, freq=e.frequency)

    agg: dict[tuple[str, str, str], dict] = defaultdict(
        lambda: {"weight": 0, "evidence": [], "docs": set(), "chunks": set()}
    )
    for c in clean:
        a = agg[(c.subj_id, c.predicate, c.obj_id)]
        a["weight"] += c.strength
        a["evidence"].append(c.evidence)
        a["docs"].add(c.doc_id)
        a["chunks"].add(c.chunk_id)

    for (s, p, o), a in agg.items():
        g.add_edge(
            s,
            o,
            key=p,
            predicate=p,
            weight=a["weight"],
            evidence=a["evidence"],
            docs=sorted(a["docs"]),
            chunks=sorted(a["chunks"]),
        )
    return g
