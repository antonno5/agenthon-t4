"""Build, validate, publish, and anonymously verify the authorized V17 image."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import traceback

ROOT=Path.cwd();OUT=ROOT/'test-output/ci-v17';OUT.mkdir(parents=True,exist_ok=True)
RECEIPT=ROOT/'research/v17-release/publication.json'
source=os.environ['GITHUB_SHA'];repository=os.environ['GITHUB_REPOSITORY'];run_id=os.environ['GITHUB_RUN_ID']
receipt=dict(source_commit=source,build_url=f'https://github.com/{repository}/actions/runs/{run_id}',status='started')


def call(args):
    print('RUN '+' '.join(map(str,args)),flush=True)
    result=subprocess.run(list(map(str,args)),capture_output=True,text=True)
    if result.stdout:print(result.stdout[-8000:],flush=True)
    if result.returncode:raise RuntimeError('Command failed: '+' '.join(map(str,args))+'\n'+result.stderr[-5000:])
    return result.stdout


def verify(image,folder):
    call(['python','scripts/check_public_v17.py','--image',image,'--units-dir','test-output/ci-official/units','--output-root',folder])
    expected=json.loads((ROOT/'research/v17-release/expected-answers.json').read_text())
    actual={p.parent.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*/answer.json')}
    assert actual==expected,'Published answers differ from locally validated answers'
    return len(actual)


def main():
    image=f'ghcr.io/antonno5/agenthon-t4:v17-{source[:12]}'
    receipt['stage']='source-verification'
    expected=json.loads((ROOT/'research/v17-release/runtime-source.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==s for p,s in expected.items())
    official=ROOT/'test-output/ci-official';official.mkdir(parents=True,exist_ok=True)
    call(['git','init',str(official)])
    call(['git','-C',str(official),'remote','add','origin','https://github.com/Agenthon-2026/track4-analysis-public.git'])
    call(['git','-C',str(official),'fetch','--depth=1','origin','458bc07efc05983de342ccb371e2b3cd793d621f'])
    call(['git','-C',str(official),'checkout','--detach','FETCH_HEAD'])
    receipt['stage']='build'
    call(['docker','build','--platform=linux/amd64','--label','org.opencontainers.image.revision='+source,'-f','Dockerfile.v17','-t',image,'.'])
    info=json.loads(call(['docker','image','inspect',image]))[0]
    assert info['Architecture']=='amd64' and info['Os']=='linux'
    assert info['Config']['Labels']['qfbench2.interface_version']=='2.0'
    receipt['stage']='local-image-verification';verify(image,OUT/'public-built')
    receipt['stage']='publish'
    pushed=call(['docker','push',image]);matches=re.findall(r'digest:\s*(sha256:[0-9a-f]{64})',pushed)
    assert len(set(matches))==1 and matches
    digest=matches[-1];pinned='ghcr.io/antonno5/agenthon-t4@'+digest
    receipt.update(image=pinned,digest=digest,tag=image,image_id=info['Id'],platform='linux/amd64',interface='2.0')
    receipt['stage']='anonymous-pull'
    with tempfile.TemporaryDirectory(prefix='v17-anonymous-') as config:
        call(['docker','--config',config,'pull',pinned])
    receipt['anonymous_pull']=True
    receipt['stage']='published-image-verification';count=verify(pinned,OUT/'public-published')
    for name in ['eps_models.json']:
        actual=call(['docker','run','--rm','--network=none','--entrypoint','python',pinned,'-c',
                     'import hashlib;from pathlib import Path;print(hashlib.sha256(Path("/app/agent_submit_v17/'+name+'").read_bytes()).hexdigest())']).strip()
        assert actual==hashlib.sha256((ROOT/'agent_submit_v17'/name).read_bytes()).hexdigest()
    receipt.update(status='verified',stage='complete',public_task_answer_parity=count,
                   new_eps_models_sha256=hashlib.sha256((ROOT/'agent_submit_v17/eps_models.json').read_bytes()).hexdigest(),
                   cpi_model_sha256=hashlib.sha256((ROOT/'agent_submit_v11/cpi_model.json').read_bytes()).hexdigest(),
                   eps_model_sha256=hashlib.sha256((ROOT/'agent_submit_v8/compact_model.json').read_bytes()).hexdigest())


if __name__=='__main__':
    try:main()
    except Exception as e:
        receipt.update(status='failed',error=type(e).__name__+': '+str(e));traceback.print_exc()
    finally:
        RECEIPT.parent.mkdir(parents=True,exist_ok=True);RECEIPT.write_text(json.dumps(receipt,indent=2)+'\n')
    raise SystemExit(0 if receipt['status']=='verified' else 1)
