"""Optional local embeddings for paraphrases that FTS5 cannot match."""

from __future__ import annotations

import math
import os
import sqlite3
from urllib.parse import urlparse

import httpx


DEFAULT_EMBED_MODEL = "nomic-embed-text"


def embed_settings() -> tuple[str, str] | None:
    """Use only the same loopback Ollama host as local answer generation."""
    model = os.getenv("OLLAMA_EMBED_MODEL", DEFAULT_EMBED_MODEL).strip()
    if not model:
        return None
    parsed = urlparse(os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat"))
    if (
        parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username or parsed.password or parsed.path != "/api/chat"
        or parsed.query or parsed.fragment
    ):
        return None
    return model, parsed._replace(path="/api/embed").geturl()


def normalise(vector: list[float]) -> tuple[float, ...]:
    if not vector or any(not isinstance(value, (float, int)) or not math.isfinite(value) for value in vector):
        raise ValueError("Invalid embedding vector")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ValueError("Zero embedding vector")
    return tuple(value / norm for value in vector)


class SemanticIndex:
    """Keep note vectors in memory; the source database remains authoritative."""

    def __init__(self) -> None:
        self.settings = embed_settings()
        self.rows: list[dict] = []
        self.vectors: list[tuple[float, ...]] = []
        self.ids: tuple[int, ...] = ()

    @property
    def available(self) -> bool:
        return bool(self.rows and self.vectors)

    def rebuild(self, connection: sqlite3.Connection) -> bool:
        """Embed approved notes in one local batch; leave keyword search available on errors."""
        if self.settings is None:
            return False
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM source_chunks WHERE status='approved' ORDER BY id"
        )]
        ids = tuple(row["id"] for row in rows)
        if ids == self.ids and self.available:
            return True
        if not rows:
            self.rows, self.vectors, self.ids = [], [], ()
            return False
        model, endpoint = self.settings
        texts = [
            f"{row['title']}. {row['section']}. {row['body']} Keywords: {row['keywords']}"
            for row in rows
        ]
        try:
            response = httpx.post(endpoint, json={"model": model, "input": texts}, timeout=12)
            response.raise_for_status()
            raw = response.json()["embeddings"]
            if len(raw) != len(rows):
                raise ValueError("Embedding count did not match source count")
            vectors = [normalise(vector) for vector in raw]
            if len({len(vector) for vector in vectors}) != 1:
                raise ValueError("Embedding dimensions did not match")
        except (httpx.HTTPError, OSError, KeyError, TypeError, ValueError):
            self.rows, self.vectors, self.ids = [], [], ()
            return False
        self.rows, self.vectors, self.ids = rows, vectors, ids
        return True

    def search(self, question: str, topic: str, limit: int = 3) -> list[dict]:
        """Return scored candidates, without deciding whether confidence is sufficient."""
        if not self.available or self.settings is None:
            return []
        model, endpoint = self.settings
        try:
            response = httpx.post(endpoint, json={"model": model, "input": question}, timeout=10)
            response.raise_for_status()
            query = normalise(response.json()["embeddings"][0])
        except (httpx.HTTPError, OSError, KeyError, IndexError, TypeError, ValueError):
            return []
        results = []
        for row, vector in zip(self.rows, self.vectors):
            if row["topic"] != topic or len(query) != len(vector):
                continue
            score = sum(left * right for left, right in zip(query, vector))
            results.append({**row, "semantic_score": score})
        return sorted(results, key=lambda row: row["semantic_score"], reverse=True)[:limit]
