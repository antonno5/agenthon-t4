"""Build input-only corpora and separately stored outcomes from public raw data."""
import argparse
import calendar
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

TENORS = [2, 3, 5, 7, 10, 30]


def day(value):
    return dt.date.fromisoformat(value[:10])


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def load_yields(raw):
    result = {t: [] for t in TENORS}
    for path in sorted(raw.glob('yields-*.xml')):
        root = ET.fromstring(path.read_bytes())
        for props in root.iter():
            if props.tag.split('}')[-1] != 'properties':
                continue
            fields = {x.tag.split('}')[-1]: x.text for x in props}
            observed = fields.get('NEW_DATE')
            if not observed:
                continue
            for tenor in TENORS:
                value = fields.get(f'BC_{tenor}YEAR')
                if value:
                    result[tenor].append(dict(date=observed[:10], available=(day(observed) + dt.timedelta(days=2)).isoformat(), value=float(value), tenor=tenor))
    for tenor in TENORS:
        result[tenor] = sorted({x['date']: x for x in result[tenor]}.values(), key=lambda x: x['date'])
    return result


def load_auctions(raw):
    rows = []
    for path in sorted(raw.glob('auctions-*.json')):
        if path.name.endswith('.meta.json'):
            continue
        for x in json.loads(path.read_text()):
            term = re.fullmatch(r'(\d+)-Year', x.get('securityTerm', ''))
            if not term or int(term[1]) not in TENORS or x.get('tips') != 'No' or x.get('floatingRate') != 'No':
                continue
            if not x.get('bidToCoverRatio') or not x.get('announcementDate') or not x.get('updatedTimestamp'):
                continue
            date = x['auctionDate'][:10]
            # Updated records are not pretended to have been known on the original date.
            available = max((day(date) + dt.timedelta(days=1)).isoformat(), x['updatedTimestamp'][:10])
            rows.append(dict(date=date, available=available, announcement=x['announcementDate'][:10],
                             value=float(x['bidToCoverRatio']), tenor=int(term[1]),
                             offering=float(x['offeringAmount']) / 1e9, reopening=int(x.get('reopening') == 'Yes'),
                             cusip=x['cusip']))
    return sorted({(x['cusip'], x['date']): x for x in rows}.values(), key=lambda x: x['date'])


def document(entity, rows, variant):
    # All variants carry only observations available by the case cutoff.
    columns = ['date', 'available', 'value', 'tenor', 'offering', 'reopening']
    header = f"Historical observations for {entity['entity_id']}.\n"
    if variant % 3 == 0:
        text = header + 'date,available,value,tenor,offering,reopening\n'
        text += '\n'.join(','.join(str(row.get(c, 0)) for c in columns) for row in rows)
        fmt = 'csv'
    elif variant % 3 == 1:
        text = header + '\n'.join('OBS ' + json.dumps({k: row.get(k, 0) for k in columns}, sort_keys=True) for row in rows)
        fmt = 'jsonl'
    else:
        text = header + '\n'.join(f"Date {r['date']}; available {r['available']}; value {r['value']}; tenor {r['tenor']}; offering {r.get('offering', 0)}; reopening {r.get('reopening', 0)}." for r in rows)
        fmt = 'sentences'
    return dict(doc_id='history-' + entity['entity_id'], doc_date=max(r['available'] for r in rows),
                entity_ids=[entity['entity_id']], text=text, format=fmt,
                provenance='Derived from hashed Treasury responses; historical vintage not certified.')


def write_case(root, split, family, cutoff, entities, histories, outcomes, variant):
    case = f'{family}-{cutoff}'
    folder = root / 'inputs' / split / case
    kind = {'auction_btc': 'regression', 'yield_change': 'regression', 'yield_direction': 'classification', 'yield_ranking': 'ranking'}[family]
    target = dict(name=family, type=kind)
    if kind == 'classification':
        target.update(labels=['non-up', 'up'], label_assertions={'non-up': 'has a yield change less than or equal to zero', 'up': 'has a positive yield change'})
    task = dict(task_id=case, schema_version='3', family=family, target=target, cutoff_date=cutoff,
                interval_level=.9, entities=entities,
                prompt='Forecast next auction bid-to-cover ratio.' if family == 'auction_btc' else 'Forecast the change in yield, in basis points, 20 observations after the latest available observation. Rank larger changes higher. Direction up iff change > 0.',
                horizon=1 if family == 'auction_btc' else 20)
    dump(folder / 'task.json', task)
    entries = []
    for n, entity in enumerate(entities):
        rows = histories[entity['entity_id']]
        assert rows and all(r['available'] <= cutoff for r in rows)
        doc = document(entity, rows, variant + n)
        path = folder / 'corpus' / (doc['doc_id'] + '.json')
        dump(path, doc)
        entries.append(dict(path=str(path.relative_to(folder)), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    dump(folder / 'manifest.json', entries)
    dump(root / 'truth' / split / (case + '.json'), dict(outcomes=outcomes))
    return dict(case=case, split=split, family=family, cutoff=cutoff, entities=len(entities),
                block=cutoff[:7], task_sha256=hashlib.sha256((folder / 'task.json').read_bytes()).hexdigest(),
                manifest_sha256=hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    if (root / 'dataset.json').exists():
        raise SystemExit('Dataset already frozen; use a new versioned root to rebuild.')
    plan = json.loads(Path(__file__).with_name('preregister.json').read_text())
    dump(root / 'preregister.json', plan)
    yields = load_yields(root / 'raw')
    auctions = load_auctions(root / 'raw')
    cases = []
    for split, years in [('dev', plan['development_years']), ('holdout', plan['holdout_years'])]:
        for year in years:
            for month in plan['months']:
                cutoff = dt.date(year, month, calendar.monthrange(year, month)[1]).isoformat()
                entities, histories, truths = [], {}, []
                for tenor in TENORS:
                    all_rows = yields[tenor]
                    eligible = [r for r in all_rows if r['available'] <= cutoff]
                    assert len(eligible) > 500
                    last = eligible[-1]
                    idx = next(i for i, r in enumerate(all_rows) if r['date'] == last['date'])
                    future = all_rows[idx + 20]
                    assert future['date'] > cutoff
                    eid = f'UST{tenor}Y'
                    entities.append(dict(entity_id=eid, name=f'US Treasury {tenor} year', tenor=tenor))
                    histories[eid] = eligible[-1000:]
                    y = round((future['value'] - last['value']) * 100, 8)
                    truths.append(dict(entity_id=eid, y=y, true_label='up' if y > 0 else 'non-up', resolved_at=future['available']))
                for family in ['yield_change', 'yield_direction', 'yield_ranking']:
                    outcomes = [({k: v for k, v in t.items() if k != 'y'} if family == 'yield_direction' else t) for t in truths]
                    cases.append(write_case(root, split, family, cutoff, entities, histories, outcomes, month))
                # Select scheduled auction bundle solely by announcement calendar, never outcomes.
                dates = sorted({r['announcement'] for r in auctions if r['announcement'].startswith(f'{year}-{month:02}')})
                assert dates
                announcement = min(dates, key=lambda d: abs(day(d).day - 22))
                targets = [r for r in auctions if r['announcement'] == announcement and r['date'] > announcement]
                entities, histories, truths = [], {}, []
                for row in targets:
                    tenor = row['tenor']
                    history = [r for r in auctions if r['tenor'] == tenor and r['available'] <= announcement]
                    assert len(history) >= 30
                    eid = f"{row['cusip']}-{row['date']}"
                    entities.append(dict(entity_id=eid, name=f'US Treasury {tenor} year auction', tenor=tenor,
                                         offering=row['offering'], reopening=row['reopening'], auction_date=row['date']))
                    histories[eid] = history[-80:]
                    truths.append(dict(entity_id=eid, y=row['value'], resolved_at=row['available']))
                assert len(entities) >= 2
                cases.append(write_case(root, split, 'auction_btc', announcement, entities, histories, truths, month))
    dump(root / 'dataset.json', dict(cases=cases, source_manifest_sha256=hashlib.sha256((root / 'sources.json').read_bytes()).hexdigest(),
                                   preregister_sha256=hashlib.sha256((root / 'preregister.json').read_bytes()).hexdigest()))
    print(json.dumps(dict(cases=len(cases), dev=sum(c['split'] == 'dev' for c in cases),
                          holdout=sum(c['split'] == 'holdout' for c in cases), entities=sum(c['entities'] for c in cases))))


if __name__ == '__main__':
    main()
