# Track 4 Development experiments

As of 2026-09-28. The CodaBench score is the only result that measures hidden
forecast quality. Local schema, smoke and NLI checks do not use resolution
labels and cannot predict the leaderboard score.

| Candidate | Image digest | CodaBench result | Local evidence |
| --- | --- | --- | --- |
| V1 official minimal baseline | `sha256:cfea7eaa99421714c7789190c6dc79ad30a14a9744ae621ec09e7d67b2b2db8d` | ID 949583, `0.1388` | 11/11 public structural and smoke |
| V2 BM25 + House | `sha256:3e3f1471568f848a631763dcc89f2ccee270ac2e1158555a5fed5f6c0ce8fbdc` | Not submitted | 11/11 public structural and smoke; House route checked with a local fake server |
| V3 House + cited historical forecasts | `sha256:5641c8876673e5b3029e2d1d0b0f48ac6f28661d01e49fb24deb9f09118a0161` | ID 949827, `0.1023` | Published digest ran offline on 11/11 public units; official smoke 11/11; local published NLI on targeted public families: CPI 11/11, macro revisions 12/12, Treasury auctions 7/7 |
| V4 policy-regime rate forecasts + interval floor | `sha256:e330b1614d1c5982ebb0ad13768eb5db73ce36447e9d2e88aa441afec7268cb5` | Awaiting upload | Anonymous GHCR digest pull; `linux/amd64`, interface `2.0`; published image structural 11/11, local official smoke 11/11, fake House route, public FOMC NLI 6/6 in each of two units |

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
