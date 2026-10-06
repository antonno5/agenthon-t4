"""Non-rankable research evaluator importing, never reimplementing, official metrics."""
import argparse
import hashlib
from importlib import resources
import json
from pathlib import Path

import jsonschema
import numpy as np
from qfbench2_track_analysis.alignment import EntityRoster, align_predictions
from qfbench2_track_analysis.scoring import SCORER_VERSION, ScoringParams, _composite, evaluate_claims

from agent_v6.pipeline import METHODS


class VerbatimOnlyJudge:
    def contradiction(self, premise, hypothesis):
        raise RuntimeError('This demo has no NLI judge; only prevalidated exact quotes are allowed.')


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def score_answer(answer, task, truth, docs, naive, schema):
    jsonschema.validate(answer, schema)
    roster = EntityRoster.from_task(task)
    kind = task['target']['type']
    aligned = align_predictions(answer, roster, target_type=kind, interval_level=.9)
    reference = align_predictions(naive, roster, target_type=kind, interval_level=.9)
    for prediction in answer['entity_predictions']:
        if not prediction['claims']:
            raise ValueError('Missing evidence')
        for claim in prediction['claims']:
            doc = docs[claim['doc_id']]
            start, end = claim['span_start'], claim['span_end']
            if (doc['doc_date'] > task['cutoff_date'] or prediction['entity_id'] not in doc['entity_ids']
                    or not isinstance(start, int) or not isinstance(end, int)
                    or not 0 <= start < end <= len(doc['text'])
                    or claim['claim'] != doc['text'][start:end]):
                raise ValueError('Invalid exact evidence')
    params = ScoringParams(kind, .9, .8, .5, (.7, .3), interval_leg=kind != 'classification')
    parts = _composite(aligned, truth, params, roster, naive_aligned=reference)
    claims = evaluate_claims(aligned, lambda doc_id: docs[doc_id], VerbatimOnlyJudge(),
                             target_type=kind, interval_scored=kind != 'classification', contradiction_bar=.9,
                             entity_admits=lambda eid, cite: eid in docs[cite['doc_id']]['entity_ids'],
                             interval_level=.9, entity_names=tuple(e['name'] for e in task['entities']))
    penalty = claims.penalty_factor(1., entity_count=roster.count, judge_verdicts=True)
    return dict(**parts, citation_penalty_factor=penalty, score=parts['composite'] * penalty,
                claim_diagnostics=claims.diagnostics())


def aggregate(rows):
    result = {}
    families = sorted({r['family'] for r in rows})
    for method in METHODS:
        by_family = {f: float(np.mean([r['score'] for r in rows if r['method'] == method and r['family'] == f])) for f in families}
        result[method] = dict(mean=float(np.mean(list(by_family.values()))), families=by_family,
                              failures=sum(r.get('failure') is not None for r in rows if r['method'] == method))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--split', choices=['dev', 'holdout'], required=True)
    args = parser.parse_args()
    root, out = args.root, args.reports
    dataset = read(root / 'dataset.json')
    plan = read(root / 'preregister.json')
    assert SCORER_VERSION == '5.2.2'
    assert hashlib.sha256((root / 'preregister.json').read_bytes()).hexdigest() == dataset['preregister_sha256']
    schema = json.loads(resources.files('qfbench2_common').joinpath('schemas/analysis.schema.json').read_text())
    rows = []
    for case in dataset['cases']:
        if case['split'] != args.split:
            continue
        directory = root / 'inputs' / args.split / case['case']
        task = read(directory / 'task.json')
        truth = read(root / 'truth' / args.split / (case['case'] + '.json'))
        docs = {doc['doc_id']: doc for doc in map(read, (directory / 'corpus').glob('*.json'))}
        answers = root / 'answers' / args.split / case['case']
        naive = read(answers / 'naive.json')
        # Broken declared reference aborts evaluation rather than becoming a low denominator.
        score_answer(naive, task, truth, docs, naive, schema)
        for method in METHODS:
            row = dict(case=case['case'], family=case['family'], block=case['block'], method=method)
            try:
                row.update(score_answer(read(answers / (method + '.json')), task, truth, docs, naive, schema))
            except Exception as error:
                row.update(score=0., failure=type(error).__name__ + ': ' + str(error)[:300])
            rows.append(row)
    summary = aggregate(rows)
    report = dict(split=args.split, rankable=False, scorer_version=SCORER_VERSION,
                  judge_mode='exact_quotes_only; no production NLI or full official verifier',
                  metric='official composite times official exact-claim penalty', methods=summary, rows=rows)
    write(out / (args.split + '.json'), report)
    if args.split == 'dev':
        selection = out / 'selection.json'
        if selection.exists():
            raise SystemExit('Selection already frozen; refusing to overwrite.')
        eligible = [m for m in METHODS if m != 'legacy_v1']
        winner = max(eligible, key=lambda m: summary[m]['mean'])
        write(selection, dict(method=winner, development_score=summary[winner]['mean'],
                              rule=plan['selection'], dev_report_sha256=hashlib.sha256((out / 'dev.json').read_bytes()).hexdigest(),
                              runtime=read(root / 'runtime.json')))
        print('DEV_SELECTION', winner, summary[winner]['mean'])
    else:
        selected = read(out / 'selection.json')['method']
        blocks = sorted({r['block'] for r in rows})
        deltas = []
        for block in blocks:
            means = {m: np.mean([r['score'] for r in rows if r['block'] == block and r['method'] == m]) for m in [selected, 'naive']}
            deltas.append(means[selected] - means['naive'])
        rng = np.random.default_rng(plan['seed'])
        draws = rng.choice(deltas, size=(10000, len(deltas)), replace=True).mean(axis=1)
        ci = np.quantile(draws, [.025, .975]).tolist()
        value = summary[selected]['mean']
        threshold = plan['submission_threshold_raw_literal']
        gates = dict(literal_score_threshold=value > threshold,
                     paired_improvement_lower_bound=ci[0] > 0,
                     representative_task_coverage=False, certified_historical_vintages=False,
                     official_full_verifier=False)
        write(out / 'gate.json', dict(submit=all(gates.values()), selected_method=selected, selected_holdout_score=value,
                                      threshold=threshold, threshold_outside_metric_domain=threshold >= 1.,
                                      paired_delta_vs_naive=float(np.mean(deltas)), paired_95_percent_ci=ci,
                                      independent_time_blocks=len(blocks), gates=gates,
                                      limitations=plan['limitations'], no_submission_attempted=True))
        print('HOLDOUT', selected, value, 'PAIRED_CI', ci, 'SUBMIT', all(gates.values()))
    print(json.dumps({m: round(s['mean'], 6) for m, s in summary.items()}))


if __name__ == '__main__':
    main()
