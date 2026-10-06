"""Past-only quarterly accounting histories, including documented YTD differences."""
from __future__ import annotations
import argparse
import datetime as dt
from pathlib import Path
from collections import Counter
import math
import os
from .v7_eps import read,write,sha,quarter,asof
from .v8_data import TAGS,index_facts

FLOW_TAGS=dict(cfo=['NetCashProvidedByUsedInOperatingActivities','NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'],
               capex=['PaymentsToAcquirePropertyPlantAndEquipment'])
STOCK_TAGS=dict(assets=['Assets'],receivables=['AccountsReceivableNetCurrent'],inventory=['InventoryNet'],
                current_assets=['AssetsCurrent'],current_liabilities=['LiabilitiesCurrent'])

def valid_rows(data,tags,unit,cutoff):
    for tag in tags:
        rows=[]
        for r in data.get('facts',{}).get('us-gaap',{}).get(tag,{}).get('units',{}).get(unit,[]):
            if not all(k in r for k in ['end','filed','val','accn']):continue
            if r['filed']>cutoff or r['end']>r['filed'] or not math.isfinite(r['val']):continue
            if r.get('form') not in ['10-Q','10-K','10-Q/A','10-K/A']:continue
            rows.append(dict(r,tag=tag))
        yield tag,rows

def unique_latest(rows):
    if not rows:return None
    ordered=sorted(rows,key=lambda r:(r['filed'],r['accn']));last=ordered[-1]
    tied=[r for r in ordered if (r['filed'],r['accn'])==(last['filed'],last['accn'])]
    if len({(r.get('start'),r['end'],r['val']) for r in tied})!=1:return None
    return last

def flow_at(data,tags,end,cutoff):
    for tag,rows in valid_rows(data,tags,'USD',cutoff):
        rows=[r for r in rows if 'start' in r]
        ending=[r for r in rows if r['end']==end]
        direct=unique_latest([r for r in ending if 65<=(dt.date.fromisoformat(r['end'])-dt.date.fromisoformat(r['start'])).days<=110])
        if direct:return direct['val'],[direct],'direct'
        # Cumulative cash-flow totals are additive; EPS itself is never derived this way.
        current=unique_latest([r for r in ending if 140<=(dt.date.fromisoformat(r['end'])-dt.date.fromisoformat(r['start'])).days<=380])
        if not current:continue
        previous=unique_latest([r for r in rows if r['start']==current['start'] and
                   65<=(dt.date.fromisoformat(current['end'])-dt.date.fromisoformat(r['end'])).days<=110])
        if previous:return current['val']-previous['val'],[current,previous],'ytd-difference'
    return None,[],'missing'

def enrich(pool,base=Path('test-output/v9'),out=Path('test-output/v9/r2')):
    if (out/'manifests'/f'{pool}.json').exists():raise RuntimeError('Accounting pool already frozen')
    out.mkdir(parents=True,exist_ok=True)
    for directory in ['truth','audit']:
        p=out/directory
        if not p.exists():p.symlink_to(os.path.relpath(base/directory,out),target_is_directory=True)
    if not (out/'plan.json').exists():(out/'plan.json').symlink_to(os.path.relpath(base/'plan.json',out))
    plan=read(base/'plan.json')
    sources=plan['old_sources'] if pool=='existing' else [dict(s,raw_folder=str(base/'raw'/pool)) for s in read(base/'raw'/pool/'sources.json')]
    by_cik={s['cik']:s for s in sources};inputs=read(base/'inputs'/f'{pool}.json');groups={}
    for r in inputs:groups.setdefault(r['cik'],[]).append(r)
    evidence=[];counts=Counter()
    for cik,rows in groups.items():
        source=by_cik[cik];p=Path(source['raw_folder'])/source['path'];assert sha(p)==source['sha256']
        data=read(p);index=index_facts(data)
        for row in rows:
            q=quarter(row['recent_period']);cutoff=row['cutoff'];history={k:[] for k in list(TAGS)+list(FLOW_TAGS)+list(STOCK_TAGS)};records=[]
            # Exact period endpoints come from admitted EPS records when available.
            eps_series=__import__('lab.v7_eps',fromlist=['facts_by_quarter']).facts_by_quarter(data)
            for lag in range(8):
                reference=asof(eps_series.get(q-lag,[]),cutoff)
                end=reference['end'] if reference else None
                for name in TAGS:
                    chosen=None
                    for tag,series in index[name].items():
                        r=asof(series.get(q-lag,[]),cutoff)
                        if r and (end is None or abs((dt.date.fromisoformat(r['end'])-dt.date.fromisoformat(end)).days)<=10):chosen=r;break
                    history[name].append(chosen['val'] if chosen else None)
                    if chosen:records.append(chosen)
                for name,tags in FLOW_TAGS.items():
                    value,used,method=flow_at(data,tags,end,cutoff) if end else (None,[],'missing')
                    history[name].append(value);records+=used;counts[method]+=1
                for name,tags in STOCK_TAGS.items():
                    chosen=None
                    if end:
                        for tag,rr in valid_rows(data,tags,'USD',cutoff):
                            chosen=unique_latest([r for r in rr if r['end']==end and 'start' not in r])
                            if chosen:break
                    history[name].append(chosen['val'] if chosen else None)
                    if chosen:records.append(chosen)
            assert all(r['filed']<=cutoff and r['end']<=row['recent_period'] for r in records)
            row['accounting']=history
            evidence.append(dict(id=row['id'],cutoff=cutoff,source_sha256=source['sha256'],records=records))
    write(out/'inputs'/f'{pool}.json',inputs);write(out/'accounting-audit'/f'{pool}.json',evidence)
    manifest=read(base/'manifests'/f'{pool}.json')
    manifest.update(input_sha256=sha(out/'inputs'/f'{pool}.json'),base_input_sha256=sha(base/'inputs'/f'{pool}.json'),
                    accounting_audit_sha256=sha(out/'accounting-audit'/f'{pool}.json'),cashflow_methods=dict(counts),
                    enriched_rows=len(inputs),target_data_used_for_features=False)
    write(out/'manifests'/f'{pool}.json',manifest)
    print(pool,len(inputs),dict(counts),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('pool');a=p.parse_args();enrich(a.pool)
