"""Prompts for one grounded, unit-aware prediction at a time."""

from __future__ import annotations

import json

from .indexer import Chunk

SYSTEM_PROMPT = (
    "You are a quantitative financial analyst. Use only the provided pre-cutoff "
    "task, row, and corpus excerpts. Forecast the requested future outcome in its "
    "stated units. Do not claim that a future outcome is already known. Check "
    "the arithmetic and that the label agrees with the numeric forecast. Reply "
    "with one valid JSON object and no prose outside it."
)


def _quantity_instruction(target_name: str, entity: dict) -> str:
    if "credit_event" in target_name:
        return ("point_forecast is a probability between 0 and 1, not a dollar "
                "amount. Choose credit_event when that probability is at least "
                "0.5, otherwise no_event. Keep the 90% interval within 0 and 1.")
    if "eps_yoy_direction" in target_name:
        return ("point_forecast is next-quarter diluted EPS in dollars per share. "
                "Compare it with prior_year_q_eps from the entity: choose up only "
                "when your EPS forecast is higher, otherwise down.")
    if "eps_yoy_growth_pct" in target_name:
        return ("point_forecast is year-over-year diluted EPS growth in PERCENT, "
                "not next-quarter EPS in dollars. First estimate next-quarter "
                "diluted EPS from pre-cutoff filings, then calculate "
                "100 * (forecast_EPS / prior_year_q_eps - 1). State the result "
                "as a percent and give a percent interval.")
    if "earnings_reaction" in target_name:
        threshold = entity.get("flat_threshold_abn_pct", 1.0)
        return ("point_forecast is the market-adjusted abnormal RETURN in percent, "
                "not the stock price or raw stock return. Choose "
                f"positive_reaction above +{threshold}%, negative_reaction "
                f"below -{threshold}%, and flat between those thresholds.")
    if "revision_direction" in target_name:
        return ("point_forecast is the NEXT REVISED LEVEL in the entity's units, "
                "not the revision amount. Choose up if it exceeds "
                "latest_precutoff_estimate and down if below it.")
    if "positioning_change" in target_name:
        return ("point_forecast is the future change in noncommercial net "
                "position as a PERCENT of starting open interest, not the net "
                "position level or a rank number. Larger values mean higher rank.")
    if "yield_change" in target_name:
        return ("point_forecast is the CHANGE in Treasury yield in BASIS POINTS "
                "from the cutoff close, not the yield level or a percent change.")
    if "cpi_component" in target_name:
        return ("point_forecast is the next component month-over-month PERCENT "
                "change, not the CPI index level or a decimal fraction.")
    if "bid_to_cover" in target_name:
        return ("point_forecast is the auction bid-to-cover RATIO, not a percent "
                "or the offering amount.")
    return "Use the numeric unit defined by the task."


def build_user_prompt(task: dict, entity: dict, retrieved: list[Chunk]) -> str:
    target = task.get("target") or {}
    target_type = target.get("type") or task.get("target_type") or "classification"
    target_name = str(target.get("name", "")).lower()
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
        + _quantity_instruction(target_name, entity) + "\n"
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
