"""Assemble and validate the answer before the container exits."""

from __future__ import annotations

import math

from .agent import EntityResult
from .indexer import IndexedCorpus


def build_answer(task: dict, results: list[EntityResult], corpus: IndexedCorpus) -> dict:
    target = task.get("target") or {}
    target_type = task.get("target_type") or target.get("type")
    answer = {
        "task_id": task.get("task_id", ""),
        "schema_version": "3",
        "entity_predictions": [result.prediction for result in results],
        "evidence_trace": (
            f"BM25 over frozen pre-cutoff corpus; "
            f"{sum(result.used_model for result in results)} model predictions; "
            f"{sum(bool(result.error) for result in results)} model failures."
        ),
    }
    if target_type:
        answer["target_type"] = target_type
    for row in answer["entity_predictions"]:
        assert row["claims"], f"{row['entity_id']}: no citation"
        for field in ("point_forecast",):
            assert math.isfinite(row[field]), f"{row['entity_id']}: nonfinite {field}"
        bounds = row["interval"]
        assert bounds["level"] == 0.9
        assert math.isfinite(bounds["lo"]) and math.isfinite(bounds["hi"])
        assert bounds["lo"] <= bounds["hi"]
        for claim in row["claims"]:
            text = corpus.doc_texts[claim["doc_id"]]
            assert 0 <= claim["span_start"] < claim["span_end"] <= len(text)
            assert corpus.doc_dates[claim["doc_id"]] <= task["cutoff_date"]
    return answer
