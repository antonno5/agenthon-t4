"""Forecast Treasury auction demand from pre-cutoff tenor history."""

from __future__ import annotations

import re

from .agent import EntityResult
from .indexer import IndexedCorpus

NUM = r"(\d+(?:\.\d+)?)"
NOTE = re.compile(
    r"NOTES[^\n]*?bid-to-cover ratio ranged from " + NUM + r" to " + NUM
    + r"; the average over[^\n]*?auctions is " + NUM,
    re.IGNORECASE,
)


def forecast_auction(task: dict, entity: dict, corpus: IndexedCorpus) -> EntityResult | None:
    target = task.get("target") or {}
    if "bid_to_cover" not in str(target.get("name", "")):
        return None
    tenor = re.search(r"\b(\d+)[-\s]*Year\b", str(entity.get("tenor", "")), re.I)
    if tenor is None:
        return None
    tenor_key = tenor.group(1) + "Y"
    candidates = []
    for doc_id, text in corpus.doc_texts.items():
        date = corpus.doc_dates.get(doc_id)
        if (not date or date > task["cutoff_date"] or
                "AUCTIONS" not in doc_id.upper() or
                tenor_key not in doc_id.upper()):
            continue
        match = NOTE.search(text)
        if match is None:
            continue
        lo, hi, point = map(float, match.groups())
        if not lo <= point <= hi:
            continue
        candidates.append((date, doc_id, match.start(), match.end(), point, lo, hi))
    if not candidates:
        return None
    _, doc_id, start, end, point, lo, hi = max(candidates, key=lambda row: (row[0], row[1]))
    return EntityResult(
        prediction={
            "entity_id": str(entity["entity_id"]),
            "point_forecast": point,
            "interval": {"level": task.get("interval_level", 0.9), "lo": lo, "hi": hi},
            "claims": [{"doc_id": doc_id, "span_start": start, "span_end": end,
                        "claim": corpus.doc_texts[doc_id][start:end]}],
        },
        used_model=False,
        error=None,
    )
