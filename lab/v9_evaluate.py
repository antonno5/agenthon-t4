"""Unchanged official scorer, paired-quarter selection, and sealed confirmation."""
from __future__ import annotations
import argparse
import copy
from collections import defaultdict
from importlib import resources
from pathlib import Path
import numpy as np
from .v7_eps import read,write,sha,validate_truth
from .v8_experiment import answer as v8_answer
from .v9_models import checked
from qfbench2_track_analysis.alignment import EntityRoster,align_predictions
from qfbench2_track_analysis.scoring import _composite,ScoringParams,SCORER_VERSION

def choices(predictions):
    first=next(iter(predictions.values()));directions={};growth={}
    for point in first['points']:
        directions[point]=dict(point=point)
        growth[point]=dict(point=point,interval='fixed')
        if point.startswith(('rich_','compact_')):
            view=point.split('_')[0]
            for factor in [.75,1.,1.25]:growth[f'{point}:q{factor}']=dict(point=point,interval='quantile',view=view,factor=factor)
    for prob in first['probabilities']:
        for threshold in [.45,.5,.55]:
            directions[f'{prob}:p{threshold}']=dict(point=prob.split('_')[0]+'_median7',probability=prob,threshold=threshold)
    return dict(eps_direction=directions,eps_growth=growth)

def make_answer(rs,predictions,config,family,base):
    ans=copy.deepcopy(base)
    for row,p in zip(rs,ans['entity_predictions']):
        estimate=predictions[row['id']]['points'][config['point']];prior=row['prior']
        if family=='eps_direction':
            up=predictions[row['id']]['probabilities'][config['probability']]>=config['threshold'] if 'probability' in config else estimate>=prior
            p['label']='up' if up else 'down'
            point=prior+(1 if up else -1)*max(abs(estimate-prior),1e-6*row['scale'])
            p['point_forecast']=point;p['interval']=dict(level=.9,lo=point-max(.5,abs(point)*.5),hi=point+max(.5,abs(point)*.5))
        else:
            point=100*(estimate-prior)/abs(prior)
            if config['interval']=='fixed':lo=point-max(50.,abs(point)*.5);hi=point+max(50.,abs(point)*.5)
            else:
                bounds=predictions[row['id']]['bounds'];view=config['view'];factor=config['factor']
                lo_eps=estimate+factor*(min(bounds[view+'_low'],estimate)-estimate)
                hi_eps=estimate+factor*(max(bounds[view+'_high'],estimate)-estimate)
                lo=100*(lo_eps-prior)/abs(prior);hi=100*(hi_eps-prior)/abs(prior)
            p['point_forecast']=point;p['interval']=dict(level=.9,lo=lo,hi=hi)
    return ans

def interval(delta):
    d=np.asarray(delta);rng=np.random.default_rng(9)
    draws=rng.choice(d,size=(20000,len(d)),replace=True).mean(axis=1)
    starts=rng.integers(0,len(d),size=(20000,(len(d)+1)//2))
    idx=np.stack([starts,(starts+1)%len(d)],axis=2).reshape(20000,-1)[:,:len(d)]
    moving=d[idx].mean(axis=1)
    return dict(delta=float(d.mean()),ci95=np.quantile(draws,[.025,.975]).tolist(),
                ci97_5=np.quantile(draws,[.0125,.9875]).tolist(),moving_two_quarter_ci97_5=np.quantile(moving,[.0125,.9875]).tolist(),
                quarter_blocks=len(d),positive_blocks=int((d>0).sum()))

def evaluate(root,pool):
    report_path=root/'reports'/f'{pool}.json'
    if report_path.exists():raise RuntimeError('Pool already evaluated; refusing to overwrite')
    rows=checked(root,pool);truth=checked(root,pool,True);predpath=root/'predictions'/f'{pool}.json';predictions=read(predpath)
    rows=[r for r in rows if r['id'] in predictions];groups=defaultdict(list)
    for r in rows:groups[r['block']].append(r)
    all_choices=choices(predictions);selection=None
    confirm=pool.startswith('confirmation')
    if confirm:
        selection=read(root/f'selection-{pool}.json')
        assert sha(predpath)==selection['prediction_sha256']
        assert sha(Path('/app/lab/v9_evaluate.py'))==selection['evaluation_code_sha256']
        configs={f:dict(v6=all_choices[f]['v6'],v7=all_choices[f]['v7'],primary=selection['families'][f]['config']) for f in all_choices}
        schema=__import__('json').loads(resources.files('qfbench2_common').joinpath('schemas/analysis.schema.json').read_text())
        from lab.score import score_answer
    else:configs=all_choices
    result=[]
    for block,rs in sorted(groups.items()):
        for family in ['eps_direction','eps_growth']:
            points={r['id']:{'v6':r['prior']} for r in rs}
            task,naive,docs,selected=v8_answer(rs,points,'v6',family,block)
            outcomes=[]
            for r in selected:
                y=truth[r['id']]['y'];prior=r['prior']
                outcomes.append(dict(entity_id=r['id'],y=y if family=='eps_direction' else 100*(y-prior)/abs(prior),true_label=truth[r['id']]['true_label']))
            actual=dict(outcomes=outcomes);validate_truth(task,actual)
            roster=EntityRoster.from_task(task);kind=task['target']['type']
            reference=align_predictions(naive,roster,target_type=kind,interval_level=.9)
            params=ScoringParams(kind,.9,.8,.5,(.7,.3),interval_leg=kind!='classification')
            for method,config in configs[family].items():
                a=naive if method=='v6' else make_answer(selected,predictions,config,family,naive)
                aligned=align_predictions(a,roster,target_type=kind,interval_level=.9)
                parts=_composite(aligned,actual,params,roster,naive_aligned=reference)
                if confirm:
                    checked_score=score_answer(a,task,actual,docs,naive,schema)
                    assert abs(checked_score['score']-parts['composite'])<1e-12
                    write(root/'answers'/pool/block/family/f'{method}.json',a)
                ps=a['entity_predictions']
                result.append(dict(block=block,family=family,method=method,rows=len(selected),score=parts['composite'],
                    predictive_quality=parts['predictive_quality'],interval_quality=parts['interval_quality'],
                    interval_coverage=parts['interval_coverage'],
                    accuracy=float(np.mean([p.get('label')==y['true_label'] for p,y in zip(ps,outcomes)])) if kind=='classification' else None,
                    mae=float(np.mean([abs(p['point_forecast']-y['y']) for p,y in zip(ps,outcomes)]))))
    summary={}
    for family,methods in configs.items():
        summary[family]={}
        for method in methods:
            data=[r for r in result if r['family']==family and r['method']==method]
            summary[family][method]=dict(mean=float(np.mean([r['score'] for r in data])),
                mae=float(np.average([r['mae'] for r in data],weights=[r['rows'] for r in data])),
                accuracy=float(np.average([r['accuracy'] for r in data],weights=[r['rows'] for r in data])) if family=='eps_direction' else None)
    report=dict(pool=pool,scorer_version=SCORER_VERSION,rankable=False,prediction_sha256=sha(predpath),methods=summary,rows=result)
    if not confirm:
        winners={f:max(methods,key=lambda m:methods[m]['mean']) for f,methods in summary.items()}
        chosen={f:dict(method=m,config=configs[f][m],development_score=summary[f][m]['mean']) for f,m in winners.items()}
        report['selected']=chosen
        candidates=['primary','v6','v7']
    else:winners={f:'primary' for f in configs};report['selection']=selection
    deltas=[]
    for block in sorted(groups):
        chosen_score=np.mean([r['score'] for r in result if r['block']==block and r['method']==winners[r['family']]])
        baseline=np.mean([r['score'] for r in result if r['block']==block and r['method']=='v7'])
        deltas.append(chosen_score-baseline)
    report['primary_vs_v7']=interval(deltas)
    report['primary_mean']=float(np.mean([summary[f][m]['mean'] for f,m in winners.items()]))
    report['v7_mean']=float(np.mean([summary[f]['v7']['mean'] for f in summary]))
    report['target_met']=report['primary_vs_v7']['ci97_5'][0]>=.1 if confirm else report['primary_vs_v7']['ci95'][0]>=.1
    write(report_path,report)
    if not confirm:write(root/'development-selection.json',dict(families=report['selected'],report_sha256=sha(report_path)))
    print(__import__('json').dumps({k:report[k] for k in ['pool','selected','primary_mean','v7_mean','primary_vs_v7','target_met'] if k in report}),flush=True)

def freeze(root,pool):
    path=root/f'selection-{pool}.json'
    if path.exists():raise RuntimeError('Already frozen')
    development=read(root/'development-selection.json')
    write(path,dict(families=development['families'],development_report_sha256=development['report_sha256'],
          prediction_sha256=sha(root/'predictions'/f'{pool}.json'),
          plan_sha256=sha(root/'plan.json'),evaluation_code_sha256=sha(Path('/app/lab/v9_evaluate.py')),
          pool=pool,threshold=.1,confidence_level=.975,no_codabench_submission=True))
    print('frozen',pool,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['evaluate','freeze']);p.add_argument('--root',type=Path,default=Path('/experiment'));p.add_argument('--pool',default='existing');a=p.parse_args()
    globals()[a.action](a.root,a.pool)
