"""Exploratory comparisons only; never edits the frozen selector or submission gate."""
import argparse
import json
from pathlib import Path
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads((args.reports / 'holdout.json').read_text())['rows']
    blocks = sorted({row['block'] for row in rows})
    result = dict(exploratory=True, adjusts_for_multiple_comparisons=False, bootstrap_seed=20261006,
                  bootstrap_draws=10000, time_blocks=len(blocks), comparisons={})
    for method in ['legacy_v1', 'rules', 'ridge', 'trees', 'ensemble']:
        differences = []
        for block in blocks:
            means = {m: np.mean([r['score'] for r in rows if r['block'] == block and r['method'] == m]) for m in [method, 'naive']}
            differences.append(means[method] - means['naive'])
        rng = np.random.default_rng(result['bootstrap_seed'])
        samples = rng.choice(differences, size=(result['bootstrap_draws'], len(blocks)), replace=True).mean(axis=1)
        result['comparisons'][method] = dict(delta_vs_naive=float(np.mean(differences)),
                                             paired_95_percent_ci=np.quantile(samples, [.025, .975]).tolist())
    (args.reports / 'exploratory.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
