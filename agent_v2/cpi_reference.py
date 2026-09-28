"""Forecast CPI components from pre-cutoff component notes when available."""

from __future__ import annotations

import re

from .agent import EntityResult
from .indexer import IndexedCorpus

NUMBER = r"([+-]?\d+(?:\.\d+)?)%"


def forecast_cpi(task: dict, entity: dict, corpus: IndexedCorpus) -> EntityResult | None:
    target = task.get("target") or {}
    name = str(target.get("name", "")).lower()
    if "cpi_component" not in name or "mom" not in name:
        return None
    component = entity.get("name")
    if not isinstance(component, str) or not component:
        return None
    candidates = []
    for doc_id, text in corpus.doc_texts.items():
        date = corpus.doc_dates.get(doc_id)
        if not date or date > task["cutoff_date"]:
            continue
        line_pattern = re.compile(r"(?m)^-\s*" + re.escape(component) + r":\s*[^\n]+")
        for line in line_pattern.finditer(text):
            historical = re.search(
                r"three-month average\s*\([^)]*\)\s*" + NUMBER,
                line.group(), re.IGNORECASE,
            )
            historical_range = re.search(
                r"range\s+" + NUMBER + r"\s+to\s+" + NUMBER,
                line.group(), re.IGNORECASE,
            )
            if historical_range is None:
                continue
            lo, hi = map(float, historical_range.groups())
            point = (
                float(historical.group(1)) if historical is not None else
                entity.get("latest_published_mom_pct")
            )
            if not isinstance(point, (int, float)) or not lo <= point <= hi:
                continue
            # Keep the cited passage through its historical-range values.
            # Trailing editorial punctuation is not part of the evidence.
            end = line.start() + historical_range.end()
            candidates.append((date, doc_id, line.start(), end, float(point), lo, hi))
    if not candidates:
        return None
    _, doc_id, start, end, point, lo, hi = max(candidates, key=lambda row: (row[0], row[1]))
    return EntityResult(
        prediction={
            "entity_id": str(entity["entity_id"]),
            "point_forecast": point,
            "interval": {"level": task.get("interval_level", 0.9), "lo": lo, "hi": hi},
            "claims": [{
                "doc_id": doc_id,
                "span_start": start,
                "span_end": end,
                "claim": corpus.doc_texts[doc_id][start:end],
            }],
        },
        used_model=False,
        error=None,
    )
