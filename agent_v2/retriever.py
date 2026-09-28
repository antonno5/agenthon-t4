"""Embargo-aware BM25 over bounded corpus windows."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .indexer import Chunk

TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return [x for x in TOKEN.findall(text.lower()) if len(x) > 1]


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float


class BM25Index:
    def __init__(self, chunks: list[Chunk], cutoff_date: str) -> None:
        self.chunks = [c for c in chunks if c.doc_date and c.doc_date <= cutoff_date]
        self.tf = [Counter(tokens(c.text)) for c in self.chunks]
        self.lengths = [sum(tf.values()) for tf in self.tf]
        self.avg_len = max(sum(self.lengths) / max(len(self.lengths), 1), 1.0)
        self.df = Counter()
        for tf in self.tf:
            self.df.update(tf.keys())

    def search(
        self, query: str, top_k: int, allowed_doc_ids: set[str] | None = None
    ) -> list[ScoredChunk]:
        terms = set(tokens(query))
        if not terms or not self.chunks:
            return []
        n = len(self.chunks)
        idf = {
            term: math.log1p((n - self.df[term] + 0.5) / (self.df[term] + 0.5))
            for term in terms
        }
        scored = []
        for chunk, tf, length in zip(self.chunks, self.tf, self.lengths):
            if allowed_doc_ids is not None and chunk.doc_id not in allowed_doc_ids:
                continue
            norm = 1.5 * (0.25 + 0.75 * length / self.avg_len)
            value = sum(
                idf[term] * count * 2.5 / (count + norm)
                for term in terms
                if (count := tf.get(term, 0))
            )
            if value > 0:
                scored.append(ScoredChunk(chunk, value))
        scored.sort(key=lambda x: (-x.score, x.chunk.doc_id, x.chunk.span_start))
        return scored[:top_k]
