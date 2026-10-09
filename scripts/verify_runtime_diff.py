"""Compare the frozen V11 and V17 images under documented runtime restrictions."""
import contextlib
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_public_v17 import check_answer
from qfbench2_common.contracts.artifact_tree import TreeLimits, validate_listing
from qfbench2_common.sanitize import walk_nofollow
from qfbench2_common.smoke import run_smoke
from qfbench2_track_analysis.scoring import build_smoke_verifier

IMAGES = {
    'v11': 'ghcr.io/antonno5/agenthon-t4@sha256:b6a841f95515f217e6b9fff421191f95e228d8e1d5e1594b9c6da1c3c226c22a',
    'v17': 'ghcr.io/antonno5/agenthon-t4@sha256:4d9d679c3eb8ec551e49058da3ac8383a73207a76ab62a449b6a469a8b01a24b',
}
FLAGS = [
    '--rm', '--platform=linux/amd64', '--network=none', '--read-only',
    '--user', '65534:65534', '--cap-drop=ALL', '--security-opt', 'no-new-privileges',
    '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=64m', '--pids-limit', '256',
    '--ulimit', 'nofile=1024:1024', '--ulimit', 'nproc=256:256',
    '--ulimit', 'fsize=67108864:67108864', '--cpus=2', '--memory=2g', '--memory-swap=2g',
    '-e', 'QFBENCH_SEED=0', '-e', 'QFBENCH_NETWORK=none',
]
PROBE = '''import json,os,resource
from pathlib import Path
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
tmp=[line.split()[3] for line in Path('/proc/mounts').read_text().splitlines() if line.split()[1]=='/tmp'][0]
print(json.dumps(dict(uid=os.getuid(),gid=os.getgid(),cap_eff=status['CapEff'].strip(),no_new_privs=status['NoNewPrivs'].strip(),tmp_options=tmp,nofile=resource.getrlimit(resource.RLIMIT_NOFILE),nproc=resource.getrlimit(resource.RLIMIT_NPROC),fsize=resource.getrlimit(resource.RLIMIT_FSIZE))))
'''


def main():
    destination = ROOT / 'research/v17-release/runtime-diff-validation.json'
    units = ROOT / 'test-output/runtime-official/units'
    report = dict(status='started', images=IMAGES, docker_flags=FLAGS, records=[],
                  toolkit=importlib.metadata.version('qfbench2-common'),
                  scorer=importlib.metadata.version('qfbench2-track-analysis'),
                  official_commit='458bc07efc05983de342ccb371e2b3cd793d621f',
                  build_url=f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
                  limitations=['CPU/memory reduced to 2 CPUs/2 GiB on CI; no GPU or House endpoint.',
                               'Public smoke is non-rankable; private organizer ingestion/scoring is not reproduced.'])
    try:
        for version, image in IMAGES.items():
            with tempfile.TemporaryDirectory(prefix='anonymous-') as config:
                subprocess.run(['docker', '--config', config, 'pull', '--platform=linux/amd64', image], check=True)
            probe = json.loads(subprocess.check_output(['docker', 'run', *FLAGS, '--entrypoint', 'python', image, '-c', PROBE], text=True))
            assert probe['uid'] == probe['gid'] == 65534
            assert int(probe['cap_eff'], 16) == 0 and probe['no_new_privs'] == '1'
            assert {'noexec', 'nosuid', 'nodev'} <= set(probe['tmp_options'].split(','))
            assert probe['nofile'] == [1024, 1024] and probe['nproc'] == [256, 256]
            report[version + '_runtime_probe'] = probe
            expected = json.loads((ROOT / f'research/{version}-release/expected-answers.json').read_text())
            for unit in sorted(units.glob('t4-*')):
                if not (unit / 'task.json').exists():
                    continue
                out = ROOT / 'test-output/runtime-diff' / version / unit.name
                out.mkdir(parents=True, exist_ok=False)
                out.chmod(0o777)
                started = time.monotonic()
                result = subprocess.run(['docker', 'run', *FLAGS, '-v', f'{unit}:/input:ro',
                    '-v', f'{out}:/output', image, 'analyze', '--task', '/input/task.json',
                    '--corpus', '/input/corpus', '--out', '/output/answer.json'],
                    capture_output=True, text=True, timeout=120)
                row = dict(version=version, unit=unit.name, returncode=result.returncode,
                           seconds=round(time.monotonic()-started, 3), stderr=result.stderr[-4000:])
                report['records'].append(row)
                if result.returncode:
                    print(json.dumps(row), flush=True)
                    continue
                bounds = TreeLimits(max_total_bytes=64*1024*1024)
                walk = walk_nofollow(out, limits=bounds)
                listing = validate_listing(walk.observations, bounds)
                row.update(output_tree_ok=walk.clean and listing.ok,
                           output_bytes=sum(n.size_bytes for n in walk.observations),
                           files=list(listing.accepted))
                check_answer(unit, out / 'answer.json')
                row['answer_sha256'] = hashlib.sha256((out / 'answer.json').read_bytes()).hexdigest()
                row['answer_parity'] = row['answer_sha256'] == expected[unit.name]
                with contextlib.redirect_stdout(io.StringIO()):
                    verdict = run_smoke(unit, out, build_smoke_verifier)
                row['smoke_admissible'] = verdict.admissible
                print(json.dumps(row), flush=True)
        rows = report['records']
        assert len(rows) == 22
        passed = sum(r['returncode'] == 0 and r.get('output_tree_ok') and r.get('answer_parity')
                     and r.get('smoke_admissible') for r in rows)
        report['passed'] = passed
        assert passed == 22, 'Inspect recorded V11/V17 runtime differences'
        report['status'] = 'verified'
    except Exception as error:
        report.update(status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        destination.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
