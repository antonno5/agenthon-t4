"""Fetch original BLS releases through their next-release announcements.

The crawl is bounded by publication date and cannot open reserved target months.
No index metadata or today's revised CPI series is substituted for a release.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request

ROOT = Path('test-output/v11-cpi')
BASE = 'https://fraser.stlouisfed.org/files/docs/publications/bls/newsreleases/cpi/'
MONTHS = '|'.join(['January','February','March','April','May','June','July','August','September','October','November','December'])
DATE = re.compile(r'\b(' + MONTHS + r')\s+(\d{1,2}),?\s+(\d{4})\b', re.I)
SHORT_DATE = re.compile(r'\b(' + MONTHS + r')\s+(\d{1,2})(?:,?\s+(\d{4}))?\b', re.I)
# Official post-shutdown calendar, verified before development scoring:
# https://www.bls.gov/bls/updated_release_schedule.htm
RESCHEDULED = {'2013-10-16':'2013-10-30','2013-11-15':'2013-11-20'}


def dates(text):
    return [dt.datetime.strptime(' '.join(m.groups()), '%B %d %Y').date() for m in DATE.finditer(text)]


def publication(text):
    candidates = dates(' '.join(text[:1600].split()))
    if not candidates:
        raise ValueError('No publication date in embargo header')
    return candidates[0]


def next_release(text, current):
    flat = ' '.join(text.split())
    matches = re.finditer(r'Consumer Price Index(?: data)?[^.]{0,100}(?:scheduled|will be released)', flat, re.I)
    # Only the first date attached to the CPI announcement. A nearby notice may
    # announce seasonal-factor revisions on a different day.
    candidates=[]
    for match in matches:
        d=SHORT_DATE.search(flat[match.end():match.end()+150])
        if d is None:continue
        month=dt.datetime.strptime(d[1],'%B').month
        # Some releases omit the year in the next monthly announcement. Infer
        # only the adjacent calendar year and retain the 45-day sanity bound.
        year=int(d[3]) if d[3] else current.year+int(month<current.month)
        following=dt.date(year,month,int(d[2]))
        if current < following <= current+dt.timedelta(days=45):candidates.append(following)
    if not candidates:
        raise ValueError('No unambiguous next-release announcement')
    if len(set(candidates)) != 1:
        raise ValueError(f'Conflicting next-release dates: {candidates}')
    return candidates[0]


def fetch(current):
    folder = ROOT/'sources'; folder.mkdir(parents=True, exist_ok=True)
    pdf = folder/f'cpi_{current:%Y%m%d}.pdf'; txt = pdf.with_suffix('.txt')
    url = BASE + pdf.name
    if not pdf.exists():
        last = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent':'historical-cpi-research/1.0'})
                with urllib.request.urlopen(req, timeout=35) as response:
                    data = response.read()
                if not data.startswith(b'%PDF-'):
                    raise ValueError('Response is not a PDF')
                tmp = pdf.with_suffix('.part'); tmp.write_bytes(data); tmp.replace(pdf)
                break
            except Exception as exc:
                last = exc
                if attempt < 2: time.sleep(2)
        else:
            raise RuntimeError(f'Fetch failed for {url}: {last}')
    if not txt.exists():
        subprocess.run(['pdftotext','-layout',str(pdf),str(txt)], check=True, capture_output=True)
    body = txt.read_text()
    actual = publication(body)
    if actual != current:
        raise ValueError(f'URL date {current} != publication header {actual}')
    return body, dict(release_date=str(current),url=url,pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                     text_sha256=hashlib.sha256(txt.read_bytes()).hexdigest(),bytes=pdf.stat().st_size)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--start',default='2000-07-18'); parser.add_argument('--end',default='2017-01-31')
    parser.add_argument('--manifest',default='download-manifest.json')
    args=parser.parse_args(); current=dt.date.fromisoformat(args.start); end=dt.date.fromisoformat(args.end)
    if end > dt.date(2017,1,31): raise ValueError('Reserved confirmation blocked by downloader')
    records=[]
    while current <= end:
        body, record = fetch(current); following=next_release(body,current)
        record['announced_next_release_date']=str(following)
        if str(following) in RESCHEDULED:
            following=dt.date.fromisoformat(RESCHEDULED[str(following)])
            record['rescheduling_source']='https://www.bls.gov/bls/updated_release_schedule.htm'
        record['next_release_date']=str(following); records.append(record)
        (ROOT/args.manifest).write_text(json.dumps(records,indent=2)+'\n')
        print(json.dumps(record),flush=True)
        current=following


if __name__ == '__main__': main()
