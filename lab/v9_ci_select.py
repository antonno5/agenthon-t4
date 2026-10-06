"""Select a stable pair on development only; confirmation metric stays unchanged."""
from pathlib import Path
import argparse
import json
import numpy as np
from .v7_eps import read,write,sha
from .v9_evaluate import choices,interval

p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/experiment/r6'));a=p.parse_args();root=a.root
report=read(root/'reports/existing.json');rows=report['rows'];blocks=sorted({r['block'] for r in rows})
names={f:sorted(report['methods'][f]) for f in report['methods']}
arrays={f:np.array([[next(r['score'] for r in rows if r['family']==f and r['block']==b and r['method']==m) for b in blocks] for m in methods]) for f,methods in names.items()}
baseline=np.mean([arrays[f][names[f].index('v7')] for f in arrays],axis=0)
rng=np.random.default_rng(9);idx=rng.integers(0,len(blocks),size=(20000,len(blocks)))
families=['eps_direction','eps_growth']
draws={f:arrays[f][:,idx].mean(axis=2) for f in families};base_draws=baseline[idx].mean(axis=1)
best=None;top=[]
for i,c in enumerate(names[families[0]]):
    for j,g in enumerate(names[families[1]]):
        d=(draws[families[0]][i]+draws[families[1]][j])*.5-base_draws
        lcb=float(np.quantile(d,.0125));mean=float((arrays[families[0]][i].mean()+arrays[families[1]][j].mean())*.5)
        key=(lcb,mean,c,g)
        if best is None or key>best:best=key
        top.append(dict(direction=c,growth=g,development_lcb97_5=lcb,mean=mean))
top.sort(key=lambda v:(v['development_lcb97_5'],v['mean']),reverse=True)
_,mean,c,g=best;chosen=dict(zip(families,[c,g]));configs=choices(read(root/'predictions/existing.json'))
selected={f:dict(method=m,config=configs[f][m],development_score=report['methods'][f][m]['mean']) for f,m in chosen.items()}
delta=np.mean([arrays[f][names[f].index(m)] for f,m in chosen.items()],axis=0)-baseline
dest=root/'development-selection-ci.json'
if dest.exists():raise RuntimeError('CI selection already frozen')
write(dest,dict(families=selected,report_sha256=sha(root/'reports/existing.json'),rule='Maximize paired quarterly 97.5% bootstrap lower bound on DEVELOPMENT only; never optimize on confirmation',
               comparisons_tested=len(top),development_primary_mean=mean,development_interval=interval(delta),top10=top[:10]))
print(json.dumps(read(dest)),flush=True)
