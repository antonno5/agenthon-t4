"""Fit frozen compact HGB experts; export non-neural trees and verify parity."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
sys.path.insert(0,'/lab')
from agent_submit_v8.numeric import compact_row,vector,FEATURES
from cpi import model_point
OUT=Path('/out');BASE=Path('/lab/test-output/v9');ALL=Path('/inputs/all-rows.json');BANK=Path('/inputs/bank-rows.json')
def read(p):return json.loads(p.read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def export(m):
 trees=[]
 for predictors in m._predictors:
  assert len(predictors)==1;tree=[]
  for n in predictors[0].nodes:
   assert not n['is_categorical']
   tree.append(dict(leaf=bool(n['is_leaf']),value=float(n['value']),feature=int(n['feature_idx']),threshold=float(n['num_threshold']),left=int(n['left']),right=int(n['right'])))
  trees.append(tree)
 return dict(kind='boost',baseline=float(m._baseline_prediction[0,0]),trees=trees)
def main():
 rows=read(ALL);banks=read(BANK);ids={r['id'] for r in rows}|{r['id'] for r in banks};truth={}
 for p in sorted((BASE/'truth').glob('*.json')):truth.update({k:v for k,v in read(p).items() if k in ids})
 assert set(truth)==ids
 params=dict(loss='absolute_error',max_iter=150,max_leaf_nodes=5,min_samples_leaf=20,l2_regularization=10,learning_rate=.05,early_stopping=False,random_state=12)
 manifest=dict(available_after='2023-01-01',fit_labels_before='2022-01-01',features=FEATURES,vector_layout='values then missing indicators; compact_row',hyperparameters=params,experts={},bank_ciks=sorted({r['cik'] for r in banks}),runtime_dependencies='Python standard library only',model_version='v17-compact-hgb')
 audit=dict(sklearn_version=sklearn.__version__,inputs_sha256={'all_rows':digest(ALL),'bank_rows':digest(BANK)},fits={})
 assert max(v['available'] for v in truth.values())<'2023-01-01'
 audit['latest_selection_label_available']=max(v['available'] for v in truth.values())
 for name,source in [('pooled',rows),('bank',banks)]:
  train=[r for r in source if truth[r['id']]['available']<'2022-01-01'];assert train
  model=HistGradientBoostingRegressor(**params)
  x=np.asarray([vector(compact_row(r)) for r in train]);y=np.asarray([np.clip(truth[r['id']]['y']/compact_row(r)['scale'],-15,15) for r in train]);w=np.asarray([np.clip(compact_row(r)['scale']/max(abs(r['prior']),.05),.05,20) for r in train])
  model.fit(x,y,sample_weight=w);portable=export(model)
  check=np.asarray([vector(compact_row(r)) for r in source]);reference=model.predict(check);actual=np.asarray([model_point(portable,v.tolist()) for v in check]);error=float(np.max(np.abs(reference-actual)));assert error<1e-12
  # Probe every tree split exactly and on its floating-point neighbours.
  probes=[]
  for tree in portable['trees']:
   for n in tree:
    if not n['leaf']:
     for val in [n['threshold'],np.nextafter(n['threshold'],-np.inf),np.nextafter(n['threshold'],np.inf)]:
      z=check[0].copy();z[n['feature']]=val;probes.append(z)
  probe_error=float(np.max(np.abs(model.predict(np.asarray(probes))-np.asarray([model_point(portable,v.tolist()) for v in probes]))));assert probe_error<1e-12
  manifest['experts'][name]=portable
  audit['fits'][name]=dict(rows=len(train),last_label_publication=max(truth[r['id']]['available'] for r in train),train_ids=[r['id'] for r in train],parity_rows=len(check),max_absolute_export_error=error,threshold_probes=len(probes),max_threshold_error=probe_error)
  print(name,len(train),len(check),error,probe_error,flush=True)
 (OUT/'eps_models.json').write_text(json.dumps(manifest,separators=(',',':'),allow_nan=False)+'\n')
 audit['model_sha256']=digest(OUT/'eps_models.json');(OUT/'export-validation.json').write_text(json.dumps(audit,indent=2)+'\n')
if __name__=='__main__':main()
