"""Target-name/family transfer and pre-availability integration checks."""
import contextlib,copy,hashlib,io,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent_submit_v17.cli import run
from agent_submit_v11.cli import run as old_run
U=Path(sys.argv[1]);OUT=Path(sys.argv[2]);OUT.mkdir(parents=True,exist_ok=True);records=[]
for unit in sorted(U.glob('t4-*')):
 if not (unit/'task.json').exists():continue
 original=json.loads((unit/'task.json').read_text())
 with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
  p=Path(folder);base=run(unit/'task.json',unit/'corpus',p/'base.json');alias=copy.deepcopy(original);alias['target']['name']='opaque_target';(p/'task.json').write_text(json.dumps(alias));changed=run(p/'task.json',unit/'corpus',p/'alias.json')
 assert changed['entity_predictions']==base['entity_predictions'];records.append(dict(unit=unit.name,target_name_alias_parity=True))
(OUT/'alias-validation.json').write_text(json.dumps(dict(passed=len(records),records=records),indent=2)+'\n');print('Typed alias replay',len(records),'passed')
