"""Typed task routing from trusted task fields; never from corpus instructions."""
import copy,re
ROUTES={
 'eps_beat_consensus':('eps_outcome','classification'),
 'auction_demand':('bid_to_cover_ratio','regression'),
 'positioning_shift':('net_positioning_change_pct_oi_rank','ranking'),
 'cpi_component_nowcast':('cpi_component_mom_first_print','regression'),
 'credit_event':('credit_event_12m','classification'),
 'eps_growth_regression':('eps_yoy_growth_pct','regression'),
 'eps_yoy_direction':('eps_yoy_direction','classification'),
 'rate_curve_cross_section':('yield_change_bps_intermeeting','regression'),
 'macro_revision_direction':('next_estimate_revision_direction','classification'),
 'post_earnings_reaction':('earnings_reaction','classification')}
LABELS={'eps_outcome':{'beat','miss','inline'},'credit_event_12m':{'credit_event','no_event'},'eps_yoy_direction':{'up','down'},'next_estimate_revision_direction':{'up','down'},'earnings_reaction':{'positive_reaction','negative_reaction','flat'}}
def canonicalize(task):
 target=task.get('target',{});kind=task.get('target_type') or target.get('type');name=target.get('name','');known={v[0]:v[1] for v in ROUTES.values()}
 if name in known:return task,'canonical'
 route=ROUTES.get(task.get('family'))
 if route is None:
  # Explicit quantity plus operation; opaque or ambiguous descriptions fall back.
  text=' '.join([str(task.get('prompt','')),str(target.get('description',''))]).lower();matches=[]
  patterns=[('bid_to_cover_ratio','regression',r'bid[ -]to[ -]cover'),('eps_yoy_growth_pct','regression',r'(?:eps|earnings per share).{0,90}(?:year.over.year|annual).{0,60}(?:growth|percent)'),('eps_yoy_direction','classification',r'(?:eps|earnings per share).{0,100}(?:year.over.year|prior.year).{0,100}(?:up or down|increase or decrease)'),('yield_change_bps_intermeeting','regression',r'(?:yield|treasury).{0,180}(?:basis points|bps).{0,200}(?:next|future|change)'),('next_estimate_revision_direction','classification',r'(?:next|published).{0,130}(?:estimate|revision).{0,180}(?:revised|revision|up or down)')]
  for n,t,p in patterns:
   if kind==t and re.search(p,text,re.S):matches.append((n,t))
  if len(matches)==1:route=matches[0]
 if route is None or route[1]!=kind:return task,'unrecognized'
 if kind=='classification' and set(target.get('labels',[]))!=LABELS[route[0]]:return task,'incompatible_labels'
 out=copy.deepcopy(task);out['target']['name']=route[0];return out,'typed_semantics'
