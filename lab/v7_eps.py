"""Causal SEC EPS mini-benchmark, with truth isolated from candidate containers."""
from __future__ import annotations

import argparse
import calendar
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time


def read(p):
    return json.loads(p.read_text())


def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, allow_nan=False)+'\n')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def validate_truth(task, truth):
    roster = [e['entity_id'] for e in task['entities']]
    rows = truth.get('outcomes', [])
    if [r.get('entity_id') for r in rows] != roster:
        raise ValueError('Truth must cover the exact ordered roster')
    for row in rows:
        if not isinstance(row.get('y'), (int, float)) or isinstance(row['y'], bool) or not math.isfinite(row['y']):
            raise ValueError('Missing or invalid numeric target')
        if task['target']['type'] == 'classification' and row.get('true_label') not in task['target']['labels']:
            raise ValueError('Official true_label is missing or outside the target labels')


def quarter(end):
    # Keeps 52/53-week quarters ending just after a calendar month boundary together.
    d = dt.date.fromisoformat(end)-dt.timedelta(days=15)
    return d.year*4 + (d.month-1)//3


def facts_by_quarter(data):
    rows = data.get('facts',{}).get('us-gaap',{}).get('EarningsPerShareDiluted',{}).get('units',{}).get('USD/shares',[])
    result = defaultdict(list)
    for r in rows:
        if not all(k in r for k in ['start','end','filed','val','accn']):
            continue
        days=(dt.date.fromisoformat(r['end'])-dt.date.fromisoformat(r['start'])).days
        if not 65 <= days <= 110 or r['filed'] > '2021-12-31' or r['end'] > r['filed']:
            continue
        if r.get('form') not in ['10-Q','10-K','10-Q/A','10-K/A'] or not math.isfinite(r['val']):
            continue
        result[quarter(r['end'])].append(r)
    return {q:sorted(rows,key=lambda x:(x['filed'],x['accn'],x['end'])) for q,rows in result.items()}


def asof(rows, cutoff, first=False):
    eligible=[r for r in rows if r['filed']<=cutoff]
    if not eligible:
        return None
    chosen=eligible[0] if first else eligible[-1]
    same=[r for r in eligible if r['filed']==chosen['filed'] and r['accn']==chosen['accn']]
    if len({(r['start'],r['end'],r['val']) for r in same}) != 1:
        return None
    return chosen


def format_eps(value, parentheses):
    if value < 0 and parentheses:
        return f'$ ( {abs(value):.4f} )'
    return f'$ {value:.4f}'


def document(eid, current, previous, index):
    end=dt.date.fromisoformat(current['end'])
    a,b=format_eps(current['val'],index%2==0),format_eps(previous['val'],index%2==0)
    year=end.year
    head=f'Three Months Ended {end.strftime("%B %d")}, {year} {year-1}'
    if index % 3 == 0:
        row=f'Earnings (loss) per common share - diluted {a} {b}'
    elif index % 3 == 1:
        row=f'Earnings per share Basic {a} {b} Diluted {a} {b} Shares used in per share calculation Basic 100 100 Diluted 105 105'
    else:
        row=f'Diluted earnings per common share {a} {b}'
    text=f'Condensed consolidated statements of income.\n{head}\nGAAP EPS in USD per share.\n{row}\n'
    return dict(doc_id='EPS_'+eid,doc_date=max(current['filed'],previous['filed']),
                period_of_report=current['end'],form_type='10-Q',ticker=eid,entity_ids=[eid],
                source='SEC companyfacts; synthetic presentation of original filed facts',text=text)


def build(args):
    root=args.root
    if (root/'dataset.json').exists():
        raise RuntimeError('Dataset already frozen')
    plan=read(args.plan)
    sources=read(root/'raw/sources.json')
    groups=defaultdict(list)
    skipped=Counter()
    for index,source in enumerate(sources):
        path=root/'raw'/source['path']
        assert sha(path)==source['sha256']
        series=facts_by_quarter(read(path))
        for q in sorted(series):
            first=asof(series[q],'2021-12-31',first=True)
            if not first or not 2012 <= int(first['end'][:4]) <= 2021:
                continue
            # Multi-entity quarterly units avoid the perfect-naive discontinuity
            # dominating a collection of singleton classification tasks. Use one
            # origin for the entire roster and resolve only later reports.
            y, m = q//4, 3*(q%4+1)
            boundary=dt.date(y,m,calendar.monthrange(y,m)[1])
            if abs((dt.date.fromisoformat(first['end'])-boundary).days)>14:
                skipped['fiscal_calendar_not_comparable']+=1
                continue
            cutoff=(boundary+dt.timedelta(days=7)).isoformat()
            if first['filed'] <= cutoff:
                skipped['outcome_already_available']+=1
                continue
            past=[asof(series.get(k,[]),cutoff) for k in [q-1,q-5,q-4]]
            if any(p is None for p in past):
                skipped['missing_unambiguous_feature']+=1
                continue
            recent,compare,prior=past
            if not 340 <= (dt.date.fromisoformat(recent['end'])-dt.date.fromisoformat(compare['end'])).days <= 390:
                skipped['comparator_period_mismatch']+=1
                continue
            if not 45 <= (dt.date.fromisoformat(first['end'])-dt.date.fromisoformat(recent['end'])).days <= 150:
                skipped['recent_period_mismatch']+=1
                continue
            # Point-in-time copies of a stock-split-adjusted comparative can conflict
            # with an older current-quarter observation. Keep actual as-of data;
            # never repair it using target or later facts.
            eid=f'ENTITY_{index:03d}'
            row=dict(entity_id=eid,name=eid,prior_year_q_eps=prior['val'],
                     quarter_reported='three months ended '+first['end'],
                     prior_year_quarter='three months ended '+prior['end'])
            doc=document(eid,recent,compare,index)
            audit=dict(source_sha256=source['sha256'],source_ticker=source['ticker'],
                       feature_records=past,cutoff=cutoff,target=first,
                       target_is_first_report=True,target_available=first['filed'])
            groups[cutoff].append((row,doc,first,audit))
    cases=[]
    for cutoff,group in sorted(groups.items()):
        year=int(cutoff[:4])
        if not 2012<=year<=2021:
            continue
        split='dev' if year<=2016 else 'holdout'
        for family,kind,target in [('eps_direction','classification','eps_yoy_direction'),('eps_growth','regression','eps_yoy_growth_pct')]:
            selected=[g for g in group if family!='eps_growth' or abs(g[0]['prior_year_q_eps'])>1e-12]
            if not selected:
                continue
            case=f'{family}-{cutoff}'
            directory=root/'inputs'/split/case
            entities=[g[0] for g in selected]
            target_spec=dict(name=target,type=kind)
            if kind=='classification': target_spec['labels']=['up','down']
            task=dict(task_id=case,schema_version='3',family=family,target=target_spec,
                      cutoff_date=cutoff,resolution_date=max(g[2]['filed'] for g in selected),
                      interval_level=.9,entities=entities,corpus_manifest='corpus/manifest.json',
                      prompt='Forecast next-quarter GAAP diluted EPS from the frozen quarterly filing. Use the given prior-year target quarter to express growth or direction. Cite the evidence.')
            write(directory/'task.json',task)
            manifest=[];outcomes=[];audits=[]
            for e,doc,truth,audit in selected:
                assert all(f['filed']<=cutoff for f in audit['feature_records'])
                assert truth['filed']>cutoff and truth['filed']<='2021-12-31'
                assert doc['doc_date']<=cutoff
                p=directory/'corpus'/(doc['doc_id']+'.json');write(p,doc)
                manifest.append(dict(path='corpus/'+p.name,role='corpus',sha256=sha(p),entity_ids=[e['entity_id']]))
                prior=e['prior_year_q_eps']
                y=truth['val'] if kind=='classification' else 100*(truth['val']-prior)/abs(prior)
                outcomes.append(dict(entity_id=e['entity_id'],y=y,true_label='up' if truth['val']>=prior else 'down'))
                audits.append(audit)
            write(directory/'corpus/manifest.json',dict(manifest_version='2.0',unit_id=case,files=manifest))
            validate_truth(task,dict(outcomes=outcomes))
            write(root/'truth'/split/(case+'.json'),dict(outcomes=outcomes))
            write(root/'audit'/split/(case+'.json'),audits)
            cases.append(dict(case=case,split=split,family=family,block=f'{year}-Q{(int(cutoff[5:7])-1)//3+1}',
                              rows=len(entities),task_sha256=sha(directory/'task.json'),
                              manifest_sha256=sha(directory/'corpus/manifest.json'),truth_sha256=sha(root/'truth'/split/(case+'.json'))))
    write(root/'plan.json',plan)
    write(root/'dataset.json',dict(cases=cases,plan_sha256=sha(root/'plan.json'),skipped=dict(skipped),
                                   source_count=len(sources),tie_label='up',constructed_from='first-reported and as-of SEC EPS facts'))
    print(json.dumps(dict(cases=len(cases),rows=sum(c['rows'] for c in cases),skipped=dict(skipped))))


def run(args):
    root=args.root.resolve()
    report=root/'reports'/(args.split+'.json')
    if report.exists(): raise RuntimeError('Split already evaluated; refusing a second look')
    if args.split=='holdout' and not (root/'reports/dev.json').exists():
        raise RuntimeError('Run development before holdout')
    models={'v6':args.v6_image,'v7':args.v7_image}
    image_ids={m:subprocess.check_output(['sudo','-n','docker','image','inspect','--format','{{.Id}}',im],text=True).strip() for m,im in models.items()}
    frozen=root/'runtime.json'
    runtime=dict(images=image_ids,dataset_sha256=sha(root/'dataset.json'),plan_sha256=sha(root/'plan.json'))
    if frozen.exists(): assert read(frozen)==runtime,'Candidate changed after freeze'
    else: write(frozen,runtime)
    common=['sudo','-n','docker','run','--rm','--network=none','--read-only','--cap-drop=ALL',
            '--security-opt=no-new-privileges','--pids-limit=128','--memory=2g','--cpus=2',
            '--user',f'{os.getuid()}:{os.getgid()}','--tmpfs','/tmp:rw,size=64m']
    cases=[c for c in read(root/'dataset.json')['cases'] if c['split']==args.split]
    for i,c in enumerate(cases):
        directory=root/'inputs'/args.split/c['case']
        assert sha(directory/'task.json')==c['task_sha256']
        assert sha(directory/'corpus/manifest.json')==c['manifest_sha256']
        for f in read(directory/'corpus/manifest.json')['files']: assert sha(directory/f['path'])==f['sha256']
        for method,image in image_ids.items():
            output=root/'answers'/args.split/c['case']/method
            output.mkdir(parents=True,exist_ok=True)
            start=time.monotonic()
            subprocess.run(common+['-v',f'{directory}:/input:ro','-v',f'{output}:/output',image,
                                   'analyze','--task','/input/task.json','--corpus','/input/corpus','--out','/output/answer.json'],
                           check=True,capture_output=True,text=True,timeout=120)
            write(output/'resources.json',dict(seconds=time.monotonic()-start,network='none',cpu_limit=2,memory_gib=2))
        if i%10==0 or i==len(cases)-1: print(f'{args.split} {i+1}/{len(cases)}',flush=True)


def score(args):
    from importlib import resources
    import numpy as np
    from lab.score import score_answer
    from qfbench2_track_analysis.scoring import SCORER_VERSION
    root=args.root
    dest=root/'reports'/(args.split+'.json')
    if dest.exists(): raise RuntimeError('This split was already scored')
    schema=json.loads(resources.files('qfbench2_common').joinpath('schemas/analysis.schema.json').read_text())
    rows=[]
    for c in read(root/'dataset.json')['cases']:
        if c['split']!=args.split: continue
        directory=root/'inputs'/args.split/c['case']
        task=read(directory/'task.json')
        truth_path=root/'truth'/args.split/(c['case']+'.json')
        assert sha(truth_path)==c['truth_sha256']
        truth=read(truth_path)
        validate_truth(task,truth)
        docs={d['doc_id']:d for p in (directory/'corpus').glob('EPS_*.json') for d in [read(p)]}
        naive=read(root/'answers'/args.split/c['case']/'v6/answer.json')
        score_answer(naive,task,truth,docs,naive,schema)
        for method in ['v6','v7']:
            answer=read(root/'answers'/args.split/c['case']/method/'answer.json')
            row=dict(case=c['case'],family=c['family'],block=c['block'],method=method,rows=c['rows'])
            try:
                row.update(score_answer(answer,task,truth,docs,naive,schema))
                pairs=list(zip(answer['entity_predictions'],truth['outcomes']))
                row['mae']=float(np.mean([abs(p['point_forecast']-y['y']) for p,y in pairs]))
                if c['family']=='eps_direction': row['accuracy']=float(np.mean([p['label']==y['true_label'] for p,y in pairs]))
            except Exception as e:
                row.update(score=0.,failure=type(e).__name__+': '+str(e)[:250])
            rows.append(row)
    summary={}
    for method in ['v6','v7']:
        families={f:float(np.mean([r['score'] for r in rows if r['method']==method and r['family']==f])) for f in ['eps_direction','eps_growth']}
        summary[method]=dict(mean=float(np.mean(list(families.values()))),families=families,
                             failures=sum('failure' in r for r in rows if r['method']==method),
                             direction_accuracy=float(np.average([r.get('accuracy',0.) for r in rows if r['method']==method and r['family']=='eps_direction'],
                                                          weights=[r['rows'] for r in rows if r['method']==method and r['family']=='eps_direction'])))
    blocks=sorted({r['block'] for r in rows})
    delta=[np.mean([r['score'] for r in rows if r['method']=='v7' and r['block']==b])-np.mean([r['score'] for r in rows if r['method']=='v6' and r['block']==b]) for b in blocks]
    draws=np.random.default_rng(7).choice(delta,size=(10000,len(delta)),replace=True).mean(axis=1)
    report=dict(split=args.split,rankable=False,scorer_version=SCORER_VERSION,methods=summary,
                paired_delta=float(np.mean(delta)),paired_95_percent_ci=np.quantile(draws,[.025,.975]).tolist(),
                quarter_blocks=len(blocks),cases=len(rows)//2,rows=rows,
                limitations=read(root/'plan.json')['limitations'],runtime=read(root/'runtime.json'))
    write(dest,report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['rows','runtime','limitations']}))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['build','run','score'])
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--plan',type=Path,default=Path('lab/v7_plan.json'))
    p.add_argument('--split',choices=['dev','holdout'],default='dev')
    p.add_argument('--v6-image',default='agenthon-t4:v6-diagnostic')
    p.add_argument('--v7-image',default='agenthon-t4:v7-candidate')
    a=p.parse_args()
    globals()[a.action](a)


if __name__=='__main__': main()
