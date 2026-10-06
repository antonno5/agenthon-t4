# V8 compact research candidate

This local image is not a CodaBench submission. The research dispatch pipeline and this compact candidate are reported separately.

The compact EPS forecast uses standardized Huber regression trained on 306 public SEC companyfacts observations from 23 companies. Every training outcome was first filed on or before 2014-12-31. Inputs contain only the latest quarterly GAAP EPS, its prior-year quarterly comparator, and the supplied prior-year target-quarter EPS. Per-record features are resolved using filing dates at the forecast origin. No 2015+ outcomes enter the fitted parameters. Hyperparameters were fixed before fitting; model selection uses 2015-2016 development observations. A separate 2017-2021 cohort of 35 eligible new companies is used for holdout evaluation.

`compact_model.json` stores scalar parameters and source hashes, not reports or future outcomes. Portable inference is checked against sklearn on all 972 input rows without opening holdout outcomes. Other task families use the V7 algorithmic fallback. Citations are copied from admitted source documents with exact offsets.

The separate analyst experiment uses a fresh Codex session agent as a research proxy. It is not NVIDIA House and is not evidence of House performance. The handbook and strict response validator are included for reproducibility, but this compact image makes zero neural calls. No external data access occurs at inference.

Limitations: current SEC API extraction with historical filing-date filtering is not an archived API vintage; synthetic benchmark documents do not measure general filing extraction; results cover EPS only and cannot establish the full track leaderboard score. Complete training manifests and evaluation artifacts remain outside the candidate image under `test-output/v8-analyst-validated`.

## Authorized Development submission (2026-10-06)

The user authorized a diagnostic CodaBench upload after the V9 research did not meet its confidence-bound target. The submitted candidate is the portable V8 Huber model, not the V9 rich-history pipeline. No V9 fitted model or evaluation answer is included.

Artifact: `agent_submit_v8/compact_model.json`, SHA-256 `efe932096f0c1210057a8823f2f536d123c2c93be10be4640ab1ce817bf9f8b9`. Model and code license: MIT. Fitting source: public SEC companyfacts API, the dated company-file hashes and input/target manifests are retained in `test-output/v8-analyst-validated`. These are public SEC financial filing facts, without a proprietary data feed. Numerical parameter fitting uses 306 observations, with the latest target first filed 2014-11-06. Primary method selection used 2015–2016 data; later candidate assessment, including the decision to submit V8 after V9 research, considered outcomes available through 2021-12-31. No further parameter fitting or interval calibration was performed for this submission.

To account conservatively for the later selection data, the learned model is used only when the supplied task cutoff is on or after **2022-01-01**. Earlier or invalid cutoffs preserve the deterministic V7 fallback. The descriptor declares the actual local Huber model with `access: local`, an immutable artifact checksum and `training_cutoff: 2021-12` encompassing selection. It declares no language model because this candidate makes no language-model calls. The original compact benchmark assessed the numerical prediction rule; the new cutoff gate is separately tested and does not change eligible public-task forecasts.

The artifact contains only numeric coefficients and metadata. The inference image includes no SEC source files, benchmark labels, credentials, or answer tables. All run-time inputs and quotations come from the supplied official corpus. The current-API/as-of and survivor-sample limitations above remain.
