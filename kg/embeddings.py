"""Embedding seam.

For the runnable demo we use a pure-python char-n-gram cosine so blocking works
with zero external models. In production swap `CharNGramEmbedder` for a real
multilingual sentence-embedding model (the `Embedder` protocol is the seam).
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Protocol


def norm_text(s: str) -> str:
    """NFC + lowercase + whitespace-collapse — the shared normalization key."""

    s = unicodedata.normalize("NFC", s or "").lower().strip()
    return re.sub(r"\s+", " ", s)


class Embedder(Protocol):
    def embed(self, text: str) -> dict[str, float]:
        """Return a sparse vector (token -> weight)."""


class CharNGramEmbedder:
    """Character n-gram bag — good enough to cluster surface variants like
    'VF 8' / 'VinFast VF8' / 'vf8' without any ML dependency."""

    def __init__(self, n: int = 3) -> None:
        self.n = n

    def embed(self, text: str) -> dict[str, float]:
        # strip spaces so 'VF 8' and 'VinFast VF8' share the 'vf8' n-gram (blocking only)
        t = "  " + norm_text(text).replace(" ", "") + "  "
        counts: dict[str, float] = {}
        for i in range(len(t) - self.n + 1):
            g = t[i : i + self.n]
            counts[g] = counts.get(g, 0.0) + 1.0
        return counts

    def embed_many(self, texts: list[str]) -> list[dict[str, float]]:
        return [self.embed(t) for t in texts]


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (na * nb)
