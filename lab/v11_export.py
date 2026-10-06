"""Freeze the causal CPI procedure using only labels released before 2017-01-19."""
from __future__ import annotations
import json
import math
from pathlib import Path
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from agent_submit.cli import half_width
from agent_submit_v11.cpi import model_point,features,point,IDS
from .v11_cpi_experiment import model_factories
from .v10_common import write,sha

ROOT=Path('test-output/v11-cpi')
OUT=Path('test-output/submission-v11')
ANCHOR='2017-01-19'


def fit(cases):
    models={}
    for i,e in enumerate(IDS):
        x=[c['rows'][i]['x'] for c in cases];y=[c['rows'][i]['y'] for c in cases]
        models[e]={m:f().fit(x,y) for m,f in model_factories().items()}
        if e in ['CPI_GASOLINE','CPI_ENERGY','CPI_ALLITEMS']:
            bx=[[c['gas_change'],*[float(int(c['target_month'][5:])==m) for m in range(1,13)]] for c in cases]
            models[e]['gas_bridge']=make_pipeline(StandardScaler(),Ridge(alpha=10)).fit(bx,y)
    return models


def serialize(model):
    if hasattr(model,'named_steps'):
        scaler,reg=model.steps[0][1],model.steps[1][1]; weights=reg.coef_/scaler.scale_
        return dict(kind='linear',weights=weights.tolist(),intercept=float(reg.intercept_-np.dot(weights,scaler.mean_)))
    trees=[]
    for stage in model._predictors:
        assert len(stage)==1
        nodes=stage[0].nodes;assert not any(n['is_categorical'] for n in nodes)
        trees.append([dict(leaf=bool(n['is_leaf']),feature=int(n['feature_idx']),threshold=float(n['num_threshold']),
                           left=int(n['left']),right=int(n['right']),value=float(n['value'])) for n in nodes])
    return dict(kind='boost',baseline=float(model._baseline_prediction[0,0]),trees=trees)


def select(past,i):
    errors={m:np.array([abs(p['case']['rows'][i]['y']-p['points'][m][i]) for p in past]) for m in past[0]['points']}
    best=min(errors,key=lambda m:(errors[m].mean(),m!='v8',m));diff=errors['v8']-errors[best]
    gain=float(diff.mean());se=float(diff.std(ddof=1)/math.sqrt(len(diff)))
    return (best if len(past)>=24 and gain>max(se,1e-12) else 'v8'),dict(best=best,mae_gain=gain,se=se,completed_origins=len(past))


def replay(cases):
    predictions=[]
    for year in range(2004,2017):
        train=[c for c in cases if c['resolved']<f'{year}-01-01']
        if len(train)<30:continue
        models=fit(train)
        for case in [c for c in cases if c['target_month'].startswith(str(year))]:
            pp={m:[] for m in ['v8','mean3','mean6','mean9','median9','gas_bridge',*model_factories()]}
            for i,row in enumerate(case['rows']):
                e=row['entity'];v=row['history'];pp['v8'].append(row['baseline'][0])
                for m,n in [('mean3',3),('mean6',6),('mean9',9)]:pp[m].append(float(np.mean(v[-n:])))
                pp['median9'].append(float(np.median(v)))
                for m in model_factories():pp[m].append(float(models[e][m].predict([row['x']])[0]))
                bx=[case['gas_change'],*[float(int(case['target_month'][5:])==m) for m in range(1,13)]]
                pp['gas_bridge'].append(float(models[e]['gas_bridge'].predict([bx])[0]) if 'gas_bridge' in models[e] else float(np.mean(v)))
            predictions.append(dict(case=case,points=pp))
        print(json.dumps(dict(replayed_year=year,train_cases=len(train))),flush=True)
    return predictions


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cases=json.loads((ROOT/'dataset.json').read_text())['cases']
    assert len(cases)==192 and max(c['target_month'] for c in cases)=='2016-12'
    assert all(c['resolved']<ANCHOR for c in cases)
    predictions=replay(cases)
    # Reconstructed prequential forecasts must match the previous development
    # experiment before their errors are used to build a deployable artifact.
    prior=json.loads((ROOT/'development.json').read_text())
    checked=0;maximum=0.
    for record in prior['rows']:
        method=record['method'].removesuffix('_causal_width').removesuffix('_v8_width')
        source=next(p for p in predictions if p['case']['target_month']==record['month'])
        error=float(np.max(np.abs(np.array(source['points'][method])-record['points'])))
        maximum=max(maximum,error);checked+=len(IDS)
    # macOS/amd64 BLAS may differ in the last optimization bits. This bound is
    # far below the 0.1pp source precision, while still catching model drift.
    assert maximum<1e-8,maximum
    routed=[]
    for current in predictions:
        past=[p for p in predictions if p['case']['resolved']<current['case']['cutoff']][-36:]
        estimates=[]
        for i in range(len(IDS)):
            method=select(past,i)[0] if len(past)>=24 else 'v8'
            estimates.append(current['points'][method][i])
        routed.append(dict(case=current['case'],points=estimates))
    past=[p for p in predictions if p['case']['resolved']<ANCHOR][-36:]
    calibration=[p for p in routed if p['case']['resolved']<ANCHOR][-36:]
    final=fit(cases);entities={};portable_error=0.;feature_error=0.;mismatch=[]
    for i,e in enumerate(IDS):
        method,selection=select(past,i)
        errors=[p['case']['rows'][i]['y']-p['points'][i] for p in calibration]
        entry=dict(method=method,width=max(.05,half_width(errors,1.)),selection=selection)
        if method in final[e]:entry['model']=serialize(final[e][method])
        for case in cases:
            history={r['entity']:r['history'] for r in case['rows']};m=int(case['target_month'][5:]);row=case['rows'][i]
            gas=tuple(row['x'][8:11]);xx=features(history,e,m,*gas)
            feature_error=max(feature_error,float(np.max(np.abs(np.array(xx)-row['x']))))
            if method in final[e]:
                x=[gas[0],*[float(m==j) for j in range(1,13)]] if method=='gas_bridge' else row['x']
                expected=float(final[e][method].predict([x])[0]);actual=point(method,history,e,m,gas,entry['model'])
                portable_error=max(portable_error,abs(expected-actual))
                if abs(expected-actual)>1e-10:
                    mismatch.append(dict(entity=e,method=method,month=case['target_month'],expected=expected,actual=actual))
        entities[e]=entry
    assert portable_error<1e-10 and feature_error<1e-10,(portable_error,feature_error,mismatch[:5])
    artifact=dict(version='v11-cpi-frozen-guard',available_after=ANCHOR,training_cases=len(cases),
                  last_target_month='2016-12',last_label_release=max(c['resolved'] for c in cases),
                  selection='36 prior resolved prequential errors; one-standard-error guard versus V8',
                  interval='90% residual quantile of prior guarded forecasts; frozen 2014-2016 calibration',
                  entities=entities)
    target=Path('agent_submit_v11/cpi_model.json');write(target,artifact)
    report=dict(artifact_sha256=sha(target),dataset_sha256=sha(ROOT/'dataset.json'),
                exported_methods={e:v['method'] for e,v in entities.items()},
                replay_predictions_checked=checked,replay_max_error=maximum,
                portable_max_error=portable_error,features_max_error=feature_error,
                training_cases=len(cases),available_after=ANCHOR,confirmation_opened=False,
                authorization='User explicitly requested a diagnostic submission despite the unpassed full-track gate',
                limitation='Frozen 2017 calibration/model state; original development metric used annual refits and online selection. No independent performance claim for the deployed artifact.')
    write(OUT/'export-validation.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
