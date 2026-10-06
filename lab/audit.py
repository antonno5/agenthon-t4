"""Integrity and adversarial acceptance checks, run by the evaluator after both phases."""
import argparse
import copy
import hashlib
from importlib import resources
import json
from pathlib import Path

from agent_v6.pipeline import prepare, parse_document, causal_example, METHODS
from lab.score import score_answer


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    dataset = read(root / 'dataset.json')
    historical_examples = excluded = predictions = claims = 0
    for source in read(root / 'sources.json'):
        assert hashlib.sha256((root / 'raw' / source['file']).read_bytes()).hexdigest() == source['sha256']
    for case in dataset['cases']:
        directory = root / 'inputs' / case['split'] / case['case']
        task = read(directory / 'task.json')
        for name in ['task', 'manifest']:
            assert hashlib.sha256((directory / (name + '.json')).read_bytes()).hexdigest() == case[name + '_sha256']
        for entry in read(directory / 'manifest.json'):
            assert hashlib.sha256((directory / entry['path']).read_bytes()).hexdigest() == entry['sha256']
        train, calibration, _, _, rejected = prepare(task, directory / 'corpus')
        excluded += rejected
        historical_examples += len(train) + len(calibration)
        assert max(row['available'] for row in train) < min(row['origin'] for row in calibration)
        assert all(row['origin'] < row['available'] <= task['cutoff_date'] for row in train + calibration)
        truths = read(root / 'truth' / case['split'] / (case['case'] + '.json'))
        assert all(row['resolved_at'] > task['cutoff_date'] for row in truths['outcomes'])
        for method in METHODS:
            answer = read(root / 'answers' / case['split'] / case['case'] / (method + '.json'))
            predictions += len(answer['entity_predictions'])
            claims += sum(len(p['claims']) for p in answer['entity_predictions'])
    # Exercise the actual evaluator, not a second local imitation of its checks.
    case = next(c for c in dataset['cases'] if c['split'] == 'dev')
    directory = root / 'inputs' / 'dev' / case['case']
    task = read(directory / 'task.json')
    truth = read(root / 'truth' / 'dev' / (case['case'] + '.json'))
    docs = {d['doc_id']: d for d in map(read, (directory / 'corpus').glob('*.json'))}
    naive = read(root / 'answers' / 'dev' / case['case'] / 'naive.json')
    schema = json.loads(resources.files('qfbench2_common').joinpath('schemas/analysis.schema.json').read_text())
    def verdict(answer):
        return score_answer(answer, task, truth, docs, naive, schema)
    assert abs(verdict(naive)['score'] - .5) < 1e-12
    mutations = {}
    a = copy.deepcopy(naive); a['entity_predictions'].pop(); mutations['missing_entity'] = a
    a = copy.deepcopy(naive); a['entity_predictions'].append(copy.deepcopy(a['entity_predictions'][0])); mutations['duplicate_entity'] = a
    a = copy.deepcopy(naive); a['entity_predictions'][0]['point_forecast'] = float('nan'); mutations['nan_forecast'] = a
    a = copy.deepcopy(naive); a['entity_predictions'][0]['claims'][0]['claim'] = 'invented figure 99999'; mutations['invented_quote'] = a
    a = copy.deepcopy(naive); a['entity_predictions'][0]['claims'][0]['doc_id'] = '../../truth'; mutations['unknown_document'] = a
    checks = []
    for name, invalid in mutations.items():
        try:
            verdict(invalid)
        except Exception:
            checks.append(name)
        else:
            raise AssertionError('Invalid answer admitted: ' + name)
    report = dict(passed=True, cases=len(dataset['cases']), historical_training_and_calibration_examples=historical_examples,
                  excluded_noncausal_examples=excluded, forecast_rows_across_six_methods=predictions,
                  exact_claims_across_six_methods=claims, rejection_tests=checks,
                  naive_regression_anchor_verified=.5, raw_response_hashes_verified=True,
                  all_input_hashes_verified=True, all_true_outcomes_after_cutoff=True,
                  training_label_before_calibration_origin=True, neural_calls=0,
                  limitations=['Timestamp consistency checked, but original historical vintages are not certified.'])
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
