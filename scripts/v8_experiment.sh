#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec sudo -n docker run --rm --network=none --read-only --user 1000:1000 \
  --cpus=4 --memory=4g --tmpfs /tmp:rw,size=64m \
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/lab:/app/lab:ro" \
  -v "$PWD/agent_submit_v8:/app/agent_submit_v8:ro" \
  -v "$PWD/test-output/independent-demo/official-track4:/official:ro" \
  -v "$PWD/test-output/v8-analyst-validated:/experiment:rw" \
  agenthon-t4:algorithmic-lab-v2 -m lab.v8_experiment "$@"
