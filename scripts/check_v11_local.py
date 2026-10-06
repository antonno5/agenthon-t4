"""Check public schemas, exact quotes, unchanged V8 routes and official smoke."""
from __future__ import annotations
import argparse
import contextlib
from importlib import resources
import io
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import jsonschema
from agent_submit_v11.cli import run
from agent_submit_v8.cli import run as old_run
from scripts.check_public import check_answer
from qfbench2_common.smoke import run_smoke
from qfbench2_track_analysis.scoring import build_smoke_verifier


def main():
    p=argparse.ArgumentParser();p.add_argument('--units',type=Path,default=Path('test-output/v10/official-track4/units'))
    p.add_argument('--out',type=Path,default=Path('test-output/submission-v11'));a=p.parse_args()
    schema=json.loads(resources.files('qfbench2_common').joinpath('schemas/analysis.schema.json').read_text())
    records=[]
    for unit in sorted(a.units.glob('t4-*')):
        if not (unit/'task.json').exists():continue
        output=a.out/'public-local'/unit.name;output.mkdir(parents=True,exist_ok=True)
        with contextlib.redirect_stdout(io.StringIO()):
            old=old_run(unit/'task.json',unit/'corpus',output/'v8.json')
            new=run(unit/'task.json',unit/'corpus',output/'answer.json')
        jsonschema.validate(new,schema);check_answer(unit,output/'answer.json')
        changed=new!=old
        if unit.name.startswith('t4-cpicomp'):assert changed
        else:assert (output/'v8.json').read_bytes()==(output/'answer.json').read_bytes()
        docs={json.loads(f.read_text())['doc_id']:json.loads(f.read_text()) for f in (unit/'corpus').glob('*.json') if f.name!='manifest.json'}
        for row in new['entity_predictions']:
            for claim in row['claims']:
                text=docs[claim['doc_id']]['text'];assert text[claim['span_start']:claim['span_end']]==claim['claim']
        smoke=a.out/'official-smoke'/unit.name;smoke.mkdir(parents=True,exist_ok=True);shutil.copyfile(output/'answer.json',smoke/'answer.json')
        with contextlib.redirect_stdout(io.StringIO()):verdict=run_smoke(unit,smoke,build_smoke_verifier)
        records.append(dict(unit=unit.name,schema=True,structure=True,exact_claims=True,changed=changed,smoke_admissible=verdict.admissible))
        print(json.dumps(records[-1]),flush=True)
    assert len(records)==11 and all(r['smoke_admissible'] for r in records)
    report=dict(passed=11,changed=[r['unit'] for r in records if r['changed']],rankable=False,records=records)
    (a.out/'public-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=11,rankable=False,changed=report['changed'])))


if __name__=='__main__':main()
