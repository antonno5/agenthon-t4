# Local T4 walk-forward test

`scripts/backtest_t4.py` turns the historical rows in the official public T4
corpora into earlier synthetic tasks. It withholds the next row/vintage, runs
each candidate image with **no network** against the truncated task and corpus,
then scores the answer against withheld history. The truth file is stored beside
the task but is never mounted into the candidate container. Case source hashes,
candidate image identities and every answer remain in the ignored
`test-output/backtest/` directory.

The test currently covers 7 monthly Treasury auction rounds, 6 monthly CPI
rounds, 17 single-series macro vintage steps, and 2 mixed-series macro rounds.
It uses the published quality and interval-coverage formula. It audits roster,
numeric fields, citation IDs, spans and dates. A separate NLI diagnostic can
apply the published local judge to selected cases.

## Run on cero

The public starter kit is checked out at `/tmp/agenthon-t4`. If it is absent,
clone `https://github.com/Agenthon-2026/track4-analysis-public` and point
`--units` at its `units` directory. Run from this repository:

```bash
python3 scripts/backtest_t4.py \
  --image v1=ghcr.io/antonno5/agenthon-t4@sha256:cfea7eaa99421714c7789190c6dc79ad30a14a9744ae621ec09e7d67b2b2db8d \
  --image v3=ghcr.io/antonno5/agenthon-t4@sha256:5641c8876673e5b3029e2d1d0b0f48ac6f28661d01e49fb24deb9f09118a0161
```

Replace or add `--image NAME=REFERENCE` to compare a local candidate. A Docker
image ID or registry digest gives a repeatable comparison. The program runs
`sudo -n docker`, which is how Docker is available to this user on cero.
It writes `results.json` and a per-candidate `answer.json` for every case.
Failed cases remain visible as `error` entries; do not average them away.

The NLI check runs inside the existing `agenthon-t4:nli` image and uses the
published two-model ensemble cached on cero. Example for the closest auction
and CPI folds:

```bash
sudo -n docker run --rm --network=none --platform=linux/amd64 \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  --mount type=bind,src=/home/antonnos/agenthon-t4/test-output/backtest,dst=/backtest,readonly \
  --mount type=bind,src=/home/antonnos/agenthon-t4/scripts/backtest_nli.py,dst=/backtest_nli.py,readonly \
  --mount type=bind,src=/home/antonnos/.cache/agenthon-nli,dst=/model-cache \
  --entrypoint /usr/local/bin/python agenthon-t4:nli /backtest_nli.py \
  --case auction/bt-auction-2024-10 --case cpi/bt-cpi-2024-09 \
  --candidate v1 --candidate v3
```

## Interpretation and limits

- `score_without_nli` is **not** a predicted CodaBench score. If the NLI
  faithfulness fraction is below 0.8, the actual unit gets the worst-case
  score (normally `-0.27`), regardless of forecast accuracy.
- The auction and macro histories carry dated rows/vintages. The CPI table is
  an October 2024 retrospective ALFRED snapshot; earlier monthly values may
  differ from what was published at each synthetic cutoff. CPI is diagnostic
  until archived as-of vintages and exact release dates are checked.
- The backtest does not recreate the House model endpoint. V3 uses deterministic
  references on these families; for the other T4 families an offline run would
  exercise its fallback and would **not** represent the submitted V3, V4 or V5.
- Historical examples are drawn from the same small official corpus. Treat
  overlapping folds as dependent observations. Hold the most recent fold out
  when choosing hyperparameters or interval widths; do not optimize against
  the 10 Development outcomes. Check the [official training policy](https://github.com/Agenthon-2026/track4-analysis-public/blob/main/docs/TRAINING-POLICY.md)
  before incorporating any feature or label into a submitted image.
- The generated cases do not cover COT, credit, earnings or FOMC tasks yet.
  Overall leaderboard rank cannot be inferred from the covered families.

## First comparison: V1 versus V3 (2026-09-28)

The numbers below are the local surrogate *without* the NLI gate. “Latest” is
the final historical fold before the official cutoff. The Development values
are the per-unit results reported in CodaBench by our team; they were not used
to build the cases or tune either image.

| Family | All folds V1 / V3 | Latest fold V1 / V3 | Development V1 / V3 |
| --- | ---: | ---: | ---: |
| Auction (7 folds) | -0.0300 / 0.0505 | -0.0300 / -0.0557 | -0.0300 / -0.0557 |
| CPI (6 folds) | 0.0211 / -0.0045 | 0.0280 / 0.0888 | -0.0300 / -0.0245 |
| Macro, mixed roster (2 folds) | 0.2752 / 0.3339 | 0.3316 / 0.4053 | 0.3500 / 0.2333 |

The latest fold selects the same winner as Development for auction and CPI,
but the opposite winner for macro. The mean over all folds selects the opposite
winner in **all three** families. This is direct evidence that the current
surrogate is useful for finding forecast and interval failures but is not yet
validated as a model-selection signal for the final leaderboard. Its sample
is small, the folds overlap, and it omits seven scored families.
The observed overall Development score was 0.1388 for V1 versus 0.1023 for V3.

On the latest auction fold, V3's mean absolute error is 0.0973 (versus V1's
2.5214), yet both get zero regression skill against the cross-sectional-mean
baseline; V3 also covers only 5/7 outcomes with its interval. That produces
its -0.0557 versus V1's -0.0300 and explains how a numerically closer forecast
can rank lower under the published metric.

The local NLI judge on the latest auction and CPI folds found V1 at 0/7 and
0/11 supported rows, and V3 at 7/7 and 10/11. Since Development gave V1
non-penalty scores on those units, faithfulness on these synthetic documents
also fails the external validity check. Treat that result as a warning about
citations on *these cases*, not as a prediction that V1 would receive -0.27
in the competition.
