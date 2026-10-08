"""V17: preserve V11 experts, add compact HGB and literal-bound EPS guidance."""
from __future__ import annotations
import argparse,datetime as dt,json,re,tempfile
from pathlib import Path
from agent_submit_v11.cli import run as baseline_run
from agent_submit_v7.eps import latest_pair
from agent_submit import cli as v6
from agent_v2.indexer import build_index
from .numeric import predict as numerical,MODEL_PATH
from .guidance import forecast as guidance
from .routing import canonicalize

def run(task_path,corpus_dir,out_path):
 original=json.loads(task_path.read_text());task,route=canonicalize(original)
 if task is original:answer=baseline_run(task_path,corpus_dir,out_path)
 else:
  with tempfile.TemporaryDirectory(prefix='t4-spec-') as folder:
   canonical=Path(folder)/'task.json';canonical.write_text(json.dumps(task));answer=baseline_run(canonical,corpus_dir,out_path)
 name=task.get('target',{}).get('name');kind=task.get('target_type') or task.get('target',{}).get('type')
 if name not in ['eps_yoy_growth_pct','eps_yoy_direction']:return answer
 try:cutoff=dt.date.fromisoformat(task['cutoff_date'])
 except (ValueError,TypeError):return answer
 artifact=json.loads(MODEL_PATH.read_text())
 if cutoff.isoformat()<artifact['available_after']:return answer
 corpus=build_index(corpus_dir);bindings=v6.bindings_for(corpus_dir);trace=json.loads(answer['evidence_trace']);trace.update(candidate='v17-corpus-and-compact',semantic_route=route,neural_calls=0)
 for entity,pred,details in zip(task['entities'],answer['entity_predictions'],trace['entities']):
  allowed=v6.allowed_docs(task,entity,corpus,bindings);prior=v6.number(entity.get('prior_year_q_eps'))
  if prior is None or name=='eps_yoy_growth_pct' and prior==0:continue
  dates=re.findall(r'\d{4}-\d{2}-\d{2}',str(entity.get('quarter_reported','')))
  if len(dates)!=1:continue
  try:target=dt.date.fromisoformat(dates[0])
  except ValueError:continue
  if not cutoff-dt.timedelta(days=120)<=target<=cutoff+dt.timedelta(days=120):continue
  pair=latest_pair(task,corpus,allowed);estimate=None;expert=None
  if pair and 45<=(target-dt.date.fromisoformat(pair.period)).days<=150:
   row=dict(eps=[pair.current,None,None,prior,pair.previous_year,None,None,None],prior=prior,scale=1.,metrics={},split_warning=False)
   chosen=numerical(row,entity,cutoff.isoformat(),artifact)
   if chosen:estimate,expert=chosen
  guided=guidance(task,entity,corpus,allowed)
  if guided:estimate=guided['value'];expert='source-guidance'
  if estimate is None:continue
  # Match the fixed-V11-interval research comparisons, without calibration on public tasks.
  width=(pred['interval']['hi']-pred['interval']['lo'])/2
  point=100*(estimate-prior)/abs(prior) if name=='eps_yoy_growth_pct' else estimate
  pred.update(point_forecast=point,interval=dict(level=task.get('interval_level',.9),lo=point-width,hi=point+width))
  if kind=='classification':pred['label']='up' if estimate>=prior else 'down'
  details.update(route='eps-v17-'+expert,forecast_eps=estimate,model='eps_models.json' if expert!='source-guidance' else 'deterministic-source-range',neural_calls=0)
  if guided:
   pred['claims']=pred['claims'][:1]+guided['claims'];details['guidance']={k:v for k,v in guided.items() if k!='claims'}
 answer['evidence_trace']=json.dumps(trace);out_path.write_text(json.dumps(answer,indent=2,allow_nan=False)+'\n');return answer

def main():
 p=argparse.ArgumentParser();p.add_argument('verb',nargs='?',choices=['analyze'],default='analyze');p.add_argument('--task',type=Path,required=True);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.task,a.corpus,a.out)
if __name__=='__main__':main()
