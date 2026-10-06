"""Download one registered pool. No adaptive choice based on financial values."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.error

p=argparse.ArgumentParser();p.add_argument('pool',choices=['additional_training','confirmation_a','confirmation_b']);args=p.parse_args()
plan=json.loads(Path('lab/v9_plan.json').read_text());raw=Path('test-output/v9/raw')/args.pool;raw.mkdir(parents=True,exist_ok=True)
records=[];failed=[]
for n,company in enumerate(plan['pools'][args.pool]):
    cik=company['cik'];url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json';path=raw/f'CIK{cik}.json'
    try:
        if not path.exists():
            req=urllib.request.Request(url,headers={'User-Agent':'Agenthon financial research antonnos local evaluation'})
            with urllib.request.urlopen(req,timeout=60) as r:content=r.read(25000000)
            assert str(json.loads(content)['cik']).zfill(10)==cik
            path.write_bytes(content);time.sleep(.3)
        content=path.read_bytes();obj=json.loads(content)
        records.append(dict(company,path=path.name,url=url,entity_name=obj['entityName'],sha256=hashlib.sha256(content).hexdigest(),retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat()))
    except (OSError,ValueError,AssertionError) as error:
        failed.append(dict(company,error=type(error).__name__,status=getattr(error,'code',None)))
    (raw/'sources.json').write_text(json.dumps(records,indent=2)+'\n');(raw/'failures.json').write_text(json.dumps(failed,indent=2)+'\n')
    if n%10==0 or n==len(plan['pools'][args.pool])-1:print(args.pool,n+1,'downloaded',len(records),'failed',len(failed),flush=True)
