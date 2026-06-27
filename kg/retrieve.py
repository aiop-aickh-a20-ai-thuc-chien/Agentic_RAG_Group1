"""ONLINE retrieval over the built graph — the query-time companion to the offline build.

The KG does NOT replace vector search; it is a THIRD retrieval channel that, given a
query, returns (a) provenance chunk_ids to FUSE into the vector candidate pool and
(b) the matching triples to hand the generator as structured facts. Both come from the
same graph the offline pipeline writes to Neo4j, so online reads whatever is live.

Store-agnostic: works off any store exposing `to_node_link()` — `kg.store.GraphStore`
(offline / tests) or `kg.store_neo4j.Neo4jStore` (production). A snapshot is built once;
call `KGRetriever.from_store(...)` again (or `refresh()`) to pick up graph changes.

    r = KGRetriever.from_store(neo4j_store)
    hit = r.retrieve("công suất tối đa của Minio Green là bao nhiêu?")
    hit.chunk_ids   # -> fuse with dense/sparse retriever
    hit.facts_text  # -> structured context for the generator
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from kg.embeddings import norm_text
from kg.resolve import _derive_stopwords, _norm_key  # reuse the OFFLINE normalization

# entity keys shorter than this are too generic to anchor a query on
_MIN_ANCHOR_LEN = 3
# names longer than this are extracted CLAUSES, not entities — never anchor on them
_MAX_ANCHOR_TOKENS = 7
# value-ish nodes are answers, not anchors — don't link the query onto them
_NON_ANCHOR_TYPES = {"value", "price", "spec"}
# real entities preferred over mis-extracted attribute-phrase nodes when ranking anchors
_PRIORITY_TYPES = {"product", "org", "location", "policy"}

# query-aware chunk scoring: boost provenance of edges that LEXICALLY match the query,
# so a high-degree anchor's RELEVANT chunks rank above its generic ones (env-tunable).
_REL_WEIGHT = float(os.getenv("KG_REL_WEIGHT", "6.0"))
_REL_BASE = float(os.getenv("KG_REL_BASE", "0.1"))
# fewer anchors = less neighborhood dilution; 2 still covers comparison (2-entity) queries
_MAX_ANCHORS = int(os.getenv("KG_MAX_ANCHORS", "2"))


@dataclass
class GraphHit:
    anchors: list[dict] = field(default_factory=list)  # matched entities
    triples: list[dict] = field(default_factory=list)  # subject/predicate/object (+provenance)
    chunk_scores: dict[str, float] = field(default_factory=dict)  # chunk_id -> graph score
    docs: list[str] = field(default_factory=list)

    @property
    def ranked_chunks(self) -> list[tuple[str, float]]:
        """Provenance chunks ranked by graph score — ready to RRF with dense/sparse."""
        return sorted(self.chunk_scores.items(), key=lambda kv: kv[1], reverse=True)

    @property
    def chunk_ids(self) -> list[str]:
        return [cid for cid, _ in self.ranked_chunks]

    @property
    def facts_text(self) -> str:
        """Compact, generator-friendly rendering of the retrieved facts."""
        return "\n".join(
            f"- {t['subject']} — {t['predicate']} → {t['object']}" for t in self.triples
        )


@dataclass
class _Walk:
    """Mutable accumulators threaded through the graph traversal."""

    triples: list[dict] = field(default_factory=list)
    chunk_scores: dict = field(default_factory=lambda: defaultdict(float))
    docs: set = field(default_factory=set)
    seen: set = field(default_factory=set)


class KGRetriever:
    def __init__(self, node_link: dict) -> None:
        self._load(node_link)

    @classmethod
    def from_store(cls, store) -> KGRetriever:
        return cls(store.to_node_link())

    def refresh(self, store) -> None:
        self._load(store.to_node_link())

    def _load(self, node_link: dict) -> None:
        self.nodes: dict[str, dict] = {n["id"]: n for n in node_link["nodes"]}
        self.out: dict[str, list[dict]] = defaultdict(list)
        self.inc: dict[str, list[dict]] = defaultdict(list)
        for e in node_link["edges"]:
            self.out[e["source"]].append(e)
            self.inc[e["target"]].append(e)
        self._build_index()

    def _derive_query_stopwords(self) -> set[str]:
        """Brand/stopwords from entity labels+aliases — the SAME routine offline used,
        so online normalizes identically (e.g. both strip 'vinfast')."""
        mentions: dict[str, dict] = {}
        for n in self.nodes.values():
            for name in [n.get("label", ""), *n.get("aliases", [])]:
                if not name:
                    continue
                m = mentions.setdefault(norm_text(name), {"surface": name, "types": Counter()})
                m["types"][n.get("type", "")] += 1
        return _derive_stopwords(mentions)

    def _build_index(self) -> None:
        """Index anchorable entities by their offline _norm_key (despaced, stopword-
        stripped): 'VF3' / 'VF 3' / 'VinFast VF 3' all collapse to one key 'vf3'."""
        self.stopwords = self._derive_query_stopwords()
        self.key_to_node: dict[str, tuple] = {}  # key -> (priority, token_len, node_id)
        self.max_key_tokens = 1
        for n in self.nodes.values():
            if n.get("type") in _NON_ANCHOR_TYPES:
                continue
            prio = 1 if n.get("type") in _PRIORITY_TYPES else 0
            for name in [n.get("label", ""), *n.get("aliases", [])]:
                toks = norm_text(name).split()
                key = _norm_key(name, self.stopwords)
                if not toks or len(toks) > _MAX_ANCHOR_TOKENS or len(key) < _MIN_ANCHOR_LEN:
                    continue
                self.max_key_tokens = max(self.max_key_tokens, len(toks))
                cand = (prio, len(toks), n["id"])
                if key not in self.key_to_node or cand > self.key_to_node[key]:
                    self.key_to_node[key] = cand

    # ---- entity linking ------------------------------------------------- #
    def link(self, query: str) -> list[str]:
        """Node ids mentioned in the query: a contiguous token window is an entity
        mention iff it normalizes (offline _norm_key) to an indexed entity key — so
        'VF3'/'VF 3'/'VinFast VF 3' hit the same node, with NO sub-span over-linking.
        Ranked by (real-entity type, entity length)."""
        toks = norm_text(query).split()
        n = len(toks)
        best: dict[str, tuple] = {}  # node_id -> (priority, token_len)
        for i in range(n):
            for j in range(i + 1, min(i + self.max_key_tokens, n) + 1):
                hit = self.key_to_node.get(_norm_key(" ".join(toks[i:j]), self.stopwords))
                if hit is None:
                    continue
                prio, klen, nid = hit
                if nid not in best or (prio, klen) > best[nid]:
                    best[nid] = (prio, klen)
        return sorted(best, key=lambda nid: best[nid], reverse=True)

    # ---- retrieval ------------------------------------------------------ #
    def retrieve(
        self, query: str, hops: int = 1, max_triples: int = 40, max_anchors: int = _MAX_ANCHORS
    ) -> GraphHit:
        anchors = self.link(query)[:max_anchors]
        if not anchors:
            return GraphHit()

        ctx = _Walk()
        # drop the anchor's own name tokens: they appear in nearly every edge of the
        # anchor → carry no signal. Keep only the FACT-specific query terms.
        qtoks = self._query_tokens(query) - {
            t for a in anchors for t in norm_text(self.nodes[a]["label"]).split()
        }
        visited: set[str] = set(anchors)
        frontier = set(anchors)
        for hop in range(max(1, hops)):
            nxt = self._expand(frontier, 1.0 / (hop + 1), ctx, qtoks)  # decay: near > far
            frontier = nxt - visited
            visited |= nxt

        triples = sorted(ctx.triples, key=lambda t: t.get("weight", 1), reverse=True)
        return GraphHit(
            anchors=[
                {"id": a, "label": self.nodes[a]["label"], "type": self.nodes[a].get("type", "")}
                for a in anchors
            ],
            triples=triples[:max_triples],
            chunk_scores=dict(ctx.chunk_scores),
            docs=sorted(ctx.docs),
        )

    def _query_tokens(self, query: str) -> set[str]:
        """Content tokens of the query (offline normalization, brand/stopwords stripped)."""
        return {t for t in norm_text(query).split() if len(t) >= 2 and t not in self.stopwords}

    def _edge_relevance(self, e: dict, qtoks: set[str]) -> float:
        """Fraction of query tokens present in the edge's endpoints + evidence — how much
        THIS edge is about what the query asks (0 = generic, 1 = fully on-topic)."""
        if not qtoks:
            return 0.0
        text = (
            self.nodes[e["target"]].get("label", "")
            + " "
            + self.nodes[e["source"]].get("label", "")
        )
        for ev in e.get("evidence", []):
            text += " " + ev
        etoks = set(norm_text(text).split())
        return len(qtoks & etoks) / len(qtoks)

    def _expand(
        self, frontier: set[str], decay: float, ctx: _Walk, qtoks: set[str] | None = None
    ) -> set[str]:
        """Visit every edge of the frontier once: record triple + QUERY-AWARE chunk scores
        (an edge that matches the query lifts its provenance chunks above a high-degree
        anchor's generic ones); return the next frontier (all touched nodes)."""
        nxt: set[str] = set()
        for nid in frontier:
            for e in self.out[nid] + self.inc[nid]:
                if id(e) not in ctx.seen:
                    ctx.seen.add(id(e))
                    ctx.triples.append(self._render(e))
                    boost = decay * (
                        _REL_BASE + _REL_WEIGHT * self._edge_relevance(e, qtoks or set())
                    )
                    for cid in e.get("chunks", []):
                        ctx.chunk_scores[cid] += e.get("weight", 1) * boost
                    ctx.docs.update(e.get("docs", []))
                nxt.update((e["source"], e["target"]))
        return nxt

    def _render(self, e: dict) -> dict:
        return {
            "subject": self.nodes[e["source"]]["label"],
            "predicate": e.get("predicate", ""),
            "object": self.nodes[e["target"]]["label"],
            "weight": e.get("weight", 1),
            "chunks": e.get("chunks", []),
            "evidence": e.get("evidence", []),
        }
