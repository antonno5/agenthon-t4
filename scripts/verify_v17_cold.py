"""Verify the exact failed submission image on a fresh anonymous Docker host."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_public_v17 import check_answer
from qfbench2_common.smoke import run_smoke
from qfbench2_track_analysis.scoring import build_smoke_verifier


def run(args):
    return subprocess.check_output(args, text=True)


def main():
    publication = json.loads((ROOT / 'research/v17-release/publication.json').read_text())
    image = publication['image']
    assert image == 'ghcr.io/antonno5/agenthon-t4@sha256:4d9d679c3eb8ec551e49058da3ac8383a73207a76ab62a449b6a469a8b01a24b'
    receipt = dict(image=image, source_commit=publication['source_commit'],
                   check_commit=os.environ['GITHUB_SHA'],
                   build_url=f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
                   status='started', scored=False)
    destination = ROOT / 'research/v17-release/cold-validation.json'
    try:
        absent = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True)
        assert absent.returncode != 0, 'The submitted image must not already be cached'
        receipt['image_initially_absent'] = True
        with tempfile.TemporaryDirectory(prefix='v17-anonymous-') as config:
            assert not list(Path(config).iterdir())
            print(run(['docker', '--config', config, 'pull', '--platform=linux/amd64', image]), flush=True)
        receipt['anonymous_cold_pull'] = True
        info = json.loads(run(['docker', 'image', 'inspect', image]))[0]
        assert info['Architecture'] == 'amd64' and info['Os'] == 'linux'
        assert info['Config']['Labels']['qfbench2.interface_version'] == '2.0'
        assert not info['Config'].get('Volumes'), 'Declared Docker volumes are not supported'
        receipt.update(platform='linux/amd64', interface='2.0', declared_volumes=False,
                       image_id=info['Id'], image_size_bytes=info['Size'])
        units = ROOT / 'test-output/retry-official/units'
        output = ROOT / 'test-output/v17-cold'
        subprocess.run([sys.executable, 'scripts/check_public_v17.py', '--image', image,
                        '--units-dir', str(units), '--output-root', str(output)], check=True)
        expected = json.loads((ROOT / 'research/v17-release/expected-answers.json').read_text())
        actual = {p.parent.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in output.glob('*/answer.json')}
        assert actual == expected, 'Cold image answers differ from the submitted release'
        records = []
        for name in sorted(actual):
            unit, answer = units / name, output / name / 'answer.json'
            check_answer(unit, answer)
            with contextlib.redirect_stdout(io.StringIO()):
                verdict = run_smoke(unit, answer.parent, build_smoke_verifier)
            assert verdict.admissible, name
            records.append(dict(unit=name, output_sha256=actual[name], smoke_admissible=True))
            print('PASS official smoke ' + name, flush=True)
        assert len(records) == 11
        receipt.update(status='verified', answer_parity=11, smoke_admissible=11, records=records)
    except Exception as error:
        receipt.update(status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        destination.write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
