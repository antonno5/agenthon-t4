"""Portable numerical CPI forecasts: no scientific runtime or network access."""
from __future__ import annotations
import json
import math
from pathlib import Path
import statistics as stats
from agent_submit.cli import mean_forecast
from agent_submit_v7.series import level_forecast

IDS=['CPI_ALLITEMS','CPI_APPAREL','CPI_CORE','CPI_ENERGY','CPI_FOOD','CPI_GASOLINE',
     'CPI_MEDICAL','CPI_NEWVEH','CPI_SHELTER','CPI_TRANSPSVC','CPI_USEDCARS']
MODEL_PATH=Path(__file__).with_name('cpi_model.json')


def array_mean(values):
    # Match NumPy's <=9-element float64 reduction used by training. Python's
    # statistics.mean and newer sum use different rounding. At a tree threshold
    # one ULP can otherwise send a valid input down a different branch.
    n=len(values)
    if not 1<=n<=9:raise ValueError('Unexpected feature window')
    if n<8:
        total=-0.0
        for value in values:total+=value
    else:
        total=((values[0]+values[1])+(values[2]+values[3]))+((values[4]+values[5])+(values[6]+values[7]))
        for value in values[8:]:total+=value
    return total/n


def features(history,entity,month,gas_change,gas_prior_change,gas_trend):
    values=history[entity]
    if len(values)!=9 or any(not math.isfinite(v) for row in history.values() for v in row):
        raise ValueError('CPI requires nine finite observations per component')
    mean=array_mean(values);deviations=[v-mean for v in values]
    std=math.sqrt(array_mean([v*v for v in deviations]))
    return [*values[-3:],array_mean(values[-3:]),array_mean(values[-6:]),mean,
            stats.median(values),std,gas_change,gas_prior_change,gas_trend,
            array_mean(history['CPI_CORE'][-3:]),array_mean(history['CPI_ENERGY'][-3:]),
            *[float(month==m) for m in range(1,13)]]


def model_point(model,x):
    if model['kind']=='linear':
        if len(x)!=len(model['weights']):raise ValueError('Feature shape mismatch')
        return model['intercept']+sum(a*b for a,b in zip(x,model['weights']))
    if model['kind']=='boost':
        value=model['baseline']
        for tree in model['trees']:
            index=0
            while not tree[index]['leaf']:
                node=tree[index];index=node['left'] if x[node['feature']]<=node['threshold'] else node['right']
            value+=tree[index]['value']
        return value
    raise ValueError('Unknown model kind')


def point(method,history,entity,month,gas,model=None):
    values=history[entity]
    if method=='v8':
        fallback=max(.2,stats.pstdev(values)*2)
        p,_,_=mean_forecast(values,3,fallback);selected,_=level_forecast(values,'mean3',fallback)
        return selected[0] if selected else p
    if method.startswith('mean'):return stats.mean(values[-int(method[4:]):])
    if method=='median9':return stats.median(values)
    if method=='gas_bridge':
        if entity not in ['CPI_GASOLINE','CPI_ENERGY','CPI_ALLITEMS']:return stats.mean(values)
        x=[gas[0],*[float(month==m) for m in range(1,13)]]
    else:x=features(history,entity,month,*gas)
    return model_point(model,x)


def forecasts(history,month,gas,artifact=None):
    artifact=artifact or json.loads(MODEL_PATH.read_text())
    if set(history)!=set(IDS):raise ValueError('Unexpected CPI roster')
    if not 1<=month<=12 or len(gas)!=3 or any(not math.isfinite(v) for v in gas):raise ValueError('Invalid monthly inputs')
    result={}
    for entity in IDS:
        entry=artifact['entities'][entity]
        p=point(entry['method'],history,entity,month,gas,entry.get('model'));w=entry['width']
        if not math.isfinite(p) or not math.isfinite(w) or w<=0:raise ValueError('Invalid CPI forecast')
        result[entity]=(p,w)
    return result
