"""Pure calculations, available without the model or outcome data."""
import math
import statistics as st

def clip(x,lo=-3.,hi=3.): return min(hi,max(lo,x))
def div(a,b): return a/b if b and math.isfinite(b) else None

def indicators(row):
    h=row['eps'];s=row['scale'];m=row['metrics'];prior=row['prior']
    deltas=[(h[i]-h[i+4])/s for i in range(4) if h[i] is not None and h[i+4] is not None]
    f={f'eps_lag{i+1}':clip(v/s,-8,8) if v is not None else None for i,v in enumerate(h)}
    f.update(prior=clip(prior/s,-8,8),eps_delta=clip((h[0]-h[4])/s),
             median_delta=clip(st.median(deltas)),delta_dispersion=min(3,st.pstdev(deltas)),
             up_fraction=sum(d>=0 for d in deltas)/len(deltas),history_count=len(deltas),
             split_warning=int(row['split_warning']))
    for name in ('revenue','operating','net','shares','tax','pretax'):
        pair=m.get(name)
        f[name+'_growth']=clip((pair[0]-pair[1])/max(abs(pair[1]),1.)) if pair else None
    op=m.get('operating');shares=m.get('shares');rev=m.get('revenue');net=m.get('net')
    f['operating_eps_delta']=clip(.75*(op[0]/shares[0]-op[1]/shares[1])/s) if op and shares and min(shares)>0 else None
    f['operating_margin_change'] = clip(10*(op[0]/rev[0]-op[1]/rev[1])) if op and rev and min(rev)>0 else None
    f['net_margin_change'] = clip(10*(net[0]/rev[0]-net[1]/rev[1])) if net and rev and min(rev)>0 else None
    f['net_operating_gap'] = clip((net[0]-.75*op[0])/shares[0]/s) if net and op and shares and shares[0]>0 else None
    tax=m.get('tax');pretax=m.get('pretax')
    f['tax_rate_change']=clip(tax[0]/pretax[0]-tax[1]/pretax[1]) if tax and pretax and min(abs(v) for v in pretax)>1 else None
    return f

FEATURES=list(indicators(dict(eps=[1.]*8,scale=1.,prior=1.,metrics={},split_warning=False)))

def vector(row):
    f=indicators(row)
    return [0. if f[k] is None else f[k] for k in FEATURES]+[float(f[k] is None) for k in FEATURES]

def candidates(row):
    f=indicators(row);p=row['prior'];s=row['scale'];h=row['eps']
    delta=h[0]-h[4]
    core=f['operating_eps_delta']
    if core is None:core=f['median_delta']
    # All new signals are clipped on a past-only EPS scale.
    return dict(v6=p,v7=p+.5*delta,
                trend=p+s*clip(delta/s),
                robust=p+s*.5*f['median_delta'],
                core=p+s*.5*core,
                ensemble=p+s*.5*st.median([f['eps_delta'],f['median_delta'],core]),
                drift=p+.05*s)

def needs_agent(row):
    f=indicators(row)
    op=f['operating_eps_delta']
    # Sparse specialist routing. No dates, identities, targets, or labels here.
    conflict=op is not None and op*f['eps_delta']<0 and abs(op-f['eps_delta'])>.2
    unstable=f['delta_dispersion']>.7 or row['split_warning']
    return conflict or unstable

def compact_row(row):
    """A deployable view requiring only the EPS pair and supplied prior target."""
    eps=[None]*8
    for i in (0,3,4):eps[i]=row['eps'][i]
    return dict(row,eps=eps,scale=max(.1,st.median(abs(v) for v in eps if v is not None)),metrics={},split_warning=False)

def packet(row,predictions):
    f=indicators(row)
    keys=['prior','eps_delta','median_delta','delta_dispersion','up_fraction','history_count',
          'revenue_growth','operating_growth','shares_growth','operating_eps_delta',
          'operating_margin_change','net_operating_gap','tax_rate_change','split_warning']
    return dict(id=row['id'],signals={k:round(f[k],3) if f[k] is not None else None for k in keys},
                choices={k:round((v-row['prior'])/row['scale'],3) for k,v in predictions.items()})
