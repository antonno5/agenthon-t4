"""Download public SEC facts with source hashes; never package them in the agent."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
import urllib.request


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--units', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    ciks = {'0000200406': 'JNJ', '0000021344': 'KO', '0000063908': 'MCD',
            '0000034088': 'XOM', '0000018230': 'CAT', '0000080424': 'PG',
            '0000789019': 'MSFT', '0001045810': 'NVDA'}
    for path in sorted(args.units.glob('*/task.json')):
        task = json.loads(path.read_text())
        if 'eps' not in task['target']['name'] and 'reaction' not in task['target']['name']:
            continue
        for e in task['entities']:
            if e.get('cik'):
                ciks[str(e['cik']).zfill(10)] = e['entity_id']
    records = []
    for cik, ticker in sorted(ciks.items()):
        url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
        dest = args.out / f'CIK{cik}.json'
        if not dest.exists():
            req = urllib.request.Request(url, headers={'User-Agent': 'Agenthon financial research antonnos local evaluation'})
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read(20000000)
            parsed = json.loads(data)
            assert str(parsed['cik']).zfill(10) == cik
            dest.write_bytes(data)
            time.sleep(.25)
        data = dest.read_bytes()
        records.append(dict(cik=cik, ticker=ticker, url=url, path=dest.name,
                            sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                            retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                            source='SEC public companyfacts XBRL API',
                            provenance_caveat='Current extraction, filter original filed dates and retain first-report targets; not archived API vintages'))
        print(ticker, len(data), flush=True)
        (args.out / 'sources.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    main()
