#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 TEAM_NUMBER" >&2
  exit 2
fi
if [ ! -t 0 ]; then
  echo "Run this script in an interactive terminal so the Team Key can be hidden." >&2
  exit 2
fi

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
team_number=$1
image_digest=sha256:cfea7eaa99421714c7789190c6dc79ad30a14a9744ae621ec09e7d67b2b2db8d

sudo -n docker run --rm -it \
  --network none \
  --volume "$repo_dir:/workspace" \
  --workdir /workspace \
  --env TEAM_NUMBER="$team_number" \
  --env IMAGE_DIGEST="$image_digest" \
  --entrypoint sh \
  agenthon-t4:checker \
  -ec '
    team_id=$(qfbench2 submission alias --team-number "$TEAM_NUMBER")
    python scripts/create_descriptor.py --team-id "$team_id" --digest "$IMAGE_DIGEST"
    qfbench2 submission pack --descriptor submission.json --team-number "$TEAM_NUMBER" --out submission.zip
    python - <<"PY"
import json, zipfile
with zipfile.ZipFile("submission.zip") as archive:
    assert set(archive.namelist()) == {"submission.json", "team-claim.json"}
    descriptor = json.loads(archive.read("submission.json"))
    claim = json.loads(archive.read("team-claim.json"))
    assert descriptor["image"]["digest"] == "sha256:cfea7eaa99421714c7789190c6dc79ad30a14a9744ae621ec09e7d67b2b2db8d"
    assert claim["schema_version"] == "2.0"
    assert "team_key" not in claim
print("ZIP contains only submission.json and team-claim.json; Team Key absent")
PY
  '
