"""Research orchestration. Fitting, prediction, and truth access are separate actions."""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
from importlib import resources
import json
from pathlib import Path
import statistics as st
import numpy as np
from .v7_eps import read, write, sha, validate_truth
from agent_submit_v8.numeric import FEATURES, vector, candidates, indicators, needs_agent, packet, clip, compact_row

def checked_inputs(root,split):
    manifest=read(root/'dataset.json');p=root/'inputs'/f'{split}.json'
    assert sha(p)==manifest['splits'][split]['input_sha256']
    return read(p)

def checked_truth(root,split):
    manifest=read(root/'dataset.json');p=root/'truth'/f'{split}.json'
    assert sha(p)==manifest['splits'][split]['truth_sha256']
    return read(p)

def fit(root,compact=False):
    import joblib
    from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
    from sklearn.linear_model import HuberRegressor, LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    modeldir=root/('models-compact' if compact else 'models')
    target=modeldir/'models.joblib'
    if target.exists():raise RuntimeError('Model already fitted')
    rows=checked_inputs(root,'train');truth=checked_truth(root,'train')
    if compact:rows=list(map(compact_row,rows))
    X=np.array([vector(r) for r in rows]);y=np.array([clip((truth[r['id']]['y']-r['prior'])/r['scale']) for r in rows])
    label=np.array([truth[r['id']]['true_label']=='up' for r in rows])
    models=dict(huber=make_pipeline(StandardScaler(),HuberRegressor(alpha=10.,epsilon=1.35,max_iter=2000)),
                tree=HistGradientBoostingRegressor(loss='absolute_error',max_iter=100,max_leaf_nodes=7,min_samples_leaf=25,l2_regularization=10,learning_rate=.05,random_state=8),
                logit=make_pipeline(StandardScaler(),LogisticRegression(C=.03,max_iter=1000)),
                tree_label=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,min_samples_leaf=25,l2_regularization=10,learning_rate=.05,random_state=8))
    for k,m in models.items():m.fit(X,label if k in ['logit','tree_label'] else y)
    target.parent.mkdir(parents=True,exist_ok=True);joblib.dump(models,target)
    write(modeldir/'provenance.json',dict(feature_view='compact' if compact else 'rich',train_input_sha256=sha(root/'inputs/train.json'),train_truth_sha256=sha(root/'truth/train.json'),
                                           model_sha256=sha(target),features=FEATURES,training_rows=len(rows),latest_target_publication=max(t['available'] for t in truth.values())))
    print('fitted',len(rows),flush=True)

def predict(root,split,compact=False):
    import joblib
    dest=root/'predictions'/f'{split}{"-compact" if compact else ""}.json'
    if dest.exists():raise RuntimeError('Predictions already frozen')
    rows=checked_inputs(root,split);models=joblib.load(root/('models-compact' if compact else 'models')/'models.joblib')
    if compact:rows=list(map(compact_row,rows))
    X=np.array([vector(r) for r in rows]);vals={k:m.predict(X) for k,m in models.items()}
    output={};packets=[]
    for i,r in enumerate(rows):
        p=candidates(r)
        for k in ['huber','tree']:p[k]=r['prior']+r['scale']*clip(float(vals[k][i]))
        p['quant_ensemble']=st.median([p['core'],p['robust'],p['tree'],p['huber']])
        for k in ['logit','tree_label']:
            direction=1 if vals[k][i] else -1
            magnitude=max(.025*r['scale'],abs(p['quant_ensemble']-r['prior']))
            p[k]=r['prior']+direction*magnitude
        output[r['id']]=p
        if needs_agent(r):
            choices={k:p[k] for k in ['v6','v7','core','robust','ensemble','quant_ensemble','logit','tree_label']}
            packets.append(packet(r,choices))
    if compact:
        base=read(root/'predictions'/f'{split}.json')
        for eid,p in output.items():base[eid].update({'compact_'+k:v for k,v in p.items() if k in ['huber','tree','quant_ensemble','logit','tree_label']})
        write(dest,base)
        print('compact',split,len(rows),flush=True)
        return
    write(dest,output)
    directory=root/'packets'/split;directory.mkdir(parents=True,exist_ok=True)
    for n in range(0,len(packets),40):
        (directory/f'batch-{n//40:02d}.jsonl').write_text(''.join(json.dumps(p,separators=(',',':'))+'\n' for p in packets[n:n+40]))
    write(directory/'manifest.json',dict(rows=len(rows),routed=len(packets),input_sha256=sha(root/'inputs'/f'{split}.json'),prediction_sha256=sha(dest),
                                        files=[dict(name=p.name,sha256=sha(p)) for p in sorted(directory.glob('batch-*.jsonl'))]))
    print(json.dumps(dict(split=split,rows=len(rows),agent_rows=len(packets),routing_rate=len(packets)/len(rows))),flush=True)

def merge_agent(root,split):
    predictions=read(root/'predictions'/f'{split}.json');rows=checked_inputs(root,split)
    packets={p['id']:p for path in (root/'packets'/split).glob('batch-*.jsonl') for p in map(json.loads,path.read_text().splitlines())}
    decisions={}
    for path in sorted((root/'decisions'/split).glob('*.jsonl')):
        for d in map(json.loads,path.read_text().splitlines()):
            assert d['id'] in packets and d['id'] not in decisions,'Unexpected or duplicate decision'
            for role in ['selector','quality','guard']:
                assert d[role] in packets[d['id']]['choices'],'Choice outside bounded set'
            assert isinstance(d['reason'],str) and len(d['reason'])<=250
            decisions[d['id']]=d
    assert set(decisions)==set(packets),f'Missing agent decisions {len(packets)-len(decisions)}'
    for row in rows:
        eid=row['id'];p=predictions[eid]
        for role in ['selector','quality','guard']:
            # Same fixed algorithm path for all unrouted cases isolates specialist contribution.
            p['agent_'+role]=p[decisions[eid][role]] if eid in decisions else p['quant_ensemble']
    dest=root/'predictions'/f'{split}-agent.json'
    if dest.exists():raise RuntimeError('Agent forecasts already frozen')
    write(dest,predictions);print('merged',len(decisions),flush=True)

def answer(rows,forecasts,method,family,block):
    regression=family=='eps_growth';kind='regression' if regression else 'classification'
    selected=[r for r in rows if not regression or abs(r['prior'])>1e-12]
    task=dict(task_id=family+'-'+block,schema_version='3',cutoff_date=max(r['cutoff'] for r in rows),
              target=dict(name=family,type=kind),interval_level=.9,
              entities=[dict(entity_id=r['id'],name=r['id'],prior_year_q_eps=r['prior']) for r in selected])
    if not regression:task['target']['labels']=['up','down']
    predictions=[];docs={}
    for r in selected:
        estimate=forecasts[r['id']][method]
        if isinstance(estimate,dict):estimate=estimate[family]
        prior=r['prior']
        point=100*(estimate-prior)/abs(prior) if regression else estimate
        width=max(50.,abs(point)*.5) if regression else max(.5,abs(point)*.5)
        # A concise exact statement of admitted observed EPS, never forecast rhetoric.
        quote=f"Reported diluted EPS: {r['eps'][0]:.6g}; same quarter of previous year: {r['eps'][4]:.6g}."
        doc_id='EPS_'+r['id']
        docs[doc_id]=dict(doc_id=doc_id,doc_date=r['cutoff'],entity_ids=[r['id']],text=quote)
        pred=dict(entity_id=r['id'],point_forecast=point,interval=dict(level=.9,lo=point-width,hi=point+width),
                  claims=[dict(doc_id=doc_id,span_start=0,span_end=len(quote),claim=quote)])
        if not regression:pred['label']='up' if estimate>=prior else 'down'
        predictions.append(pred)
    return task,dict(task_id=task['task_id'],schema_version='3',target_type=kind,entity_predictions=predictions),docs,selected

def score(root,split,with_agent=False,compact=False,all_methods=False):
    from lab.score import score_answer
    from qfbench2_track_analysis.scoring import SCORER_VERSION
    rows=checked_inputs(root,split);truth=checked_truth(root,split)
    suffix='-all' if all_methods else '-compact' if compact else '-agent' if with_agent else ''
    predictions=read(root/'predictions'/f'{split}{suffix}.json')
    dest=root/'reports'/f'{split}{suffix}.json'
    if dest.exists():raise RuntimeError('Refusing to overwrite an evaluation')
    if split=='holdout' and not (root/'selection.json').exists():raise RuntimeError('Freeze primary before holdout')
    schema=json.loads(resources.files('qfbench2_common').joinpath('schemas/analysis.schema.json').read_text())
    methods=list(next(iter(predictions.values())))
    records=[];group=defaultdict(list)
    for r in rows:group[r['block']].append(r)
    for block,rs in sorted(group.items()):
        for family in ['eps_direction','eps_growth']:
            _,naive,_,_=answer(rs,predictions,'v6',family,block)
            for method in methods:
                task,a,docs,selected=answer(rs,predictions,method,family,block)
                outcomes=[]
                for r in selected:
                    y=truth[r['id']]['y'];prior=r['prior']
                    outcomes.append(dict(entity_id=r['id'],y=100*(y-prior)/abs(prior) if family=='eps_growth' else y,true_label=truth[r['id']]['true_label']))
                actual=dict(outcomes=outcomes);validate_truth(task,actual)
                result=score_answer(a,task,actual,docs,naive,schema)
                ps=a['entity_predictions']
                records.append(dict(block=block,family=family,method=method,rows=len(selected),score=result['score'],
                                    mae=float(np.mean([abs(p['point_forecast']-y['y']) for p,y in zip(ps,outcomes)])),
                                    accuracy=float(np.mean([p.get('label')==y['true_label'] for p,y in zip(ps,outcomes)])) if family=='eps_direction' else None))
    summary={}
    for method in methods:
        mr=[r for r in records if r['method']==method]
        families={f:float(np.mean([r['score'] for r in mr if r['family']==f])) for f in ['eps_direction','eps_growth']}
        summary[method]=dict(mean=float(np.mean(list(families.values()))),families=families,
            direction_accuracy=float(np.average([r['accuracy'] for r in mr if r['family']=='eps_direction'],weights=[r['rows'] for r in mr if r['family']=='eps_direction'])),
            eps_mae=float(np.average([r['mae'] for r in mr if r['family']=='eps_direction'],weights=[r['rows'] for r in mr if r['family']=='eps_direction'])),
            growth_mae=float(np.average([r['mae'] for r in mr if r['family']=='eps_growth'],weights=[r['rows'] for r in mr if r['family']=='eps_growth'])))
    report=dict(split=split,scorer_version=SCORER_VERSION,rankable=False,methods=summary,rows=records,
                model_provenance=read(root/'models/provenance.json'),dataset_sha256=sha(root/'dataset.json'),
                limitations=read(root/'plan.json')['limitations'])
    if split=='holdout':
        selection=read(root/'selection.json');selected=selection['method'];report['selection']=selection;comparisons={}
        for baseline in ['v6','v7','quant_ensemble']:
            delta=[np.mean([r['score'] for r in records if r['block']==b and r['method']==selected])-np.mean([r['score'] for r in records if r['block']==b and r['method']==baseline]) for b in sorted(group)]
            draws=np.random.default_rng(8).choice(delta,size=(10000,len(delta)),replace=True).mean(axis=1)
            comparisons[baseline]=dict(delta=float(np.mean(delta)),ci95=np.quantile(draws,[.025,.975]).tolist(),blocks=len(delta))
        report['comparisons']=comparisons
        report['meaningful_gain']=comparisons['v7']['delta']>=.03 and comparisons['v7']['ci95'][0]>0
    write(dest,report)
    print(json.dumps({k:report[k] for k in ['split','methods','comparisons','meaningful_gain'] if k in report}),flush=True)

def select(root):
    dest=root/'selection.json'
    if dest.exists():raise RuntimeError('Selection already frozen')
    methods={}
    files=[root/'reports'/f'dev{suffix}.json' for suffix in ['', '-agent','-compact']]
    for p in files:methods.update(read(p)['methods'])
    families={f:max(methods,key=lambda m:methods[m]['families'][f]) for f in ['eps_direction','eps_growth']}
    write(dest,dict(method='selected_by_family',family_methods=families,
                    development_score=sum(methods[m]['families'][f] for f,m in families.items())/2,
                    rule='Select independently by target family using dev only; deploy one frozen dispatch pipeline.',
                    development_reports={p.name:sha(p) for p in files},dataset_sha256=sha(root/'dataset.json'),
                    numeric_source_sha256=sha(Path('/app/agent_submit_v8/numeric.py')),
                    handbook_sha256=sha(Path('/app/agent_submit_v8/ANALYST_HANDBOOK.md')),
                    primary_threshold='delta >= .03 and quarterly paired 95% CI lower > 0 versus V7',
                    agent_model='Fresh Codex session subagent, inherited model; research proxy, not House',
                    no_codabench_submission=True))
    print(json.dumps(read(dest)),flush=True)

def assemble(root,split):
    result=read(root/'predictions'/f'{split}.json')
    for suffix in ['-agent','-compact']:
        for eid,values in read(root/'predictions'/f'{split}{suffix}.json').items():result[eid].update(values)
    selection=read(root/'selection.json')
    for eid,p in result.items():p['selected_by_family']={f:p[m] for f,m in selection['family_methods'].items()}
    dest=root/'predictions'/f'{split}-all.json'
    if dest.exists():raise RuntimeError('Combined predictions already frozen')
    write(dest,result)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['fit','predict','merge_agent','score','select','assemble']);p.add_argument('--root',type=Path,default=Path('/experiment'))
    p.add_argument('--split',choices=['train','dev','holdout'],default='dev');p.add_argument('--with-agent',action='store_true');p.add_argument('--compact',action='store_true');p.add_argument('--all-methods',action='store_true');a=p.parse_args()
    if a.action=='fit':fit(a.root,a.compact)
    elif a.action=='score':score(a.root,a.split,a.with_agent,a.compact,a.all_methods)
    elif a.action=='predict':predict(a.root,a.split,a.compact)
    elif a.action=='select':select(a.root)
    elif a.action=='assemble':assemble(a.root,a.split)
    else:merge_agent(a.root,a.split)

if __name__=='__main__':main()
