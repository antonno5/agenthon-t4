"""Pack the authorized V11 image with both numerical model declarations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
import qfbench2_common
from qfbench2_common.team_claim import pack_submission


def main():
    p=argparse.ArgumentParser();p.add_argument('--credentials',type=Path,required=True)
    p.add_argument('--digest',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--eps-model',type=Path,required=True);p.add_argument('--cpi-model',type=Path,required=True);a=p.parse_args()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',a.digest):raise ValueError('Invalid digest')
    fields={}
    for line in a.credentials.read_text().splitlines():
        m=re.match(r'^[-*\s]*([^:`]{1,70}):\s*(.*)$',line)
        if m:fields[m[1].strip().strip('*')]=m[2].strip().strip('`').strip()
    descriptor=json.loads((Path(qfbench2_common.__file__).parent/'contracts/fixtures/c5/analysis_dev.json').read_text())
    descriptor.pop('team_id',None)
    models=[dict(name='Agenthon compact EPS Huber regression',version='v8-compact',training_cutoff='2021-12',access='local',revision='sha256:'+hashlib.sha256(a.eps_model.read_bytes()).hexdigest()),
            dict(name='Agenthon CPI component regression and boosting ensemble',version='v11-frozen-guard',training_cutoff='2017-01',access='local',revision='sha256:'+hashlib.sha256(a.cpi_model.read_bytes()).hexdigest())]
    descriptor.update(category='api',models=models,license='MIT',image_access='public',
                      image=dict(registry='ghcr.io',repository='antonno5/agenthon-t4',digest=a.digest))
    team_id=pack_submission(descriptor,int(fields['Team Number']),fields['Team Key'],a.out)
    with zipfile.ZipFile(a.out) as z:
        assert set(z.namelist())=={'submission.json','team-claim.json'}
        assert all(fields['Team Key'].encode() not in z.read(n) for n in z.namelist())
        sealed=json.loads(z.read('submission.json'))
        assert sealed['phase']=='dev' and sealed['track']=='analysis' and sealed['models']==models
    print(json.dumps(dict(zip=str(a.out),zip_sha256=hashlib.sha256(a.out.read_bytes()).hexdigest(),
                          team_id=team_id,image_digest=a.digest,secret_absent=True,model_count=2)))


if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps(dict(error=type(e).__name__)));raise SystemExit(1) from None
