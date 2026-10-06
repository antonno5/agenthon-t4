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
    return x

def scale(row,view):return prepare(row,view)['scale']
