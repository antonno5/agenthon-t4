"""Deployable compact research candidate with V7 fallback for other targets."""
from __future__ import annotations
import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
from agent_v2.indexer import build_index
from agent_v2.retriever import BM25Index
from agent_submit import cli as v6
from agent_submit_v7 import cli as v7
from agent_submit_v7.eps import latest_pair
from .compact import forecast

def predict(task,entity,corpus,allowed):
    prediction,route,ncal,preferred,details=v7.predict(task,entity,corpus,allowed)
    name=task['target']['name'].lower()
    if 'eps' not in name or not any(k in name for k in ['growth','direction']):return prediction,route,ncal,preferred,details
    prior=v6.number(entity.get('prior_year_q_eps'));pair=latest_pair(task,corpus,allowed)
    if pair is None or prior is None:return prediction,route,ncal,preferred,details
    dates=re.findall(r'\d{4}-\d{2}-\d{2}',str(entity.get('quarter_reported','')))
    lag=(dt.date.fromisoformat(dates[-1])-dt.date.fromisoformat(pair.period)).days if dates else 90
    if not 45<=lag<=150:return prediction,route,ncal,preferred,details
    row=dict(eps=[pair.current,None,None,prior,pair.previous_year,None,None,None],prior=prior,
             scale=1.,metrics={},split_warning=False)
    estimate=forecast(row)
    if 'growth' in name:
        if not prior:return prediction,route,ncal,preferred,details
        point=100*(estimate-prior)/abs(prior);width=max(50.,abs(point)*.5)
    else:
        point=estimate;width=max(.5,abs(estimate)*.5)
        prediction['label']='up' if estimate>=prior else 'down'
    prediction.update(point_forecast=point,interval=dict(level=task.get('interval_level',.9),lo=point-width,hi=point+width))
    details.update(forecast_eps=estimate,model='compact-huber-pre2015',neural_calls=0)
    return prediction,'eps-compact-huber',306,(pair.doc_id,pair.start,pair.end),details

def run(task_path,corpus_dir,out_path):
    task=json.loads(task_path.read_text());corpus=build_index(corpus_dir)
    index=BM25Index(corpus.chunks,task['cutoff_date']);bindings=v6.bindings_for(corpus_dir)
    predictions=[];trace=[];kind=task.get('target_type') or task['target']['type']
    for entity in task['entities']:
        allowed=v6.allowed_docs(task,entity,corpus,bindings)
        if not allowed:raise ValueError('No admitted pre-cutoff evidence')
        pred,route,ncal,preferred,details=predict(task,entity,corpus,allowed)
        if kind!='classification':pred.pop('label',None)
        pred['entity_id']=entity['entity_id'];pred['claims']=[v6.evidence(task,entity,corpus,index,allowed,preferred)]
        predictions.append(pred);trace.append(dict(entity_id=entity['entity_id'],route=route,calibration_examples=ncal,**details))
    answer=dict(task_id=task['task_id'],schema_version='3',target_type=kind,entity_predictions=predictions,
                evidence_trace=json.dumps(dict(candidate='v8-compact-research',neural_calls=0,entities=trace)))
    out_path.parent.mkdir(parents=True,exist_ok=True);out_path.write_text(json.dumps(answer,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(rows=len(predictions),neural_calls=0,routes=dict(Counter(t['route'] for t in trace)))))
    return answer

def main():
    p=argparse.ArgumentParser();p.add_argument('verb',nargs='?',choices=['analyze'],default='analyze')
    p.add_argument('--task',type=Path,required=True);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.task,a.corpus,a.out)

if __name__=='__main__':main()
