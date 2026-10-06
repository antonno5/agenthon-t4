"""Historical series replay; not an independent holdout or leaderboard estimate."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics as stats

from agent_submit.cli import tables, number, norm
from agent_submit_v7.series import level_forecast, positioning_forecast, change_point


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--units',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    records=[];sources=[]
    for family,prefix,column,window,width in [('auction','t4-auction','bid_to_cover',6,.5),('cpi','t4-cpicomp',None,3,2.)]:
        unit=next(args.units.glob(prefix+'*'));task=json.loads((unit/'task.json').read_text())
        for path in sorted((unit/'corpus').glob('*.json')):
            doc=json.loads(path.read_text());used=False
            for header,rows in tables(doc.get('text',''),task['cutoff_date']):
                cols=[norm(c) for c in header]
                use=[cols.index(norm(column))] if column and norm(column) in cols else list(range(1,len(cols))) if family=='cpi' and cols[0]=='month' else []
                for j in use:
                    values=[number(row[j]) for row in rows]
                    if any(v is None for v in values):continue
                    used=True
                    for i in range(window,len(values)):
                        base=stats.mean(values[max(0,i-window):i])
                        forecast,trace=level_forecast(values[:i],'mean'+str(window),width)
                        new=forecast[0] if forecast else base
                        records.append(dict(family=family,origin=rows[i-1][0],target=rows[i][0],series=header[j],source=path.name,
                                            v6_error=abs(values[i]-base),v7_error=abs(values[i]-new),changed=bool(forecast),selection=trace))
            if used:sources.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    unit=next(args.units.glob('t4-cotpos*'));task=json.loads((unit/'task.json').read_text())
    for path in sorted((unit/'corpus').glob('COT_*.json')):
        doc=json.loads(path.read_text())
        for header,rows in tables(doc.get('text',''),task['cutoff_date']):
            cols=[norm(c) for c in header]
            if not {'noncommnet','openinterest'}<=set(cols):continue
            values=[number(r[cols.index('noncommnet')]) for r in rows]
            oi=[number(r[cols.index('openinterest')]) for r in rows]
            if any(v is None for v in values+oi) or min(oi)<=0:continue
            sources.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            horizon=5
            for i in range(11,len(values)-horizon):
                base=change_point(values[:i+1],oi[:i+1],horizon,'momentum4')
                forecast,trace=positioning_forecast(values[:i+1],oi[:i+1],horizon)
                new=forecast[0] if forecast else base
                y=(values[i+horizon]-values[i])/oi[i]*100
                records.append(dict(family='positioning',origin=rows[i][0],target=rows[i+horizon][0],series=path.stem,source=path.name,
                                    v6_error=abs(y-base),v7_error=abs(y-new),changed=bool(forecast),selection=trace))
    summary={}
    for family in sorted({r['family'] for r in records}):
        rows=[r for r in records if r['family']==family]
        summary[family]=dict(rows=len(rows),changed=sum(r['changed'] for r in rows),
                             v6_mae=stats.mean(r['v6_error'] for r in rows),v7_mae=stats.mean(r['v7_error'] for r in rows))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(dict(rankable=False,independent_holdout=False,summary=summary,rows=records,sources=sources,
                                       limitation='Historical replay of the final frozen pre-cutoff snapshot; not separately certified as-of snapshots at each earlier origin.'),indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
