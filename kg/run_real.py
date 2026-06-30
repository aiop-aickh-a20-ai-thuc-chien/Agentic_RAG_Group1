"""Real run — read chunks from S3 -> build graph with OpenAI -> write graph to Neo4j.

Data flow:  S3 (READ chunks)  ->  OpenAI (extract)  ->  Neo4j (WRITE graph)
            S3 is read-only; nothing is ever written back to S3.

Prereqs
-------
  uv pip install neo4j
  .env :  OPENAI_API_KEY, LLM_MODEL=gpt-4o-mini
          AWS_S3_BUCKET, AWS_S3_PREFIX, AWS_PROFILE (or keys), AWS_DEFAULT_REGION
          NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io, NEO4J_USER, NEO4J_PASSWORD   (Aura)

Usage
-----
  python -m kg.run_real --check                 # test OpenAI + S3(list) + Neo4j, no build
  python -m kg.run_real --source s3 --limit 5   # build from 5 S3 docs -> Neo4j
  python -m kg.run_real --source sample         # build from bundled sample
  python -m kg.run_real --source s3 --wipe      # wipe Neo4j graph before load

NOTE: real OpenAI calls cost tokens — start with a small --limit.
"""

from __future__ import annotations

import argparse
import os


def load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass


def _load_documents(source: str, limit: int | None):
    use_s3 = source == "s3" or (source == "auto" and os.getenv("AWS_S3_BUCKET", "").strip())
    if use_s3:
        from kg.s3_loader import load_documents_from_s3

        docs = load_documents_from_s3(limit=limit)
        nchunks = sum(len(d.chunks) for d in docs)
        print(
            f"[source] S3 bucket={os.getenv('AWS_S3_BUCKET')} prefix={os.getenv('AWS_S3_PREFIX', '')} "
            f"-> {len(docs)} docs / {nchunks} chunks (limit={limit})"
        )
        return docs
    from kg.sample_data import DOCUMENTS

    print(f"[source] sample_data -> {len(DOCUMENTS)} docs")
    return DOCUMENTS


def cmd_check() -> int:
    ok = True
    # OpenAI — 1-token ping
    try:
        from kg.llm import OpenAILLM

        llm = OpenAILLM()
        r = llm._client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": "reply with: ok"}],
            max_tokens=2,
            temperature=0.0,
        )
        print(f"[OpenAI] OK  model={llm.model} -> {r.choices[0].message.content!r}")
    except Exception as exc:
        ok = False
        print(f"[OpenAI] FAIL  {exc}")
    # S3 — read-only list
    try:
        from kg.s3_loader import _list_chunk_keys, _norm_prefix, _s3_client

        bucket = os.getenv("AWS_S3_BUCKET", "").strip()
        keys = _list_chunk_keys(_s3_client(), bucket, _norm_prefix(os.getenv("AWS_S3_PREFIX", "")))
        print(f"[S3]     OK  bucket={bucket} -> {len(keys)} document(s) (read-only)")
    except Exception as exc:
        ok = False
        print(f"[S3]     FAIL  {exc}")
    # Neo4j
    try:
        from kg.store_neo4j import Neo4jStore

        store = Neo4jStore()
        print(f"[Neo4j]  OK  {store.uri} ({store.stats()})")
        store.close()
    except Exception as exc:
        ok = False
        print(f"[Neo4j]  FAIL  {exc}")
    return 0 if ok else 1


def _cap_chunks(documents, max_chunks: int):
    """Trim the corpus to at most `max_chunks` chunks total (cheap smoke test)."""
    from kg.schema import Document

    out, used = [], 0
    for doc in documents:
        if used >= max_chunks:
            break
        take = doc.chunks[: max_chunks - used]
        out.append(Document(doc_id=doc.doc_id, title=doc.title, chunks=take))
        used += len(take)
    return out


def _dump_result(result) -> None:
    s = result.stats
    id2name = {e.canonical_id: e.canonical_name for e in result.canon_entities.values()}
    print(f"\n=== ENTITIES ({s['resolution']['entities']}) — resolution={s['resolution']} ===")
    for e in sorted(result.canon_entities.values(), key=lambda e: -e.frequency):
        extra = [a for a in e.aliases if a != e.canonical_name]
        tag = f"   «{' | '.join(extra)}»" if extra else ""
        print(f"  [{e.type or '?'}] {e.canonical_name} (f={e.frequency}){tag}")
    print(f"\n=== PREDICATES ({s['predicates']['canonical_predicates']}) ===")
    for p in sorted(result.registry.values(), key=lambda p: -p.frequency):
        print(f"  {p.canonical} ({p.direction or 'n/a'})  <- {p.members}")
    print(f"\n=== CLEAN TRIPLES ({s['clean_triples']}, showing 40) ===")
    for c in result.clean[:40]:
        flip = " [flip]" if c.flipped else ""
        print(
            f"  {id2name.get(c.subj_id, c.subj_id)} —{c.predicate}→ {id2name.get(c.obj_id, c.obj_id)}{flip}"
        )


def _populate(pipe, staging: str, source: str, limit, max_chunks, cache) -> bool:
    """Fill the pipeline's staging (neon-incremental / JSON-cache / fresh extract).
    Returns False when there's nothing to build."""
    if staging == "neon":
        documents = _load_documents(source, limit)
        if max_chunks:
            documents = _cap_chunks(documents, max_chunks)
        added = pipe.ingest(documents)  # extract-cache skips chunks already in Neon
        print(f"[ingest] {added} NEW triples (cached chunks skipped) — {pipe.staging.stats()}")
        return True
    if cache and os.path.exists(cache):
        n = pipe.load_staging(cache)
        print(f"[cache] loaded {n} staged triples from {cache} (EXTRACT skipped)")
        return True
    documents = _load_documents(source, limit)
    if max_chunks:
        documents = _cap_chunks(documents, max_chunks)
        nchunks = sum(len(d.chunks) for d in documents)
        print(
            f"[source] capped -> {len(documents)} docs / {nchunks} chunks (max_chunks={max_chunks})"
        )
    if not documents:
        print("[build] no documents — nothing to do")
        return False
    pipe.ingest(documents)
    if cache:
        pipe.save_staging(cache)
        print(f"[cache] saved staged triples -> {cache}")
    return True


def cmd_build(
    source: str,
    limit: int | None,
    wipe: bool,
    max_chunks: int | None,
    cache: str | None,
    dump: bool,
    no_neo4j: bool,
    staging: str = "memory",
) -> int:
    from kg.llm import OpenAIEmbedder, OpenAILLM
    from kg.pipeline import KGPipeline

    llm = OpenAILLM()
    # Entity blocking is LEXICAL (free, no API) by default — see kg/resolve.py. Dense
    # embeddings are opt-in (KG_OPENAI_EMBED=1) for the optional LLM-judge escalation.
    embedder = OpenAIEmbedder() if os.getenv("KG_OPENAI_EMBED", "0") == "1" else None

    staging_store = None
    if staging == "neon":
        from kg.staging_neon import NeonStagingStore

        staging_store = NeonStagingStore()
        print(f"[staging] Neon (persistent) — {staging_store.stats()}")
    pipe = KGPipeline(
        llm=llm,
        embedder=embedder,
        gleanings=int(os.getenv("KG_GLEANINGS", "1")),
        staging=staging_store,
    )

    if not _populate(pipe, staging, source, limit, max_chunks, cache):
        return 1

    result = pipe.build()
    s = result.stats
    print(
        f"[build] staged={s['staged_triples']} entities={s['resolution']['entities']} "
        f"predicates={s['predicates']['canonical_predicates']} clean={s['clean_triples']} "
        f"dropped={s['dropped_triples']} flips={s['flips']} "
        f"graph={s['graph']['nodes']}n/{s['graph']['edges']}e"
    )
    print(f"[build] OpenAI calls: {s['llm_calls']}")
    if dump:
        _dump_result(result)

    if no_neo4j:
        print("[neo4j] skipped (--no-neo4j)")
        return 0
    from kg.store_neo4j import Neo4jStore

    store = Neo4jStore()
    print(f"[neo4j] loaded -> {store.load(result.store.to_node_link(), wipe=wipe)}")
    store.close()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Real KG run (S3 read -> OpenAI -> Neo4j write)")
    p.add_argument("--check", action="store_true", help="test connectivity only")
    p.add_argument("--source", choices=["auto", "s3", "sample"], default="auto")
    p.add_argument("--limit", type=int, default=None, help="max number of S3 documents")
    p.add_argument(
        "--max-chunks", type=int, default=None, help="cap total chunks (cheap smoke test)"
    )
    p.add_argument("--cache", default=None, help="staged-triple cache file: extract once, reuse")
    p.add_argument("--dump", action="store_true", help="print entities/predicates/triples")
    p.add_argument("--no-neo4j", action="store_true", help="skip the Neo4j load (offline inspect)")
    p.add_argument("--wipe", action="store_true", help="wipe Neo4j graph before load")
    p.add_argument(
        "--staging",
        choices=["memory", "neon"],
        default="memory",
        help="neon = persistent staging + extract-cache (resumable, incremental)",
    )
    args = p.parse_args()

    load_env()
    if args.check:
        return cmd_check()
    return cmd_build(
        args.source,
        args.limit,
        args.wipe,
        args.max_chunks,
        args.cache,
        args.dump,
        args.no_neo4j,
        args.staging,
    )


if __name__ == "__main__":
    raise SystemExit(main())
