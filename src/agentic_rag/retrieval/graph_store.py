from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.metadata import normalize as normalize_entity

logger = logging.getLogger(__name__)

class GraphStore:
    def __init__(self, filepath: str | Path | None = None) -> None:
        if filepath is None:
            # Default storage path under storage/local_pdf
            base_dir = Path("storage/local_pdf")
            base_dir.mkdir(parents=True, exist_ok=True)
            self.filepath = base_dir / "graph_store.json"
        else:
            self.filepath = Path(filepath)

        # Adjacency list: entity_name -> list of dicts: {"neighbor": str, "relation": str, "strength": float}
        self.adj: dict[str, list[dict[str, Any]]] = {}

        # Neo4j setup
        self.neo4j_uri = os.getenv("NEO4J_URI")
        self.neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD")
        self.use_neo4j = bool(self.neo4j_uri and self.neo4j_password)
        self.driver = None

        if self.use_neo4j:
            try:
                from neo4j import GraphDatabase
                self.driver = GraphDatabase.driver(
                    self.neo4j_uri,
                    auth=(self.neo4j_username, self.neo4j_password)
                )
                logger.info("Initialized Neo4j driver in GraphStore")
            except ImportError:
                logger.warning("neo4j package not installed; falling back to local file graph store.")
                self.use_neo4j = False
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j database: {e}")
                self.use_neo4j = False

        self.load()

    def close(self) -> None:
        """Close Neo4j driver connections."""
        if self.driver:
            try:
                self.driver.close()
            except Exception as e:
                logger.warning(f"Error closing Neo4j driver: {e}")

    def __del__(self) -> None:
        self.close()

    def load(self) -> None:
        """Load the graph from a local JSON file (no-op if Neo4j is active)."""
        if self.use_neo4j:
            return

        if not self.filepath.exists():
            self.adj = {}
            return

        try:
            with self.filepath.open("r", encoding="utf-8") as f:
                self.adj = json.load(f)
            logger.info(f"Loaded knowledge graph from {self.filepath} ({len(self.adj)} nodes)")
        except Exception as e:
            logger.error(f"Failed to load knowledge graph from {self.filepath}: {e}")
            self.adj = {}

    def save(self) -> None:
        """Save the graph to a local JSON file (no-op if Neo4j is active)."""
        if self.use_neo4j:
            return

        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with self.filepath.open("w", encoding="utf-8") as f:
                json.dump(self.adj, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved knowledge graph to {self.filepath}")
        except Exception as e:
            logger.error(f"Failed to save knowledge graph to {self.filepath}: {e}")

    def add_relation(self, head: str, relation: str, tail: str, strength: float = 1.0) -> None:
        """Add or update a relationship edge in Neo4j or local GraphStore."""
        norm_head = normalize_entity(head).strip().upper()
        norm_tail = normalize_entity(tail).strip().upper()
        norm_relation = relation.strip().lower()

        if not norm_head or not norm_tail:
            return

        if self.use_neo4j:
            try:
                with self.driver.session() as session:
                    query = (
                        "MERGE (h:Entity {name: $head_name}) "
                        "MERGE (t:Entity {name: $tail_name}) "
                        "MERGE (h)-[r:RELATION {type: $relation_type}]->(t) "
                        "ON CREATE SET r.strength = $strength "
                        "ON MATCH SET r.strength = CASE WHEN $strength > r.strength THEN $strength ELSE r.strength END"
                    )
                    session.run(
                        query,
                        head_name=norm_head,
                        tail_name=norm_tail,
                        relation_type=norm_relation.upper(),
                        strength=strength
                    )
            except Exception as e:
                logger.error(f"Failed to write relation to Neo4j: {e}")
            return

        # Local JSON Fallback Adjacency List
        if norm_head not in self.adj:
            self.adj[norm_head] = []

        exists = False
        for edge in self.adj[norm_head]:
            if edge["neighbor"] == norm_tail:
                edge["strength"] = max(edge["strength"], strength)
                edge["relation"] = norm_relation
                exists = True
                break

        if not exists:
            self.adj[norm_head].append({
                "neighbor": norm_tail,
                "relation": norm_relation,
                "strength": strength
            })

        if norm_tail not in self.adj:
            self.adj[norm_tail] = []
        
        exists_rev = False
        for edge in self.adj[norm_tail]:
            if edge["neighbor"] == norm_head:
                edge["strength"] = max(edge["strength"], strength)
                exists_rev = True
                break
        
        if not exists_rev:
            self.adj[norm_tail].append({
                "neighbor": norm_head,
                "relation": norm_relation,
                "strength": strength
            })

    def get_neighbors(self, seeds: list[str], max_depth: int = 1) -> list[str]:
        """Perform a BFS neighbors query starting from seed entities (on Neo4j or local GraphStore)."""
        normalized_seeds = {normalize_entity(s).strip().upper() for s in seeds}
        normalized_seeds = {s for s in normalized_seeds if s}

        if not normalized_seeds:
            return []

        if self.use_neo4j:
            try:
                with self.driver.session() as session:
                    query = (
                        "MATCH (h:Entity) WHERE h.name IN $seeds "
                        f"MATCH (h)-[r:RELATION*1..{max_depth}]-(t:Entity) "
                        "WHERE NOT t.name IN $seeds "
                        "RETURN DISTINCT t.name AS name"
                    )
                    result = session.run(query, seeds=list(normalized_seeds))
                    return [record["name"] for record in result]
            except Exception as e:
                logger.error(f"Failed to query neighbors from Neo4j: {e}")
                return []

        # Local JSON Fallback BFS
        visited = set(normalized_seeds)
        queue = list(normalized_seeds)
        level_map = {node: 0 for node in normalized_seeds}

        while queue:
            curr = queue.pop(0)
            curr_depth = level_map[curr]
            
            if curr_depth >= max_depth:
                continue

            neighbors = self.adj.get(curr, [])
            for edge in neighbors:
                neighbor = edge["neighbor"]
                if neighbor not in visited:
                    visited.add(neighbor)
                    level_map[neighbor] = curr_depth + 1
                    queue.append(neighbor)

        return [node for node in visited if node not in normalized_seeds]

    def rebuild_from_chunks(self, chunks: list[Chunk]) -> None:
        """Scan all chunks and rebuild the knowledge graph on Neo4j or local store."""
        if self.use_neo4j:
            try:
                with self.driver.session() as session:
                    session.run("MATCH (n) DETACH DELETE n")
            except Exception as e:
                logger.error(f"Failed to clear Neo4j graph during rebuild: {e}")
        else:
            self.adj = {}
        
        for chunk in chunks:
            metadata = chunk.metadata
            if not metadata:
                continue

            # 1. First extract explicit LLM-extracted relations
            relations = metadata.get("relations")
            if isinstance(relations, list):
                for rel in relations:
                    if isinstance(rel, dict):
                        head = rel.get("head")
                        relation = rel.get("relation") or "related"
                        tail = rel.get("tail")
                        strength = float(rel.get("strength") or 5.0)
                        if head and tail:
                            self.add_relation(head, relation, tail, strength)
            
            # 2. Fall back to co-occurrence graph building if no explicit relationships
            entities_canonical = metadata.get("entities_canonical")
            if isinstance(entities_canonical, list) and len(entities_canonical) > 1:
                for i in range(len(entities_canonical)):
                    for j in range(i + 1, len(entities_canonical)):
                        ent_a = entities_canonical[i]
                        ent_b = entities_canonical[j]
                        self.add_relation(ent_a, "cooccur", ent_b, 1.0)
        
        if not self.use_neo4j:
            self.save()
