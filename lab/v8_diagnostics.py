"""Post-evaluation sensitivity checks; no model selection or forecast changes."""
from collections import Counter
from pathlib import Path
import numpy as np
from .v7_eps import read,write,sha

root=Path('/experiment');report=read(root/'reports/holdout-all.json');rows=report['rows']
blocks=sorted({r['block'] for r in rows})
def deltas(method,baseline,family=None):
    def mean(m,b):return np.mean([r['score'] for r in rows if r['method']==m and r['block']==b and (family is None or r['family']==family)])
    return np.array([mean(method,b)-mean(baseline,b) for b in blocks])

comparisons={}
for method,baseline in [('selected_by_family','v7'),('selected_by_family','v6'),('compact_huber','v7'),('compact_huber','v6'),
                        ('agent_selector','quant_ensemble'),('agent_quality','quant_ensemble'),('agent_guard','quant_ensemble')]:
    d=deltas(method,baseline);rng=np.random.default_rng(8)
    independent=rng.choice(d,size=(10000,len(d)),replace=True).mean(axis=1)
    # Circular moving blocks preserve neighboring-quarter dependence as a sensitivity.
    starts=rng.integers(0,len(d),size=(10000,(len(d)+1)//2))
    indices=np.stack([starts,(starts+1)%len(d)],axis=2).reshape(10000,-1)[:,:len(d)]
    moving=d[indices].mean(axis=1)
    comparisons[method+' vs '+baseline]=dict(delta=float(d.mean()),quarterly_ci95=np.quantile(independent,[.025,.975]).tolist(),
                                            two_quarter_block_ci95=np.quantile(moving,[.025,.975]).tolist(),
                                            positive_blocks=int((d>0).sum()),blocks=len(d),
                                            confirmatory=method=='selected_by_family' and baseline in ['v6','v7'])
features=read(root/'inputs/holdout.json');truth=read(root/'truth/holdout.json')
predictions=read(root/'predictions/holdout-all.json')
packets={p['id'] for f in (root/'packets/holdout').glob('batch-*.jsonl') for p in map(__import__('json').loads,f.read_text().splitlines())}
agent={}
for method in ['quant_ensemble','agent_selector','agent_quality','agent_guard']:
    chosen=[r for r in features if r['id'] in packets]
    correct=lambda r,m:('up' if predictions[r['id']][m]>=r['prior'] else 'down')==truth[r['id']]['true_label']
    agent[method]=dict(routed_accuracy=sum(correct(r,method) for r in chosen)/len(chosen),
                       changed_from_algorithm=sum(predictions[r['id']][method]!=predictions[r['id']]['quant_ensemble'] for r in chosen),
                       helped_direction=sum(correct(r,method) and not correct(r,'quant_ensemble') for r in chosen),
                       harmed_direction=sum(not correct(r,method) and correct(r,'quant_ensemble') for r in chosen))
write(root/'reports/sensitivity.json',dict(source_report_sha256=sha(root/'reports/holdout-all.json'),comparisons=comparisons,
                                         agent_routed_rows=len(packets),agent_routed=agent,
                                         posthoc=True,used_for_selection=False))
print(__import__('json').dumps(dict(comparisons=comparisons,agent_routed=agent)))
