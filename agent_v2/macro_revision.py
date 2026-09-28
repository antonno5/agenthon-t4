"""Use pre-cutoff vintage revisions to predict the next direction."""

from __future__ import annotations

import math
import re

from .agent import EntityResult
from .indexer import IndexedCorpus

REVISION = re.compile(
    r"(?m)^- The (\d{4}-\d{2}) estimate was revised (UP|DOWN) from [^\n]+"
)


def forecast_revision(task: dict, entity: dict, corpus: IndexedCorpus) -> EntityResult | None:
    target = task.get("target") or {}
    if "revision_direction" not in str(target.get("name", "")):
        return None
    series = entity.get("series_id")
    if not isinstance(series, str) or not series:
        return None
    candidates = []
    for doc_id, text in corpus.doc_texts.items():
        date = corpus.doc_dates.get(doc_id)
        if not date or date > task["cutoff_date"] or series.lower() not in doc_id.lower():
            continue
        notes = list(REVISION.finditer(text))
        if not notes:
            continue
        exact = [note for note in notes if note.group(1) == entity.get("ref_month")]
        note = (exact or notes)[-1]
        end = note.end() - int(text[note.end() - 1] == ".")
        label = note.group(2).lower()
        if label not in (target.get("labels") or []):
            continue
        candidates.append((date, doc_id, note.start(), end, label, text))
    if not candidates:
        return None
    _, doc_id, start, end, label, text = max(candidates, key=lambda row: (row[0], row[1]))
    scale = max(
        (abs(float(value)) for value in entity.values()
         if isinstance(value, (int, float)) and not isinstance(value, bool)
         and math.isfinite(value)),
        default=1.0,
    )
    width = 10.0 * max(scale, 1.0)
    return EntityResult(
        prediction={
            "entity_id": str(entity["entity_id"]),
            "label": label,
            "point_forecast": 0.0,
            "interval": {"level": task.get("interval_level", 0.9),
                         "lo": -width, "hi": width},
            "claims": [{"doc_id": doc_id, "span_start": start,
                        "span_end": end, "claim": text[start:end]}],
        },
        used_model=False,
        error=None,
    )
