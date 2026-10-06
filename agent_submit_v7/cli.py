"""The official analyze interface with a conservative V6 fallback."""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
import statistics as stats

from agent_v2.indexer import build_index
from agent_v2.retriever import BM25Index
from agent_submit import cli as v6
from .eps import latest_pair, seasonal_forecast
from .series import level_forecast, positioning_forecast


def eligible_series(task, entity, corpus, allowed):
    name = task['target']['name'].lower()
    for doc_id in allowed:
        for header, rows in v6.tables(corpus.doc_texts[doc_id], task['cutoff_date']):
            cols = [v6.norm(c) for c in header]
            desired = 'bidtocover' if 'bid_to_cover' in name else v6.norm(entity.get('name', ''))
            if 'positioning' in name:
                desired = 'noncommnet'
            if not desired or desired not in cols:
                continue
            # Sort and refuse contradictory duplicates rather than silently creating a trend.
            by_date = {}
            for row in rows:
                if row[0] in by_date and row != by_date[row[0]]:
                    raise ValueError('Conflicting dated observations')
                by_date[row[0]] = row
            ordered = [by_date[k] for k in sorted(by_date)]
            values = [v6.number(r[cols.index(desired)]) for r in ordered]
            if any(v is None for v in values):
                continue  # missing observations are not silently collapsed in time
            oi = None
            if 'positioning' in name:
                if 'openinterest' not in cols:
                    continue
                oi = [v6.number(r[cols.index('openinterest')]) for r in ordered]
                if any(v is None or v <= 0 for v in oi):
                    continue
            return values, oi
    return None


def predict(task, entity, corpus, allowed):
    prediction, route, ncal, preferred = v6.forecast(task, entity, corpus, allowed)
    details = dict(baseline_route=route)
    name = task['target']['name'].lower()
    if 'eps' in name and ('growth' in name or 'direction' in name):
        prior = v6.number(entity.get('prior_year_q_eps'))
        pair = latest_pair(task, corpus, allowed)
        if pair is not None and prior is not None:
            # Require the extracted quarter to precede the requested quarter.
            target_dates = re.findall(r'\d{4}-\d{2}-\d{2}', str(entity.get('quarter_reported', '')))
            lag = (dt.date.fromisoformat(target_dates[-1])-dt.date.fromisoformat(pair.period)).days if target_dates else 90
            if 45 <= lag <= 150:
                estimate = seasonal_forecast(prior, pair)
                if 'growth' in name:
                    point = 100 * (estimate-prior) / abs(prior) if prior else 0.
                    width = max(50., abs(point)*.5)
                else:
                    point, width = estimate, max(.5, abs(estimate)*.5)
                    wanted = 'up' if estimate >= prior else 'down'
                    if wanted in task['target'].get('labels', []):
                        prediction['label'] = wanted
                prediction.update(point_forecast=point, interval=dict(level=task.get('interval_level', .9), lo=point-width, hi=point+width))
                route = 'eps-quarterly-seasonal-difference-half'
                preferred = (pair.doc_id, pair.start, pair.end)
                details.update(current_eps=pair.current, previous_year_eps=pair.previous_year,
                               period=pair.period, parser=pair.method, forecast_eps=estimate)
    elif any(x in name for x in ['bid_to_cover', 'cpi_component_mom', 'positioning']):
        series = eligible_series(task, entity, corpus, allowed)
        if series:
            values, oi = series
            result = None
            if 'positioning' in name and len(values) >= 12:
                match = re.search(r'from the (\d{4}-\d{2}-\d{2}).*?to the (\d{4}-\d{2}-\d{2})', task.get('prompt',''), re.I|re.S)
                horizon = max(1,round((dt.date.fromisoformat(match[2])-dt.date.fromisoformat(match[1])).days/7)) if match else 4
                result, details['selection'] = positioning_forecast(values, oi, horizon)
            elif 'bid_to_cover' in name and len(values) >= 6:
                result, details['selection'] = level_forecast(values, 'mean6', .5)
            elif 'cpi' in name and len(values) >= 3:
                result, details['selection'] = level_forecast(values, 'mean3', max(.2,stats.pstdev(values)*2))
            if result:
                point, width = result
                prediction.update(point_forecast=point, interval=dict(level=task.get('interval_level',.9),lo=point-width,hi=point+width))
                route = 'series-historical-selection-' + details['selection']['selected']
                ncal = details['selection']['origins']
    return prediction, route, ncal, preferred, details


def run(task_path, corpus_dir, out_path):
    task = json.loads(task_path.read_text())
    corpus = build_index(corpus_dir)
    index = BM25Index(corpus.chunks, task['cutoff_date'])
    bindings = v6.bindings_for(corpus_dir)
    predictions, trace = [], []
    kind = task.get('target_type') or task['target']['type']
    for entity in task['entities']:
        allowed = v6.allowed_docs(task, entity, corpus, bindings)
        if not allowed:
            raise ValueError('No admitted pre-cutoff evidence')
        pred, route, ncal, preferred, details = predict(task, entity, corpus, allowed)
        if kind != 'classification':
            pred.pop('label')
        pred['entity_id'] = entity['entity_id']
        pred['claims'] = [v6.evidence(task, entity, corpus, index, allowed, preferred)]
        predictions.append(pred)
        trace.append(dict(entity_id=entity['entity_id'], route=route, calibration_examples=ncal, **details))
    answer = dict(task_id=task['task_id'], schema_version='3', target_type=kind,
                  entity_predictions=predictions,
                  evidence_trace=json.dumps(dict(candidate='v7',neural_calls=0,fitted_offline_models=0,entities=trace)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(answer, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(rows=len(predictions),neural_calls=0,routes=dict(Counter(t['route'] for t in trace)))))
    return answer


def main():
    p = argparse.ArgumentParser()
    p.add_argument('verb', nargs='?', choices=['analyze'], default='analyze')
    p.add_argument('--task', type=Path, required=True)
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a=p.parse_args()
    run(a.task,a.corpus,a.out)


if __name__ == '__main__':
    main()
