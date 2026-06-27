"""[3b] PREDICATE CANONICALIZATION — EDC's Define -> Canonicalize.

Free-form predicates ("sản xuất bởi" / "made by" / "do ... sản xuất") are
collapsed onto a small canonical set with a fixed direction each. We DEFINE each
predicate (so 'hỗ trợ' the policy != 'hỗ trợ' the part), then let the LLM judge
which are truly synonymous (near-meaning != synonym), and assign a canonical
direction so Vietnamese passive voice can be straightened in stage [4].
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

from kg.embeddings import norm_text
from kg.llm import LLMClient
from kg.schema import CanonicalPredicate, StagedTriple

# Vietnamese function/filler words removed from the predicate key. The key is the
# SORTED SET of the remaining content tokens, so word-order and filler differences
# collapse ("có thông số D×R×C lần lượt là" == "thông số D×R×C") while distinct
# attributes stay apart ({tốc,độ,tối,đa} != {công,suất,tối,đa}). Language-level, not
# domain. Tunable via KG_PRED_STOP (comma-separated, replaces the defaults).
_PRED_STOP = set(
    os.getenv(
        "KG_PRED_STOP",
        "có,là,được,sẽ,đã,bị,cho,với,và,ở,tại,theo,trong,của,khi,để,các,những,một,"
        "này,đó,lần,lượt,sở,hữu,trang,dùng,sử,dụng,gồm,mang,đạt,thuộc,cũng,như,lên,"
        "ra,vào,đến,từ,về,do,thì,mà,hay,hoặc,rất,cùng",
    ).split(",")
)


def _min_pred_freq() -> int:
    """Predicates recurring fewer than this become `related_to` (bounds Neo4j rel-type
    count). Read at call time so env overrides (and the demo) take effect."""
    return int(os.getenv("KG_MIN_PRED_FREQ", "3"))


def _judge(llm: LLMClient, items: list[dict]) -> list[dict]:
    """Define + group in ONE batched call (folding the old per-predicate define step in)."""
    payload = {"predicates": items}
    prompt = (
        "[[KG_TASK=pred_judge]]\n"
        "Cho danh sách quan hệ (predicate) kèm ví dụ. GỘP các predicate ĐỒNG NGHĨA "
        "(cẩn thận: gần nghĩa ≠ đồng nghĩa, vd 'sản xuất bởi' ≠ 'phân phối bởi'). "
        "Đặt tên canonical NGẮN GỌN tiếng Việt, ghi hướng chuẩn (vd 'product->spec') "
        "và 1 định nghĩa ngắn cho mỗi nhóm.\n"
        'Trả JSON {"groups":[{"canonical","members","direction","definition"}]}.\n'
        f"[[PAYLOAD]]{json.dumps(payload, ensure_ascii=False)}[[/PAYLOAD]]"
    )
    try:
        return list(json.loads(llm.complete(prompt)).get("groups", []))
    except json.JSONDecodeError:
        return []


def _pred_key(predicate: str) -> str:
    """Order-independent content-token key: drop function words, sort the rest. So
    'có thông số D×R×C lần lượt là' and 'thông số D×R×C' collapse, but 'tốc độ tối đa'
    and 'công suất tối đa' stay apart."""
    toks = sorted(t for t in norm_text(predicate).split() if t not in _PRED_STOP)
    return "|".join(toks) if toks else norm_text(predicate)


def _group_conservative(freq: Counter) -> list[dict]:
    """Deterministic grouping by normalized key — no LLM, never over-merges (the
    default; LLM synonym-merge is opt-in via KG_PRED_GROUP=llm)."""
    buckets: dict[str, list[str]] = defaultdict(list)
    for p in freq:
        buckets[_pred_key(p)].append(p)
    return [
        {
            "canonical": max(members, key=lambda m: freq[m]),
            "members": members,
            "direction": "",
            "definition": "",
        }
        for members in buckets.values()
    ]


def canonicalize_predicates(
    staged: list[StagedTriple], llm: LLMClient
) -> tuple[dict[str, CanonicalPredicate], dict[str, str], dict]:
    freq = Counter(t.predicate for t in staged)
    example = {t.predicate: t.evidence for t in staged}  # one example per predicate
    preds = list(freq)

    # Default: deterministic key-grouping (0 API, no over-merge). LLM synonym-merge
    # (1 batched call) is opt-in — it can over-merge distinct spec attributes.
    if os.getenv("KG_PRED_GROUP", "conservative").lower() == "llm":
        groups = _judge(llm, [{"predicate": p, "example": example.get(p, "")} for p in preds])
    else:
        groups = _group_conservative(freq)

    registry: dict[str, CanonicalPredicate] = {}
    surface_to_canon: dict[str, str] = {}
    min_freq = _min_pred_freq()

    def _to_related(members: list[str]) -> None:
        reg = registry.setdefault("related_to", CanonicalPredicate("related_to"))
        for m in members:
            surface_to_canon[m] = "related_to"
            reg.members.append(m)
            reg.frequency += freq[m]

    for g in groups:
        members = [m for m in g.get("members", []) if m in freq]
        if not members:
            continue
        # Rare predicates are overwhelmingly one-off clause-phrases from prose ("sẽ được
        # triển khai ở...") — bucket them under related_to so the edge survives but the
        # rel-type explosion does not (the original phrase stays in the triple evidence).
        if sum(freq[m] for m in members) < min_freq:
            _to_related(members)
            continue
        # Prefer the LLM's canonical label, else the MOST-FREQUENT surface member
        # (deterministic; also catches the LLM leaking the direction 'product->...').
        canon = (g.get("canonical") or "").strip()
        if not canon or "->" in canon:
            canon = max(members, key=lambda m: freq[m])
        registry[canon] = CanonicalPredicate(
            canonical=canon,
            definition=g.get("definition", ""),
            direction=g.get("direction", ""),
            members=members,
            frequency=sum(freq[m] for m in members),
        )
        for m in members:
            surface_to_canon[m] = canon

    _to_related([p for p in preds if p not in surface_to_canon])

    stats = {"surface_predicates": len(preds), "canonical_predicates": len(registry)}
    return registry, surface_to_canon, stats
