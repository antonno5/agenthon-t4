"""Development-only analyst routing: retain V8 unless past errors justify a switch.

This follow-up was designed after looking at the first V11 development results.
Its intervals are descriptive, never a new independent confirmation.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import numpy as np
from agent_submit.cli import half_width
from .v10_common import score, interval, write, sha
from .v11_cpi_parse import ROOT, IDS


def run():
    source=ROOT/'prequential-predictions.json'; predictions=json.loads(source.read_text())
    routed=[]; records=[]; routes=[]
    for current in predictions:
        case=current['case']; past=[p for p in predictions if p['case']['resolved']<case['cutoff']][-36:]
        points={'physical':[],'online_guard':[]}; selection=[]
        for i,e in enumerate(IDS):
            physical='huber' if e in ['CPI_GASOLINE','CPI_ENERGY','CPI_ALLITEMS'] else 'v8'
            points['physical'].append(current['points'][physical][i])
            selected='v8'; best='v8'; gain=0.; se=None
            if len(past)>=24:
                errors={m:np.array([abs(p['case']['rows'][i]['y']-p['points'][m][i]) for p in past]) for m in current['points']}
                best=min(errors,key=lambda m:(errors[m].mean(),m!='v8',m))
                diff=errors['v8']-errors[best]; gain=float(diff.mean()); se=float(diff.std(ddof=1)/math.sqrt(len(diff)))
                if gain>max(se,1e-12):selected=best
            points['online_guard'].append(current['points'][selected][i])
            selection.append(dict(entity=e,selected=selected,best=best,mae_gain=gain,se=se,completed_origins=len(past)))
        routed.append(dict(case=case,points=points))
        if case['target_month']<'2007-01':continue
        routes.append(dict(month=case['target_month'],selection=selection))
        y=[r['y'] for r in case['rows']]; naive=[float(np.mean(r['history'][-3:])) for r in case['rows']]
        calibration=[p for p in routed if p['case']['resolved']<case['cutoff']][-36:]
        for name,pp in points.items():
            for variant in ['v8_width','causal_width']:
                ww=[]
                for i,row in enumerate(case['rows']):
                    errors=[p['case']['rows'][i]['y']-p['points'][name][i] for p in calibration]
                    ww.append(max(.05,half_width(errors,1.)) if variant=='causal_width' and len(errors)>=24 else row['baseline'][1])
                metric=score('regression',IDS,y,pp,ww,naive,[1.]*len(IDS))
                records.append(dict(month=case['target_month'],block=case['block'],method=name+'_'+variant,
                                    score=metric['composite'],mae=float(np.mean(np.abs(np.array(y)-pp))),
                                    coverage=metric['interval_coverage'],points=pp,widths=ww,y=y))
    original=json.loads((ROOT/'development.json').read_text())
    baseline=[r for r in original['rows'] if r['method']=='v8'];blocks=sorted({r['block'] for r in baseline});methods={}
    for name in sorted({r['method'] for r in records}):
        own=[r for r in records if r['method']==name]
        delta=[np.mean([r['score'] for r in own if r['block']==b])-np.mean([r['score'] for r in baseline if r['block']==b]) for b in blocks]
        methods[name]=dict(mean=float(np.mean([r['score'] for r in own])),versus_v8=interval(delta),
                           mae=float(np.mean([r['mae'] for r in own])),coverage=float(np.mean([r['coverage'] for r in own])),
                           component_mae={e:float(np.mean([abs(r['y'][i]-r['points'][i]) for r in own])) for i,e in enumerate(IDS)})
    out=dict(split='development_followup',rankable=False,eligible_for_submission_gate=False,confirmation_opened=False,
             methods=methods,rows=records,selection_trace=routes,source_sha256=sha(source),code_sha256=sha(__file__),
             limitations=original['limitations']+['Hypotheses informed by first development results; intervals are not independent confirmation',
                 'Routing uses up to 36 completed historical forecast errors available before each cutoff. A deployment needs frozen pre-cutoff calibration state; the supplied nine-month corpus cannot reconstruct this state alone. No deployable V11 artifact is exported.'])
    write(ROOT/'routing-development.json',out);print(json.dumps(methods),flush=True)


if __name__=='__main__':run()
