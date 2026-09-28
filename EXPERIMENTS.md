# Track 4 Development experiments

As of 2026-09-28. The CodaBench score is the only result that measures hidden
forecast quality. Local schema, smoke and NLI checks do not use resolution
labels and cannot predict the leaderboard score.

| Candidate | Image digest | CodaBench result | Local evidence |
| --- | --- | --- | --- |
| V1 official minimal baseline | `sha256:cfea7eaa99421714c7789190c6dc79ad30a14a9744ae621ec09e7d67b2b2db8d` | ID 949583, `0.1388` | 11/11 public structural and smoke |
| V2 BM25 + House | `sha256:3e3f1471568f848a631763dcc89f2ccee270ac2e1158555a5fed5f6c0ce8fbdc` | Not submitted | 11/11 public structural and smoke; House route checked with a local fake server |
| V3 House + cited historical forecasts | `sha256:5641c8876673e5b3029e2d1d0b0f48ac6f28661d01e49fb24deb9f09118a0161` | Awaiting upload | Published digest ran offline on 11/11 public units; official smoke 11/11; local published NLI on targeted public families: CPI 11/11, macro revisions 12/12, Treasury auctions 7/7 |

V3 uses only the pre-cutoff frozen corpus for its historical estimates and
citations. The three specialized paths use a three-month CPI average, the most
recent same-series revision direction, and a same-tenor auction average. The
other families use House forecasts with BM25-retrieved excerpts and exact
citations. See `ARTIFACT_PROVENANCE.md`.

Next comparison after V3 finishes: record the total Development score and any
per-unit faithfulness, prediction and coverage metrics available in Detailed
Results. Keep V1 as a known-good fallback. A score above `0.3097` would have
matched third place on the public T4 board at this document's date; the board
can change.
