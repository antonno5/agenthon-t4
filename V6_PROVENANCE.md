# V6 diagnostic submission

V6 tests deterministic corpus processing and sensible numeric units on the official
Track 4 contract. It is an adaptation of the laboratory approach, not the laboratory
Ridge model or a claim that the lab's 0.5925 score transfers to organizer tasks.

The user explicitly authorized one diagnostic Development submission on 2026-10-06.
The old lab gate and its literal threshold >2 remain unchanged as experiment records.
This diagnostic upload is a separate, newly authorized action.

The image contains Python 3.13 and MIT-licensed source only. Retrieval reuses the
existing chunk index and BM25 code. No external data, laboratory tasks, outcomes,
offline-fitted coefficients, neural weights, credentials, or submission ZIP is copied
into the image. House is not called. Descriptor category is `api`, `models=[]`.

All prediction inputs and citations come from the mounted task and its official
frozen corpus. Document dates and manifest entity bindings constrain retrieval.
Assertions about historical evidence are exact bounded quotations; predictions are
separate numeric estimates, not rewritten as historical facts.

The routes are selected by target semantics, never by task ID, company identity,
resolved labels or leaderboard scores:

- Auction: last six bid-to-cover observations of the admitted tenor; intervals from
  completed past one-step mean-six forecast errors.
- CPI: three-month component mean, with past completed mean-three forecast errors.
- Rates: no-change forecast and explicitly unfitted 150 bp half-width. Public snapshots
  do not contain enough completed intermeeting windows to fit/calibrate the lab Ridge
  model. External Treasury history and fitted lab artifacts are not imported.
- Positioning: continue the last four-week net change for the requested horizon;
  historical completed-window errors use each origin's open interest denominator.
- Revisions: median historical nonzero revisions in the admitted series, added to the
  task's latest estimate. Past revision dispersion gives the interval when sufficient.
- Earnings: carry forward only an explicitly stated diluted-EPS observation in prose;
  otherwise use the supplied prior-quarter or consensus reference. Ambiguous flattened
  financial tables are not parsed into invented earnings values. Growth is expressed
  relative to the given prior-year quarter; intervals are unfitted allowances.
- Credit: explicit non-negated distress disclosures drive a fixed, uncalibrated rule;
  absent such a disclosure, use a conservative no-event prior.
- Post-earnings reaction: zero abnormal return with an unfitted +/-10% interval.
- Unknown target: supplied numeric prior where recognized, otherwise zero; report the
  fallback route in evidence_trace rather than pretending to have a fitted model.

The code performs no offline fitting or model selection. Residual quantiles are computed
only from historical observations inside the current official input. Serial dependence,
short histories, revisions, and unsupported layouts limit calibration; the intervals are
not claimed to have guaranteed 90% coverage. Static fallback widths are engineering
priors, not backtested improvements. Published dev outcomes and previous submission
scores are not used to tune these routes.

The original local demo's selection was naive forecasting. Its new-period Ridge result
remains exploratory and has not been used to fit or select a deployed Ridge artifact.
