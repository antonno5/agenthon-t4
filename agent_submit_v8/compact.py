"""Portable Huber inference; model parameters are fitted on pre-2015 data only."""
import json
from pathlib import Path
from .numeric import compact_row,vector,clip,FEATURES

def forecast(row,model=None):
    if model is None:model=json.loads(Path(__file__).with_name('compact_model.json').read_text())
    if model['features']!=FEATURES:raise ValueError('Model feature schema mismatch')
    row=compact_row(row);x=vector(row)
    if len(x)!=len(model['coef']):raise ValueError('Model feature length mismatch')
    delta=model['intercept']+sum(w*(v-m)/s for w,v,m,s in zip(model['coef'],x,model['mean'],model['scale']))
    return row['prior']+row['scale']*clip(delta)
