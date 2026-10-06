"""Official analyze contract; only eligible CPI units change the V8 answer."""
from __future__ import annotations
import argparse
import calendar
import datetime as dt
import json
from pathlib import Path
import re
import statistics as stats
from agent_submit import cli as v6
from agent_submit_v8 import cli as v8
from agent_v2.indexer import build_index
from .cpi import IDS,MODEL_PATH,forecasts


def shift(month,delta):
    y,m=map(int,month.split('-')); n=y*12+m-1+delta
    return f'{n//12:04d}-{n%12+1:02d}'


def cpi_inputs(task,corpus,bindings,artifact):
    name=task.get('target',{}).get('name','').lower()
    if 'cpi_component_mom' not in name or task.get('target',{}).get('type')!='regression':return None
    try:cutoff=dt.date.fromisoformat(str(task.get('cutoff_date','')))
    except ValueError:return None
    if str(cutoff)<artifact['available_after']:return None
    if cutoff.day!=calendar.monthrange(cutoff.year,cutoff.month)[1]:return None
    entities=task.get('entities',[]);month=str(cutoff)[:7]
    if len(entities)!=11 or {e.get('entity_id') for e in entities}!=set(IDS):return None
    if any(e.get('ref_month')!=month for e in entities):return None
    months=[shift(month,k) for k in range(-9,0)]
    history={};gas_rows={};gas_sources={}
    for entity in entities:
        allowed=v6.allowed_docs(task,entity,corpus,bindings);name=v6.norm(entity.get('name',''));values={}
        # Prefer the most recent admitted vintage; never splice future documents.
        for doc_id in sorted(allowed,key=lambda k:(corpus.doc_dates[k],k),reverse=True):
            for header,rows in v6.tables(corpus.doc_texts[doc_id],str(cutoff)):
                names=[v6.norm(c) for c in header]
                if name not in names:continue
                current={}
                for row in rows:
                    ref=row[0][:7]
                    if ref not in months:continue
                    value=v6.number(row[names.index(name)])
                    if value is None:return None
                    if ref in current and current[ref]!=value:return None
                    current[ref]=value
                if all(m in current for m in months):values=current;break
            if values:break
        if not values:return None
        history[entity['entity_id']]=[values[m] for m in months]
        # The gasoline source must be admitted for every component, not merely
        # present somewhere in the mounted corpus.
        this_gas={};sources={}
        for doc_id in allowed:
            for header,rows in v6.tables(corpus.doc_texts[doc_id],str(cutoff)):
                names=[v6.norm(c) for c in header]
                if 'usdpergallon' not in names or names[0]!='weekending':continue
                for row in rows:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',row[0]):return None
                    date=dt.date.fromisoformat(row[0])
                    if date>cutoff-dt.timedelta(days=2) or row[0][:7]<shift(month,-2):continue
                    price=v6.number(row[names.index('usdpergallon')])
                    if price is None or price<=0:return None
                    if row[0] in this_gas and this_gas[row[0]]!=price:return None
                    this_gas[row[0]]=price;sources[doc_id]=True
        if gas_rows and gas_rows!=this_gas:return None
        if not this_gas:return None
        gas_rows=this_gas;gas_sources=sources
    monthly={}
    for ref in [shift(month,-2),shift(month,-1),month]:
        values=[v for d,v in sorted(gas_rows.items()) if d[:7]==ref]
        if len(values)<3:return None
        monthly[ref]=stats.mean(values)
    current=[(d,v) for d,v in sorted(gas_rows.items()) if d[:7]==month]
    gas=(100*(monthly[month]/monthly[shift(month,-1)]-1),
         100*(monthly[shift(month,-1)]/monthly[shift(month,-2)]-1),100*(current[-1][1]/current[0][1]-1))
    return dict(history=history,month=cutoff.month,gas=gas,gas_sources=sorted(gas_sources))


def run(task_path,corpus_dir,out_path):
    answer=v8.run(task_path,corpus_dir,out_path)
    task=json.loads(task_path.read_text())
    if 'cpi_component_mom' not in task.get('target',{}).get('name','').lower():return answer
    artifact=json.loads(MODEL_PATH.read_text());corpus=build_index(corpus_dir)
    inputs=cpi_inputs(task,corpus,v6.bindings_for(corpus_dir),artifact)
    if inputs is None:return answer
    estimates=forecasts(inputs['history'],inputs['month'],inputs['gas'],artifact)
    trace=json.loads(answer['evidence_trace']);trace['candidate']='v11-cpi-frozen-guard';trace['neural_calls']=0
    for row,details in zip(answer['entity_predictions'],trace['entities']):
        entity=row['entity_id'];p,w=estimates[entity];entry=artifact['entities'][entity]
        row.update(point_forecast=p,interval=dict(level=task.get('interval_level',.9),lo=p-w,hi=p+w))
        details.update(route='cpi-frozen-pre2017-'+entry['method'],model='cpi_model.json',
                       calibration='frozen-36-pre2017-prequential-errors',gas_sources=inputs['gas_sources'])
        # Historical component quote is kept verbatim. Add the input-price table
        # as another exact quote so the new contemporaneous signal is evidenced.
        if entity in ['CPI_GASOLINE','CPI_ENERGY','CPI_ALLITEMS']:
            doc_id=inputs['gas_sources'][0];text=corpus.doc_texts[doc_id]
            match=re.search(r'(?m)^week_ending\s*\|\s*usd_per_gallon\s*$',text)
            if match:
                end=text.find('\n\n',match.start())
                end=len(text) if end<0 else end
                # The public source is a 44-week table; cite its last 10 rows
                # as one bounded exact span, without invented derived figures.
                lines=list(re.finditer(r'(?m)^\d{4}-\d{2}-\d{2}\s*\|[^\n]+',text[match.end():end]))[-10:]
                if lines:
                    start=match.end()+lines[0].start();stop=match.end()+lines[-1].end()
                    row['claims'].append(dict(doc_id=doc_id,span_start=start,span_end=stop,claim=text[start:stop]))
    answer['evidence_trace']=json.dumps(trace)
    out_path.write_text(json.dumps(answer,indent=2,allow_nan=False)+'\n')
    return answer


def main():
    p=argparse.ArgumentParser();p.add_argument('verb',nargs='?',choices=['analyze'],default='analyze')
    p.add_argument('--task',type=Path,required=True);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.task,a.corpus,a.out)


if __name__=='__main__':main()
