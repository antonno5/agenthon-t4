# Agenthon 2026 Track 4 — first submission

This repository packages the official deterministic minimal baseline for a first
Development submission. It is an interface and submission-path check, not a
competitive forecasting method. The source comes from
`Agenthon-2026/track4-analysis-public` at commit
`7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491` (MIT License).

The submitted image contains only this baseline and Python 3.13. Public task data,
team credentials and HFT data are not included.

## Local checks on cero

Docker requires `sudo -n` on this host. The official public kit is needed only
for local checks. Clone it outside this repository and verify the pinned commit.

```bash
git clone https://github.com/Agenthon-2026/track4-analysis-public.git /tmp/agenthon-t4
git -C /tmp/agenthon-t4 checkout 7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491
cd /home/antonnos/agenthon-t4
sudo -n docker build --platform linux/amd64 -t agenthon-t4:local .
python3 scripts/check_public.py --docker 'sudo -n docker' \
  --image agenthon-t4:local --units-dir /tmp/agenthon-t4/units
sudo -n docker build -f Dockerfile.check -t agenthon-t4:checker .
for unit in /tmp/agenthon-t4/units/t4-*; do
  test -f "$unit/task.json" || continue
  sudo -n docker run --rm --network=none \
    -v "$PWD/test-output/$(basename "$unit"):/output:ro" \
    agenthon-t4:checker "/opt/track4/units/$(basename "$unit")" /output --track analysis
done
```

`qfbench2-smoke` is a non-rankable interface preview. It does not establish
prediction quality or the production faithfulness score.

## Publishing and submitting

The first image was published by [this workflow run](https://github.com/antonno5/agenthon-t4/actions/runs/36405553926)
at digest `sha256:cfea7eaa99421714c7789190c6dc79ad30a14a9744ae621ec09e7d67b2b2db8d`.
Make the GHCR package public, then verify this exact digest anonymously and
confirm `linux/amd64` before packing. The checkout remains private.

On cero, in an interactive terminal, run:

```bash
cd /home/antonnos/agenthon-t4
./scripts/pack_submission.sh YOUR_TEAM_NUMBER
```

The script uses the official `qfbench2-common@v2.4.4` toolkit already installed
in the Python 3.13 checker image. It copies the T4 Development fixture, runs
`qfbench2 submission alias` and `qfbench2 submission pack`, and checks that the
ZIP has exactly `submission.json` and `team-claim.json`. Both toolkit commands
ask for the Team Key on a hidden terminal prompt. The Team Key is not saved to
the host, image or ZIP. Never put it in this repository, chat or command arguments.
Upload `submission.zip` from the team's sole CodaBench account under T4
Development → My Submissions.

## V2: evidence retrieval and House forecasting

`Dockerfile.v2` builds the next candidate. It chunks long filings into exact,
citable windows, retrieves pre-cutoff passages per entity, asks the official
House model for a forecast and quoted evidence, and validates the answer before
writing it. It falls back to a deterministic forecast if the model route fails.
The container uses only the Python standard library. See
`ARTIFACT_PROVENANCE.md` for the artifact record.

Build and exercise it on cero:

```bash
sudo -n docker build -f Dockerfile.v2 -t agenthon-t4:v2-local .
python3 scripts/check_public.py --docker 'sudo -n docker' \
  --image agenthon-t4:v2-local --units-dir /tmp/agenthon-t4/units
python3 -m scripts.check_model_route
```

The published V2 digest is passed to `scripts/pack_submission_v2.sh` together
with the team number. The script discloses the House model in the descriptor and
creates `submission-v2.zip` with a hidden Team Key prompt.

V3 adds a CPI-component path that uses the cited pre-cutoff three-month
average as its point forecast and the cited historical range as its interval.
On the public CPI practice unit, the official local NLI judge supports all
11 predictions, versus 1 of 11 for the V2 offline fallback. This is a
faithfulness diagnostic; resolved CPI values are unavailable locally.
It also uses the latest pre-cutoff vintage revision note to forecast the next
revision direction. The local NLI judge supports all 12 public revision rows,
versus 9 of 12 for the V2 fallback.
For Treasury auctions, it forecasts from the cited same-tenor recent average
and historical range; the local NLI judge supports all seven public rows,
versus two of seven for the V2 fallback.

V4 adds an explicit pre-cutoff policy-regime forecast for FOMC yield-curve
tasks and a broad uncertainty floor for House regression forecasts. On the two
public FOMC practice units, the published local NLI judge supports 6/6 rows
in each. All 11 public units pass structure and official smoke checks. These
checks do not predict the hidden Development score; see `EXPERIMENTS.md` for
actual V1 and V3 CodaBench results.

The V4 image was published by [this workflow run](https://github.com/antonno5/agenthon-t4/actions/runs/36433485761)
at digest `sha256:e330b1614d1c5982ebb0ad13768eb5db73ce36447e9d2e88aa441afec7268cb5`.
An anonymous pull by digest confirmed `linux/amd64` and interface label `2.0`.
The exact published digest ran offline on all 11 public units.
