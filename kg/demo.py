"""End-to-end demo. Run:  python -m kg.demo

Builds the KG from the Vietnamese EV sample, prints a stage-by-stage report
showing what each step did (merges, canonicalization, dropped junk, direction
flips, lifecycle delete), and writes:
    kg/output/graph.html         interactive graph
    kg/output/architecture.html  pipeline diagram + live stats
    kg/output/graph.json         node-link data
"""

from __future__ import annotations

import os

from kg.architecture_html import render_architecture_html
from kg.llm import MockLLM
from kg.pipeline import KGPipeline
from kg.sample_data import DOCUMENTS, SIMULATED_EXTRACTIONS
from kg.visualize import render_graph_html

OUT = os.path.join(os.path.dirname(__file__), "output")


def _line(c: str = "─") -> None:
    print(c * 64)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    # Demo showcases LLM synonym-merge (made_by ← sản xuất/made by/...); the MockLLM
    # groups deterministically. Real runs default to conservative key-grouping.
    os.environ.setdefault("KG_PRED_GROUP", "llm")
    # The tiny sample has every predicate at freq 1-2; don't let the scale-oriented
    # rare-predicate bucketing fold them into related_to (real runs keep the default).
    os.environ.setdefault("KG_MIN_PRED_FREQ", "1")
    llm = MockLLM(SIMULATED_EXTRACTIONS)
    pipe = KGPipeline(llm=llm, gleanings=1)

    result = pipe.run(DOCUMENTS)
    s = result.stats

    _line("═")
    print("  KNOWLEDGE-GRAPH CONSTRUCTION — DEMO")
    _line("═")
    print(
        f"[1+2] EXTRACT+STAGE : {s['staged_triples']} raw triples từ "
        f"{sum(len(d.chunks) for d in DOCUMENTS)} chunks / {len(DOCUMENTS)} docs"
    )
    print(
        f"[3a]  RESOLUTION    : {s['resolution']['mentions']} mentions → "
        f"{s['resolution']['entities']} entities "
        f"(auto-merge {s['resolution']['auto_merges']}, LLM-judge {s['resolution']['llm_judge_calls']})"
    )
    print(
        f"[3b]  PREDICATES    : {s['predicates']['surface_predicates']} surface → "
        f"{s['predicates']['canonical_predicates']} canonical"
    )
    print(f"[3c]  GATES         : dropped {s['dropped_triples']} triples")
    print(f"[4]   MERGE         : {s['clean_triples']} clean triples, đảo hướng {s['flips']}")
    print(f"[6]   GRAPH         : {s['graph']['nodes']} nodes, {s['graph']['edges']} edges")
    print(f"      LLM calls     : {s['llm_calls']}")

    _line()
    print("ENTITY RESOLUTION — các cụm đã gộp (>1 biến thể):")
    for e in result.canon_entities.values():
        if len(e.aliases) > 1:
            print(f"   • {e.canonical_name:<22} [{e.type}]  ← {e.aliases}")

    _line()
    print("PREDICATE CANONICALIZE — gộp + hướng:")
    for p in result.registry.values():
        if p.members:
            print(f"   • {p.canonical:<16} ({p.direction or 'n/a':<16}) ← {p.members}")

    _line()
    print("QUALITY GATES — triple bị loại:")
    for t, reason in result.dropped:
        print(f"   ✗ ({t.subject} —{t.predicate}→ {t.object})  :: {reason}")

    _line()
    print("DIRECTION FLIPS — cạnh được đảo hướng cho đúng:")
    for c in result.clean:
        if c.flipped:
            sn = result.canon_entities[c.subj_id].canonical_name
            on = result.canon_entities[c.obj_id].canonical_name
            print(f"   ↔ {sn} —{c.predicate}→ {on}   (từ: “{c.evidence}”)")

    # ---- lifecycle demo: delete one document -------------------------------
    _line()
    before = result.store.stats()
    removed = result.store.delete_document("d_vf5")
    after = result.store.stats()
    print(
        f"LIFECYCLE — xoá doc 'd_vf5': gỡ {removed} cạnh "
        f"({before['edges']}→{after['edges']} edges, {before['nodes']}→{after['nodes']} nodes)"
    )

    # rebuild a fresh store for the HTML (so output shows the full graph)
    full = pipe.build()
    graph_html = os.path.join(OUT, "graph.html")
    arch_html = os.path.join(OUT, "architecture.html")
    graph_json = os.path.join(OUT, "graph.json")
    render_graph_html(
        full.store,
        graph_html,
        title="Knowledge Graph — VinFast EV (demo)",
        subtitle=f"{full.stats['graph']['nodes']} nodes · {full.stats['graph']['edges']} edges",
    )
    render_architecture_html(full.stats, arch_html)
    full.store.save_json(graph_json)

    _line("═")
    print("OUTPUT:")
    print(f"   {graph_html}")
    print(f"   {arch_html}")
    print(f"   {graph_json}")
    _line("═")


if __name__ == "__main__":
    main()
