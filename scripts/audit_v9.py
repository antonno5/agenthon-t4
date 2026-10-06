"""Check saved provenance without fitting or choosing any additional candidate."""
import hashlib
import json
from pathlib import Path

root=Path('test-output/v9')
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan=read(Path('lab/v9_plan.json'))
bciks={x['cik'] for x in plan['pools']['confirmation_b']}
assert len(bciks)==100
model_metadata={};training_configs={}
for stage in ['r4','r5','r6','r7']:
    p=root/stage;config=read(p/'training-pools.json');training_configs[stage]=config
    for pool in config['pools']:
        rs=read(p/'inputs'/f'{pool}.json')
        assert not bciks.intersection(r['cik'] for r in rs)
    for year in range(2015,2022):
        m=read(p/'models'/f'{year}.json')
        assert m['latest_target_publication']<f'{year}-01-01'
        assert m['model_sha256']==sha(p/'models'/f'{year}.joblib')
        model_metadata[f'{stage}/{year}']=m
confirmations={}
for pool,stage in [('confirmation_a','r6'),('confirmation_b','r7')]:
    p=root/stage;report=read(p/'reports'/f'{pool}.json');selection=read(p/f'selection-{pool}.json')
    assert report['prediction_sha256']==selection['prediction_sha256']==sha(p/'predictions'/f'{pool}.json')
    assert selection['evaluation_code_sha256']==sha(Path('lab/v9_evaluate.py'))
    assert selection['development_selection_sha256']==sha(p/'development-selection-ci.json')
    assert selection['plan_sha256']==sha(p/'plan.json')
    rows=read(root/'r4/inputs'/f'{pool}.json');truth=read(root/'truth'/f'{pool}.json')
    assert len(rows)==len({r['id'] for r in rows})
    for r in rows:assert r['cutoff']<truth[r['id']]['available']<='2021-12-31'
    assert all(0<=x['score']<=1 for x in report['rows'])
    answers=list((p/'answers'/pool).glob('*/*/*.json'))
    assert len(answers)==len(report['rows'])==27*2*3
    confirmations[pool]=dict(rows=len(rows),companies=len({r['cik'] for r in rows}),full_scored_answers=len(answers),
        input_sha256=sha(root/'r4/inputs'/f'{pool}.json'),truth_sha256=sha(root/'truth'/f'{pool}.json'),
        prediction_sha256=selection['prediction_sha256'],report_sha256=sha(p/'reports'/f'{pool}.json'),
        selection_sha256=sha(p/f'selection-{pool}.json'),target_met=report['target_met'])
out=dict(training_configs=training_configs,models=model_metadata,confirmations=confirmations,
         no_confirmation_b_training_companies=True,annual_publication_cutoffs_valid=True,
         models_match_hashes=True,predictions_and_selection_match_hashes=True,
         paired_quarters=27,bootstrap_draws=20000,seed=9,no_codabench_submission=True)
Path('research/v9/provenance-audit.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(confirmations,indent=2))
