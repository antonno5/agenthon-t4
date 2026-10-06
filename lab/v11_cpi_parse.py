"""Audited extraction of eleven CPI-U components from original release tables."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import re

from .v11_cpi_archive import ROOT, MONTHS, publication

LABELS = {
    'All items':'CPI_ALLITEMS', 'Apparel':'CPI_APPAREL',
    'All items less food and energy':'CPI_CORE', 'Energy':'CPI_ENERGY',
    'Food':'CPI_FOOD', 'Gasoline all types':'CPI_GASOLINE',
    'Medical care':'CPI_MEDICAL', 'New vehicles':'CPI_NEWVEH',
    'Shelter':'CPI_SHELTER', 'Transportation services':'CPI_TRANSPSVC',
    'Used cars and trucks':'CPI_USEDCARS',
}
IDS = sorted(LABELS.values())
TOKEN = re.compile(r'[Rr]?[+-]?(?:\d+(?:\.\d+)?|\.\d+)[Rr]?')


def month_shift(month, delta):
    y,m=map(int,month.split('-')); total=y*12+m-1+delta
    return f'{total//12:04d}-{total%12+1:02d}'


def parse_release(text, path):
    released=publication(text)
    title=re.search(r'CONSUMER PRICE INDEX\s*[-:–—]\s*('+MONTHS+r')\s+(\d{4})', text[:2500], re.I)
    if not title: raise ValueError('Missing reference month in title')
    target=dt.datetime.strptime(' '.join(title.groups()),'%B %Y').strftime('%Y-%m')
    if not (target < released.strftime('%Y-%m') <= month_shift(target,2)):
        raise ValueError('Invalid target/publication ordering')
    lines=text.splitlines(); active=False; table=None; found={}
    for index,line in enumerate(lines):
        h=re.match(r'\s*Table\s+(\d+)\.',line)
        if h:
            table=int(h.group(1)); header=' '.join(lines[index:index+3])
            active=(table in [1,3] and '(CPI-U)' in header and
                    ('expenditure' in header.lower() or 'special aggregate' in header.lower()))
        if not active: continue
        first=re.search(r'\s{2,}([+-]?(?:\d+\.\d+|\.\d+)r?)\s+',line)
        if not first: continue
        label=' '.join(re.sub(r'[\d,().]+',' ',line[:first.start()]).split())
        if label not in LABELS: continue
        tokens=line[first.start():].split()
        if len(tokens) not in [8,9] or any(not TOKEN.fullmatch(x) for x in tokens):
            raise ValueError(f'Ambiguous {label} row at line {index+1}: {tokens}')
        values=[float(x.strip('Rr')) for x in tokens]
        if not 0 < values[0] <= 100: raise ValueError('Invalid relative importance')
        entity=LABELS[label]
        row=dict(entity=entity,relative_importance=values[0],
                 rates={month_shift(target,k-2):v for k,v in enumerate(values[-3:])},
                 nsa_month_change=values[-4],line=index+1,table=table,
                 source_path=str(path),raw_line=line,revision_marked=any('r' in x.lower() for x in tokens))
        if entity in found and found[entity]['rates'] != row['rates']:
            raise ValueError(f'Duplicate component disagreement: {entity}')
        found[entity]=row
    missing=sorted(set(IDS)-set(found))
    if missing: raise ValueError(f'Missing components: {missing}')
    return dict(target_month=target,release_date=str(released),components=found)


def main():
    manifest=json.loads((ROOT/'download-manifest.json').read_text())
    results=[]; errors=[]
    for item in manifest:
        path=ROOT/'sources'/f"cpi_{item['release_date'].replace('-','')}.txt"
        try:
            text=path.read_text()
            if hashlib.sha256(text.encode()).hexdigest() != item['text_sha256']:
                raise ValueError('Text hash mismatch')
            row=parse_release(text,path); row['pdf_sha256']=item['pdf_sha256']; row['url']=item['url']
            if row['target_month'] > '2016-12': raise ValueError('Reserved target month')
            results.append(row)
        except Exception as exc:
            errors.append(dict(release_date=item['release_date'],error=str(exc)))
    out=dict(releases=results,errors=errors,coverage=len(results),attempted=len(manifest),
             code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (ROOT/'parsed-releases.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:out[k] for k in ['coverage','attempted','errors']},indent=2))


if __name__ == '__main__': main()
