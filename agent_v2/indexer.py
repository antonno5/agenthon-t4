"""Load the official corpus and create citation-ready, bounded text windows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

WINDOW = 1100
OVERLAP = 150


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    doc_date: str | None
    span_start: int
    span_end: int
    text: str


@dataclass(frozen=True)
class IndexedCorpus:
    chunks: list[Chunk]
    doc_texts: dict[str, str]
    doc_dates: dict[str, str | None]
    doc_meta: dict[str, dict]


def _joined_text(doc: dict) -> str:
    if isinstance(doc.get("text"), str):
        return doc["text"]
    spans = doc.get("spans")
    if isinstance(spans, list):
        return " ".join(
            span.get("text", "") if isinstance(span, dict) else ""
            for span in spans
        )
    return ""


def _windows(text: str):
    """Yield exact character windows; offsets refer to the scorer's joined text."""
    start = 0
    while start < len(text):
        end = min(start + WINDOW, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start + WINDOW // 2, end),
                           text.rfind(" ", start + WINDOW // 2, end))
            if boundary > start:
                end = boundary + 1
        if text[start:end].strip():
            yield start, end, text[start:end]
        if end >= len(text):
            break
        start = max(start + 1, end - OVERLAP)


def build_index(corpus_dir: str | Path) -> IndexedCorpus:
    chunks: list[Chunk] = []
    doc_texts: dict[str, str] = {}
    doc_dates: dict[str, str | None] = {}
    doc_meta: dict[str, dict] = {}
    for path in sorted(Path(corpus_dir).glob("*.json")):
        if path.name == "manifest.json":
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc_id = str(doc.get("doc_id") or path.stem)
        text = _joined_text(doc)
        date = doc.get("doc_date")
        doc_texts[doc_id] = text
        doc_dates[doc_id] = date
        doc_meta[doc_id] = {k: v for k, v in doc.items() if k not in ("text", "spans")}
        for start, end, window in _windows(text):
            chunks.append(Chunk(doc_id, date, start, end, window))
    return IndexedCorpus(chunks, doc_texts, doc_dates, doc_meta)
