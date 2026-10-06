# V7 deterministic candidate

V7 reads quarterly GAAP diluted earnings per share from the supplied frozen filing,
checks the period and comparator columns, and uses an equal blend of seasonal
no-change and the most recent year-over-year earnings difference. This is ordinary
statistical code with a fixed 0.5 blend, not an offline-fitted artifact. Ambiguous,
adjusted, annual-only, prospective and post-cutoff observations are rejected.

Numeric history routes compare a small fixed set of simple forecasters using only
completed windows in the current task's corpus. A replacement must improve mean
absolute error by more than one standard error of paired historical errors on at
least four origins. Positioning uses non-overlapping target windows. This guard
does not provide a hypothesis-test guarantee after multiple candidate comparisons.
Residual intervals inherit V6's short-history and dependence limitations.

All other predictions, admissible-document selection and exact quotation rules
inherit V6. There are no company-specific prediction rules, task-ID branches,
stored answers, external documents, credentials, offline-fitted coefficients or
neural weights in the image. Neural calls are zero. Evaluation has no network input.
The image contains Python 3.13 and this repository's MIT-licensed source; its base
digest is pinned in Dockerfile.v7. No additional packages or learned models are loaded.

The separate EPS validation uses publicly accessible SEC companyfacts XBRL data,
with URLs, retrieval dates and SHA-256 hashes recorded outside the image. Target
labels must have first been filed by 2021-12-31; simulated features use only facts
filed by the origin. Targets use their first reported value, not the newest
restatement. The current SEC extraction is not an archived historical API snapshot,
so extraction corrections remain a provenance limitation. Synthetic filing layouts
test the entire interface but do not measure arbitrary real-document parsing.
The fixed recipe and split are recorded in lab/v7_plan.json before evaluation.

Data and derived outcomes stay under test-output/v7-eps and are never copied into
the image. Runtime EPS features come solely from the supplied official corpus.
The SEC evaluation does not license importing its facts into inference or citations.
Observed CodaBench scores are diagnostic and are not fitted labels or task answers.
