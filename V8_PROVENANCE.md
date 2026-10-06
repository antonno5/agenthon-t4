# V8 compact research candidate

This local image is not a CodaBench submission. The research dispatch pipeline and this compact candidate are reported separately.

The compact EPS forecast uses standardized Huber regression trained on 306 public SEC companyfacts observations from 23 companies. Every training outcome was first filed on or before 2014-12-31. Inputs contain only the latest quarterly GAAP EPS, its prior-year quarterly comparator, and the supplied prior-year target-quarter EPS. Per-record features are resolved using filing dates at the forecast origin. No 2015+ outcomes enter the fitted parameters. Hyperparameters were fixed before fitting; model selection uses 2015-2016 development observations. A separate 2017-2021 cohort of 35 eligible new companies is used for holdout evaluation.

`compact_model.json` stores scalar parameters and source hashes, not reports or future outcomes. Portable inference is checked against sklearn on all 972 input rows without opening holdout outcomes. Other task families use the V7 algorithmic fallback. Citations are copied from admitted source documents with exact offsets.

The separate analyst experiment uses a fresh Codex session agent as a research proxy. It is not NVIDIA House and is not evidence of House performance. The handbook and strict response validator are included for reproducibility, but this compact image makes zero neural calls. No external data access occurs at inference.

Limitations: current SEC API extraction with historical filing-date filtering is not an archived API vintage; synthetic benchmark documents do not measure general filing extraction; results cover EPS only and cannot establish the full track leaderboard score. Complete training manifests and evaluation artifacts remain outside the candidate image under `test-output/v8-analyst-validated`.
