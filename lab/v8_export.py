"""Export and verify portable inference against sklearn without reading holdout truth."""
from pathlib import Path
import joblib
from .v7_eps import read,write,sha
from agent_submit_v8.numeric import FEATURES,compact_row,vector,clip
from agent_submit_v8.compact import forecast

root=Path('/experiment')
models=joblib.load(root/'models-compact/models.joblib')
pipeline=models['huber'];scaler=pipeline[0];reg=pipeline[1]
model=dict(kind='standardized-huber',features=FEATURES,coef=reg.coef_.tolist(),
           mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),intercept=float(reg.intercept_),
           provenance=read(root/'models-compact/provenance.json'))
rows=read(root/'inputs/train.json')+read(root/'inputs/dev.json')+read(root/'inputs/holdout.json')
sklearn=pipeline.predict([vector(compact_row(r)) for r in rows])
error=max(abs(forecast(r,model)-(r['prior']+compact_row(r)['scale']*clip(float(v)))) for r,v in zip(rows,sklearn))
assert error<1e-10
write(Path('/export/compact_model.json'),model)
write(root/'reports/export.json',dict(rows=len(rows),max_absolute_difference=error,
                                     exported_model_sha256=sha(Path('/export/compact_model.json')),
                                     verification='All inputs, no holdout labels used'))
print('portable export',len(rows),'max_error',error)
