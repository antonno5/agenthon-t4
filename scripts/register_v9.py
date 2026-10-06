"""Register disjoint company pools before any new financial outcomes are fetched."""
import csv
import hashlib
import json
from pathlib import Path
from collections import Counter

root=Path('test-output/v9');universe=root/'raw/universe.csv'
old={}
for folder in ['test-output/v7-eps/raw','test-output/v8-analyst/raw']:
    for s in json.loads((Path(folder)/'sources.json').read_text()):old[s['cik']]=dict(s,raw_folder=folder)
fresh={}
for r in csv.DictReader(universe.open()):
    cik=r['CIK'].zfill(10)
    if cik not in old and cik not in fresh:
        fresh[cik]=dict(cik=cik,ticker=r['Symbol'],name=r['Security'],sector=r['GICS Sector'])
ordered=sorted(fresh.values(),key=lambda r:hashlib.sha256(('v9-fixed-pools-20261006:'+r['cik']).encode()).hexdigest())
assert len(ordered)>=300
pools=dict(additional_training=ordered[:100],confirmation_a=ordered[100:200],confirmation_b=ordered[200:300])
plan=dict(version='v9-1',target='lower confidence bound of mean EPS composite improvement >= 0.10 versus frozen V7',
          baseline='V7 seasonal half-difference; V6 remains scorer reference; V8 comparisons secondary',
          metric='Unchanged official 5.2.2, equal-weight EPS direction and EPS growth, same calendar-quarter tasks and inclusion rules as V8',
          seed=9,universe_url='https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv',
          universe_sha256=hashlib.sha256(universe.read_bytes()).hexdigest(),old_sources=list(old.values()),pools=pools,
          development='Existing 69-company pool, 2015-2021. All earlier V7/V8 test outcomes are now development data, never fresh confirmation.',
          training='Existing and additional-training companies only. Expanding annual models; target publication strictly before January 1 of each forecast year. All features filed by origin. New confirmation companies excluded from training at every date.',
          confirmation='Companies assigned by seeded SHA256 before downloading outcomes. 2015-2021 targets first filed by 2021-12-31. No exclusions based on errors. Same data eligibility rules as V8.',
          hypotheses=['larger causal training set','EPS-level and growth-weighted regression','past-error interval calibration','simple numeric model ensembles','compact vs richer financial features'],
          selection='Select algorithms on development only; freeze prediction source/model hashes and all predictions before scoring each confirmation pool. Do not open confirmation until development lower bound >= .10 or a documented exhausted-search decision.',
          confidence=dict(primary='paired calendar-quarter bootstrap',draws=20000,
                          standard='two-sided 95% interval reported',
                          sequential='At most two confirmation looks. Each uses two-sided 97.5% interval (Bonferroni family coverage >=95%). Success requires its lower bound >=.10. If A fails, it becomes development; B remains untouched.',
                          sensitivity='circular moving blocks of two adjacent quarters; report without changing primary metric'),
          no_codabench_submission=True,
          limitations=['Only EPS families, not full track','Current constituent universe has survivorship bias','Current SEC API filtered by original filed dates, not archived API vintages','Exact-quote judge, no production NLI','27 or fewer calendar-quarter blocks; firms and dates can remain dependent'])
dest=Path('lab/v9_plan.json')
if dest.exists():raise RuntimeError('Plan already registered')
dest.write_text(json.dumps(plan,indent=2)+'\n')
(root/'plan.json').write_text(dest.read_text())
print(json.dumps(dict(old_companies=len(old),pools={k:dict(rows=len(v),sectors=dict(Counter(r['sector'] for r in v))) for k,v in pools.items()},plan_sha256=hashlib.sha256(dest.read_bytes()).hexdigest())))
