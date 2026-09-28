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

Run the `Publish T4 image` GitHub Actions workflow, then make the GHCR package
public. Verify the exact digest anonymously and confirm `linux/amd64` before
putting it in a descriptor. Install the official `qfbench2-common` toolkit at
`v2.4.4` in a Python 3.13 environment. Copy its
`contracts/fixtures/c5/analysis_dev.json` fixture and set the team's derived
`team_id`, `image.registry=ghcr.io`, `image.repository=antonno5/agenthon-t4`,
the pushed digest, `image_access=public`, `models=[]`, and `license=MIT`.
Keep `competition_id=agenthon2026-analysis-dev`, `track=analysis`,
`phase=dev`, and `category=api`.

Use `qfbench2 submission alias --team-number <N>` and
`qfbench2 submission pack --descriptor submission.json --team-number <N>
--out submission.zip`. The toolkit prompts for the Team Key without echoing it.
Never put the key in this repository, image, ZIP, chat or command arguments.
Upload the ZIP in T4 Development using the team's sole CodaBench account.
