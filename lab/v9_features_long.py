"""Company seasonality features computed from past EPS, with explicit missingness."""
import statistics as st
from .v9_features import vector as base_vector
from agent_submit_v8.numeric import clip

def history_signals(row):
    h=row.get('long_eps',row['eps']+[None]*16);s=row['scale']
    same=[(i//4+1,h[i]/s) for i in range(3,24,4) if h[i] is not None]
    slopes=[(a-b)/(yb-ya) for j,(ya,a) in enumerate(same) for yb,b in same[j+1:]]
    offsets=[]
    for i in range(3,21,4):
        peers=[v/s for v in h[i+1:i+4] if v is not None]
        if h[i] is not None and len(peers)>=2:offsets.append(h[i]/s-st.median(peers))
    recent=[v/s for v in h[:3] if v is not None]
    return dict(seasonal_trend=st.median(slopes) if slopes else None,
                seasonal_offset=st.median(offsets) if offsets else None,
                seasonal_level=st.median(recent)+st.median(offsets) if recent and offsets else None,
                same_count=len(same),offset_dispersion=st.pstdev(offsets) if offsets else None,
                last_target_change=(h[3]-h[7])/s if h[7] is not None else None)

def vector(row,view='rich'):
    x=base_vector(row,view);h=row.get('long_eps',row['eps']+[None]*16) if view=='rich' else [None]*24;s=row['scale']
    def add(v):x.extend([clip(v,-12,12) if v is not None else 0.,float(v is None)])
    for i in range(8,24):add(h[i]/s if h[i] is not None else None)
    for i in range(20):add((h[i]-h[i+4])/s if h[i] is not None and h[i+4] is not None else None)
    signals=history_signals(row) if view=='rich' else {k:None for k in history_signals(row)}
    for v in signals.values():add(v)
    q=int(row['block'][-1]);x.extend(float(q==i) for i in range(1,5))
    return x
