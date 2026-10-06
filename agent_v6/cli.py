import argparse
import json
from pathlib import Path
from .pipeline import predict_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--method', default='all', choices=['all', 'naive', 'rules', 'ridge', 'trees', 'ensemble', 'legacy_v1'])
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    answers, audit = predict_all(args.task, args.corpus, args.out / 'legacy-native.json')
    for name, answer in answers.items():
        if args.method in ('all', name):
            (args.out / (name + '.json')).write_text(json.dumps(answer, indent=2, allow_nan=False) + '\n')
    (args.out / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')


if __name__ == '__main__':
    main()
