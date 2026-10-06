#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
module="$1"
shift
exec sudo -n docker run --rm --network=none --read-only --user 1000:1000 \
  --cpus=8 --memory=12g --tmpfs /tmp:rw,size=128m \
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/lab:/app/lab:ro" -v "$PWD/agent_submit_v8:/app/agent_submit_v8:ro" \
  -v "$PWD/test-output/independent-demo/official-track4:/official:ro" \
  -v "$PWD/test-output/v9:/experiment:rw" \
  agenthon-t4:algorithmic-lab-v2 -m "$module" "$@"
