"""Retrieve bounded evidence, forecast with House, and always emit a valid row."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .client import ModelClient
from .indexer import Chunk, IndexedCorpus
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .retriever import BM25Index
from .span_finder import find_span


@dataclass
class EntityResult:
    prediction: dict
    used_model: bool
    error: str | None


def _parse_json(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    if start < 0:
        raise ValueError("model returned no JSON object")
    parsed, _ = json.JSONDecoder().raw_decode(raw[start:])
    if not isinstance(parsed, dict):
        raise ValueError("model returned a non-object")
    return parsed


def _target_type(task: dict) -> str:
    target = task.get("target") or {}
    return task.get("target_type") or target.get("type") or "classification"


def _doc_ids_for_entity(entity: dict, corpus: IndexedCorpus) -> set[str]:
    eid = str(entity.get("entity_id", "")).lower()
    cik = str(entity.get("cik", ""))
    series = str(entity.get("series_id", entity.get("series_fred", ""))).lower()
    tenor = str(entity.get("tenor", "")).lower().replace("-", "")
    result = set()
    for doc_id, meta in corpus.doc_meta.items():
        doc_id_lower = doc_id.lower()
        doc_series = str(meta.get("series_id", "")).lower()
        doc_ticker = str(meta.get("ticker", "")).lower()
        doc_cik = str(meta.get("cik", ""))
        title = str(meta.get("title", "")).lower().replace("-", "")
        if (
            (eid and (doc_ticker == eid or eid in doc_id_lower))
            or (cik and doc_cik == cik)
            or (series and (doc_series == series or series in doc_id_lower))
            or (tenor and (tenor in doc_id_lower.replace("-", "") or tenor in title))
        ):
            result.add(doc_id)
    return result


def _retrieve(task: dict, entity: dict, index: BM25Index,
              corpus: IndexedCorpus, top_k: int) -> list[Chunk]:
    target = task.get("target") or {}
    target_name = str(target.get("name", "")).lower()
    if "credit" in target_name:
        topic = "going concern substantial doubt default liquidity covenant debt cash financing"
    elif "eps" in target_name:
        topic = "diluted earnings per share net income quarterly revenue guidance outlook"
    elif "reaction" in target_name:
        topic = "revenue growth gross margin earnings guidance outlook demand"
    elif "yield" in target_name:
        topic = "Treasury yield rate inflation FOMC policy duration curve"
    elif "cpi" in target_name:
        topic = "consumer price component month change first print average"
    elif "bid_to_cover" in target_name:
        topic = "auction bid to cover ratio demand recent reopening"
    elif "positioning" in target_name:
        topic = "noncommercial net position open interest weekly change"
    elif "revision" in target_name:
        topic = "vintage estimate revised up down reference month previous"
    else:
        topic = target_name.replace("_", " ") + " historical recent change outlook"
    identifiers = " ".join(str(entity.get(key, "")) for key in
                           ("entity_id", "name", "series_id", "series_name", "tenor"))
    query = identifiers + " " + topic
    local_ids = _doc_ids_for_entity(entity, corpus)
    if entity.get("cik") and local_ids:
        local = index.search(topic, top_k, local_ids)
        global_hits = []
    else:
        local = index.search(topic, max(1, top_k - 2), local_ids) if local_ids else []
        global_hits = index.search(query, top_k)
    selected: list[Chunk] = []
    seen: set[tuple[str, int]] = set()
    for hit in local + global_hits:
        chunk = hit.chunk
        key = (chunk.doc_id, chunk.span_start)
        if key not in seen:
            selected.append(chunk)
            seen.add(key)
        if len(selected) >= top_k:
            break
    if not selected and index.chunks:
        selected = [index.chunks[0]]
    return selected


def _finite(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _fallback(task: dict, entity: dict) -> tuple[str | None, float, tuple[float, float]]:
    target = task.get("target") or {}
    name = str(target.get("name", "")).lower()
    labels = target.get("labels") or []
    if "credit" in name and "no_event" in labels:
        label = "no_event"
    elif "eps_yoy" in name and "up" in labels:
        label = "up"
    elif "earnings_reaction" in name and "flat" in labels:
        label = "flat"
    elif "inline" in labels:
        label = "inline"
    else:
        label = labels[0] if labels else None

    if "bid_to_cover" in name:
        point, width = 2.5, 1.5
    elif "cpi_component" in name:
        point = _finite(entity.get("latest_published_mom_pct")) or 0.0
        width = 2.0
    elif "yield_change" in name:
        point, width = 0.0, 150.0
    elif "eps_yoy_growth" in name:
        point, width = 0.0, 200.0
    elif "positioning" in name:
        point = _finite(entity.get("trailing_4wk_net_change_pct_oi")) or 0.0
        width = 20.0
    elif "eps_outcome" in name:
        point = _finite(entity.get("consensus_eps")) or 0.0
        width = max(abs(point), 1.0)
    else:
        point, width = 0.0, 1.0
    # A missing model result carries little information about the outcome.
    # Use the public baseline's deliberately broad, feature-scaled interval.
    feature_scale = max(
        (abs(float(value)) for value in entity.values()
         if isinstance(value, (int, float)) and not isinstance(value, bool)
         and math.isfinite(value)),
        default=1.0,
    )
    width = max(width, 10.0 * max(feature_scale, 1.0))
    return label, point, (point - width, point + width)


def _claims(parsed: dict, retrieved: list[Chunk]) -> list[dict]:
    result = []
    evidence = parsed.get("evidence")
    if not isinstance(evidence, list):
        evidence = []
    for item in evidence[:3]:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        if source is None and isinstance(item.get("doc_id"), str):
            source = next((i for i, chunk in enumerate(retrieved, 1)
                           if chunk.doc_id == item["doc_id"]), None)
        if not isinstance(source, int) or not 1 <= source <= len(retrieved):
            continue
        chunk = retrieved[source - 1]
        quote = str(item.get("quote", ""))
        location = find_span(chunk.text, quote)
        start, end = location if location is not None else (0, len(chunk.text))
        result.append({
            "doc_id": chunk.doc_id,
            "span_start": chunk.span_start + start,
            "span_end": chunk.span_start + end,
            "claim": str(item.get("claim") or quote).strip(),
        })
    if not result and retrieved:
        chunk = retrieved[0]
        result = [{
            "doc_id": chunk.doc_id,
            "span_start": chunk.span_start,
            "span_end": min(chunk.span_end, chunk.span_start + 240),
            "claim": chunk.text[:200],
        }]
    return result


def run_entity(task: dict, entity: dict, index: BM25Index,
               corpus: IndexedCorpus, client: ModelClient | None,
               top_k: int) -> EntityResult:
    retrieved = _retrieve(task, entity, index, corpus, top_k)
    fallback_label, fallback_point, fallback_band = _fallback(task, entity)
    parsed: dict = {}
    error = None
    if client is not None:
        try:
            raw = client.complete(SYSTEM_PROMPT, build_user_prompt(task, entity, retrieved))
            parsed = _parse_json(raw)
        except Exception as exc:
            error = type(exc).__name__

    target = task.get("target") or {}
    labels = target.get("labels") or []
    label = parsed.get("label") if parsed.get("label") in labels else fallback_label
    point = _finite(parsed.get("point_forecast"))
    if point is None:
        point = fallback_point
    interval = parsed.get("interval") if isinstance(parsed.get("interval"), dict) else {}
    lo, hi = _finite(interval.get("lo")), _finite(interval.get("hi"))
    if lo is None or hi is None or lo > hi or not lo <= point <= hi:
        width = max(fallback_band[1] - fallback_point, abs(point) * 0.2)
        lo, hi = point - width, point + width
    claims = _claims(parsed, retrieved)

    prediction = {
        "entity_id": str(entity.get("entity_id", "")),
        "point_forecast": point,
        "interval": {"level": task.get("interval_level", 0.9), "lo": lo, "hi": hi},
        "claims": claims,
    }
    if _target_type(task) == "classification":
        prediction["label"] = label
    return EntityResult(prediction, bool(parsed), error)
