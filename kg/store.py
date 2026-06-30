"""[6] STORE (+ optional [5] ENRICH) — graph store with query + community.

Wraps a networkx MultiDiGraph. In production this is Neo4j (GDS for resolution +
community, Cypher for traversal) or networkx+SQLite; the query surface is the same.
Supports per-document delete (lifecycle / GDPR) and community detection (the
GraphRAG "global" enrichment).
"""

from __future__ import annotations

import json

from kg.embeddings import norm_text


class GraphStore:
    def __init__(self, graph) -> None:
        self.g = graph

    # ---- query ----------------------------------------------------------- #
    def find_node(self, name: str) -> str | None:
        key = norm_text(name)
        for nid, data in self.g.nodes(data=True):
            if norm_text(data.get("label", "")) == key:
                return nid
            if any(norm_text(a) == key for a in data.get("aliases", [])):
                return nid
        return None

    def neighbors(self, node_id: str, hops: int = 1) -> set[str]:
        """k-hop neighborhood (undirected reach)."""
        frontier = {node_id}
        seen = {node_id}
        und = self.g.to_undirected(as_view=True)
        for _ in range(hops):
            nxt: set[str] = set()
            for n in frontier:
                nxt |= set(und.neighbors(n))
            nxt -= seen
            seen |= nxt
            frontier = nxt
        seen.discard(node_id)
        return seen

    def edges_of(self, node_id: str) -> list[dict]:
        out = []
        for _, o, data in self.g.out_edges(node_id, data=True):
            out.append({"subject": node_id, "predicate": data["predicate"], "object": o, **data})
        for s, _, data in self.g.in_edges(node_id, data=True):
            out.append({"subject": s, "predicate": data["predicate"], "object": node_id, **data})
        return out

    # ---- lifecycle ------------------------------------------------------- #
    def delete_document(self, doc_id: str) -> int:
        to_remove = [
            (u, v, k)
            for u, v, k, d in self.g.edges(keys=True, data=True)
            if doc_id in d.get("docs", [])
        ]
        for u, v, k in to_remove:
            self.g.remove_edge(u, v, key=k)
        # GC orphan nodes
        for n in [n for n in list(self.g.nodes) if self.g.degree(n) == 0]:
            self.g.remove_node(n)
        return len(to_remove)

    # ---- enrich [5] ------------------------------------------------------ #
    def communities(self) -> dict[str, int]:
        try:
            from networkx.algorithms.community import greedy_modularity_communities

            comms = greedy_modularity_communities(self.g.to_undirected())
        except Exception:
            return {n: 0 for n in self.g.nodes}
        out: dict[str, int] = {}
        for i, c in enumerate(comms):
            for n in c:
                out[n] = i
        return out

    # ---- io -------------------------------------------------------------- #
    def stats(self) -> dict:
        preds: dict[str, int] = {}
        for _, _, d in self.g.edges(data=True):
            preds[d["predicate"]] = preds.get(d["predicate"], 0) + 1
        return {
            "nodes": self.g.number_of_nodes(),
            "edges": self.g.number_of_edges(),
            "predicates": preds,
        }

    def to_node_link(self) -> dict:
        comm = self.communities()
        nodes = [
            {
                "id": n,
                "label": d.get("label", n),
                "type": d.get("type", ""),
                "aliases": d.get("aliases", []),
                "freq": d.get("freq", 0),
                "community": comm.get(n, 0),
            }
            for n, d in self.g.nodes(data=True)
        ]
        edges = [
            {
                "source": u,
                "target": v,
                "predicate": d["predicate"],
                "weight": d.get("weight", 1),
                "docs": d.get("docs", []),
                "chunks": d.get("chunks", []),  # provenance for online graph->chunk fusion
                "evidence": d.get("evidence", []),
            }
            for u, v, d in self.g.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges}

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_node_link(), f, ensure_ascii=False, indent=2)
