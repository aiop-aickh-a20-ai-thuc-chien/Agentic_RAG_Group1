"""Neo4j-backed graph store — same query surface as `kg.store.GraphStore`.

Swap target for production: durable, concurrent-safe, Cypher traversal for the
ONLINE retrieval step, GDS-ready. Pipeline stages [1]-[4] do not change — we just
load the built graph (node-link) into Neo4j and serve queries with Cypher.

Connection (env): NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD / NEO4J_DATABASE.
Local instance:  docker run -p7474:7474 -p7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5
"""

from __future__ import annotations

import os
import re
from collections import defaultdict


def _rel_type(predicate: str) -> str:
    """Turn a canonical predicate into the Neo4j relationship TYPE (what the browser
    shows on the arrow). Vietnamese kept readable; whitespace -> '_'; a backtick is
    stripped because it would break the back-quoted identifier in Cypher."""
    t = re.sub(r"\s+", "_", (predicate or "").strip()).replace("`", "")
    return t or "REL"


class Neo4jStore:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        from neo4j import GraphDatabase

        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER") or "neo4j"
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.database = database or os.getenv("NEO4J_DATABASE", "neo4j")
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self) -> None:
        self._driver.close()

    def _run(self, cypher: str, **params):
        with self._driver.session(database=self.database) as s:
            return list(s.run(cypher, **params))

    # ---- connectivity ---------------------------------------------------- #
    def check(self) -> bool:
        return self._run("RETURN 1 AS ok")[0]["ok"] == 1

    # ---- load (from a built node-link graph) ----------------------------- #
    def load(self, node_link: dict, wipe: bool = False, batch: int = 1000) -> dict:
        """Bulk-load via UNWIND — one round-trip per `batch` rows, not per row.

        On cloud Aura each statement is a network round-trip (~50-200ms), so the
        old per-node/per-edge loop spent most of its time waiting. UNWIND ships a
        whole batch in a single statement.
        """
        if wipe:
            self._run("MATCH (n:Entity) DETACH DELETE n")
        self._run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")
        node_rows = [
            {
                "id": n["id"],
                "label": n.get("label", ""),
                "type": n.get("type", ""),
                "aliases": n.get("aliases", []),
                "freq": n.get("freq", 0),
                "community": n.get("community", 0),
            }
            for n in node_link["nodes"]
        ]
        for i in range(0, len(node_rows), batch):
            self._run(
                "UNWIND $rows AS r MERGE (n:Entity {id:r.id}) "
                "SET n.label=r.label, n.type=r.type, n.aliases=r.aliases, "
                "n.freq=r.freq, n.community=r.community",
                rows=node_rows[i : i + batch],
            )
        # Relationship TYPE = the predicate (so the Neo4j browser shows "công suất",
        # not "REL"). Cypher can't parameterize a rel type, so we group edges by type
        # and bake the (sanitized) type into each UNWIND. `predicate` is kept as a
        # property too, so generic queries / to_node_link still work uniformly.
        by_type: dict[str, list[dict]] = defaultdict(list)
        for e in node_link["edges"]:
            by_type[_rel_type(e.get("predicate", ""))].append(
                {
                    "s": e["source"],
                    "t": e["target"],
                    "p": e.get("predicate", ""),
                    "w": e.get("weight", 1),
                    "docs": e.get("docs", []),
                    "ch": e.get("chunks", []),
                    "ev": e.get("evidence", []),
                }
            )
        for rtype, rows in by_type.items():
            for i in range(0, len(rows), batch):
                self._run(
                    "UNWIND $rows AS r MATCH (s:Entity {id:r.s}), (t:Entity {id:r.t}) "
                    f"MERGE (s)-[x:`{rtype}` {{predicate:r.p}}]->(t) "
                    "SET x.weight=r.w, x.docs=r.docs, x.chunks=r.ch, x.evidence=r.ev",
                    rows=rows[i : i + batch],
                )
        return self.stats()

    # ---- query ----------------------------------------------------------- #
    def find_node(self, name: str) -> str | None:
        rows = self._run(
            "MATCH (n:Entity) WHERE toLower(n.label)=toLower($q) "
            "OR any(a IN n.aliases WHERE toLower(a)=toLower($q)) "
            "RETURN n.id AS id LIMIT 1",
            q=name,
        )
        return rows[0]["id"] if rows else None

    def neighbors(self, node_id: str, hops: int = 1) -> set[str]:
        rows = self._run(
            f"MATCH (n:Entity {{id:$id}})-[*1..{int(hops)}]-(m:Entity) RETURN DISTINCT m.id AS id",
            id=node_id,
        )
        return {r["id"] for r in rows}

    def edges_of(self, node_id: str) -> list[dict]:
        rows = self._run(
            "MATCH (n:Entity {id:$id})-[r]-(m:Entity) "
            "RETURN startNode(r).id AS s, endNode(r).id AS o, "
            "coalesce(r.predicate, type(r)) AS p, r.evidence AS ev, r.chunks AS ch, r.weight AS w",
            id=node_id,
        )
        return [
            {
                "subject": r["s"],
                "object": r["o"],
                "predicate": r["p"],
                "evidence": r["ev"],
                "chunks": r["ch"] or [],
                "weight": r["w"],
            }
            for r in rows
        ]

    # ---- lifecycle ------------------------------------------------------- #
    def delete_document(self, doc_id: str) -> int:
        removed = self._run(
            "MATCH (:Entity)-[r]->(:Entity) WHERE $d IN r.docs "
            "WITH r, count(*) AS _ DELETE r RETURN count(*) AS c",
            d=doc_id,
        )
        self._run("MATCH (n:Entity) WHERE NOT (n)--() DELETE n")
        return removed[0]["c"] if removed else 0

    # ---- io -------------------------------------------------------------- #
    def stats(self) -> dict:
        nodes = self._run("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
        edges = self._run("MATCH (:Entity)-[r]->(:Entity) RETURN count(r) AS c")[0]["c"]
        return {"nodes": nodes, "edges": edges}

    def to_node_link(self) -> dict:
        nodes = [
            {
                "id": r["id"],
                "label": r["label"],
                "type": r["type"],
                "aliases": r["aliases"],
                "freq": r["freq"],
                "community": r["community"],
            }
            for r in self._run(
                "MATCH (n:Entity) RETURN n.id AS id, n.label AS label, n.type AS type, "
                "n.aliases AS aliases, n.freq AS freq, n.community AS community"
            )
        ]
        edges = [
            {
                "source": r["s"],
                "target": r["t"],
                "predicate": r["p"],
                "weight": r["w"],
                "docs": r["docs"],
                "chunks": r["chunks"] or [],
                "evidence": r["ev"],
            }
            for r in self._run(
                "MATCH (s:Entity)-[r]->(t:Entity) RETURN s.id AS s, t.id AS t, "
                "coalesce(r.predicate, type(r)) AS p, r.weight AS w, r.docs AS docs, "
                "r.chunks AS chunks, r.evidence AS ev"
            )
        ]
        return {"nodes": nodes, "edges": edges}
