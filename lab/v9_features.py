"""Anonymous numeric EPS features; dates and company IDs never enter the learner."""
import math
import statistics as st
from agent_submit_v8.numeric import vector as v8_vector,indicators,clip,compact_row

def prepare(row,view='rich'):
    return compact_row(row) if view=='compact' else row

def vector(row,view='rich'):
    r=prepare(row,view);h=r['eps'];s=r['scale'];p=r['prior']
    x=v8_vector(r);valid=[v/s for v in h if v is not None]
    median=st.median(valid);mean=st.mean(valid)
    other=[v/s for i,v in enumerate(h) if v is not None and i!=3]
    x.extend([clip(h[0]/s-p/s,-8,8),clip(median,-8,8),clip(mean,-8,8),
              clip(p/s-st.median(other),-8,8),min(5,st.pstdev(valid)),
              sum(v<0 for v in valid)/len(valid),clip(h[0]/max(abs(h[4]),.1),-8,8),
              min(10,abs(p)/s),float(abs(p)<.1),float(p<0),float(h[0]<0)])
    # Absolute levels on an EPS scale identify whether a profit change is recurring
    # and whether the prior target was unusual; no dollar size/identity features.
    m=r['metrics'];shares=m.get('shares');op=m.get('operating');net=m.get('net');rev=m.get('revenue')
    for pair in [op,net,rev]:
        values=[pair[i]/shares[i]/s for i in range(2)] if pair and shares and min(shares)>0 else [None,None]
        for v in values:x.extend([clip(v,-20,20) if v is not None else 0.,float(v is None)])
    accounting=row.get('accounting',{}) if view=='rich' else {}
    def val(name,i):
        values=accounting.get(name,[None]*8)
        return values[i]
    def per_share(name,i):
        amount,shares=val(name,i),val('shares',i)
        return amount/shares/s if amount is not None and shares is not None and shares>0 else None
    def add(value,limit=12):x.extend([clip(value,-limit,limit) if value is not None else 0.,float(value is None)])
    for i in [0,1,2,3,4,7]:
        for name in ['operating','net','cfo','capex','pretax','tax']:add(per_share(name,i))
        op=per_share('operating',i);cf=per_share('cfo',i)
        add(h[i]/s-.75*op if op is not None and h[i] is not None else None)
        add(h[i]/s-cf if cf is not None and h[i] is not None else None)
        tax,pretax=val('tax',i),val('pretax',i)
        add(tax/pretax if tax is not None and pretax is not None and abs(pretax)>1 else None,2)
        op,rev=val('operating',i),val('revenue',i)
        add(op/rev if op is not None and rev is not None and rev>0 else None,2)
    for name in ['operating','net','cfo','capex']:
        a,b,c=per_share(name,0),per_share(name,3),per_share(name,4)
        add(a+b-c if all(v is not None for v in [a,b,c]) else None)
        add(b-c if b is not None and c is not None else None)
        add(a-c if a is not None and c is not None else None)
    for name in ['assets','receivables','inventory','current_assets','current_liabilities']:
        a,b,assets=val(name,0),val(name,4),val('assets',0)
        add((a-b)/assets if all(v is not None for v in [a,b,assets]) and assets>0 else None,3)
    # Seasonal operating profit plus a recent estimate of the persistent non-operating gap.
    ops=[per_share('operating',i) for i in [0,3,4]]
    if all(v is not None for v in ops):
        seasonal=.75*(ops[0]+ops[1]-ops[2]);add(seasonal)
        gaps=[h[i]/s-.75*per_share('operating',i) for i in range(8) if h[i] is not None and per_share('operating',i) is not None and i!=3]
        add(seasonal+st.median(gaps) if gaps else None)
    else:add(None);add(None)
    return x

def scale(row,view):return prepare(row,view)['scale']
