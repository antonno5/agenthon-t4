"""Causal eleven-component CPI development experiment, bounded before 2017."""
from __future__ import annotations

import calendar
import datetime as dt
import json
from pathlib import Path
import statistics as stats
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import HuberRegressor, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from agent_submit.cli import mean_forecast, half_width
from agent_submit_v7.series import level_forecast
from agent_submit_v8.cli import predict as deployed_predict
from .v10_common import score, interval, write, sha
from .v11_cpi_parse import ROOT, IDS, LABELS, month_shift


def v8(values):
    fallback=max(.2,stats.pstdev(values)*2)
    point,width,_=mean_forecast(values,3,fallback)
    selected,_=level_forecast(values,'mean3',fallback)
    return selected if selected else (point,width)


def verify_baseline(case):
    # Exercise the real V8 parser and predictor, not just an equivalent formula.
    names={v:k for k,v in LABELS.items()}
    text='month | '+' | '.join(names[e] for e in IDS)+'\n'
    for k in range(9):
        text+=month_shift(case['target_month'],k-9)+' | '+' | '.join(str(r['history'][k]) for r in case['rows'])+'\n'
    corpus=SimpleNamespace(doc_texts={'HISTORY':text},doc_dates={'HISTORY':case['cutoff']})
    task=dict(cutoff_date=case['cutoff'],target=dict(name='cpi_component_mom_first_print',type='regression'),interval_level=.9)
    for row in case['rows']:
        entity=dict(entity_id=row['entity'],name=names[row['entity']],latest_published_mom_pct=row['history'][-1])
        actual=deployed_predict(task,entity,corpus,['HISTORY'])[0]
        p,w=row['baseline']
        if abs(actual['point_forecast']-p)>1e-12 or abs(actual['interval']['hi']-p-w)>1e-12:
            raise AssertionError('Baseline differs from deployed V8')


def build_cases():
    parsed=json.loads((ROOT/'parsed-releases.json').read_text())
    if parsed['errors']: raise ValueError('Resolve all parsing errors before scoring')
    releases=sorted(parsed['releases'],key=lambda r:r['release_date'])
    if any(r['target_month']>'2016-12' for r in releases): raise ValueError('Reserved labels blocked')
    gas=pd.read_csv(ROOT/'gas-development.csv',parse_dates=['date']).set_index('date')['price']
    result=[]; exclusions=[]
    for target in releases:
        month=target['target_month']; year,m=map(int,month.split('-'))
        cutoff=dt.date(year,m,calendar.monthrange(year,m)[1]).isoformat()
        known=[r for r in releases if r['release_date']<=cutoff]
        hist={e:{} for e in IDS}; origins={e:{} for e in IDS}
        for release in known:
            for e,row in release['components'].items():
                for ref,value in row['rates'].items():
                    hist[e][ref]=value; origins[e][ref]=release['release_date']
        months=[month_shift(month,k) for k in range(-9,0)]
        missing=[(e,k) for e in IDS for k in months if k not in hist[e]]
        if missing:
            exclusions.append(dict(month=month,reason='missing prior nine-month history',missing=missing)); continue
        if target['release_date']<=cutoff: raise ValueError('Target already available')
        observed=gas.loc[:pd.Timestamp(cutoff)-pd.Timedelta(days=2)]
        monthly=observed.groupby(observed.index.to_period('M')).mean()
        p=pd.Period(month,freq='M')
        if any(k not in monthly for k in [p-2,p-1,p]):
            exclusions.append(dict(month=month,reason='missing current/prior gas')); continue
        g=float(100*(monthly[p]/monthly[p-1]-1)); gp=float(100*(monthly[p-1]/monthly[p-2]-1))
        weekly=observed[observed.index.to_period('M')==p]
        trend=float(100*(weekly.iloc[-1]/weekly.iloc[0]-1))
        rows=[]
        for e in IDS:
            values=[hist[e][k] for k in months]
            x=[*values[-3:],np.mean(values[-3:]),np.mean(values[-6:]),np.mean(values),np.median(values),np.std(values),
               g,gp,trend,np.mean([hist['CPI_CORE'][k] for k in months[-3:]]),
               np.mean([hist['CPI_ENERGY'][k] for k in months[-3:]]),
               *[float(m==j) for j in range(1,13)]]
            rows.append(dict(entity=e,history=values,x=[float(z) for z in x],
                             y=target['components'][e]['rates'][month],baseline=list(v8(values)),
                             input_release_dates=[origins[e][k] for k in months]))
        case=dict(target_month=month,cutoff=cutoff,resolved=target['release_date'],
                  block=f'{year}Q{(m-1)//3+1}',gas_change=g,gas_prior_change=gp,rows=rows)
        verify_baseline(case); result.append(case)
    write(ROOT/'dataset.json',dict(cases=result,exclusions=exclusions,baseline_parity_rows=len(result)*len(IDS),
                                  parsed_sha256=sha(ROOT/'parsed-releases.json'),gas_sha256=sha(ROOT/'gas-development.csv')))
    return result,exclusions


def model_factories():
    return {
        'ridge10':lambda:make_pipeline(StandardScaler(),Ridge(alpha=10)),
        'ridge100':lambda:make_pipeline(StandardScaler(),Ridge(alpha=100)),
        'huber':lambda:make_pipeline(StandardScaler(),HuberRegressor(alpha=1.,max_iter=2000)),
        'boost':lambda:HistGradientBoostingRegressor(max_iter=70,max_leaf_nodes=4,min_samples_leaf=20,l2_regularization=3.,random_state=11),
    }


def run():
    cases,excluded=build_cases(); predictions=[]; fit_audit=[]
    for year in range(2004,2017):
        train=[c for c in cases if c['resolved']<f'{year}-01-01']
        test=[c for c in cases if c['target_month'].startswith(str(year))]
        if len(train)<30: continue
        models={}; bridges={}
        for i,e in enumerate(IDS):
            x=[c['rows'][i]['x'] for c in train]; y=[c['rows'][i]['y'] for c in train]
            models[e]={}
            for name,factory in model_factories().items():
                models[e][name]=factory().fit(x,y)
            # Structural gas channel: one contemporaneous monthly change plus
            # regularized month effects. Other components use the nine-month mean.
            if e in ['CPI_GASOLINE','CPI_ENERGY','CPI_ALLITEMS']:
                features=[[c['gas_change'],*[float(int(c['target_month'][5:])==m) for m in range(1,13)]] for c in train]
                bridges[e]=make_pipeline(StandardScaler(),Ridge(alpha=10)).fit(features,y)
        fit_audit.append(dict(year=year,training_cases=len(train),last_resolution=max(c['resolved'] for c in train)))
        for case in test:
            points={name:[] for name in ['v8','mean3','mean6','mean9','median9','gas_bridge',*model_factories()]}
            for i,row in enumerate(case['rows']):
                e=row['entity']; values=row['history']; points['v8'].append(row['baseline'][0])
                for name,n in [('mean3',3),('mean6',6),('mean9',9)]: points[name].append(float(np.mean(values[-n:])))
                points['median9'].append(float(np.median(values)))
                bf=[case['gas_change'],*[float(int(case['target_month'][5:])==m) for m in range(1,13)]]
                points['gas_bridge'].append(float(bridges[e].predict([bf])[0]) if e in bridges else float(np.mean(values)))
                for name,model in models[e].items(): points[name].append(float(model.predict([row['x']])[0]))
            predictions.append(dict(case=case,points=points))
        print(json.dumps(fit_audit[-1]),flush=True)
    write(ROOT/'prequential-predictions.json',predictions)
    records=[]
    for item in predictions:
        case=item['case']; rows=case['rows']
        if case['target_month']<'2007-01':continue
        y=[r['y'] for r in rows]; naive=[float(np.mean(r['history'][-3:])) for r in rows]
        previous=[p for p in predictions if p['case']['resolved']<case['cutoff']][-36:]
        for name,points in item['points'].items():
            variants=['original'] if name=='v8' else ['v8_width','causal_width']
            for variant in variants:
                widths=[]
                for i,row in enumerate(rows):
                    errors=[p['case']['rows'][i]['y']-p['points'][name][i] for p in previous]
                    widths.append(max(.05,half_width(errors,1.)) if variant=='causal_width' and len(errors)>=24 else row['baseline'][1])
                metric=score('regression',IDS,y,points,widths,naive,[1.]*len(rows))
                records.append(dict(month=case['target_month'],block=case['block'],
                                    method=name if name=='v8' else name+'_'+variant,score=metric['composite'],
                                    mae=float(np.mean(np.abs(np.array(y)-points))),coverage=metric['interval_coverage'],
                                    points=points,widths=widths,y=y))
    methods={}; blocks=sorted({r['block'] for r in records})
    baseline={b:np.mean([r['score'] for r in records if r['block']==b and r['method']=='v8']) for b in blocks}
    for name in sorted({r['method'] for r in records}):
        own=[r for r in records if r['method']==name]
        differences=[np.mean([r['score'] for r in own if r['block']==b])-baseline[b] for b in blocks]
        methods[name]=dict(mean=float(np.mean([r['score'] for r in own])),versus_v8=interval(differences),
                           mae=float(np.mean([r['mae'] for r in own])),coverage=float(np.mean([r['coverage'] for r in own])),
                           component_mae={e:float(np.mean([abs(r['y'][i]-r['points'][i]) for r in own])) for i,e in enumerate(IDS)})
    best=max((m for m in methods if m!='v8'),key=lambda m:methods[m]['mean'])
    out=dict(split='development',rankable=False,eligible_for_submission_gate=False,
             cases=len({r['month'] for r in records}),entities=IDS,methods=methods,best_development=best,
             annual_fits=fit_audit,rows=records,exclusions=excluded,code_sha256=sha(__file__),
             plan_sha256=sha('research/v11/plan.json'),dataset_sha256=sha(ROOT/'dataset.json'),
             confirmation_opened=False,limitations=json.loads(Path('research/v11/plan.json').read_text())['limitations'])
    write(ROOT/'development.json',out)
    print(json.dumps(dict(cases=out['cases'],best=best,baseline=methods['v8'],candidate=methods[best])),flush=True)


if __name__=='__main__':run()
