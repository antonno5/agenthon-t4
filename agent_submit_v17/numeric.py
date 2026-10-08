"""Frozen compact numerical experts with a conservative availability guard."""
import json,math
from pathlib import Path
from agent_submit_v8.numeric import compact_row,vector,FEATURES
from agent_submit_v11.cpi import model_point
MODEL_PATH=Path(__file__).with_name('eps_models.json')
def predict(row,entity,cutoff,artifact=None):
 artifact=artifact or json.loads(MODEL_PATH.read_text())
 if cutoff<artifact['available_after']:return None
 if artifact['features']!=FEATURES:raise ValueError('EPS feature schema mismatch')
 compact=compact_row(row);x=vector(compact)
 if not all(math.isfinite(v) for v in x):return None
 cik=str(entity.get('cik','')).zfill(10);expert='bank' if cik in artifact['bank_ciks'] else 'pooled'
 value=model_point(artifact['experts'][expert],x)*compact['scale']
 if not math.isfinite(value):return None
 return value,expert
