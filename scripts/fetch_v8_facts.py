"""Fetch the pre-registered company list, without looking at target outcomes."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
import urllib.request

root = Path('test-output/v8-analyst')
raw = root / 'raw'
raw.mkdir(parents=True, exist_ok=True)
plan = json.loads(Path('lab/v8_plan.json').read_text())
records = []
for ticker, cik in plan['companies'].items():
    url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
    path = raw / f'CIK{cik}.json'
    if not path.exists():
        req = urllib.request.Request(url, headers={'User-Agent': 'Agenthon financial research antonnos local evaluation'})
        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read(25000000)
        assert str(json.loads(content)['cik']).zfill(10) == cik
        path.write_bytes(content)
        time.sleep(.3)
    content = path.read_bytes()
    obj = json.loads(content)
    records.append(dict(ticker=ticker, cik=cik, path=path.name, url=url,
                        entity_name=obj['entityName'], sha256=hashlib.sha256(content).hexdigest(),
                        retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat()))
    (raw/'sources.json').write_text(json.dumps(records, indent=2)+'\n')
    print(ticker, obj['entityName'], len(content), flush=True)
