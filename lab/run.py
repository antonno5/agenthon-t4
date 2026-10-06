"""Host runner: one task per isolated container; evaluator alone receives truth."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--split', choices=['dev', 'holdout'], required=True)
    parser.add_argument('--image', default='agenthon-t4:algorithmic-lab-v2')
    args = parser.parse_args()
    root = args.root.resolve()
    reports = root / 'reports'
    reports.mkdir(exist_ok=True)
    if (reports / (args.split + '.json')).exists():
        raise SystemExit('This phase is already evaluated; refusing another look.')
    if args.split == 'holdout' and not (reports / 'selection.json').exists():
        raise SystemExit('Development selection must be frozen before holdout.')
    image_id = run(['sudo', '-n', 'docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], capture_output=True).stdout.strip()
    official = root / 'official-track4'
    commit = run(['git', '-C', str(official), 'rev-parse', 'HEAD'], capture_output=True).stdout.strip()
    runtime = dict(image_id=image_id, official_commit=commit,
                   dataset_sha256=hashlib.sha256((root / 'dataset.json').read_bytes()).hexdigest())
    plan = json.loads((root / 'preregister.json').read_text())
    assert commit == plan['scorer_commit']
    runtime_path = root / 'runtime.json'
    if runtime_path.exists():
        assert json.loads(runtime_path.read_text()) == runtime, 'Runtime changed after freeze'
    else:
        runtime_path.write_text(json.dumps(runtime, indent=2) + '\n')
    common = ['sudo', '-n', 'docker', 'run', '--rm', '--network=none', '--read-only',
              '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=128',
              '--memory=2g', '--cpus=2', '--user', f'{os.getuid()}:{os.getgid()}', '--tmpfs', '/tmp:rw,size=64m']
    cases = [c for c in json.loads((root / 'dataset.json').read_text())['cases'] if c['split'] == args.split]
    for i, case in enumerate(cases):
        directory = root / 'inputs' / args.split / case['case']
        for name in ['task', 'manifest']:
            assert hashlib.sha256((directory / (name + '.json')).read_bytes()).hexdigest() == case[name + '_sha256']
        for entry in json.loads((directory / 'manifest.json').read_text()):
            assert hashlib.sha256((directory / entry['path']).read_bytes()).hexdigest() == entry['sha256']
        output = root / 'answers' / args.split / case['case']
        output.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        # Only THIS task is mounted: neither truth nor other cases (with later histories) exist here.
        run(common + ['-v', f'{directory}:/input:ro', '-v', f'{output}:/output:rw', image_id,
                      '-m', 'agent_v6.cli', '--task', '/input/task.json', '--corpus', '/input/corpus', '--out', '/output'],
            capture_output=True, timeout=180)
        elapsed = time.monotonic() - start
        (output / 'resources.json').write_text(json.dumps(dict(wall_seconds=elapsed, network='none', cpu_limit=2, memory_limit_gib=2)) + '\n')
        print(f'{args.split} {i + 1}/{len(cases)} {case["case"]} {elapsed:.2f}s', flush=True)
    run(common + ['-v', f'{root}:/experiment:ro', '-v', f'{reports}:/reports:rw',
                  '-v', f'{official}:/official:ro', image_id, '-m', 'lab.score', '--root', '/experiment',
                  '--reports', '/reports', '--split', args.split])


if __name__ == '__main__':
    main()
