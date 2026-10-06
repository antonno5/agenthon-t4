"""Point-in-time numeric statements. Outcomes never enter predictor inputs."""
from __future__ import annotations
import calendar
from collections import Counter, defaultdict
import datetime as dt
import json
import math
from pathlib import Path
import statistics
from .v7_eps import asof, quarter, read, write, sha, facts_by_quarter

TAGS = {
    'revenue': ['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet', 'SalesRevenueGoodsNet', 'RevenueFromContractWithCustomerIncludingAssessedTax'],
    'operating': ['OperatingIncomeLoss'],
    'net': ['NetIncomeLossAvailableToCommonStockholdersBasic', 'NetIncomeLoss', 'ProfitLoss'],
    'shares': ['WeightedAverageNumberOfDilutedSharesOutstanding'],
    'tax': ['IncomeTaxExpenseBenefit'],
    'pretax': ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments']
}

def index_facts(data):
    result = {}
    for name, tags in TAGS.items():
        result[name] = {}
        for tag in tags:
            unit = 'shares' if name == 'shares' else 'USD'
            quarters = defaultdict(list)
            for r in data.get('facts', {}).get('us-gaap', {}).get(tag, {}).get('units', {}).get(unit, []):
                if not all(k in r for k in ('start', 'end', 'filed', 'val', 'accn')): continue
                days = (dt.date.fromisoformat(r['end'])-dt.date.fromisoformat(r['start'])).days
                if not 65 <= days <= 110 or r['filed'] > '2021-12-31' or r['end'] > r['filed']: continue
                if r.get('form') not in ('10-Q','10-K','10-Q/A','10-K/A') or not math.isfinite(r['val']): continue
                quarters[quarter(r['end'])].append(dict(r, tag=tag))
            result[name][tag] = {q: sorted(v, key=lambda r:(r['filed'],r['accn'],r['end'])) for q,v in quarters.items()}
    return result

def matching_pair(index, name, q, cutoff, end1, end2):
    # Never divide values from different taxonomy concepts or incompatible periods.
    for tag, series in index[name].items():
        a, b = asof(series.get(q, []), cutoff), asof(series.get(q-4, []), cutoff)
        if a is None or b is None: continue
        if any(abs((dt.date.fromisoformat(r['end'])-dt.date.fromisoformat(end)).days)>10 for r,end in [(a,end1),(b,end2)]): continue
        return a, b
    return None

def build(root=Path('test-output/v8-analyst-validated')):
    if (root/'dataset.json').exists(): raise RuntimeError('Frozen dataset already exists')
    plan=read(Path('lab/v8_plan.json'))
    inputs=defaultdict(list); truth=defaultdict(dict); audit=defaultdict(list); skipped=Counter()
    sources=[]
    for pool, raw in [('old',Path('test-output/v7-eps/raw')),('new',root/'raw')]:
        for source in read(raw/'sources.json'):
            path=raw/source['path']; assert sha(path)==source['sha256']
            sources.append(dict(source,pool=pool))
            data=read(path); eps=facts_by_quarter(data); extra=index_facts(data)
            for q in sorted(eps):
                first=asof(eps[q],'2021-12-31',first=True)
                if not first: continue
                year=q//4
                split=('train' if year<=2014 else 'dev') if pool=='old' else 'holdout'
                if pool=='old' and not 2010<=year<=2016: continue
                if pool=='new' and not 2017<=year<=2021: continue
                if split=='train' and first['filed']>'2014-12-31': continue
                if split=='dev' and first['filed']>'2016-12-31': continue
                month=3*(q%4+1); boundary=dt.date(year,month,calendar.monthrange(year,month)[1])
                if abs((dt.date.fromisoformat(first['end'])-boundary).days)>14:
                    skipped['fiscal_calendar']+=1;continue
                cutoff=(boundary+dt.timedelta(days=7)).isoformat()
                if first['filed']<=cutoff: skipped['known_outcome']+=1;continue
                history=[asof(eps.get(q-i,[]),cutoff) for i in range(1,9)]
                recent,compare,prior=history[0],history[4],history[3]
                if any(r is None for r in [recent,compare,prior]): skipped['missing_eps']+=1;continue
                if not 340 <= (dt.date.fromisoformat(recent['end'])-dt.date.fromisoformat(compare['end'])).days <= 390: continue
                if not 45 <= (dt.date.fromisoformat(first['end'])-dt.date.fromisoformat(recent['end'])).days <= 150: continue
                values=[r['val'] if r else None for r in history]
                scale=max(.1,statistics.median([abs(x) for x in values if x is not None]))
                pairs={name:matching_pair(extra,name,q-1,cutoff,recent['end'],compare['end']) for name in TAGS}
                pairvals={name: [r['val'] for r in pair] if pair else None for name,pair in pairs.items()}
                # Derive a split warning from shares AND EPS. Do not use future split data.
                shr=pairvals['shares']; split_warning=False
                if shr and min(shr)>0:
                    ratio=shr[0]/shr[1]
                    split_warning=ratio<.6 or ratio>1.7
                eid='R'+__import__('hashlib').sha256(f'{source["cik"]}:{q}'.encode()).hexdigest()[:12]
                row=dict(id=eid,block=f'{year}-Q{q%4+1}',cutoff=cutoff,eps=values,scale=scale,
                         prior=prior['val'],metrics=pairvals,split_warning=split_warning)
                inputs[split].append(row)
                truth[split][eid]=dict(y=first['val'],true_label='up' if first['val']>=prior['val'] else 'down',
                                      available=first['filed'])
                records=[r for r in history if r]+[r for pair in pairs.values() if pair for r in pair]
                assert all(r['filed']<=cutoff for r in records)
                audit[split].append(dict(id=eid,ticker=source['ticker'],cik=source['cik'],source_sha256=source['sha256'],
                                         feature_records=records,target=first))
    for split in inputs:
        inputs[split].sort(key=lambda r:(r['block'],r['id']))
        write(root/'inputs'/f'{split}.json',inputs[split]);write(root/'truth'/f'{split}.json',truth[split]);write(root/'audit'/f'{split}.json',audit[split])
    write(root/'plan.json',plan)
    manifest=dict(plan_sha256=sha(root/'plan.json'),sources=sources,skipped=dict(skipped),
                  splits={s:dict(rows=len(inputs[s]),blocks=len({r['block'] for r in inputs[s]}),
                                 input_sha256=sha(root/'inputs'/f'{s}.json'),truth_sha256=sha(root/'truth'/f'{s}.json')) for s in inputs})
    write(root/'dataset.json',manifest)
    print(json.dumps(dict(splits=manifest['splits'],skipped=dict(skipped))))

if __name__=='__main__':build()
