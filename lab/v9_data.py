"""Expanded point-in-time EPS data. Confirmation labels stay in separate files."""
from __future__ import annotations
import argparse
import calendar
from collections import Counter
import datetime as dt
import hashlib
from pathlib import Path
import statistics
from .v7_eps import asof,read,write,sha,facts_by_quarter
from .v8_data import index_facts,matching_pair,TAGS

def build(pool):
    root=Path('test-output/v9');plan=read(root/'plan.json')
    manifest=root/'manifests'/f'{pool}.json'
    if manifest.exists():raise RuntimeError('Pool already frozen')
    if pool=='existing':sources=plan['old_sources']
    else:sources=[dict(s,raw_folder=str(root/'raw'/pool)) for s in read(root/'raw'/pool/'sources.json')]
    rows=[];truth={};audits=[];skipped=Counter();eligible=set()
    for source in sources:
        path=Path(source['raw_folder'])/source['path'];assert sha(path)==source['sha256']
        data=read(path);eps=facts_by_quarter(data);extra=index_facts(data)
        for q in sorted(eps):
            first=asof(eps[q],'2021-12-31',first=True)
            if not first:continue
            year=q//4
            if not 2010<=year<=2021:continue
            if pool.startswith('confirmation') and year<2015:continue
            month=3*(q%4+1);boundary=dt.date(year,month,calendar.monthrange(year,month)[1])
            if abs((dt.date.fromisoformat(first['end'])-boundary).days)>14:skipped['fiscal_calendar']+=1;continue
            cutoff=(boundary+dt.timedelta(days=7)).isoformat()
            if first['filed']<=cutoff:skipped['known_outcome']+=1;continue
            history=[asof(eps.get(q-i,[]),cutoff) for i in range(1,9)]
            recent,compare,prior=history[0],history[4],history[3]
            if any(r is None for r in [recent,compare,prior]):skipped['missing_eps']+=1;continue
            if not 340<=(dt.date.fromisoformat(recent['end'])-dt.date.fromisoformat(compare['end'])).days<=390:continue
            if not 45<=(dt.date.fromisoformat(first['end'])-dt.date.fromisoformat(recent['end'])).days<=150:continue
            values=[r['val'] if r else None for r in history]
            scale=max(.1,statistics.median([abs(x) for x in values if x is not None]))
            pairs={name:matching_pair(extra,name,q-1,cutoff,recent['end'],compare['end']) for name in TAGS}
            pairvals={name:[r['val'] for r in pair] if pair else None for name,pair in pairs.items()}
            shares=pairvals['shares'];warning=False
            if shares and min(shares)>0:warning=shares[0]/shares[1]<.6 or shares[0]/shares[1]>1.7
            eid='R'+hashlib.sha256(f'{source["cik"]}:{q}'.encode()).hexdigest()[:12]
            row=dict(id=eid,cik=source['cik'],block=f'{year}-Q{q%4+1}',cutoff=cutoff,eps=values,scale=scale,prior=prior['val'],
                     metrics=pairvals,split_warning=warning,period=first['end'],recent_period=recent['end'])
            rows.append(row);eligible.add(source['cik'])
            truth[eid]=dict(y=first['val'],true_label='up' if first['val']>=prior['val'] else 'down',available=first['filed'])
            records=[r for r in history if r]+[r for pair in pairs.values() if pair for r in pair]
            assert all(r['filed']<=cutoff for r in records)
            audits.append(dict(id=eid,ticker=source['ticker'],cik=source['cik'],source_sha256=source['sha256'],feature_records=records,target=first))
    rows.sort(key=lambda r:(r['block'],r['id']))
    assert len({r['id'] for r in rows})==len(rows)
    write(root/'inputs'/f'{pool}.json',rows);write(root/'truth'/f'{pool}.json',truth);write(root/'audit'/f'{pool}.json',audits)
    result=dict(pool=pool,rows=len(rows),companies=len(eligible),registered_companies=len(sources),blocks=len({r['block'] for r in rows}),
                plan_sha256=sha(root/'plan.json'),input_sha256=sha(root/'inputs'/f'{pool}.json'),truth_sha256=sha(root/'truth'/f'{pool}.json'),
                skipped=dict(skipped),feature_coverage={k:sum(r['metrics'][k] is not None for r in rows) for k in TAGS})
    write(manifest,result);print(__import__('json').dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('pool',choices=['existing','additional_training','training_extension','opened_a_training','confirmation_a','confirmation_b']);a=p.parse_args();build(a.pool)
