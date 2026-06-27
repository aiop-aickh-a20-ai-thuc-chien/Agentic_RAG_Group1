"""Greenfield Knowledge-Graph construction pipeline (self-contained, no dependency
on the existing agentic_rag modules).

Pipeline stages (EDC backbone — Extract -> Define -> Canonicalize):

    [1] Extract (open)   kg.extract
    [2] Stage            kg.stage
    [3] Canonicalize     kg.resolve (entities) + kg.canonicalize (predicates) + kg.gates
    [4] Merge            kg.merge
    [5] Enrich (opt.)    kg.store (community detection)
    [6] Store            kg.store

Run the demo:  python -m kg.demo
"""
