"""Wait for an existing submission; this watcher never creates or reruns one."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import time

p=argparse.ArgumentParser();p.add_argument('--id',type=int,required=True);p.add_argument('--cookies',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--previous-report',type=Path);p.add_argument('--seconds',type=int,default=21600);p.add_argument('--interval',type=int,default=45);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=True)
cmd=['python3','scripts/fetch_codabench_result.py','--id',str(a.id),'--cookies',str(a.cookies),'--out',str(a.out)]
if a.previous_report:cmd+=['--previous-report',str(a.previous_report)]
start=time.monotonic();state=dict(submission_id=a.id,pid=os.getpid(),started_at=dt.datetime.now(dt.timezone.utc).isoformat(),state='waiting')
last=None
while time.monotonic()-start<a.seconds:
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
        latest=json.loads((a.out/'latest-status.json').read_text())
        status=latest['status'];state.update(last_checked=dt.datetime.now(dt.timezone.utc).isoformat(),status=status,last_fetch_returncode=r.returncode)
        if status!=last:print(state['last_checked'],status,flush=True);last=status
        if status in ['Finished','Failed','Cancelled'] and r.returncode==0:
            state['state']='complete';print(r.stdout,flush=True)
            summary=json.loads((a.out/'result-summary.json').read_text())
            (a.out/'RESULT.md').write_text(f"# CodaBench submission {a.id}\n\nStatus: **{status}**\n\n```json\n"+json.dumps(summary,indent=2)+'\n```\n')
            (a.out/'watch-state.json').write_text(json.dumps(state,indent=2)+'\n');break
    except Exception as e:state.update(last_checked=dt.datetime.now(dt.timezone.utc).isoformat(),last_error=type(e).__name__)
    (a.out/'watch-state.json').write_text(json.dumps(state,indent=2)+'\n');time.sleep(a.interval)
else:
    state['state']='timeout';(a.out/'watch-state.json').write_text(json.dumps(state,indent=2)+'\n');print('Watcher timeout; submission not altered',flush=True)
