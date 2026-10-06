#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
pool="$1"
case "$pool" in confirmation_a|confirmation_b) ;; *) exit 2;; esac
root="$PWD/test-output/v9"
mounts=(-v "$PWD/lab:/app/lab:ro" -v "$PWD/agent_submit_v8:/app/agent_submit_v8:ro")
for round in r4 r5 r6; do
  mkdir -p "$root/$round/predictions"
  mounts+=(-v "$root/r4/inputs:/experiment/$round/inputs:ro")
  mounts+=(-v "$root/r4/manifests:/experiment/$round/manifests:ro")
  mounts+=(-v "$root/$round/models:/experiment/$round/models:ro")
  mounts+=(-v "$root/$round/predictions:/experiment/$round/predictions:rw")
done
mounts+=(-v "$root/r4/feature-view.json:/experiment/r4/feature-view.json:ro")
mounts+=(-v "$root/r4/feature-view.json:/experiment/r5/feature-view.json:ro")
mounts+=(-v "$root/r5/base-root.json:/experiment/r5/base-root.json:ro")
run_predict() {
  sudo -n docker run --rm --network=none --read-only --user 1000:1000 \
    --cpus=8 --memory=12g --cap-drop=ALL --security-opt=no-new-privileges \
    --tmpfs /tmp:rw,size=64m --tmpfs /experiment:rw,size=64m,uid=1000,gid=1000 \
    -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e PYTHONDONTWRITEBYTECODE=1 \
    "${mounts[@]}" agenthon-t4:v9-lab -m "$1" predict --root "/experiment/$2" --pool "$pool"
}
run_predict lab.v9_models r4
run_predict lab.v9_advanced r5
run_predict lab.v9_stack r6
