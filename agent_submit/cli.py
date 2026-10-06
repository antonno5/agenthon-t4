"""Official analyze contract: bounded retrieval, numerical forecasts, exact quotations."""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
import math
from pathlib import Path
import re
import statistics as stats

from agent_v2.indexer import build_index
from agent_v2.retriever import BM25Index

NUMBER = r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'


def number(raw):
    if isinstance(raw, bool):
        return None
    try:
        value = float(str(raw).strip().replace(',', '').replace('%', '').replace('−', '-'))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def norm(text):
    return re.sub(r'[^a-z0-9]', '', str(text).lower())


def tables(text, cutoff):
    """Read dated pipe tables; unrecognized cells remain missing, never guessed."""
    header, rows = [], []
    for line in text.splitlines():
        if '|' not in line:
            if rows:
                yield header, rows
            header, rows = [], []
            continue
        cells = [s.strip() for s in line.strip().strip('|').split('|')]
        if re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?', cells[0]):
            if header and len(cells) == len(header) and cells[0] <= cutoff[:len(cells[0])]:
                rows.append(cells)
        else:
            if rows:
                yield header, rows
            header, rows = cells, []
    if rows:
        yield header, rows


def half_width(errors, fallback):
    errors = sorted(abs(x) for x in errors if math.isfinite(x))
    if len(errors) < 4:
        return fallback
    index = min(len(errors) - 1, math.ceil((len(errors) + 1) * .9) - 1)
    return max(errors[index], fallback * .05, .0001)


def mean_forecast(values, window, fallback_width):
    point = stats.mean(values[-window:])
    residuals = [values[i] - stats.mean(values[i-window:i]) for i in range(window, len(values))]
    return point, half_width(residuals, fallback_width), len(residuals)


def bindings_for(corpus_dir):
    bindings = {}
    for path in [corpus_dir.parent / 'manifest.json', corpus_dir / 'manifest.json']:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for entry in data.get('files', []):
            if entry.get('role') == 'corpus':
                bindings[Path(entry['path']).stem] = entry
    return bindings


def allowed_docs(task, entity, corpus, bindings):
    result = []
    eid = str(entity['entity_id'])
    for doc_id, meta in corpus.doc_meta.items():
        date = corpus.doc_dates[doc_id]
        if not date or date > task['cutoff_date']:
            continue
        binding = bindings.get(doc_id, {})
        if 'entity_ids' in binding or 'shared' in binding:
            admits = binding.get('shared') is True or eid in binding.get('entity_ids', [])
        else:
            admits = (str(meta.get('ticker', '')).upper() == eid.upper()
                      or bool(entity.get('cik')) and str(meta.get('cik', '')).zfill(10) == str(entity['cik']).zfill(10)
                      or norm(eid) in norm(doc_id)
                      or bool(entity.get('series_id')) and norm(entity['series_id']) in norm(doc_id)
                      or not entity.get('cik') and not meta.get('ticker') and not meta.get('cik'))
        if admits:
            result.append(doc_id)
    return sorted(result, key=lambda key: (corpus.doc_dates[key], key), reverse=True)


def quote(doc_id, text, start, end):
    selected = text[start:end]
    trimmed = selected.strip()
    start += len(selected) - len(selected.lstrip())
    end = start + len(trimmed)
    if not trimmed or end - start > 1200:
        raise ValueError('Invalid bounded quotation')
    return dict(doc_id=doc_id, span_start=start, span_end=end, claim=trimmed)


def evidence(task, entity, corpus, index, allowed, preferred=None):
    if preferred is not None:
        doc_id, start, end = preferred
        if doc_id not in allowed:
            raise ValueError('Evidence belongs to a different entity')
        return quote(doc_id, corpus.doc_texts[doc_id], start, end)
    name = str(task.get('target', {}).get('name', ''))
    topic = {'credit_event': 'substantial doubt liquidity debt cash default',
             'eps': 'diluted earnings per share net income',
             'yield': 'Treasury yield percent policy',
             'revision': 'revised vintage estimate',
             'reaction': 'revenue income growth outlook' }
    query = next((v for k, v in topic.items() if k in name), name.replace('_', ' '))
    query += ' ' + str(entity.get('name', entity['entity_id']))
    hits = index.search(query, 1, set(allowed))
    if not hits:
        raise ValueError('No eligible evidence')
    chunk = hits[0].chunk
    text = corpus.doc_texts[chunk.doc_id]
    start = chunk.span_start
    end = min(chunk.span_end, start + 600)
    if end < chunk.span_end:
        boundary = text.rfind(' ', start + 300, end)
        if boundary > start:
            end = boundary
    return quote(chunk.doc_id, text, start, end)


def latest_eps(corpus, allowed):
    """Only explicit EPS prose; ambiguous SEC flattened tables are not inferred."""
    pattern = re.compile(r'diluted (?:earnings|net (?:income|loss)) per (?:common )?share(?:\s*\(EPS\))?\s*(?:was|were|of|:|amounted to)\s*\$?\s*(' + NUMBER + r')', re.I)
    for doc_id in allowed:
        text = corpus.doc_texts[doc_id]
        for match in pattern.finditer(text):
            before = text[max(0, match.start()-100):match.start()]
            if re.search(r'expected|expect|forecast|guidance|projected', before, re.I):
                continue
            value = number(match[1])
            if value is not None and abs(value) <= 1000:
                return value, (doc_id, max(0, match.start()-60), min(len(text), match.end()+160))
    return None


def forecast(task, entity, corpus, allowed):
    target = task.get('target', {})
    name = str(target.get('name', '')).lower()
    labels = target.get('labels', [])
    label = next((v for v in ['inline', 'no_event', 'flat', 'unchanged', 'up'] if v in labels), labels[0] if labels else None)
    point, width, route, ncal, preferred = 0., 1., 'generic-zero', 0, None
    dated = [(doc_id, corpus.doc_texts[doc_id]) for doc_id in allowed]

    if 'bid_to_cover' in name:
        point, width, route = 2.5, 1., 'auction-prior'
        for doc_id, text in dated:
            for header, rows in tables(text, task['cutoff_date']):
                cols = [norm(c) for c in header]
                if 'bidtocover' not in cols:
                    continue
                idx = cols.index('bidtocover')
                values = [number(r[idx]) for r in rows]
                values = [v for v in values if v is not None]
                if len(values) >= 6:
                    point, width, ncal = mean_forecast(values, 6, .5)
                    route = 'auction-mean6-residual-interval'
                    break
            if ncal:
                break
    elif 'cpi' in name and 'mom' in name:
        point = number(entity.get('latest_published_mom_pct')) or 0.
        width, route = 2., 'cpi-latest'
        for doc_id, text in dated:
            for header, rows in tables(text, task['cutoff_date']):
                cols = [norm(c) for c in header]
                key = norm(entity.get('name', ''))
                if not key or key not in cols:
                    continue
                values = [number(row[cols.index(key)]) for row in rows]
                values = [v for v in values if v is not None]
                if len(values) >= 3:
                    point, width, ncal = mean_forecast(values, 3, max(.2, stats.pstdev(values) * 2))
                    route = 'cpi-mean3-residual-interval'
                    # Component note is a short exact quote in a shared source.
                    match = re.search(r'(?m)^-\s*' + re.escape(str(entity['name'])) + r':[^\n]+', text)
                    if match:
                        preferred = (doc_id, match.start(), min(match.end(), match.start()+1000))
                    break
            if ncal:
                break
    elif 'yield_change' in name:
        point, width, route = 0., 150., 'yield-no-change-insufficient-horizon-history'
        # The published snapshots do not provide enough resolved intermeeting windows
        # to fit the demo Ridge model or calibrate its horizon. Do not import lab data.
    elif 'positioning' in name:
        point = number(entity.get('trailing_4wk_net_change_pct_oi')) or 0.
        width, route = 20., 'positioning-recent-change'
        for doc_id, text in dated:
            for header, rows in tables(text, task['cutoff_date']):
                cols = [norm(c) for c in header]
                if 'noncommnet' not in cols or 'openinterest' not in cols:
                    continue
                net = [number(row[cols.index('noncommnet')]) for row in rows]
                oi = [number(row[cols.index('openinterest')]) for row in rows]
                if any(v is None for v in net + oi) or min(oi) <= 0 or len(net) < 12:
                    continue
                horizon, lookback = 4, 4
                dates = re.search(r'from the (\d{4}-\d{2}-\d{2}).*?to the (\d{4}-\d{2}-\d{2})', task.get('prompt', ''), re.I | re.S)
                if dates:
                    horizon = max(1, round((dt.date.fromisoformat(dates[2]) - dt.date.fromisoformat(dates[1])).days / 7))
                # Past completed forecast windows, normalized by their own origin OI.
                errors = [(net[i+horizon]-net[i]-(net[i]-net[i-lookback])*horizon/lookback) / oi[i] * 100
                          for i in range(lookback, len(net)-horizon)]
                point = (net[-1] - net[-1-lookback]) / oi[-1] * 100 * horizon/lookback
                width, ncal, route = half_width(errors, 20.), len(errors), 'positioning-change-residual-interval'
                break
            if ncal:
                break
    elif 'revision' in name:
        point = number(entity.get('latest_precutoff_estimate')) or 0.
        width, route = max(1., abs(point)*.05), 'revision-no-change'
        changes = []
        for doc_id, text in dated:
            for header, rows in tables(text, task['cutoff_date']):
                if not header or norm(header[0]) != 'referencemonth':
                    continue
                cols = [i for i, h in enumerate(header) if h.startswith('as_of_') and h[6:] <= task['cutoff_date']]
                for row in rows:
                    values = [number(row[i]) for i in cols]
                    for left, right in zip(values, values[1:]):
                        if left is not None and right is not None and right != left:
                            changes.append(right-left)
        if changes:
            direction = stats.median(changes)
            wanted = 'up' if direction > 0 else 'down' if direction < 0 else 'unchanged'
            if wanted in labels:
                label = wanted
            point += direction
            width = half_width([change-direction for change in changes], width)
            ncal = len(changes)
            route = 'revision-median-past-nonzero-change'
    elif 'credit' in name:
        point, width, route = .1, .3, 'credit-no-explicit-distress'
        pattern = re.compile(r'substantial doubt.{0,100}ability to continue|(?:events? of default (?:were|have been) triggered)|unable to (?:repay|pay|satisfy)', re.I | re.S)
        for doc_id, text in dated:
            match = pattern.search(text)
            if not match:
                continue
            context = text[max(0, match.start()-100):match.start()]
            if re.search(r'(?:no|not|without)\s+(?:\w+\s+){0,5}$', context, re.I):
                continue
            if 'credit_event' in labels:
                label = 'credit_event'
            point, width, route = .7, .3, 'credit-explicit-distress-disclosure'
            preferred = (doc_id, max(0, match.start()-100), min(len(text), match.end()+200))
            break
    elif 'eps' in name:
        prior = number(entity.get('prior_year_q_eps'))
        consensus = number(entity.get('consensus_eps'))
        actual = latest_eps(corpus, allowed)
        estimate = actual[0] if actual else prior if prior is not None else consensus if consensus is not None else 0.
        preferred = actual[1] if actual else None
        route = 'eps-explicit-prose-carry-forward' if actual else 'eps-prior-or-consensus'
        if 'growth' in name:
            point = 100 * (estimate - prior) / abs(prior) if prior else 0.
            width = max(50., abs(point) * .5)
        elif 'direction' in name:
            point, width = estimate, max(.5, abs(estimate) * .5)
            wanted = 'up' if prior is None or estimate >= prior else 'down'
            if wanted in labels:
                label = wanted
        else:
            point, width = estimate, max(.5, abs(estimate) * .5)
            threshold = number(entity.get('threshold_pct')) or .05
            if consensus is not None:
                margin = abs(consensus) * threshold
                wanted = 'beat' if estimate > consensus + margin else 'miss' if estimate < consensus - margin else 'inline'
                if wanted in labels:
                    label = wanted
    elif 'reaction' in name:
        point, width, route = 0., 10., 'reaction-zero-unfitted-band'
    else:
        for key in ['consensus', 'consensus_estimate', 'latest_value', 'previous_value', 'baseline']:
            value = number(entity.get(key))
            if value is not None:
                point, width, route = value, max(1., abs(value)*.5), 'generic-declared-prior'
                break
    lo, hi = point - width, point + width
    if 'credit' in name:
        lo, hi = max(0., lo), min(1., hi)
    return dict(label=label, point_forecast=point, interval=dict(level=task.get('interval_level', .9), lo=lo, hi=hi)), route, ncal, preferred


def run(task_path, corpus_dir, out_path):
    task = json.loads(task_path.read_text())
    corpus = build_index(corpus_dir)
    index = BM25Index(corpus.chunks, task['cutoff_date'])
    bindings = bindings_for(corpus_dir)
    predictions, trace = [], []
    kind = task.get('target_type') or task['target']['type']
    for entity in task['entities']:
        allowed = allowed_docs(task, entity, corpus, bindings)
        if not allowed:
            raise ValueError('No admitted pre-cutoff evidence for ' + entity['entity_id'])
        pred, route, ncal, preferred = forecast(task, entity, corpus, allowed)
        if kind != 'classification':
            pred.pop('label')
        pred['entity_id'] = entity['entity_id']
        pred['claims'] = [evidence(task, entity, corpus, index, allowed, preferred)]
        predictions.append(pred)
        trace.append(dict(entity_id=entity['entity_id'], route=route, calibration_examples=ncal))
    answer = dict(task_id=task['task_id'], schema_version='3', target_type=kind,
                  entity_predictions=predictions, evidence_trace=json.dumps(dict(neural_calls=0, fitted_offline_models=0, entities=trace)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(answer, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(rows=len(predictions), neural_calls=0, routes=dict(Counter(row['route'] for row in trace)))))
    return answer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('verb', nargs='?', choices=['analyze'], default='analyze')
    parser.add_argument('--task', required=True, type=Path)
    parser.add_argument('--corpus', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    run(args.task, args.corpus, args.out)


if __name__ == '__main__':
    main()
