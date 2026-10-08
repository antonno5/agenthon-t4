"""Outcome-blind, fail-closed adapters for issuer EPS outlooks.
Every value is parsed from a retained literal span. Model output only selects IDs.
"""
import hashlib,json,re
from pathlib import Path
ORD={'first':1,'second':2,'third':3,'fourth':4}
NUM=r'\(?\$?\s*-?(?:\d+(?:\.\d+)?|\.\d+)\)?'
RANGE=re.compile(r'(?P<a>'+NUM+r')\s*(?:to|and|[-–—])\s*(?P<b>'+NUM+r')\s*(?P<unit>cents)?',re.I)
EPS=re.compile(r'earnings[\s-]+per[\s-]+share|\bEPS\b',re.I)
NON=re.compile(r'non[ -]?GAAP|adjusted',re.I)
def digest(b):return hashlib.sha256(b).hexdigest()
def canonical(text):return '\n'.join(re.sub(r'[^\S\n]+',' ',x).strip() for x in text.replace('\x0c','\n').splitlines())
def number(s):
 neg='(' in s or '-' in s;v=float(re.sub(r'[^\d.]','',s));return -v if neg else v

def candidates(text,row):
 s=canonical(text);out=[]
 def add(start,end,low,high,unit,basis,year,q,context_start,context_end,kind):
  if not(-100<=low<=high<=100):return
  context=s[context_start:context_end]
  out.append(dict(candidate_id=f'C{len(out):03d}',span=[start,end],literal=s[start:end],low=low,high=high,midpoint=(low+high)/2,unit=unit,basis=basis,year=year,quarter=q,kind=kind,context_span=[context_start,context_end],context=context))
 if row['ticker']=='TXN':
  for em in EPS.finditer(s):
   tail=s[em.end():em.end()+150]
   m=re.match(r'\s+(?:between|(?:in )?(?:the )?range(?: of)?|of)\s*',tail,re.I)
   if not m:continue
   match=RANGE.match(tail,m.end())
   if not match:continue
   start=em.end()+match.start();end=em.end()+match.end()
   prefix=s[max(0,em.start()-600):em.start()];ctx_start=max(0,em.start()-600)
   # Use the latest quoted management bullet when present.
   quotes=[m.end() for m in re.finditer('["“]',prefix)]
   if quotes:ctx_start+=quotes[-1];prefix=prefix[quotes[-1]:]
   if not re.search(r'outlook|guidance|expect|forecast',prefix,re.I):continue
   if re.search(r'(?:full[ -]year|annual).{0,35}(?:EPS|earnings)',prefix+s[em.start():em.end()],re.I):continue
   periods=[ORD[m[1].lower()] for m in re.finditer(r'\b(first|second|third|fourth)[\s-]+quarter\b',prefix,re.I)]
   q=row['target_quarter'] if row['target_quarter'] in periods else (periods[-1] if periods else 0)
   ym=re.search(r'\b(?:first|second|third|fourth)[\s-]+quarter\s+(?:of\s+)?(20\d\d)',prefix,re.I)
   year=int(ym[1]) if ym else row['target_year']
   units='cents' if match['unit'] else 'dollars' if '$' in match[0] else 'unknown'
   if units=='unknown':continue
   low,high=number(match['a']),number(match['b'])
   if units=='cents':low/=100;high/=100
   basis='non_gaap' if NON.search(s[max(em.start()-25,ctx_start):em.end()]) else 'unadjusted'
   add(start,end,low,high,units,basis,year,q,ctx_start,min(len(s),end+130),'range')
 elif row['ticker']=='QCOM':
  headers=list(re.finditer(r'Q([1-4])\s*FY\s*(\d{2,4})\s+Estimates',s,re.I))
  for h in headers:
   year=int(h[2]);year+=2000 if year<100 else 0
   stop=re.search(r'\bFISCAL YEAR\b|\bFull[ -]Year\b|\bQ[1-4]\s*FY\s*\d{2,4}\s+Estimates',s[h.end():],re.I)
   end=min(len(s),h.end()+2600,h.end()+stop.start() if stop else len(s))
   for lm in re.finditer(r'[^\n]+',s[h.end():end]):
    line=lm[0]
    if not EPS.search(line) or not re.search(r'GAAP',line,re.I):continue
    matches=list(RANGE.finditer(line));matches=[m for m in matches if '$' in m[0]]
    if len(matches)!=1:continue # Do not guess among current/previous guidance columns.
    m=matches[0];a=h.end()+lm.start()+m.start();b=h.end()+lm.start()+m.end()
    basis='non_gaap' if NON.search(line[:m.start()]) else 'gaap'
    add(a,b,number(m['a']),number(m['b']),'dollars',basis,year,int(h[1]),max(0,h.start()-110),min(end,h.end()+lm.end()+100),'range')
 elif row['ticker']=='INTC':
  # Quarterly outlook table must explicitly label GAAP as first numeric column.
  for h in re.finditer(r'\bQ([1-4])\s+(20\d\d)\s*(?:\|\s*)?GAAP\s*(?:\|\s*)*Non[ -]GAAP',s,re.I):
   prefix=s[max(0,h.start()-1600):h.start()]
   if not re.search(r'Business Outlook|guidance',prefix,re.I):continue
   stop=re.search(r'Full[ -]Year|\bQ[1-4]\s+20\d\d',s[h.end():],re.I)
   end=min(len(s),h.end()+2600,h.end()+stop.start() if stop else len(s))
   for lm in re.finditer(r'[^\n]+',s[h.end():end]):
    line=lm[0];em=EPS.search(line)
    if not em:continue
    vals=list(re.finditer(r'\$\s*-?\d+\.\d+|\b\d+\s+cents\b',line[em.end():],re.I))
    if len(vals)<2:continue
    for i,m in enumerate(vals[:2]):
     a=h.end()+lm.start()+em.end()+m.start();b=h.end()+lm.start()+em.end()+m.end()
     unit='cents' if 'cents' in m[0].lower() else 'dollars';v=number(m[0])/(100 if unit=='cents' else 1)
     add(a,b,v,v,unit,'gaap' if i==0 else 'non_gaap',int(h[2]),int(h[1]),max(0,h.start()-400),min(end,h.end()+lm.end()+100),'quoted_center')
 return s,out

def eligible(c,row):
 return c['basis'] in ['gaap','unadjusted'] and c['year']==row['target_year'] and c['quarter']==row['target_quarter'] and c['unit'] in ['cents','dollars']

def validate(obj,case):
 if set(obj)!={'candidate_id','basis','period'}:raise ValueError('schema')
 cid=obj['candidate_id']
 if cid is None:return None
 cs=[c for c in case['candidates'] if c['candidate_id']==cid]
 if len(cs)!=1:raise ValueError('unknown_candidate')
 c=cs[0]
 if obj['basis'] not in ['gaap','unadjusted'] or obj['period']!='next_quarter':raise ValueError('semantic_rejection')
 if not eligible(c,case):raise ValueError('basis_or_period')
 if case['source']['status']!='ok' or not case['recent_period']<case['source']['publication']['date']<=case['cutoff']:raise ValueError('publication_cutoff')
 values={round(x['midpoint'],8) for x in case['candidates'] if eligible(x,case)}
 if len(values)!=1:raise ValueError('conflicting_guidance')
 return c
