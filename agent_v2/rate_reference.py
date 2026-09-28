"""A conservative, pre-cutoff rate-curve forecast for explicit policy regimes."""

from __future__ import annotations

import math
import re

from .agent import EntityResult
from .indexer import IndexedCorpus


def forecast_rate_change(task: dict, entity: dict,
                         corpus: IndexedCorpus) -> EntityResult | None:
    target = task.get("target") or {}
    if "yield_change_bps_intermeeting" not in str(target.get("name", "")):
        return None
    maturity = entity.get("maturity_years")
    if not isinstance(maturity, (int, float)) or maturity <= 0:
        return None

    candidates = []
    for doc_id, meta in corpus.doc_meta.items():
        date = corpus.doc_dates.get(doc_id)
        text = corpus.doc_texts[doc_id]
        if (not date or date > task["cutoff_date"]
                or meta.get("form_type") != "rates_market_snapshot"
                or "Monetary policy." not in text):
            continue
        start = text.index("Monetary policy.")
        body = text[start:]
        # The policy paragraph and market-positioning paragraph jointly explain
        # the forecast. Stop before the long historical table, if present.
        table = re.search(r"\n\n(?:U\.S\. Treasury constant-maturity yields|date \|)", body)
        end = start + table.start() if table else len(text)
        evidence = text[start:end]
        policy_step = re.search(r"(\d+) basis point(?:s)?", evidence, re.I)
        if policy_step is None:
            continue
        step = float(policy_step.group(1))
        if "lowered" in evidence.lower() and re.search(
            r"market-implied paths.*more aggressive than.*projected path",
            evidence, re.I | re.S,
        ):
            # An easing path already priced more aggressively than the SEP
            # leaves room for a modest upward repricing of Treasury yields.
            direction = 1
        elif "raised" in evidence.lower() and "ongoing increases" in evidence.lower():
            direction = 1
        else:
            continue
        candidates.append((date, doc_id, start, end, step, direction))
    if not candidates:
        return None

    _, doc_id, start, end, step, direction = max(candidates)
    # A policy move is not a Treasury-yield forecast. Apply a conservative
    # fraction of that pre-cutoff signal, decaying with maturity because the
    # front end is more sensitive to the expected policy path.
    point = round(direction * 0.6 * step * math.sqrt(2.0 / maturity))
    width = max(150.0, 2.0 * step)
    text = corpus.doc_texts[doc_id]
    return EntityResult(
        prediction={
            "entity_id": str(entity["entity_id"]),
            "point_forecast": point,
            "interval": {
                "level": task.get("interval_level", 0.9),
                "lo": point - width,
                "hi": point + width,
            },
            "claims": [{
                "doc_id": doc_id,
                "span_start": start,
                "span_end": end,
                "claim": text[start:end].strip(),
            }],
        },
        used_model=False,
        error=None,
    )
