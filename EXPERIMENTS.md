# Track 4 Development experiments

Historical results through 2026-09-28; V6 diagnostic upload added 2026-10-06. The CodaBench score is the only result that measures hidden
forecast quality. Local schema, smoke and NLI checks do not use resolution
labels and cannot predict the leaderboard score.

| Candidate | Image digest | CodaBench result | Local evidence |
| --- | --- | --- | --- |
| V1 official minimal baseline | `sha256:cfea7eaa99421714c7789190c6dc79ad30a14a9744ae621ec09e7d67b2b2db8d` | ID 949583, `0.1388` | 11/11 public structural and smoke |
| V2 BM25 + House | `sha256:3e3f1471568f848a631763dcc89f2ccee270ac2e1158555a5fed5f6c0ce8fbdc` | Not submitted | 11/11 public structural and smoke; House route checked with a local fake server |
| V3 House + cited historical forecasts | `sha256:5641c8876673e5b3029e2d1d0b0f48ac6f28661d01e49fb24deb9f09118a0161` | ID 949827, `0.1023` | Published digest ran offline on 11/11 public units; official smoke 11/11; local published NLI on targeted public families: CPI 11/11, macro revisions 12/12, Treasury auctions 7/7 |
| V4 policy-regime rate forecasts + interval floor | `sha256:e330b1614d1c5982ebb0ad13768eb5db73ce36447e9d2e88aa441afec7268cb5` | ID 950051, `0.1129` | Anonymous GHCR digest pull; `linux/amd64`, interface `2.0`; published image structural 11/11, local official smoke 11/11, fake House route, public FOMC NLI 6/6 in each of two units |
| V5 House thinking enabled globally | `sha256:60f651c1cebe0524ea6f63a0af67950de706838eec7576bdce4377f9cae3d7ec` | Not submitted | Anonymous digest pull; `linux/amd64`, interface `2.0`; exact published image structural and smoke 11/11; fake House route passed; hidden quality unknown |

V3 uses only the pre-cutoff frozen corpus for its historical estimates and
citations. The three specialized paths use a three-month CPI average, the most
recent same-series revision direction, and a same-tenor auction average. The
other families use House forecasts with BM25-retrieved excerpts and exact
citations. See `ARTIFACT_PROVENANCE.md`.

The visible Development report has only per-unit composite scores, not
faithfulness, predictive quality, coverage, or program logs:

| Unit | V1 | V3 | V3 minus V1 |
| --- | ---: | ---: | ---: |
| Treasury auctions | -0.0300 | -0.0557 | -0.0257 |
| COT positioning | 0.3200 | 0.3229 | +0.0029 |
| CPI components | -0.0300 | -0.0245 | +0.0055 |
| Credit events | 0.3200 | 0.3175 | -0.0025 |
| Bank EPS growth | 0.0411 | -0.1575 | -0.1986 |
| EPS direction | 0.3200 | 0.4800 | +0.1600 |
| FOMC July 2022 | -0.1700 | -0.0200 | +0.1500 |
| FOMC September 2024 | -0.1700 | -0.2700 | -0.1000 |
| Macro revisions | 0.3500 | 0.2333 | -0.1167 |
| Post-earnings reaction | 0.4367 | 0.1967 | -0.2400 |

The `-0.2700` FOMC 2024 score is consistent with a failed faithfulness gate:
the V3 offline answer scored 0/6 with the published local NLI judge. This is a
diagnosis, not proof of the sealed run's reason code. The V4 pre-cutoff rate
forecast cites the policy and market-positioning context and scores 6/6 on
both public FOMC practice units locally. The original V1 remains our highest
completed Development score.

The score comparison is diagnostic only. We do not select per-task variants or
fit intervals from post-cutoff outcomes or scores. For Treasury auctions, a
walk-forward check on pre-cutoff rows (49 next-auction predictions) found that
the same-issue-type average only slightly improved MAE from 0.0943 to 0.0922
against the six-auction average; this is too small to justify a change.
For CPI, pre-cutoff monthly rows give unstable short-window forecasts. No
resolved Development outcomes are in the image.

Third place on the public T4 board was `0.3097` when checked on 2026-09-28.
That benchmark can change, and local checks cannot estimate V4's hidden score.

V4 scored all 10 units. The per-unit scores in official order were `-0.0557`,
`0.2929`, `-0.0245`, `0.2300`, `-0.0300`, `0.4800`, `-0.0300`,
`-0.0300`, `0.2333`, and `0.0633`. The V4 FOMC scores are consistent with
admission plus zero regression skill and full interval coverage. This is an
inference from the composite formula; the hidden detail fields are unavailable.
Auction, CPI, macro, and EPS-direction scores were identical to V3 even though
other House-driven families changed substantially. The classification code and
retrieval for those changed families did not change between V3 and V4. Model
output variance, call failures, and platform execution differences remain
possible explanations; the participant report cannot distinguish them.


## V6 diagnostic — 2026-10-06

Submission **963432** is accepted in Development and currently **Submitted**,
with no score returned yet. See [V6_SUBMISSION.md](V6_SUBMISSION.md) for the exact
image digest, ZIP hash, source commit, and publication workflow.

This version uses deterministic corpus-only extraction and forecasting, with zero
neural calls and no external fitted model. It is an adaptation for the official
input contract, not the independently tested laboratory Ridge candidate. Six
unit tests, 11 public tasks, and all 11 official smoke checks passed; the published
digest produced byte-identical answers. These checks establish executability and
format admission, not hidden forecast quality.

The official scoring rules changed after the September submissions. Any numerical
comparison with V1/V3/V4 needs that caveat; no improvement is claimed while the
new score and participant report remain unavailable.
