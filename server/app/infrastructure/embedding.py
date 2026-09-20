"""Embedding provider interface and implementations."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimensions(self) -> int: ...


class FakeEmbeddingProvider:
    """Deterministic unit-vector embeddings for CI/local dev."""

    _DIM = 1536

    @property
    def dimensions(self) -> int:
        return self._DIM

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        vec: list[float] = []
        state = seed
        for _ in range(self._DIM):
            state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
            val = ((state >> 33) ^ state) * 0x62A9D9ED799705F5
            val = (val ^ (val >> 28)) * 0xCB24D0A5C88C35B3
            val = (val ^ (val >> 32)) & 0xFFFFFFFFFFFFFFFF
            vec.append((val / 0xFFFFFFFFFFFFFFFF) * 2 - 1)
        mag = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / mag for v in vec]
