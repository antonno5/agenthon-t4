"""Choose on consumed development cohorts only; never inspect confirmation."""
from pathlib import Path
import argparse
import json
import numpy as np
from .v7_eps import read,write,sha
from .v9_evaluate import choices,interval


def select(root,pools):
    if any(p.startswith('confirmation') for p in pools):
        raise ValueError('Use explicitly opened development aliases, never confirmation reports')
    dest=root/'development-selection-ci.json'
    if dest.exists():raise RuntimeError('CI selection already frozen')
    reports={p:read(root/'reports'/f'{p}.json') for p in pools}
    families=['eps_direction','eps_growth']
    names={f:sorted(set.intersection(*(set(r['methods'][f]) for r in reports.values()))) for f in families}
    cohorts={}
    for pool,report in reports.items():
        rows=report['rows'];blocks=sorted({r['block'] for r in rows})
        lookup={(r['family'],r['block'],r['method']):r['score'] for r in rows}
        arrays={f:np.array([[lookup[f,b,m] for b in blocks] for m in names[f]]) for f in families}
        baseline=np.mean([arrays[f][names[f].index('v7')] for f in families],axis=0)
        idx=np.random.default_rng(9).integers(0,len(blocks),size=(20000,len(blocks)))
        draws={f:arrays[f][:,idx].mean(axis=2) for f in families}
        cohorts[pool]=dict(arrays=arrays,baseline=baseline,draws=draws,base_draws=baseline[idx].mean(axis=1))
    best=None;top=[]
    for i,c in enumerate(names[families[0]]):
        for j,g in enumerate(names[families[1]]):
            lcbs=[];means=[]
            for data in cohorts.values():
                d=(data['draws'][families[0]][i]+data['draws'][families[1]][j])*.5-data['base_draws']
                lcbs.append(float(np.quantile(d,.0125)))
                means.append(float((data['arrays'][families[0]][i].mean()+data['arrays'][families[1]][j].mean())*.5))
            lcb=min(lcbs);mean=float(np.mean(means));key=(lcb,mean,c,g)
            if best is None or key>best:best=key
            top.append(dict(direction=c,growth=g,development_worst_lcb97_5=lcb,mean=mean,cohort_lcbs=dict(zip(pools,lcbs))))
    top.sort(key=lambda v:(v['development_worst_lcb97_5'],v['mean']),reverse=True)
    _,mean,c,g=best;chosen=dict(zip(families,[c,g]));configs=choices(read(root/'predictions'/f'{pools[0]}.json'))
    selected={f:dict(method=m,config=configs[f][m],development_score=float(np.mean([r['methods'][f][m]['mean'] for r in reports.values()]))) for f,m in chosen.items()}
    bypool={}
    for pool,data in cohorts.items():
        score=np.mean([data['arrays'][f][names[f].index(m)] for f,m in chosen.items()],axis=0)
        bypool[pool]=dict(primary_mean=float(score.mean()),v7_mean=float(data['baseline'].mean()),interval=interval(score-data['baseline']))
    write(dest,dict(families=selected,report_sha256=sha(root/'reports'/f'{pools[0]}.json'),
        report_sha256_by_pool={p:sha(root/'reports'/f'{p}.json') for p in pools},
        rule='Maximize MINIMUM paired-quarter 97.5% bootstrap lower bound across consumed DEVELOPMENT cohorts. Tie: equal-cohort score, method name. No confirmation data.',
        comparisons_tested=len(top),development_primary_mean=mean,development_by_pool=bypool,top10=top[:10]))
    print(json.dumps(read(dest)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/experiment/r7'));p.add_argument('--pools',nargs='+',default=['existing','opened_a_training']);a=p.parse_args()
    select(a.root,a.pools)
