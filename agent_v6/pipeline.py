"""Bounded extraction -> temporal features -> numerical models -> exact citations."""
import csv
import io
import json
import math
import re
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

METHODS = ['legacy_v1', 'naive', 'rules', 'ridge', 'trees', 'ensemble']
PATTERN = re.compile(r'^Date (\d{4}-\d{2}-\d{2}); available (\d{4}-\d{2}-\d{2}); value ([-\d.eE+]+); tenor (\d+); offering ([-\d.eE+]+); reopening (\d+)\.$')


def parse_document(doc, cutoff):
    if not isinstance(doc.get('doc_date'), str) or doc['doc_date'] > cutoff:
        raise ValueError('Undated or post-cutoff document')
    text = doc['text']
    if len(text) > 1_000_000:
        raise ValueError('Document exceeds extraction budget')
    lines = text.splitlines()[1:]
    if lines and lines[0] == 'date,available,value,tenor,offering,reopening':
        rows = list(csv.DictReader(io.StringIO('\n'.join(lines))))
    elif lines and all(line.startswith('OBS ') for line in lines):
        rows = [json.loads(line[4:]) for line in lines]
    else:
        rows = []
        for line in lines:
            match = PATTERN.fullmatch(line)
            if not match:
                raise ValueError('Unknown layout; extraction abstains')
            rows.append(dict(zip(['date', 'available', 'value', 'tenor', 'offering', 'reopening'], match.groups())))
    if not rows:
        raise ValueError('Empty history')
    for row in rows:
        if row['available'] > cutoff or row['date'] > row['available']:
            raise ValueError('Post-cutoff or invalid observation')
        for key in ['value', 'tenor', 'offering', 'reopening']:
            row[key] = float(row[key])
            if not math.isfinite(row[key]):
                raise ValueError('Non-finite observation')
    rows.sort(key=lambda row: row['date'])
    if len({r['date'] for r in rows}) != len(rows):
        raise ValueError('Duplicate dates')
    return rows


def accept_locator_response(response, documents, cutoff, max_chars=1200):
    """Optional neural locator contract only. No execution, prediction or model API here.

    A caller may supply at most two shortlisted snippets to a House locator. Its only
    accepted return is an exact quote in an admitted document. Unknown formats still
    abstain: unverified model-created numbers never enter the forecasting path.
    """
    if set(response) != {'doc_id', 'quote'}:
        raise ValueError('Locator must only identify a span')
    doc = documents.get(response['doc_id'])
    quote = response['quote']
    if doc is None or not isinstance(quote, str) or not 1 <= len(quote) <= max_chars:
        raise ValueError('Invalid locator response')
    if not doc.get('doc_date') or doc['doc_date'] > cutoff or quote not in doc['text']:
        raise ValueError('Unverified locator span')
    start = doc['text'].index(quote)
    return dict(doc_id=doc['doc_id'], span_start=start, span_end=start + len(quote), claim=quote)


def features(rows, index, target, auction):
    values = np.array([row['value'] for row in rows[:index + 1]], dtype=float)
    last = values[-1]
    if auction:
        x = [last, np.mean(values[-3:]), np.mean(values[-6:]), np.median(values[-12:]),
             np.std(values[-12:]), last - values[-4], target['tenor'], target.get('offering', 0), target.get('reopening', 0)]
        naive = float(np.mean(values[-6:]))
        rules = float(np.median(values[-6:]) + np.clip(.15 * (np.mean(values[-3:]) - np.mean(values[-6:])), -.15, .15))
    else:
        x = [last, (last - values[-6]) * 100, (last - values[-21]) * 100,
             (last - values[-61]) * 100, np.std(np.diff(values[-61:])) * 100,
             (last - np.mean(values[-61:])) * 100, target['tenor'], 0, 0]
        naive = 0.0
        rules = float(-.2 * (last - values[-21]) * 100)
    return x, naive, rules


def causal_example(rows, index, horizon):
    origin = rows[index]['available']
    return (max(r['available'] for r in rows[:index + 1]) <= origin
            and rows[index + horizon]['available'] > origin)


def prepare(task, corpus):
    docs = {}
    for path in sorted(corpus.glob('*.json')):
        doc = json.loads(path.read_text())
        if doc['doc_id'] in docs:
            raise ValueError('Duplicate document ID')
        docs[doc['doc_id']] = doc
    auction = task['family'] == 'auction_btc'
    horizon = 1 if auction else 20
    examples, current, citations = [], [], {}
    excluded = 0
    for entity in task['entities']:
        eid = entity['entity_id']
        matching = [doc for doc in docs.values() if doc.get('entity_ids') == [eid]]
        if len(matching) != 1:
            raise ValueError('Ambiguous or missing entity history')
        doc = matching[0]
        rows = parse_document(doc, task['cutoff_date'])
        minimum, step = (12, 1) if auction else (60, 5)
        for i in range(minimum, len(rows) - horizon, step):
            if not causal_example(rows, i, horizon):
                excluded += 1
                continue
            future = rows[i + horizon]
            origin = rows[i]['available']
            # For auctions, covariates of a historical next auction are used only if announced.
            target = future if auction else entity
            if auction:
                # Corpus intentionally lacks historical announcement timestamps: omit offering
                # and reopening from ALL fitted examples and predictions to avoid a guessed date.
                target = dict(tenor=entity['tenor'], offering=0, reopening=0)
            x, naive, rules = features(rows, i, target, auction)
            y = future['value'] if auction else (future['value'] - rows[i]['value']) * 100
            examples.append(dict(x=x, y=y, naive=naive, rules=rules, eid=eid, origin=origin, available=future['available']))
        target = dict(entity, offering=0, reopening=0) if auction else entity
        x, naive, rules = features(rows, len(rows) - 1, target, auction)
        current.append(dict(x=x, naive=naive, rules=rules, eid=eid))
        quote = doc['text'].splitlines()[-1]
        citations[eid] = accept_locator_response(dict(doc_id=doc['doc_id'], quote=quote), docs, task['cutoff_date'])
    examples.sort(key=lambda row: (row['origin'], row['eid']))
    dates = sorted({row['origin'] for row in examples})
    boundary = dates[int(len(dates) * .7)]
    train = [row for row in examples if row['available'] < boundary]
    calibration = [row for row in examples if row['origin'] >= boundary]
    if len(train) < 20 or len(calibration) < 10:
        raise ValueError('Insufficient past-only training/calibration history')
    assert max(row['available'] for row in train) < min(row['origin'] for row in calibration)
    assert max(row['available'] for row in examples) <= task['cutoff_date']
    return train, calibration, current, citations, excluded


def predict_all(task_path, corpus, legacy_out):
    task = json.loads(task_path.read_text())
    train, calibration, current, citations, excluded = prepare(task, corpus)
    x = np.array([row['x'] for row in train])
    y = np.array([row['y'] for row in train])
    xc = np.array([row['x'] for row in calibration])
    xt = np.array([row['x'] for row in current])
    fitted = {
        'ridge': make_pipeline(StandardScaler(), Ridge(alpha=30.0)),
        'trees': HistGradientBoostingRegressor(loss='absolute_error', max_iter=60, max_leaf_nodes=7,
                                             min_samples_leaf=15, l2_regularization=20., max_bins=64,
                                             early_stopping=False, random_state=20261006),
    }
    pc = {m: np.array([r[m] for r in calibration]) for m in ['naive', 'rules']}
    pt = {m: np.array([r[m] for r in current]) for m in ['naive', 'rules']}
    for name, model in fitted.items():
        model.fit(x, y)
        pc[name], pt[name] = model.predict(xc), model.predict(xt)
    pc['ensemble'] = (pc['naive'] + pc['ridge'] + pc['trees']) / 3
    pt['ensemble'] = (pt['naive'] + pt['ridge'] + pt['trees']) / 3
    yc = np.array([r['y'] for r in calibration])
    answers = {}
    audit = dict(task_id=task['task_id'], train_examples=len(train), calibration_examples=len(calibration),
                 train_latest_label=max(r['available'] for r in train),
                 calibration_first_origin=min(r['origin'] for r in calibration),
                 latest_used_label=max(r['available'] for r in calibration),
                 cutoff=task['cutoff_date'], neural_calls=0, feature_count=int(x.shape[1]),
                 excluded_noncausal_historical_examples=excluded)
    for method in ['naive', 'rules', 'ridge', 'trees', 'ensemble']:
        predictions = []
        for index, entity in enumerate(task['entities']):
            eid = entity['entity_id']
            mask = np.array([r['eid'] == eid for r in calibration])
            residuals = np.abs(yc[mask] - pc[method][mask])
            # Finite-sample order statistic; serial dependence prevents an IID coverage claim.
            level = min(1., math.ceil((len(residuals) + 1) * .9) / len(residuals))
            width = max(float(np.quantile(residuals, level, method='higher')), .0001)
            point = float(pt[method][index])
            predictions.append(dict(entity_id=eid, label='up' if point > 0 else 'non-up', point_forecast=point,
                                    interval=dict(level=.9, lo=point - width, hi=point + width), claims=[citations[eid]]))
        answers[method] = dict(task_id=task['task_id'], schema_version='3', target_type=task['target']['type'],
                               entity_predictions=predictions,
                               evidence_trace='Exact historical quotes; numerical forecasts computed separately. Method=' + method + '; neural_calls=0.')
    from baseline_agent.cli import run
    legacy = run(task_path, corpus, legacy_out)
    # Retain legacy numerical forecast, label and interval; share verified citations so this
    # comparison measures forecasting rather than claiming a fake NLI score for the old prose.
    for pred in legacy['entity_predictions']:
        pred['claims'] = [citations[pred['entity_id']]]
    legacy['evidence_trace'] = 'Legacy V1 forecasts with shared exact-citation wrapper; not native V1 end-to-end score.'
    answers['legacy_v1'] = legacy
    return answers, audit
