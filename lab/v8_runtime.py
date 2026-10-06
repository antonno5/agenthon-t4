"""End-to-end candidate replay using inputs only; no truth directory is mounted."""
from collections import defaultdict
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
from .v7_eps import read,write,sha,document

root=Path('test-output/v8-analyst-validated')
rows=read(root/'inputs/holdout.json')
predictions=read(root/'predictions/holdout-compact.json')
groups=defaultdict(list)
for r in rows:groups[r['block']].append(r)
image='agenthon-t4:v8-compact-research'
image_id=subprocess.check_output(['sudo','-n','docker','image','inspect','--format','{{.Id}}',image],text=True).strip()
max_error=0.;changed_labels=0;cases=0;records=0
for block,rs in sorted(groups.items()):
    for family in ['eps_direction','eps_growth']:
        selected=[r for r in rs if family!='eps_growth' or abs(r['prior'])>1e-12]
        case=family+'-'+block;directory=(root/'runtime-inputs'/case).resolve();output=(root/'runtime-answers'/case).resolve()
        output.mkdir(parents=True,exist_ok=True)
        target='eps_yoy_direction' if family=='eps_direction' else 'eps_yoy_growth_pct'
        kind='classification' if family=='eps_direction' else 'regression'
        task=dict(task_id=case,schema_version='3',cutoff_date=rs[0]['cutoff'],interval_level=.9,
                  target=dict(name=target,type=kind),entities=[],corpus_manifest='corpus/manifest.json')
        if kind=='classification':task['target']['labels']=['up','down']
        manifest=[]
        for i,r in enumerate(selected):
            # Use calendar-aligned display dates derived from input cutoff; numbers
            # remain the admitted input values. No target/audit files are read.
            boundary=dt.date.fromisoformat(r['cutoff'])-dt.timedelta(days=7)
            recent=boundary-dt.timedelta(days=90)
            compare=recent.replace(year=recent.year-1)
            a=dict(val=r['eps'][0],end=recent.isoformat(),filed=(recent+dt.timedelta(days=45)).isoformat())
            b=dict(val=r['eps'][4],end=compare.isoformat(),filed=a['filed'])
            doc=document(r['id'],a,b,i)
            p=directory/'corpus'/(doc['doc_id']+'.json');write(p,doc)
            manifest.append(dict(path='corpus/'+p.name,role='corpus',sha256=sha(p),entity_ids=[r['id']]))
            task['entities'].append(dict(entity_id=r['id'],name=r['id'],prior_year_q_eps=r['prior'],quarter_reported='three months ended '+boundary.isoformat()))
        write(directory/'task.json',task);write(directory/'corpus/manifest.json',dict(manifest_version='2.0',unit_id=case,files=manifest))
        subprocess.run(['sudo','-n','docker','run','--rm','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
                        '--pids-limit=128','--memory=2g','--cpus=2','--user',f'{os.getuid()}:{os.getgid()}',
                        '-v',f'{directory}:/input:ro','-v',f'{output}:/output',image_id,'analyze','--task','/input/task.json',
                        '--corpus','/input/corpus','--out','/output/answer.json'],check=True,capture_output=True,text=True,timeout=90)
        answer=read(output/'answer.json')
        assert [p['entity_id'] for p in answer['entity_predictions']]==[r['id'] for r in selected]
        for r,p in zip(selected,answer['entity_predictions']):
            estimate=predictions[r['id']]['compact_huber']
            expected=estimate if kind=='classification' else 100*(estimate-r['prior'])/abs(r['prior'])
            max_error=max(max_error,abs(p['point_forecast']-expected))
            if kind=='classification':changed_labels+=p['label']!=('up' if estimate>=r['prior'] else 'down')
            records+=1
        cases+=1
        if cases%10==0:print('runtime',cases,flush=True)
assert max_error<1e-8 and changed_labels==0,(max_error,changed_labels)
write(root/'reports/runtime-parity.json',dict(cases=cases,predictions=records,max_absolute_error=max_error,
                                            label_mismatches=changed_labels,image_id=image_id,
                                            truth_available_to_candidate=False,network='none'))
print('runtime parity',cases,records,max_error,flush=True)
