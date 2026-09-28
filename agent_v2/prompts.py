"""Prompts for one grounded, unit-aware prediction at a time."""

from __future__ import annotations

import json

from .indexer import Chunk

SYSTEM_PROMPT = (
    "You are a quantitative financial analyst. Use only the provided pre-cutoff "
    "task, row, and corpus excerpts. Forecast the requested future outcome in its "
    "stated units. Do not claim that a future outcome is already known. Reply with "
    "one valid JSON object and no prose outside it."
)


def build_user_prompt(task: dict, entity: dict, retrieved: list[Chunk]) -> str:
    target = task.get("target") or {}
    target_type = target.get("type") or task.get("target_type") or "classification"
    labels = target.get("labels") or []
    excerpts = [
        {
            "source": i,
            "doc_id": chunk.doc_id,
            "doc_date": chunk.doc_date,
            "text": chunk.text,
        }
        for i, chunk in enumerate(retrieved, 1)
    ]
    instructions = {
        "classification": (
            "Choose label exactly from allowed_labels. Point forecast must estimate the "
            "underlying numeric quantity if the task defines one, otherwise use a numeric "
            "confidence from 0 to 1."
        ),
        "regression": "Predict the target as a number in the units of the task prompt.",
        "ranking": (
            "Predict the underlying ranking metric as a number; larger point_forecast "
            "must mean a higher rank. Do not output a rank integer."
        ),
    }[target_type]
    payload = {
        "task": task.get("prompt", ""),
        "cutoff_date": task.get("cutoff_date"),
        "resolution_date": task.get("resolution_date"),
        "target": target,
        "target_type": target_type,
        "allowed_labels": labels,
        "interval_level": task.get("interval_level", 0.9),
        "entity": {k: v for k, v in entity.items() if k != "corpus_ref"},
        "excerpts": excerpts,
    }
    return (
        "Analyze this one entity. " + instructions + "\n"
        "Use the row's numeric features and relevant historical excerpts to forecast. "
        "Give a 90% interval for the same numeric quantity as point_forecast. "
        "Copy 1 to 3 short verbatim quotes from the numbered excerpts that best "
        "support the direction and magnitude of your forecast. Cite only excerpts "
        "shown below. If evidence is weak, be conservative.\n"
        "JSON output shape: {\"label\": string or null, \"point_forecast\": number, "
        "\"interval\": {\"lo\": number, \"hi\": number}, "
        "\"evidence\": [{\"source\": integer, \"quote\": string, "
        "\"claim\": string}]}\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
