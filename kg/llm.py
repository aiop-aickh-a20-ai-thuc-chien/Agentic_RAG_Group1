"""LLM seam.

The pipeline only depends on the `LLMClient` protocol (`.complete(prompt, system)`).
`MockLLM` makes the whole pipeline runnable with NO API key so you can see every
stage work end-to-end. To go to production, implement `LLMClient` over your real
model (an example `LiteLLMClient` stub is at the bottom) — nothing else changes.

How the mock stays deterministic: each prompt embeds a hidden `[[KG_TASK=...]]`
tag and a `[[PAYLOAD]]{json}[[/PAYLOAD]]` block. A real LLM ignores the tag and
reads the natural-language instruction; the mock reads the payload and answers by
rule. The seam (prompt in, JSON out) is identical for both.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import threading
import time
from typing import Protocol

from kg.embeddings import norm_text

_BRAND_WORDS = ("vinfast", "hãng", "xe", "ô tô", "oto", "chiếc")


class LLMClient(Protocol):
    def complete(self, prompt: str, system: str = "") -> str: ...


def task_of(prompt: str) -> str:
    m = re.search(r"\[\[KG_TASK=([a-z_]+)\]\]", prompt)
    return m.group(1) if m else ""


def payload_of(prompt: str) -> dict:
    m = re.search(r"\[\[PAYLOAD\]\](.*?)\[\[/PAYLOAD\]\]", prompt, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _entity_key(surface: str) -> str:
    k = norm_text(surface)
    for w in _BRAND_WORDS:
        k = k.replace(w, "")
    return re.sub(r"\s+", "", k)


def _entity_tokens(surface: str) -> set[str]:
    toks = set(norm_text(surface).split())
    return {t for t in toks if t not in _BRAND_WORDS}


def _predicate_bucket(pred: str) -> tuple[str, str]:
    """Map a free-form predicate onto a canonical (label, direction)."""

    n = norm_text(pred)
    if any(k in n for k in ("sản xuất", "made", "produc", "chế tạo")):
        return "made_by", "product->org"
    if any(k in n for k in ("trang bị", "equip", "tích hợp", "lắp")):
        return "has_feature", "product->feature"
    if any(k in n for k in ("áp dụng", "chính sách", "bảo hành", "subject")):
        return "applies_policy", "product->policy"
    if any(k in n for k in ("tương thích", "compatible", "kết nối")):
        return "compatible_with", "product->product"
    if any(k in n for k in ("giá", "price", "chi phí")):
        return "has_price", "product->value"
    return "related_to", ""


class MockLLM:
    """Deterministic stand-in for a real LLM — demo only."""

    def __init__(self, simulated_extractions: dict[str, list]) -> None:
        # chunk_id -> list[OpenTriple]
        self._sim = simulated_extractions
        self.calls: dict[str, int] = {}

    def complete(self, prompt: str, system: str = "") -> str:
        task = task_of(prompt)
        self.calls[task] = self.calls.get(task, 0) + 1
        payload = payload_of(prompt)

        if task == "extract":
            triples = self._sim.get(payload.get("chunk_id", ""), [])
            return json.dumps([dataclasses.asdict(t) for t in triples], ensure_ascii=False)

        if task == "entity_judge":
            a, b = payload.get("a", {}), payload.get("b", {})
            ka, kb = _entity_key(a.get("surface", "")), _entity_key(b.get("surface", ""))
            ta, tb = _entity_tokens(a.get("surface", "")), _entity_tokens(b.get("surface", ""))
            small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
            # token-subset merge only when the larger adds AT MOST one token
            # (so "pin LFP" ⊆ "pin lithium LFP" merges, but "VF 8" ⊄ "Thảm cốp 3D VF 8")
            token_sub = bool(small) and small <= big and (len(big) - len(small) <= 1)
            same = bool(ka) and (ka == kb or token_sub)
            sa, sb = a.get("surface", ""), b.get("surface", "")
            canonical = max((sa, sb), key=len)
            return json.dumps({"same": same, "canonical": canonical}, ensure_ascii=False)

        if task == "define":
            p = payload.get("predicate", "")
            return json.dumps(
                {"definition": f"Quan hệ '{p}' giữa chủ thể và đối tượng."},
                ensure_ascii=False,
            )

        if task == "pred_judge":
            preds = payload.get("predicates", [])
            groups: dict[str, dict] = {}
            for item in preds:
                name = item["predicate"] if isinstance(item, dict) else item
                label, direction = _predicate_bucket(name)
                g = groups.setdefault(
                    label,
                    {
                        "canonical": label,
                        "direction": direction,
                        "members": [],
                        "definition": f"Quan hệ {label}.",
                    },
                )
                g["members"].append(name)
            return json.dumps({"groups": list(groups.values())}, ensure_ascii=False)

        return "{}"


# --------------------------------------------------------------------------- #
# Production clients — real OpenAI SDK (no litellm).
# --------------------------------------------------------------------------- #
def _backoff_seconds(attempt: int, err: str) -> float:
    """Exponential backoff between retries; longer when it smells like a 429."""
    e = err.lower()
    rate_limited = "429" in e or "rate limit" in e or "ratelimit" in e
    base = 2.0 if rate_limited else 0.4
    return base * (2**attempt)


def _extract_json_text(text: str) -> str:
    """Pull the JSON value out of a model reply (strip code fences / prose)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t).strip()
    starts = [i for i in (t.find("["), t.find("{")) if i >= 0]
    if not starts:
        return t
    i = min(starts)
    closer = "]" if t[i] == "[" else "}"
    j = t.rfind(closer)
    return t[i : j + 1] if j > i else t[i:]


class OpenAILLM:
    """Real LLM client over the OpenAI SDK.

    model  ← $LLM_MODEL (default gpt-4o-mini) · key ← $OPENAI_API_KEY.
    Same `.complete(prompt, system)` seam as MockLLM — nothing else in the
    pipeline changes.
    """

    def __init__(
        self, model: str | None = None, api_key: str | None = None, retries: int = 2
    ) -> None:
        from openai import OpenAI

        self.model = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        self.retries = retries
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.calls: dict[str, int] = {}
        self._lock = threading.Lock()  # complete() runs from many threads (pmap)

    def complete(self, prompt: str, system: str = "") -> str:
        key = task_of(prompt) or "?"
        with self._lock:  # dict mutation isn't atomic across get+set under threads
            self.calls[key] = self.calls.get(key, 0) + 1
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        last = ""
        for attempt in range(self.retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model, messages=messages, temperature=0.0
                )
                return _extract_json_text(resp.choices[0].message.content or "")
            except Exception as exc:
                last = str(exc)
                if attempt < self.retries:
                    time.sleep(_backoff_seconds(attempt, last))
        raise RuntimeError(f"OpenAI call failed after {self.retries + 1} tries: {last}")


class OpenAIEmbedder:
    """Real multilingual embeddings (text-embedding-3-small) as a dense dict vector."""

    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None) -> None:
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    def embed(self, text: str) -> dict[str, float]:
        vec = self._client.embeddings.create(model=self.model, input=text or " ").data[0].embedding
        return {str(i): v for i, v in enumerate(vec)}

    def embed_many(self, texts: list[str]) -> list[dict[str, float]]:
        """Embed every surface in as FEW calls as possible (the API takes a list).

        Collapses N sequential per-mention calls into ceil(N / batch) calls.
        Results come back in input order, so the mapping is positional.
        """
        if not texts:
            return []
        out: list[dict[str, float]] = []
        batch = 256
        for i in range(0, len(texts), batch):
            inputs = [t or " " for t in texts[i : i + batch]]
            resp = self._client.embeddings.create(model=self.model, input=inputs)
            out.extend({str(j): v for j, v in enumerate(d.embedding)} for d in resp.data)
        return out


def make_llm(simulated: dict | None = None):
    """OpenAILLM when a key is present (unless KG_USE_MOCK=1), else MockLLM (demo)."""
    if os.getenv("OPENAI_API_KEY") and os.getenv("KG_USE_MOCK", "0") != "1":
        return OpenAILLM()
    return MockLLM(simulated or {})
