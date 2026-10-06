"""Version-pinned numeric scoring and dependence-aware research intervals."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from qfbench2_track_analysis.alignment import EntityRoster, align_predictions
from qfbench2_track_analysis.scoring import SCORER_VERSION, ScoringParams, _composite

def write(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def score(kind, ids, y, points, widths, naive_points, naive_widths, labels=None, naive_labels=None, true_labels=None):
    assert SCORER_VERSION == '5.2.2'
    target = dict(type=kind, name='historical_analogue')
    if kind == 'classification': target['labels'] = ['up', 'down']
    task = dict(task_id='v10-local', target=target, entities=[dict(entity_id=x, name=x) for x in ids])
    roster = EntityRoster.from_task(task)
    def answer(p, w, lab):
        # Alignment requires a claim even for the numeric-only API. This explicit
        # preview marker is NOT a source citation; no faithfulness/NLI score is claimed.
        marker=dict(claim='Numeric research preview; evidence is not scored.',
                    doc_id='NUMERIC_PREVIEW_NOT_SUBMITTABLE',span_start=0,span_end=49)
        rows = [dict(entity_id=e, point_forecast=float(a), interval=dict(level=.9,lo=float(a-b),hi=float(a+b)), claims=[marker])
                for e,a,b in zip(ids,p,w)]
        if lab is not None:
            for row,label in zip(rows,lab): row['label']=label
        return align_predictions(dict(entity_predictions=rows), roster, target_type=kind, interval_level=.9)
    actual = dict(outcomes=[dict(entity_id=e, y=float(value), **({'true_label': label} if true_labels is not None else {}))
                            for e,value,label in zip(ids,y,true_labels if true_labels is not None else [None]*len(ids))])
    return _composite(answer(points,widths,labels), actual,
                      ScoringParams(kind,.9,.8,.5,(.7,.3),interval_leg=kind!='classification'), roster,
                      naive_aligned=answer(naive_points,naive_widths,naive_labels))

def interval(blocks):
    # Each observation is a paired calendar-quarter mean, never an entity draw.
    values=np.asarray(blocks,float); rng=np.random.default_rng(10); n=len(values)
    starts=rng.integers(0,n,size=(20000,(n+1)//2))
    idx=np.stack([starts,(starts+1)%n],axis=-1).reshape(20000,-1)[:,:n]
    draws=values[idx].mean(axis=1)
    single=values[rng.integers(0,n,size=(20000,n))].mean(axis=1)
    return dict(delta=float(values.mean()),ci95=np.quantile(draws,[.025,.975]).tolist(),
                single_quarter_ci95=np.quantile(single,[.025,.975]).tolist(),quarter_blocks=n)
