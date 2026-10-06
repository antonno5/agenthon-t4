"""Publish verification and one explicitly authorized V8 Development submission."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

root=Path.cwd();out=root/'test-output/submission-v8';out.mkdir(parents=True,exist_ok=True)
run_id='37456110767';expected='b53a9e66dfe994c21c9acdb611d37f7179016467'
def capture(cmd):return subprocess.check_output(cmd,text=True)
run=json.loads(capture(['gh','run','view',run_id,'--json','status,conclusion,headSha,url']))
assert run['status']=='completed' and run['conclusion']=='success' and run['headSha']==expected
log=capture(['gh','run','view',run_id,'--log'])
matches=re.findall(r'Image digest=(sha256:[0-9a-f]{64})',log)
assert matches and len(set(matches))==1
digest=matches[0];image='ghcr.io/antonno5/agenthon-t4@'+digest
with tempfile.TemporaryDirectory(prefix='v8-anonymous-docker-') as config:
    subprocess.run(['sudo','-n','docker','--config',config,'pull',image],check=True)
info=json.loads(capture(['sudo','-n','docker','image','inspect',image]))[0]
assert info['Architecture']=='amd64' and info['Os']=='linux'
assert info['Config']['Labels']['qfbench2.interface_version']=='2.0'
model_sha=hashlib.sha256((root/'agent_submit_v8/compact_model.json').read_bytes()).hexdigest()
actual=capture(['sudo','-n','docker','run','--rm','--network=none','--entrypoint','python',image,'-c',
                'import hashlib;from pathlib import Path;print(hashlib.sha256(Path("/app/agent_submit_v8/compact_model.json").read_bytes()).hexdigest())']).strip()
assert actual==model_sha
subprocess.run(['python3','scripts/check_public.py','--docker','sudo -n docker','--image',image,
    '--units-dir','test-output/independent-demo/official-track4/units','--output-root',str(out/'public-published')],check=True)
for path in (out/'public-local').glob('*/answer.json'):
    assert path.read_bytes()==(out/'public-published'/path.parent.name/'answer.json').read_bytes()
publication=dict(source_commit=expected,build_url=run['url'],image=image,digest=digest,image_id=info['Id'],
    platform='linux/amd64',interface='2.0',anonymous_pull=True,public_task_answer_parity=11,model_sha256=model_sha)
(out/'publication.json').write_text(json.dumps(publication,indent=2)+'\n')
zipname='submission-v8-b53a9e6.zip'
pack=['sudo','-n','docker','run','--rm','--network=none','--read-only','--user','1000:1000','--tmpfs','/tmp:rw,size=16m',
    '-v',f'{root}/scripts:/scripts:ro','-v','/home/antonnos/t3-handoff-template.md:/credentials:ro',
    '-v',f'{root}/agent_submit_v8/compact_model.json:/model.json:ro','-v',f'{out}:/output',
    'agenthon-t4:algorithmic-lab-v2','/scripts/pack_submission_v8.py','--credentials','/credentials',
    '--digest',digest,'--model','/model.json','--out','/output/'+zipname]
packed=capture(pack);validation=json.loads(packed.strip().splitlines()[-1]);assert validation['secret_absent']
(out/'pack-validation.json').write_text(json.dumps(validation,indent=2)+'\n')
print(json.dumps(publication),flush=True)
subprocess.run(['python3','scripts/codabench_v6.py','upload','--cookies','/home/antonnos/.local/state/agenthon/codabench.cookies',
    '--zip',str(out/zipname),'--receipt',str(out/'submission-receipt.json')],check=True)
