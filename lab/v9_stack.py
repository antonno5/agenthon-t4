"""Supervised combinations trained exclusively on earlier out-of-time predictions."""
from __future__ import annotations
import argparse
import copy
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
from sklearn.linear_model import HuberRegressor,LogisticRegression,QuantileRegressor,Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from .v9_models import checked,training_pools
from .v7_eps import read,write,sha
from agent_submit_v8.numeric import indicators,clip

POINTS=['v7','rich_median7','rich_median15','rich_growth7','rich_growth15','rich_huber','rich_delta7',
        'rich_cat_mae4','rich_cat_mae6','rich_cat_growth4','rich_cat_growth6','rich_cat_asinh6',
        'rich_xgb_mae3','rich_xgb_growth5','rich_history_trend','rich_history_level','compact_huber']
PROBS=['rich_clf7','rich_clf15','rich_cat_clf4','rich_cat_clf6','rich_xgb_clf3','rich_xgb_clf5','rich_logit']

def features(row,pred):
    f=indicators(row)
    values=[clip((pred['points'][k]-row['prior'])/row['scale'],-12,12) for k in POINTS]
    values+=[pred['probabilities'][k] for k in PROBS]
    values+=[sum(pred['points'][k]>=row['prior'] for k in POINTS)/len(POINTS),
             float(np.std([(pred['points'][k]-row['prior'])/row['scale'] for k in POINTS]))]
    for k in ['rich_low','rich_high']:
        values.append(clip((pred['bounds'][k]-row['prior'])/row['scale'],-15,15))
    for k in ['prior','eps_delta','median_delta','delta_dispersion','operating_eps_delta','net_operating_gap']:
        values+=[f[k] if f[k] is not None else 0.,float(f[k] is None)]
    values+=[float(int(row['block'][-1])==q) for q in range(1,5)]
    return values

def fit(root):
    rows=[];truth={};preds={}
    base=root.parent/'r5'
    for pool in training_pools(root):
        pred=read(base/'predictions'/f'{pool}-oof.json');preds.update(pred)
        rows.extend(r for r in checked(root,pool) if r['id'] in pred)
        truth.update(checked(root,pool,True))
    for year in range(2015,2022):
        path=root/'models'/f'{year}.joblib'
        if path.exists():continue
        selected=[r for r in rows if truth[r['id']]['available']<f'{year}-01-01']
        X=np.array([features(r,preds[r['id']]) for r in selected]);y=np.array([clip((truth[r['id']]['y']-r['prior'])/r['scale'],-15,15) for r in selected])
        labels=np.array([truth[r['id']]['y']>=r['prior'] for r in selected]);weights=np.array([np.clip(r['scale']/max(abs(r['prior']),.05),.05,20)**.5 for r in selected])
        models=dict(huber=make_pipeline(StandardScaler(),HuberRegressor(alpha=10.,epsilon=1.35,max_iter=3000)),
                    quantile=make_pipeline(StandardScaler(),QuantileRegressor(quantile=.5,alpha=.03,solver='highs')),
                    ridge=make_pipeline(StandardScaler(),Ridge(alpha=100.)),
                    tree=HistGradientBoostingRegressor(loss='absolute_error',max_iter=150,max_leaf_nodes=7,min_samples_leaf=40,l2_regularization=20,learning_rate=.04,random_state=9),
                    logit=make_pipeline(StandardScaler(),LogisticRegression(C=.05,max_iter=2000)),
                    clf=HistGradientBoostingClassifier(max_iter=150,max_leaf_nodes=7,min_samples_leaf=40,l2_regularization=20,learning_rate=.04,random_state=9))
        for name,model in models.items():
            target=labels if name in ['logit','clf'] else y
            if name in ['huber','quantile','ridge']:model.fit(X,target,**{model.steps[-1][0]+'__sample_weight':weights})
            else:model.fit(X,target)
        path.parent.mkdir(parents=True,exist_ok=True);joblib.dump(models,path)
        write(root/'models'/f'{year}.json',dict(year=year,rows=len(selected),latest_target_publication=max(truth[r['id']]['available'] for r in selected),
                                              model_sha256=sha(path),training_predictions='earlier annual out-of-time forecasts',
                                              model_features=POINTS+PROBS))
        print('stack fit',year,len(selected),flush=True)

def predict(root,pool):
    dest=root/'predictions'/f'{pool}.json'
    if dest.exists():raise RuntimeError('Predictions already frozen')
    output=copy.deepcopy(read(root.parent/'r5/predictions'/f'{pool}.json'))
    rows=[r for r in checked(root,pool) if r['id'] in output]
    for year in sorted({int(r['cutoff'][:4]) for r in rows}):
        path=root/'models'/f'{year}.joblib';meta=read(root/'models'/f'{year}.json');assert sha(path)==meta['model_sha256'] and meta['latest_target_publication']<f'{year}-01-01'
        models=joblib.load(path);batch=[r for r in rows if int(r['cutoff'][:4])==year];X=np.array([features(r,output[r['id']]) for r in batch])
        for name,model in models.items():
            classifier=name in ['logit','clf'];values=model.predict_proba(X)[:,1] if classifier else model.predict(X)
            for r,v in zip(batch,values):
                p=output[r['id']]
                if classifier:p['probabilities']['rich_stack_'+name]=float(v)
                else:p['points']['rich_stack_'+name]=r['prior']+r['scale']*clip(float(v),-15,15)
        for r in batch:
            p=output[r['id']]['points'];p['rich_stack_ensemble']=float(np.median([p['rich_stack_huber'],p['rich_stack_quantile'],p['rich_median15'],p['rich_cat_ensemble']]))
    write(dest,output);print('stack predicted',pool,len(rows),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['fit','predict']);p.add_argument('--root',type=Path,default=Path('/experiment/r6'));p.add_argument('--pool',default='existing');a=p.parse_args()
    fit(a.root) if a.action=='fit' else predict(a.root,a.pool)
