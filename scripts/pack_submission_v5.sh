#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 TEAM_NUMBER IMAGE_DIGEST" >&2
  exit 2
fi
if [ ! -t 0 ]; then
  echo "Run this script in an interactive terminal so the Team Key can be hidden." >&2
  exit 2
fi

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
team_number=$1
image_digest=$2
case "$image_digest" in
  sha256:????????????????????????????????????????????????????????????????) ;;
  *) echo "IMAGE_DIGEST must be sha256:<64 hex characters>" >&2; exit 2 ;;
esac

sudo -n docker run --rm -it \
  --network none \
  --user "$(id -u):$(id -g)" \
  --volume "$repo_dir:/workspace" \
  --workdir /workspace \
  --env TEAM_NUMBER="$team_number" \
  --env IMAGE_DIGEST="$image_digest" \
  --entrypoint sh \
  agenthon-t4:checker \
  -ec '
    team_id=$(qfbench2 submission alias --team-number "$TEAM_NUMBER")
    python scripts/create_descriptor.py --team-id "$team_id" --digest "$IMAGE_DIGEST" --house-model --out submission-v5.json
    qfbench2 submission pack --descriptor submission-v5.json --team-number "$TEAM_NUMBER" --out submission-v5.zip
    python - <<"PY"
import json, os, zipfile
with zipfile.ZipFile("submission-v5.zip") as archive:
    assert set(archive.namelist()) == {"submission.json", "team-claim.json"}
    descriptor = json.loads(archive.read("submission.json"))
    claim = json.loads(archive.read("team-claim.json"))
    assert descriptor["image"]["digest"] == os.environ["IMAGE_DIGEST"]
    assert len(descriptor["models"]) == 1
    assert descriptor["models"][0]["access"] == "api"
    assert claim["schema_version"] == "2.0"
    assert "team_key" not in claim
print("V5 ZIP validated; Team Key absent")
PY
  '
