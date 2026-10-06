"""Download only the designated submission's own result and summarize score tables."""
import argparse
import http.cookiejar
import json
from pathlib import Path
import urllib.request
from html.parser import HTMLParser

class Tables(HTMLParser):
    def __init__(self):super().__init__();self.cell=None;self.row=[];self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        if tag in ['td','th']:self.cell=[]
    def handle_data(self,s):
        if self.cell is not None:self.cell.append(s.strip())
    def handle_endtag(self,tag):
        if tag in ['td','th'] and self.cell is not None:
            self.row.append(' '.join(x for x in self.cell if x));self.cell=None
        if tag=='tr' and self.row:self.rows.append(self.row)

def main():
    p=argparse.ArgumentParser();p.add_argument('--id',type=int,required=True);p.add_argument('--cookies',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--previous-report',type=Path);a=p.parse_args()
    jar=http.cookiejar.MozillaCookieJar(str(a.cookies));jar.load(ignore_discard=True,ignore_expires=True)
    o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    base=f'https://www.codabench.org/api/submissions/{a.id}/'
    with o.open(base,timeout=45) as r:submission=json.load(r)
    safe={k:submission.get(k) for k in ['id','phase','status','status_details','created_when','owner','filename','scores']}
    assert safe['owner']=='imak_ai_lab' and safe['phase']==29649
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'latest-status.json').write_text(json.dumps(safe,indent=2)+'\n')
    if safe['status'] not in ['Finished','Failed','Cancelled']:
        print(json.dumps(dict(id=a.id,status=safe['status'])));return
    with o.open(base+'get_details/',timeout=45) as r:details=json.load(r)
    for key,filename in [('detailed_result','detailed-result.html'),('scoring_result','scoring-result.zip')]:
        url=details.get(key)
        if not url:continue
        assert isinstance(url,str) and url.startswith('https://')
        # Storage downloads receive no platform cookies or authorization headers.
        with urllib.request.urlopen(url,timeout=60) as r:content=r.read(25000001)
        assert len(content)<=25000000
        (a.out/filename).write_bytes(content)
    summary=dict(id=a.id,status=safe['status'],scores={x['column_key']:float(x['score']) for x in safe['scores']})
    report=a.out/'detailed-result.html'
    if report.exists():
        parser=Tables();parser.feed(report.read_text());summary['tables']=parser.rows
        current={r[0]:float(r[2]) for r in parser.rows if len(r)==3 and r[0].startswith('t4-') and r[1]=='scored'}
        if a.previous_report:
            old=Tables();old.feed(a.previous_report.read_text());oldrows={r[0]:float(r[2]) for r in old.rows if len(r)==3 and r[0].startswith('t4-') and r[1]=='scored'}
            summary['unit_comparison_rounded']=[dict(unit=u,previous=oldrows[u],current=v,delta=round(v-oldrows[u],4)) for u,v in current.items() if u in oldrows]
    (a.out/'result-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
