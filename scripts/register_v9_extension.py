"""Use every still-unassigned company for training, preserving both sealed pools."""
import csv,json,hashlib
from pathlib import Path
root=Path('test-output/v9');plan=json.loads((root/'plan.json').read_text())
used={s['cik'] for s in plan['old_sources']}
for pool in plan['pools'].values():used.update(s['cik'] for s in pool)
companies={}
for r in csv.DictReader((root/'raw/universe.csv').open()):
    cik=r['CIK'].zfill(10)
    if cik not in used:companies[cik]=dict(cik=cik,ticker=r['Symbol'],name=r['Security'],sector=r['GICS Sector'])
obj=dict(amendment='Training-only expansion before either confirmation pool is downloaded or evaluated',
         parent_plan_sha256=hashlib.sha256((root/'plan.json').read_bytes()).hexdigest(),
         companies=sorted(companies.values(),key=lambda r:r['cik']),
         selection_rule='All remaining unassigned CIKs in the already frozen universe; no financial-result selection',
         unchanged=['confirmation A/B company membership','2015-2021 evaluation period','V7 comparator','official metric','CI target','two-look confidence adjustment'])
dest=Path('lab/v9_training_extension.json')
if dest.exists():raise RuntimeError('Extension already registered')
dest.write_text(json.dumps(obj,indent=2)+'\n');(root/'training-extension.json').write_text(dest.read_text())
print('Additional training CIKs',len(companies))
