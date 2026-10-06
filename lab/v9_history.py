"""Extend only the visible EPS history to six years, without reading outcomes."""
from pathlib import Path
import argparse
from .v7_eps import read,write,sha,asof,quarter,facts_by_quarter

def enrich(pool):
    base=Path('test-output/v9');src=base/'r2';out=base/'r4';out.mkdir(exist_ok=True)
    if (out/'manifests'/f'{pool}.json').exists():raise RuntimeError('History already frozen')
    for name in ['truth','plan.json']:
        p=out/name
        if not p.exists():p.symlink_to('../'+name,target_is_directory=name=='truth')
    write(out/'feature-view.json',dict(version=3,description='Accounting histories plus six-year EPS seasonality'))
    plan=read(base/'plan.json')
    sources=plan['old_sources'] if pool=='existing' else [dict(s,raw_folder=str(base/'raw'/pool)) for s in read(base/'raw'/pool/'sources.json')]
    source_map={s['cik']:s for s in sources};inputs=read(src/'inputs'/f'{pool}.json');groups={}
    for r in inputs:groups.setdefault(r['cik'],[]).append(r)
    audits=[]
    for cik,rows in groups.items():
        source=source_map[cik];path=Path(source['raw_folder'])/source['path'];assert sha(path)==source['sha256']
        series=facts_by_quarter(read(path))
        for r in rows:
            q=quarter(r['recent_period']);records=[asof(series.get(q-i,[]),r['cutoff']) for i in range(24)]
            values=[v['val'] if v else None for v in records];assert values[:8]==r['eps']
            assert all(v['filed']<=r['cutoff'] for v in records if v)
            r['long_eps']=values;audits.append(dict(id=r['id'],cutoff=r['cutoff'],records=[v for v in records if v]))
    write(out/'inputs'/f'{pool}.json',inputs);write(out/'history-audit'/f'{pool}.json',audits)
    manifest=read(src/'manifests'/f'{pool}.json');manifest.update(input_sha256=sha(out/'inputs'/f'{pool}.json'),accounting_input_sha256=sha(src/'inputs'/f'{pool}.json'),history_audit_sha256=sha(out/'history-audit'/f'{pool}.json'))
    write(out/'manifests'/f'{pool}.json',manifest);print('history',pool,len(inputs),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('pool');a=p.parse_args();enrich(a.pool)
