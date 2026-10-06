"""Use the official toolkit with an authorized credential file; never print secrets."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

import qfbench2_common
from qfbench2_common.team_claim import pack_submission


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--digest', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.digest):
        raise ValueError('Invalid image digest')
    fields = {}
    for line in args.credentials.read_text().splitlines():
        match = re.match(r'^[-*\s]*([^:`]{1,70}):\s*(.*)$', line)
        if match:
            fields[match[1].strip().strip('*')] = match[2].strip().strip('`').strip()
    team_number = int(fields['Team Number'])
    team_key = fields['Team Key']
    fixture = Path(qfbench2_common.__file__).parent / 'contracts/fixtures/c5/analysis_dev.json'
    descriptor = json.loads(fixture.read_text())
    # The fixture's example team is not this team; let the official packer derive it.
    descriptor.pop('team_id', None)
    model_sha = hashlib.sha256(args.model.read_bytes()).hexdigest()
    models = [dict(name='Agenthon compact EPS Huber regression', version='v8-compact',
                   training_cutoff='2021-12', access='local', revision='sha256:' + model_sha)]
    descriptor.update(category='api', models=models, license='MIT', image_access='public',
                      image=dict(registry='ghcr.io', repository='antonno5/agenthon-t4', digest=args.digest))
    team_id = pack_submission(descriptor, team_number, team_key, args.out)
    with zipfile.ZipFile(args.out) as archive:
        assert set(archive.namelist()) == {'submission.json', 'team-claim.json'}
        for name in archive.namelist():
            assert team_key.encode() not in archive.read(name)
        sealed = json.loads(archive.read('submission.json'))
        assert sealed['phase'] == 'dev' and sealed['track'] == 'analysis'
        assert sealed['models'] == models and sealed['image']['digest'] == args.digest
    print(json.dumps(dict(zip=str(args.out), zip_sha256=hashlib.sha256(args.out.read_bytes()).hexdigest(),
                          team_id=team_id, image_digest=args.digest, secret_absent=True)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Packaging failed: ' + type(error).__name__)
        raise SystemExit(1) from None
