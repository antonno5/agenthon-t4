"""Bounded House-compatible analyst. Invalid/missing responses retain algorithms."""
from __future__ import annotations
import json
import os
from pathlib import Path
import urllib.request

ROLES=('selector','quality','guard')
FIELDS={'id',*ROLES,'reason'}
HANDBOOK=Path(__file__).with_name('ANALYST_HANDBOOK.md').read_text()

def validate_decisions(text,packets):
    # Reject markdown fences, prose, extra fields, duplicate IDs, partial batches.
    expected={p['id']:p for p in packets}
    if len(expected)!=len(packets):raise ValueError('Duplicate packet IDs')
    found={}
    for line in text.strip().splitlines():
        d=json.loads(line)
        if not isinstance(d,dict) or set(d)!=FIELDS:raise ValueError('Unexpected response schema')
        if d['id'] not in expected or d['id'] in found:raise ValueError('Unexpected or duplicate decision ID')
        for role in ROLES:
            if not isinstance(d[role],str) or d[role] not in expected[d['id']]['choices']:raise ValueError('Unsupported numeric candidate')
        if not isinstance(d['reason'],str) or len(d['reason'])>250:raise ValueError('Invalid rationale')
        found[d['id']]=d
    if set(found)!=set(expected):raise ValueError('Incomplete analyst batch')
    return found

def assess(packets,role='selector',max_calls=8,timeout=45):
    if role not in ROLES:raise ValueError('Unknown analyst role')
    endpoint=os.getenv('MODEL_ENDPOINT','');model=os.getenv('MODEL_NAME') or os.getenv('MODEL_ID') or 'house'
    if not endpoint:return {},dict(calls=0,fallback='MODEL_ENDPOINT unavailable')
    endpoint=endpoint.rstrip('/')
    if not endpoint.endswith('/v1'):endpoint+='/v1'
    decisions={};trace=[]
    for start in range(0,min(len(packets),max_calls*8),8):
        batch=packets[start:start+8]
        payload=dict(model=model,temperature=0,max_tokens=2000,
                     chat_template_kwargs=dict(enable_thinking=False),
                     messages=[dict(role='system',content=HANDBOOK),dict(role='user',content='\n'.join(json.dumps(p,separators=(',',':')) for p in batch))])
        headers={'Content-Type':'application/json'}
        if os.getenv('MODEL_TOKEN'):headers['Authorization']='Bearer '+os.environ['MODEL_TOKEN']
        try:
            req=urllib.request.Request(endpoint+'/chat/completions',data=json.dumps(payload).encode(),headers=headers)
            with urllib.request.urlopen(req,timeout=timeout) as response:raw=json.loads(response.read(1000000))
            valid=validate_decisions(raw['choices'][0]['message']['content'],batch)
            decisions.update({k:d[role] for k,d in valid.items()});trace.append(dict(rows=len(batch),valid=True))
        except (ValueError,KeyError,IndexError,OSError,TypeError) as error:
            # Do not leak endpoint/token or response body into traces. No retries.
            trace.append(dict(rows=len(batch),valid=False,error=type(error).__name__))
    return decisions,dict(calls=len(trace),batches=trace,unhandled=len(packets)-len(decisions))
