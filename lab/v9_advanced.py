"""Additional CPU tree learners; annual target publication limits are unchanged."""
from __future__ import annotations
import argparse
import copy
from pathlib import Path
import time
import joblib
import numpy as np
from catboost import CatBoostRegressor,CatBoostClassifier
from xgboost import XGBRegressor,XGBClassifier
from .v9_models import checked,feature_function,training_pools
from .v9_features import vector,scale
from .v7_eps import read,write,sha

def features(row,vector_fn=vector):
    q=int(row['block'][-1])
    return vector_fn(row,'rich')+[float(q==i) for i in range(1,5)]

CONFIGS={
 'cat_mae4':dict(engine='cat',depth=4,target='level',weight=0.),
 'cat_mae6':dict(engine='cat',depth=6,target='level',weight=0.),
 'cat_growth4':dict(engine='cat',depth=4,target='level',weight=1.),
 'cat_growth6':dict(engine='cat',depth=6,target='level',weight=.5),
 'cat_delta4':dict(engine='cat',depth=4,target='delta',weight=0.),
 'cat_asinh6':dict(engine='cat',depth=6,target='asinh',weight=.5),
 'cat_recent4':dict(engine='cat',depth=4,target='level',weight=.5,recent=True),
 'cat_clf4':dict(engine='cat',depth=4,target='label'),
 'cat_clf6':dict(engine='cat',depth=6,target='label'),
 'xgb_mae3':dict(engine='xgb',depth=3,target='level',weight=0.),
 'xgb_growth5':dict(engine='xgb',depth=5,target='level',weight=.5),
 'xgb_asinh3':dict(engine='xgb',depth=3,target='asinh',weight=.5),
 'xgb_clf3':dict(engine='xgb',depth=3,target='label'),
 'xgb_clf5':dict(engine='xgb',depth=5,target='label')}

def fit(root,year):
    dest=root/'models'/f'{year}.joblib'
    if dest.exists():return
    rows=[];truth={}
    for pool in training_pools(root):
        rows+=checked(root,pool);truth.update(checked(root,pool,True))
    rows=[r for r in rows if truth[r['id']]['available']<f'{year}-01-01']
    vector_fn=feature_function(root)
    X=np.array([features(r,vector_fn) for r in rows]);s=np.array([r['scale'] for r in rows]);prior=np.array([r['prior'] for r in rows]);y=np.array([truth[r['id']]['y'] for r in rows])
    out={};start=time.monotonic()
    for name,c in CONFIGS.items():
        label=c['target']=='label';target=(y>=prior).astype(int) if label else np.arcsinh(y/s) if c['target']=='asinh' else np.clip((y-prior)/s if c['target']=='delta' else y/s,-20,20)
        weights=np.clip(s/np.maximum(abs(prior),.05),.05,20)**c.get('weight',0.)
        if c.get('recent'):weights*=np.array([2**(-(year-int(truth[r['id']]['available'][:4]))/3.) for r in rows])
        if c['engine']=='cat':
            cls=CatBoostClassifier if label else CatBoostRegressor
            loss='Logloss' if label else 'RMSE' if c['target']=='asinh' else 'MAE'
            model=cls(iterations=600,depth=c['depth'],learning_rate=.035,l2_leaf_reg=8,loss_function=loss,random_seed=9,
                      thread_count=4,verbose=False,allow_writing_files=False)
        else:
            cls=XGBClassifier if label else XGBRegressor
            obj='binary:logistic' if label else 'reg:squarederror' if c['target']=='asinh' else 'reg:absoluteerror'
            model=cls(n_estimators=450,max_depth=c['depth'],learning_rate=.035,min_child_weight=20,reg_lambda=10,
                      subsample=.85,colsample_bytree=.8,random_state=9,n_jobs=4,objective=obj,tree_method='hist')
        model.fit(X,target,sample_weight=weights)
        out['rich_'+name]=dict(config=c,model=model)
    dest.parent.mkdir(parents=True,exist_ok=True);joblib.dump(out,dest)
    write(root/'models'/f'{year}.json',dict(year=year,rows=len(rows),latest_target_publication=max(truth[r['id']]['available'] for r in rows),model_sha256=sha(dest),
                                           feature_code_sha256=sha(Path('/app/lab/v9_features.py')),advanced_code_sha256=sha(Path('/app/lab/v9_advanced.py')),seconds=time.monotonic()-start))
    print('advanced fit',year,len(rows),round(time.monotonic()-start,1),flush=True)

def predict(root,pool,first_year=None,suffix=''):
    dest=root/'predictions'/f'{pool}{suffix}.json'
    if dest.exists():raise RuntimeError('Predictions already frozen')
    rows=checked(root,pool)
    if first_year is not None:rows=[r for r in rows if int(r['cutoff'][:4])>=first_year]
    elif pool=='existing':rows=[r for r in rows if int(r['block'][:4])>=2015]
    base=Path(read(root/'base-root.json')['path']) if (root/'base-root.json').exists() else root.parent/'r2'
    output=copy.deepcopy(read(base/'predictions'/f'{pool}{suffix}.json'));vector_fn=feature_function(root)
    for year in sorted({int(r['cutoff'][:4]) for r in rows}):
        p=root/'models'/f'{year}.joblib';meta=read(root/'models'/f'{year}.json');assert sha(p)==meta['model_sha256'] and meta['latest_target_publication']<f'{year}-01-01'
        models=joblib.load(p);batch=[r for r in rows if int(r['cutoff'][:4])==year];X=np.array([features(r,vector_fn) for r in batch])
        for name,item in models.items():
            model=item['model'];c=item['config'];label=c['target']=='label'
            vals=model.predict_proba(X)[:,1] if label else model.predict(X)
            for r,v in zip(batch,vals):
                if label:output[r['id']]['probabilities'][name]=float(v)
                else:
                    if c['target']=='asinh':v=np.sinh(np.clip(v,-5,5))
                    value=float(v)*r['scale']+(r['prior'] if c['target']=='delta' else 0.)
                    output[r['id']]['points'][name]=value
        for r in batch:
            entry=output[r['id']];p=entry['points'];probs=entry['probabilities']
            for name,components in dict(cat_ensemble=['cat_mae4','cat_mae6','cat_growth4','cat_growth6'],
                                        modern_ensemble=['cat_mae6','xgb_mae3','median15','cat_growth6'],
                                        modern_growth=['cat_growth4','cat_growth6','xgb_growth5','growth7'],
                                        broad_ensemble=['cat_mae4','cat_mae6','xgb_mae3','median15','huber']).items():
                p['rich_'+name]=float(np.median([p['rich_'+c] for c in components]))
            probs['rich_modern_clf']=float(np.mean([probs['rich_'+c] for c in ['cat_clf4','cat_clf6','xgb_clf3','clf7']]))
        print('advanced predict',pool,year,len(batch),flush=True)
    write(dest,output)
    write(root/'predictions'/f'{pool}{suffix}-manifest.json',dict(rows=len(rows),prediction_sha256=sha(dest),model_files={p.name:sha(p) for p in sorted((root/'models').glob('*.joblib'))},target_data_loaded=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['fit','predict']);p.add_argument('--root',type=Path,default=Path('/experiment/r3'));p.add_argument('--pool',default='existing');p.add_argument('--year',type=int);p.add_argument('--first-year',type=int);p.add_argument('--suffix',default='');a=p.parse_args()
    if a.action=='fit':
        for year in [a.year] if a.year else range(2015,2022):fit(a.root,year)
    else:predict(a.root,a.pool,a.first_year,a.suffix)
