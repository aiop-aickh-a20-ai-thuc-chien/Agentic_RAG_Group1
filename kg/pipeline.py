"""Pipeline orchestrator — wires [1] -> [6].

INGEST ([1] extract + [2] stage) runs per-document and is incremental (this is the
part that would live in the ingest path / out-of-band worker).
BUILD ([3] resolve + canonicalize + gates, [4] merge, [6] store) runs as a BATCH
over everything staged, so canonicals are a function of the data, not upload order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kg.canonicalize import canonicalize_predicates
from kg.concurrency import pmap
from kg.embeddings import CharNGramEmbedder, Embedder
from kg.extract import extract_chunk
from kg.llm import LLMClient
from kg.merge import build_clean_triples, build_graph
from kg.resolve import resolve_entities
from kg.schema import Document
from kg.stage import StagingStore
from kg.store import GraphStore


@dataclass
class KGResult:
    store: GraphStore
    staged: list
    canon_entities: dict
    key_to_id: dict
    registry: dict
    surface_to_canon: dict
    clean: list
    dropped: list
    stats: dict = field(default_factory=dict)


class KGPipeline:
    def __init__(
        self,
        llm: LLMClient,
        embedder: Embedder | None = None,
        gleanings: int = 1,
        staging: object | None = None,
    ) -> None:
        self.llm = llm
        self.embedder = embedder or CharNGramEmbedder()
        self.gleanings = gleanings
        self.staging = staging or StagingStore()  # swap for NeonStagingStore in prod
        self.chunk_text: dict[str, str] = {}
        self._resolve_cache: tuple | None = None  # (sig, resolve_out, canon_out) — R3 memo

    # [1] + [2] — per-document, incremental
    def ingest(self, documents: list[Document]) -> int:
        # Extract chunks CONCURRENTLY, but SKIP any chunk already in the extract cache
        # (persistent staging) — so re-runs / `--add` only pay for genuinely new chunks
        # and a crash mid-run loses nothing already extracted.
        from kg.staging_neon import chunk_hash  # pure fn; no DB import at module load

        has_cache = hasattr(self.staging, "is_extracted")
        pending: list[tuple] = []
        for chunk in (c for doc in documents for c in doc.chunks):
            self.chunk_text[chunk.chunk_id] = chunk.text
            h = chunk_hash(chunk.text)
            if has_cache and self.staging.is_extracted(chunk.chunk_id, h):
                continue
            pending.append((chunk, h))

        results = pmap(lambda ch: extract_chunk(ch[0], self.llm, self.gleanings), pending)
        added = 0
        model = getattr(self.llm, "model", "")
        for (chunk, h), triples in zip(pending, results, strict=False):
            added += self.staging.add(chunk, triples)
            if has_cache:
                self.staging.mark_extracted(chunk, h, model, len(triples))
        return added

    # [3] + [4] + [6] — batch over the global staging view
    def build(self) -> KGResult:
        staged = self.staging.all()
        # Recover chunk texts staged in EARLIER runs (persistent backend), so the
        # evidence gate works over the whole staged set during an incremental build.
        if hasattr(self.staging, "chunk_texts"):
            self.chunk_text = {**self.staging.chunk_texts(), **self.chunk_text}
        # R3: resolution+canonicalization are a pure function of the staged set, so
        # memoize them by its signature. Repeated build() on unchanged staging (e.g.
        # tuning [4]/[6], demo's second build) skips the O(mentions + reps^2) work.
        sig = hash(frozenset(t.triple_id for t in staged))
        if self._resolve_cache and self._resolve_cache[0] == sig:
            (canon_entities, key_to_id, er_stats), (registry, surface_to_canon, pc_stats) = (
                self._resolve_cache[1],
                self._resolve_cache[2],
            )
        else:
            resolve_out = resolve_entities(staged, self.embedder, self.llm)
            canon_out = canonicalize_predicates(staged, self.llm)
            self._resolve_cache = (sig, resolve_out, canon_out)
            (canon_entities, key_to_id, er_stats) = resolve_out
            (registry, surface_to_canon, pc_stats) = canon_out
        clean, dropped = build_clean_triples(
            staged, key_to_id, canon_entities, surface_to_canon, registry, self.chunk_text
        )
        store = GraphStore(build_graph(clean, canon_entities))
        stats = {
            "staged_triples": len(staged),
            "resolution": er_stats,
            "predicates": pc_stats,
            "clean_triples": len(clean),
            "dropped_triples": len(dropped),
            "flips": sum(1 for c in clean if c.flipped),
            "graph": store.stats(),
            "llm_calls": getattr(self.llm, "calls", {}),
        }
        return KGResult(
            store,
            staged,
            canon_entities,
            key_to_id,
            registry,
            surface_to_canon,
            clean,
            dropped,
            stats,
        )

    def run(self, documents: list[Document]) -> KGResult:
        self.ingest(documents)
        return self.build()

    # ---- staged cache: extract ONCE, then tune [3]-[6] for free ----------- #
    def save_staging(self, path: str) -> None:
        import dataclasses
        import json

        data = {
            "staged": [dataclasses.asdict(t) for t in self.staging.all()],
            "chunk_text": self.chunk_text,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def load_staging(self, path: str) -> int:
        import json

        from kg.schema import StagedTriple

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.staging.rows = [StagedTriple(**d) for d in data["staged"]]
        self.staging._seen = {t.triple_id for t in self.staging.rows}
        self.chunk_text = dict(data["chunk_text"])
        return len(self.staging.rows)
