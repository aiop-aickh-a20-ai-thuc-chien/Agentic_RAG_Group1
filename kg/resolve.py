"""[3a] ENTITY RESOLUTION — merge surface variants into canonical entities.

Chosen design: LEXICAL-FIRST, free, deterministic, reproducible.
  (1) normalized-key blocking  — strip stopwords/brand, join tokens; same key => merge
                                 ("VF 8" / "VinFast VF8" / "vf8" -> key "vf8")
  (2) token-containment        — one name's tokens ⊆ another's, adds <=1 token,
                                 compatible type => merge ("pin LFP" ⊆ "pin lithium LFP")
  (3) LLM judge (OPT-IN only)  — KG_ENTITY_JUDGE=llm escalates the char-ngram gray
                                 band, capped at top-K, for max recall.

Why not dense embeddings? Merging surface variants of SHORT names is a lexical job;
dense vectors pull related-but-distinct entities together ("VF 8" vs "VF 5") and cost
API calls. Default path uses neither embeddings nor the LLM — entity resolution is 0đ.

Runs BATCH over all staged triples so the canonical is a function of the DATA,
not of upload order (reproducible + A/B-able).
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

from kg.concurrency import pmap
from kg.embeddings import Embedder, cosine, norm_text
from kg.llm import LLMClient
from kg.schema import CanonicalEntity, StagedTriple, content_id

# LLM-escalation knobs (only used when KG_ENTITY_JUDGE=llm)
SIM_LOW = float(os.getenv("KG_SIM_LOW", "0.42"))  # char-ngram gray-band floor
JUDGE_TOPK = int(os.getenv("KG_JUDGE_TOPK", "4"))  # cap judge fan-out per mention
ENTITY_JUDGE = os.getenv("KG_ENTITY_JUDGE", "lexical").lower()  # lexical | llm | off
# Token-containment is lexical's one SEMANTIC leap (subset + <=1 token). Optionally have
# the LLM confirm just these few, uncertain merges — bounded by candidate count, NOT
# O(n^2). Default off (free/deterministic); set KG_TOKEN_VERIFY=llm in production.
TOKEN_VERIFY = os.getenv("KG_TOKEN_VERIFY", "off").lower()  # off | llm

_GENERIC = {"generic", "other", "unknown", "accessory", ""}
# NO domain words baked in. Optional manual stopwords come from env (default EMPTY);
# brand/qualifier tokens are LEARNED from the corpus in _derive_stopwords().
_MANUAL_STOPWORDS = {w for w in os.getenv("KG_STOPWORDS", "").lower().split(",") if w}
STOP_MIN_FRAC = float(os.getenv("KG_STOP_MIN_FRAC", "0.04"))  # token must span >= this share


# --------------------------------------------------------------------------- #
# Normalization + lexical decision (free)
# --------------------------------------------------------------------------- #
def _content_tokens(surface: str, stopwords: set[str]) -> list[str]:
    return [t for t in norm_text(surface).split() if t not in stopwords]


def _norm_key(surface: str, stopwords: set[str]) -> str:
    """Stopword-stripped, de-spaced key. Falls back to the full form for brand-only
    names (so two bare 'VinFast' mentions still share a key instead of colliding on '')."""
    toks = _content_tokens(surface, stopwords)
    return "".join(toks) if toks else norm_text(surface).replace(" ", "")


def _dominant_type(m: dict) -> str:
    non_generic = [(t, c) for t, c in m["types"].items() if t and t not in _GENERIC]
    if non_generic:
        return max(non_generic, key=lambda x: x[1])[0]
    return m["types"].most_common(1)[0][0] if m["types"] else ""


def _derive_stopwords(mentions: dict[str, dict]) -> set[str]:
    """Learn brand tokens from the data — a token that (a) qualifies many DISTINCT
    entities AND (b) is itself a standalone entity (e.g. 'VinFast' has its own org
    node) is a brand, not an identifier. This spares identifying tokens like 'vf',
    'km', 'pin' that modify names but never stand alone. No hard-coded domain list."""
    standalone = {
        norm_text(m["surface"])
        for m in mentions.values()
        if len(norm_text(m["surface"]).split()) == 1
    }
    tok_ents: dict[str, set[str]] = defaultdict(set)
    for k, m in mentions.items():
        for tok in set(norm_text(m["surface"]).split()):
            tok_ents[tok].add(k)
    min_ents = max(2, int(STOP_MIN_FRAC * len(mentions)))
    learned = {
        tok
        for tok, ents in tok_ents.items()
        if len(ents) >= min_ents and tok in standalone and not tok.isdigit()
    }
    return _MANUAL_STOPWORDS | learned


def _types_compatible(ma: dict, mb: dict) -> bool:
    da, db = _dominant_type(ma), _dominant_type(mb)
    if da in _GENERIC or db in _GENERIC:
        return True
    return da == db


def _token_contained(ma: dict, mb: dict, stopwords: set[str]) -> bool:
    """True when one token set ⊆ the other, the larger adds at most one token, and the
    types don't conflict — so 'pin LFP' ⊆ 'pin lithium LFP' merges but an accessory
    'Thảm cốp VF 8' (many extra tokens / different type) does not fold into 'VF 8'."""
    ta = set(_content_tokens(ma["surface"], stopwords))
    tb = set(_content_tokens(mb["surface"], stopwords))
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if not small or not small.issubset(big) or (len(big) - len(small) > 1):
        return False
    return _types_compatible(ma, mb)


def _entity_judge(llm: LLMClient, ma: dict, mb: dict) -> bool:
    payload = {
        "a": {"surface": ma["surface"], "type": _dominant_type(ma)},
        "b": {"surface": mb["surface"], "type": _dominant_type(mb)},
    }
    prompt = (
        "[[KG_TASK=entity_judge]]\n"
        "Hai cụm chữ sau có chỉ CÙNG MỘT thực thể thật không? Xét cả loại (type).\n"
        f'A: "{ma["surface"]}"  B: "{mb["surface"]}"\n'
        'Trả JSON {"same": true/false, "canonical": "tên chuẩn"}.\n'
        f"[[PAYLOAD]]{json.dumps(payload, ensure_ascii=False)}[[/PAYLOAD]]"
    )
    try:
        return bool(json.loads(llm.complete(prompt)).get("same"))
    except json.JSONDecodeError:
        return False


# --------------------------------------------------------------------------- #
# Mentions + union-find
# --------------------------------------------------------------------------- #
def _collect_mentions(staged: list[StagedTriple]) -> dict[str, dict]:
    """One entry per distinct normalized surface form."""
    mentions: dict[str, dict] = {}
    for t in staged:
        for surf, typ in ((t.subject, t.subject_type), (t.object, t.object_type)):
            m = mentions.setdefault(
                norm_text(surf), {"surface": surf, "types": Counter(), "freq": 0}
            )
            m["types"][typ or ""] += 1
            m["freq"] += 1
            if len(surf) > len(m["surface"]):
                m["surface"] = surf
    return mentions


class _UnionFind:
    def __init__(self, items: list[str]) -> None:
        self.parent = {x: x for x in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)


# --------------------------------------------------------------------------- #
# Clustering — (1) key blocking, (2) token containment, (3) optional LLM
# --------------------------------------------------------------------------- #
def _key_blocks(
    mentions: dict[str, dict], uf: _UnionFind, stopwords: set[str]
) -> tuple[list[str], int]:
    """Group mentions by normalized key; same key -> merge. Returns one rep per key."""
    by_key: dict[str, list[str]] = defaultdict(list)
    for k in mentions:
        by_key[_norm_key(mentions[k]["surface"], stopwords)].append(k)
    merges = 0
    for group in by_key.values():
        for other in group[1:]:
            uf.union(group[0], other)
            merges += 1
    return [g[0] for g in by_key.values()], merges


def _containment_candidates(
    reps: list[str], mentions: dict[str, dict], uf: _UnionFind, stopwords: set[str]
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i, a in enumerate(reps):
        for b in reps[i + 1 :]:
            if uf.find(a) != uf.find(b) and _token_contained(mentions[a], mentions[b], stopwords):
                out.append((a, b))
    return out


def _token_block(
    reps: list[str],
    mentions: dict[str, dict],
    uf: _UnionFind,
    stopwords: set[str],
    llm: LLMClient | None = None,
) -> int:
    """Merge distinct keys when one's tokens contain the other's (free, O(n^2) strings).
    These containment candidates are the only semantically-uncertain merges, so when
    KG_TOKEN_VERIFY=llm they (and only they) are confirmed by the LLM — a bounded number
    of calls, run concurrently."""
    candidates = _containment_candidates(reps, mentions, uf, stopwords)
    if TOKEN_VERIFY == "llm" and llm is not None and candidates:
        oks = pmap(lambda ab: _entity_judge(llm, mentions[ab[0]], mentions[ab[1]]), candidates)
    else:
        oks = [True] * len(candidates)
    merges = 0
    for (a, b), ok in zip(candidates, oks, strict=False):
        if ok and uf.find(a) != uf.find(b):
            uf.union(a, b)
            merges += 1
    return merges


def _embed_all(embedder: Embedder, surfaces: list[str]) -> list[dict]:
    batch = getattr(embedder, "embed_many", None)
    return batch(surfaces) if batch is not None else [embedder.embed(s) for s in surfaces]


def _gray_candidates(
    reps: list[str], vecs: dict[str, dict], uf: _UnionFind
) -> dict[str, list[tuple[float, str]]]:
    cand: dict[str, list[tuple[float, str]]] = {r: [] for r in reps}
    for i, a in enumerate(reps):
        for b in reps[i + 1 :]:
            if uf.find(a) == uf.find(b):
                continue
            score = cosine(vecs[a], vecs[b])
            if score >= SIM_LOW:
                cand[a].append((score, b))
                cand[b].append((score, a))
    return cand


def _topk_pairs(reps: list[str], cand: dict[str, list[tuple[float, str]]]) -> list[tuple[str, str]]:
    gray: set[tuple[str, str]] = set()
    for a in reps:
        for _, b in sorted(cand[a], reverse=True)[:JUDGE_TOPK]:
            gray.add((a, b) if a < b else (b, a))
    return list(gray)


def _llm_escalate(
    reps: list[str], mentions: dict[str, dict], embedder: Embedder, llm: LLMClient, uf: _UnionFind
) -> int:
    """OPT-IN: judge the char-ngram gray band, top-K per rep, concurrently."""
    vecs = dict(
        zip(reps, _embed_all(embedder, [mentions[r]["surface"] for r in reps]), strict=False)
    )
    cand = _gray_candidates(reps, vecs, uf)
    pending = [(a, b) for a, b in _topk_pairs(reps, cand) if uf.find(a) != uf.find(b)]
    verdicts = pmap(lambda ab: _entity_judge(llm, mentions[ab[0]], mentions[ab[1]]), pending)
    for (a, b), same in zip(pending, verdicts, strict=False):
        if same:
            uf.union(a, b)
    return len(pending)


def _cluster(
    mentions: dict[str, dict], embedder: Embedder, llm: LLMClient
) -> tuple[dict[str, list[str]], dict]:
    stopwords = _derive_stopwords(mentions)
    uf = _UnionFind(list(mentions))
    reps, key_m = _key_blocks(mentions, uf, stopwords)
    tok_m = _token_block(reps, mentions, uf, stopwords, llm)
    judged = _llm_escalate(reps, mentions, embedder, llm, uf) if ENTITY_JUDGE == "llm" else 0

    clusters: dict[str, list[str]] = defaultdict(list)
    for k in mentions:
        clusters[uf.find(k)].append(k)
    return clusters, {
        "mentions": len(mentions),
        "auto_merges": key_m + tok_m,
        "key_merges": key_m,
        "token_merges": tok_m,
        "stopwords_learned": len(stopwords - _MANUAL_STOPWORDS),
        # full set surfaced so builds can be diffed — a sudden jump = drift warning (R2).
        "stopwords": sorted(stopwords),
        "llm_judge_calls": judged,
    }


# --------------------------------------------------------------------------- #
# Build canonical entities
# --------------------------------------------------------------------------- #
def _build_entity(members: list[str], mentions: dict[str, dict]) -> CanonicalEntity:
    # `k` (the normalized surface) is the final, ORDER-INDEPENDENT tiebreaker so a
    # freq+len tie can't flip the chosen name/id with staging order (R1: id drift).
    best = max(members, key=lambda k: (mentions[k]["freq"], len(mentions[k]["surface"]), k))
    name = mentions[best]["surface"]
    type_counter: Counter = Counter()
    for k in members:
        type_counter.update(mentions[k]["types"])
    # IDENTITY is content-addressed on the MEMBER SET (sorted normalized keys), not the
    # frequency-dependent display name. So when the corpus grows and a different variant
    # becomes most-frequent, the label changes but the id (and Neo4j node) stays put.
    return CanonicalEntity(
        canonical_id=content_id("ent", "|".join(sorted(members))),
        canonical_name=name,
        type=_dominant_type({"types": type_counter}),
        aliases=sorted({mentions[k]["surface"] for k in members}),
        frequency=sum(mentions[k]["freq"] for k in members),
    )


def resolve_entities(
    staged: list[StagedTriple], embedder: Embedder, llm: LLMClient
) -> tuple[dict[str, CanonicalEntity], dict[str, str], dict]:
    mentions = _collect_mentions(staged)
    clusters, stats = _cluster(mentions, embedder, llm)

    canon: dict[str, CanonicalEntity] = {}
    key_to_id: dict[str, str] = {}
    for members in clusters.values():
        entity = _build_entity(members, mentions)
        canon[entity.canonical_id] = entity
        for k in members:
            key_to_id[k] = entity.canonical_id

    stats["entities"] = len(canon)
    return canon, key_to_id, stats
