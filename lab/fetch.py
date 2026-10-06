"""Small official-source downloads; every response is hashed, never silently replaced."""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.request

UA = 'iMak AI Lab research (https://github.com/antonno5)'


def fetch_one(root, name, url):
    dest = root / name
    meta = root / (name + '.meta.json')
    if dest.exists() and meta.exists():
        record = json.loads(meta.read_text())
        assert hashlib.sha256(dest.read_bytes()).hexdigest() == record['sha256']
        return record
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    record = dict(file=name, url=url, sha256=hashlib.sha256(data).hexdigest(),
                  retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat(), bytes=len(data),
                  source='US Department of the Treasury', vintage_certified=False)
    dest.write_bytes(data)
    meta.write_text(json.dumps(record, indent=2) + '\n')
    print(name, len(data), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--end-year', type=int, default=2025)
    args = parser.parse_args()
    raw = args.root / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    jobs = []
    for year in range(2013, args.end_year + 1):
        jobs.append((raw, f'yields-{year}.xml', 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=' + str(year)))
        for kind in ['Note', 'Bond']:
            jobs.append((raw, f'auctions-{kind}-{year}.json', f'https://www.treasurydirect.gov/TA_WS/securities/search?startDate=01/01/{year}&endDate=12/31/{year}&format=json&type={kind}'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda job: fetch_one(*job), jobs))
    (args.root / 'sources.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    main()
