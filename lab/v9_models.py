"""Causal annual numeric models; no confirmation outcome is ever loaded here."""
from __future__ import annotations
import argparse
from pathlib import Path
import time
import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor as HGR,HistGradientBoostingClassifier as HGC,ExtraTreesRegressor
from sklearn.linear_model import HuberRegressor,LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from .v7_eps import read,write,sha
from .v9_features import vector,scale
from agent_submit_v8.numeric import candidates

def feature_function(root):
    if (root/'feature-view.json').exists() and read(root/'feature-view.json')['version']==3:
        from .v9_features_long import vector as long_vector
        return long_vector
    return vector

def training_pools(root):
    if (root/'training-pools.json').exists():return read(root/'training-pools.json')['pools']
    pools=['existing','additional_training']
    if (root/'manifests/training_extension.json').exists():pools.append('training_extension')
    if (root/'manifests/opened_a_training.json').exists():pools.append('opened_a_training')
    return pools

def checked(root,pool,truth=False):
    directory='truth' if truth else 'inputs';p=root/directory/f'{pool}.json'
    assert sha(p)==read(root/'manifests'/f'{pool}.json')[directory[:-1]+'_sha256' if directory=='inputs' else 'truth_sha256']
    return read(p)

def configurations():
    return dict(median7=dict(kind='reg',loss='absolute_error',leaves=7,target='level',weight=0.),
                median15=dict(kind='reg',loss='absolute_error',leaves=15,target='level',weight=0.),
                growth7=dict(kind='reg',loss='absolute_error',leaves=7,target='level',weight=1.),
                growth15=dict(kind='reg',loss='absolute_error',leaves=15,target='level',weight=.5),
                delta7=dict(kind='reg',loss='absolute_error',leaves=7,target='delta',weight=0.),
                mean7=dict(kind='reg',loss='squared_error',leaves=7,target='level',weight=.5),
                huber=dict(kind='huber',target='level',weight=.5),
                extra=dict(kind='extra',target='level',weight=.5),
                clf7=dict(kind='clf',leaves=7),clf15=dict(kind='clf',leaves=15),
                logit=dict(kind='logit'),low=dict(kind='quantile',quantile=.05),high=dict(kind='quantile',quantile=.95))

def fit(root,year):
    dest=root/'models'/f'{year}.joblib'
    if dest.exists():return
    rows=[];truth={}
    for pool in training_pools(root):
        rows+=checked(root,pool);truth.update(checked(root,pool,True))
    limit=f'{year}-01-01'
    rows=[r for r in rows if truth[r['id']]['available']<limit]
    assert all(truth[r['id']]['available']<limit for r in rows)
    result={};started=time.monotonic();vector_fn=feature_function(root)
    for view in ['compact','rich']:
        X=np.array([vector_fn(r,view) for r in rows]);s=np.array([scale(r,view) for r in rows]);prior=np.array([r['prior'] for r in rows])
        y=np.array([truth[r['id']]['y'] for r in rows]);label=y>=prior
        for name,c in configurations().items():
            kind=c['kind']
            if kind in ['reg','quantile']:
                model=HGR(loss=c.get('loss','quantile'),quantile=c.get('quantile'),max_iter=180,max_leaf_nodes=c.get('leaves',7),min_samples_leaf=35,l2_regularization=10,learning_rate=.05,random_state=9,early_stopping=False)
            elif kind=='clf':model=HGC(max_iter=180,max_leaf_nodes=c['leaves'],min_samples_leaf=35,l2_regularization=10,learning_rate=.05,random_state=9,early_stopping=False)
            elif kind=='logit':model=make_pipeline(StandardScaler(),LogisticRegression(C=.05,max_iter=1000))
            elif kind=='extra':model=ExtraTreesRegressor(n_estimators=150,min_samples_leaf=15,max_features=.8,n_jobs=2,random_state=9)
            else:model=make_pipeline(StandardScaler(),HuberRegressor(alpha=10.,epsilon=1.35,max_iter=3000))
            target=label if kind in ['clf','logit'] else np.clip((y-prior)/s if c.get('target')=='delta' else y/s,-15,15)
            weight=np.clip(s/np.maximum(abs(prior),.05),.05,20)**c.get('weight',0.)
            if kind=='huber':model.fit(X,target,huberregressor__sample_weight=weight)
            elif kind=='logit':model.fit(X,target)
            else:model.fit(X,target,sample_weight=weight)
            result[view+'_'+name]=dict(model=model,config=c)
    dest.parent.mkdir(parents=True,exist_ok=True);joblib.dump(result,dest)
    write(root/'models'/f'{year}.json',dict(year=year,training_rows=len(rows),training_companies=len({r['cik'] for r in rows}),
          latest_target_publication=max(truth[r['id']]['available'] for r in rows),model_sha256=sha(dest),
          training_ids_sha256=__import__('hashlib').sha256('\n'.join(sorted(r['id'] for r in rows)).encode()).hexdigest(),
          feature_source_sha256=sha(Path('/app/lab/v9_features.py')),training_pools=training_pools(root),feature_version=3 if vector_fn!=vector else 2,seconds=time.monotonic()-started))
    print('fit',year,len(rows),round(time.monotonic()-started,1),flush=True)

def predict(root,pool,first_year=None,suffix=''):
    dest=root/'predictions'/f'{pool}{suffix}.json'
    if dest.exists():raise RuntimeError('Predictions already frozen')
    rows=checked(root,pool)
    if first_year is not None:rows=[r for r in rows if int(r['cutoff'][:4])>=first_year]
    elif pool=='existing':rows=[r for r in rows if int(r['block'][:4])>=2015]
    output={};vector_fn=feature_function(root)
    for year in sorted({int(r['cutoff'][:4]) for r in rows}):
        fitpath=root/'models'/f'{year}.joblib';meta=read(root/'models'/f'{year}.json')
        assert sha(fitpath)==meta['model_sha256'] and meta['latest_target_publication']<f'{year}-01-01'
        models=joblib.load(fitpath);batch=[r for r in rows if int(r['cutoff'][:4])==year]
        for r in batch:output[r['id']]=dict(points=candidates(r),probabilities={},bounds={})
        for view in ['compact','rich']:
            X=np.array([vector_fn(r,view) for r in batch]);s=np.array([scale(r,view) for r in batch]);prior=np.array([r['prior'] for r in batch])
            for name,c in models.items():
                if not name.startswith(view+'_'):continue
                model=c['model'];config=c['config'];kind=config['kind']
                vals=model.predict_proba(X)[:,1] if kind in ['clf','logit'] else model.predict(X)
                for i,r in enumerate(batch):
                    entry=output[r['id']]
                    if kind in ['clf','logit']:entry['probabilities'][name]=float(vals[i])
                    elif kind=='quantile':entry['bounds'][name]=float(vals[i]*s[i])
                    else:entry['points'][name]=float(vals[i]*s[i]+(prior[i] if config.get('target')=='delta' else 0.))
            for r in batch:
                p=output[r['id']]['points']
                p[view+'_ensemble']=float(np.median([p[view+'_'+n] for n in ['median7','growth7','delta7','huber']]))
                p[view+'_trees']=float(np.median([p[view+'_'+n] for n in ['median7','median15','growth7','growth15']]))
        if vector_fn!=vector:
            from .v9_features_long import history_signals
            for r in batch:
                sig=history_signals(r);p=output[r['id']]['points']
                p['rich_history_trend']=r['prior']+.5*r['scale']*(sig['seasonal_trend'] or 0.)
                p['rich_history_level']=r['scale']*sig['seasonal_level'] if sig['seasonal_level'] is not None else p['rich_median15']
        print('predict',pool,year,len(batch),flush=True)
    write(dest,output)
    write(root/'predictions'/f'{pool}{suffix}-manifest.json',dict(rows=len(rows),prediction_sha256=sha(dest),
          input_sha256=sha(root/'inputs'/f'{pool}.json'),model_files={p.name:sha(p) for p in sorted((root/'models').glob('*.joblib'))},
          prediction_code_sha256=sha(Path('/app/lab/v9_models.py')),target_data_loaded=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['fit','predict']);p.add_argument('--root',type=Path,default=Path('/experiment'))
    p.add_argument('--year',type=int);p.add_argument('--pool',default='existing');p.add_argument('--first-year',type=int);p.add_argument('--suffix',default='');a=p.parse_args()
    if a.action=='fit':
        for year in [a.year] if a.year else range(2015,2022):fit(a.root,year)
    else:predict(a.root,a.pool,a.first_year,a.suffix)
