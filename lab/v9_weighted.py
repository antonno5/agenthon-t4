"""Optimize past-quarter relative errors, matching the official aggregation unit."""
from __future__ import annotations
import argparse
import copy
from collections import defaultdict
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor as HGR,HistGradientBoostingClassifier as HGC
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from catboost import CatBoostRegressor,CatBoostClassifier
from .v9_features_long import vector
from .v9_models import checked,training_pools
from .v7_eps import read,write,sha

def fit(root):
    rows=[];truth={}
    for pool in training_pools(root):rows+=checked(root,pool);truth.update(checked(root,pool,True))
    for year in range(2015,2022):
        path=root/'models'/f'{year}.joblib'
        if path.exists():continue
        rs=[r for r in rows if truth[r['id']]['available']<f'{year}-01-01'];X=np.array([vector(r,'rich') for r in rs]);s=np.array([r['scale'] for r in rs])
        prior=np.array([r['prior'] for r in rs]);y=np.array([truth[r['id']]['y'] for r in rs]);label=(y>=prior).astype(int)
        byblock=defaultdict(list)
        for i,r in enumerate(rs):byblock[r['block']].append(i)
        wg=np.zeros(len(rs));wc=np.zeros(len(rs));absolute=np.zeros(len(rs))
        for block,ids in byblock.items():
            ids=np.array(ids);nz=ids[abs(prior[ids])>1e-12]
            naive=np.mean(abs(y[nz]-prior[nz])/abs(prior[nz])) if len(nz) else 1.
            if len(nz):wg[nz]=s[nz]/abs(prior[nz])/max(naive,.05)/len(nz)
            wc[ids]=1./max(int((label[ids]==0).sum()),1)
            absolute[ids]=1./len(ids)
        wg*=len(rs)/wg.sum();wc*=len(rs)/wc.sum();absolute*=len(rs)/absolute.sum()
        definitions={
            'unit_level7':('reg',7,'level',wg), 'unit_level15':('reg',15,'level',wg),
            'unit_delta15':('reg',15,'delta',wg), 'unit_sqrt15':('reg',15,'level',np.sqrt(wg)),
            'unit_equal15':('reg',15,'level',absolute),
            'unit_cat4':('cat',4,'level',wg),'unit_cat6':('cat',6,'level',wg),
            'unit_clf7':('clf',7,'label',wc),'unit_clf15':('clf',15,'label',wc),
            'unit_catclf4':('catclf',4,'label',wc)}
        models={}
        for name,(kind,depth,target,weights) in definitions.items():
            values=label if target=='label' else (y-prior)/s if target=='delta' else y/s
            if kind=='reg':model=HGR(loss='absolute_error',max_iter=250,max_leaf_nodes=depth,min_samples_leaf=35,l2_regularization=10,learning_rate=.04,random_state=9,early_stopping=False)
            elif kind=='clf':model=HGC(max_iter=250,max_leaf_nodes=depth,min_samples_leaf=35,l2_regularization=10,learning_rate=.04,random_state=9,early_stopping=False)
            elif kind in ['cat','catclf']:
                cls=CatBoostClassifier if kind=='catclf' else CatBoostRegressor
                model=cls(iterations=600,depth=depth,learning_rate=.035,l2_leaf_reg=8,loss_function='Logloss' if kind=='catclf' else 'MAE',
                          thread_count=4,random_seed=9,allow_writing_files=False,verbose=False)
            else:model=make_pipeline(StandardScaler(),HuberRegressor(alpha=10.,epsilon=1.35,max_iter=3000))
            if kind=='huber':model.fit(X,np.clip(values,-30,30),huberregressor__sample_weight=weights)
            else:model.fit(X,values,sample_weight=weights)
            models['rich_'+name]=dict(model=model,target=target)
        path.parent.mkdir(parents=True,exist_ok=True);joblib.dump(models,path)
        write(root/'models'/f'{year}.json',dict(year=year,rows=len(rs),latest_target_publication=max(truth[r['id']]['available'] for r in rs),
                                              training_pools=training_pools(root),model_sha256=sha(path),weighting='past-quarter baseline-relative EPS error; exact nonzero growth denominators'))
        print('unit-weighted fit',year,len(rs),flush=True)

def predict(root,pool,base_pool=None):
    dest=root/'predictions'/f'{pool}.json'
    if dest.exists():raise RuntimeError('Already predicted')
    source_pool=base_pool or pool
    output=copy.deepcopy(read(root.parent/'r6/predictions'/f'{source_pool}.json'))
    rows=[r for r in checked(root,pool) if r['id'] in output]
    for year in sorted({int(r['cutoff'][:4]) for r in rows}):
        p=root/'models'/f'{year}.joblib';meta=read(root/'models'/f'{year}.json');assert sha(p)==meta['model_sha256'] and meta['latest_target_publication']<f'{year}-01-01'
        models=joblib.load(p);batch=[r for r in rows if int(r['cutoff'][:4])==year];X=np.array([vector(r,'rich') for r in batch])
        for name,item in models.items():
            # Discard this candidate globally after a solver failure in the 2020 fit.
            if name=='rich_unit_huber':continue
            target=item['target'];m=item['model'];vs=m.predict_proba(X)[:,1] if target=='label' else m.predict(X)
            for r,v in zip(batch,vs):
                entry=output[r['id']]
                if target=='label':entry['probabilities'][name]=float(v)
                else:entry['points'][name]=float(v)*r['scale']+(r['prior'] if target=='delta' else 0.)
        for r in batch:
            p=output[r['id']]['points']
            p['rich_unit_ensemble']=float(np.median([p[k] for k in ['rich_unit_level15','rich_unit_cat6','rich_xgb_growth5','rich_cat_ensemble']]))
            for amount in [.25,.5,.75]:p[f'rich_unit_blend{amount}']=amount*p['rich_unit_ensemble']+(1-amount)*p['rich_xgb_growth5']
    write(dest,output);print('unit-weighted predicted',pool,len(rows),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['fit','predict']);p.add_argument('--root',type=Path,default=Path('/experiment/r7'));p.add_argument('--pool',default='existing');p.add_argument('--base-pool');a=p.parse_args()
    fit(a.root) if a.action=='fit' else predict(a.root,a.pool,a.base_pool)
