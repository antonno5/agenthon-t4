"""Finish audit and readable report without repeating a forecast or choosing a model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path('LAB_RESULTS.md'))
    args = parser.parse_args()
    root = args.root.resolve()
    reports = root / 'reports'
    runtime = json.loads((root / 'runtime.json').read_text())
    assert hashlib.sha256((root / 'dataset.json').read_bytes()).hexdigest() == runtime['dataset_sha256']
    assert (reports / 'holdout.json').exists()
    common = ['sudo', '-n', 'docker', 'run', '--rm', '--network=none', '--read-only', '--cpus=2', '--memory=2g',
              '--user', f'{os.getuid()}:{os.getgid()}', '-v', f'{reports}:/reports:rw']
    if not (reports / 'validation.json').exists():
        subprocess.run(common + ['-v', f'{root}:/experiment:ro', '-v', f'{root / "official-track4"}:/official:ro',
                                 runtime['image_id'], '-m', 'lab.audit', '--root', '/experiment', '--out', '/reports/validation.json'], check=True)
    if not (reports / 'exploratory.json').exists():
        script = Path(__file__).with_name('diagnostics.py').resolve()
        subprocess.run(common + ['-v', f'{script}:/diagnostics.py:ro', runtime['image_id'],
                                 '/diagnostics.py', '--reports', '/reports'], check=True)
    subprocess.run(['python3', '-m', 'lab.report', '--root', str(root), '--out', str(args.out)], check=True)


if __name__ == '__main__':
    main()
