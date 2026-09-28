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
