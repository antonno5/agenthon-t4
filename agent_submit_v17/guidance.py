"""Admit quarterly GAAP guidance only from the entity's supplied frozen corpus."""
import calendar,datetime as dt,re
from .guidance_rules import canonical,candidates,eligible
from agent_submit.cli import quote
TICKERS={'0000097476':'TXN','0000804328':'QCOM','0000050863':'INTC'}
def fiscal(date,ticker):
 d=dt.date.fromisoformat(date);ends=[dt.date(y,m,calendar.monthrange(y,m)[1]) for y in [d.year-1,d.year,d.year+1] for m in [3,6,9,12]];near=min(ends,key=lambda v:abs((v-d).days))
 if abs((near-d).days)>8:return None
 q=near.month//3;y=near.year
 return (y+int(q==4),q%4+1) if ticker=='QCOM' else (y,q)
def mapped_text(text):
 # Normalize whitespace with a parallel original-character map, never fuzzy matching.
 chars=[];positions=[];offset=0;lines=text.splitlines(keepends=True)
 for i,line in enumerate(lines):
  tokens=list(re.finditer(r'\S+',line))
  for j,m in enumerate(tokens):
   if j:chars.append(' ');positions.append(offset+tokens[j-1].end())
   chars.extend(m[0]);positions.extend(range(offset+m.start(),offset+m.end()))
  offset+=len(line)
  if i+1<len(lines):chars.append('\n');positions.append(max(0,offset-1))
 normalized=''.join(chars)
 if normalized!=canonical(text):raise ValueError('Whitespace mapping mismatch')
 return normalized,positions
def claims(text,doc_id,candidate):
 normalized,positions=mapped_text(text);a,b=candidate['span'];assert normalized[a:b]==candidate['literal']
 start,end=positions[a],positions[b-1]+1
 context_a,context_b=candidate['context_span'];begin,finish=positions[context_a],positions[context_b-1]+1
 if finish-begin<=1100:return [quote(doc_id,text,begin,finish)]
 # Preserve the period/header and numeric row in separate exact bounded spans.
 result=[quote(doc_id,text,max(begin,start-160),min(len(text),end+100))]
 if start-begin>500:result.insert(0,quote(doc_id,text,begin,min(begin+400,start)))
 return result

def forecast(task,entity,corpus,allowed):
 if task['cutoff_date']<'2023-01-01':return None
 ticker=TICKERS.get(str(entity.get('cik','')).zfill(10)) or str(entity.get('ticker',entity['entity_id'])).upper()
 if ticker not in ['TXN','QCOM','INTC']:return None
 dates=re.findall(r'\d{4}-\d{2}-\d{2}',str(entity.get('quarter_reported','')))
 if len(dates)!=1:return None
 try:
  target=dt.date.fromisoformat(dates[0]);period=fiscal(dates[0],ticker);cutoff=dt.date.fromisoformat(task['cutoff_date'])
 except ValueError:return None
 if period is None:return None
 # Previous calendar-quarter boundary approximates issuer's 52/53-week calendar.
 near=min([dt.date(y,m,calendar.monthrange(y,m)[1]) for y in [target.year-1,target.year,target.year+1] for m in [3,6,9,12]],key=lambda x:abs((x-target).days))
 py,pm=(near.year,near.month-3) if near.month>3 else (near.year-1,12);previous=dt.date(py,pm,calendar.monthrange(py,pm)[1])
 row=dict(ticker=ticker,target_year=period[0],target_quarter=period[1]);found=[]
 for doc_id in allowed:
  try:published=dt.date.fromisoformat(corpus.doc_dates[doc_id][:10])
  except (ValueError,TypeError):continue
  if not previous-dt.timedelta(days=8)<published<=min(cutoff,target):continue
  text=corpus.doc_texts[doc_id];_,cs=candidates(text,row);cs=[c for c in cs if eligible(c,row)]
  if not cs:continue
  values={round(c['midpoint'],8) for c in cs}
  if len(values)!=1:return None
  c=cs[0]
  try:evidence=claims(text,doc_id,c)
  except (ValueError,AssertionError,IndexError):continue
  found.append(dict(value=c['midpoint'],doc_id=doc_id,date=published.isoformat(),literal=c['literal'],basis=c['basis'],target_year=period[0],target_quarter=period[1],claims=evidence))
 if not found:return None
 newest=max(x['date'] for x in found);fresh=[x for x in found if x['date']==newest]
 if len({round(x['value'],8) for x in fresh})!=1:return None
 for doc_id in allowed:
  if corpus.doc_dates[doc_id][:10]>=newest and re.search(r'withdraw\w*\s+(?:\w+\s+){0,5}(?:guidance|outlook)',corpus.doc_texts[doc_id],re.I):return None
 return sorted(fresh,key=lambda x:x['doc_id'])[0]
