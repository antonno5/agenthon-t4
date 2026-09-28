"""Run the submitted image on every public T4 unit and check output structure."""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baseline_agent.indexer import build_index


def check_answer(unit: Path, answer_path: Path) -> None:
    task = json.loads((unit / "task.json").read_text(encoding="utf-8"))
    card = tomllib.loads((unit / "card.toml").read_text(encoding="utf-8"))
    answer = json.loads(answer_path.read_text(encoding="utf-8"))

    assert answer["task_id"] == task["task_id"], unit.name
    target = task.get("target_type") or task.get("target", {}).get("type")
    assert answer.get("target_type") == target, unit.name
    expected = [entity["entity_id"] for entity in task["entities"]]
    predictions = answer["entity_predictions"]
    assert [entry["entity_id"] for entry in predictions] == expected, unit.name
    level = card["scoring"]["params"]["interval_level"]

    # Use the starter kit's text and offset convention, including flat `text` documents.
    docs = {doc.doc_id: doc for doc in build_index(unit / "corpus")}
    assert docs, unit.name
    for entry in predictions:
        point = entry["point_forecast"]
        interval = entry["interval"]
        assert isinstance(point, (int, float)) and math.isfinite(point), unit.name
        assert interval["level"] == level, unit.name
        assert all(math.isfinite(interval[key]) for key in ("lo", "hi")), unit.name
        assert interval["lo"] <= interval["hi"], unit.name
        assert entry["claims"], unit.name
        for claim in entry["claims"]:
            doc = docs[claim["doc_id"]]
            assert doc.doc_date and doc.doc_date <= task["cutoff_date"], unit.name
            start, end = claim["span_start"], claim["span_end"]
            assert 0 <= start < end <= len(doc.text), unit.name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--units-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("test-output"))
    parser.add_argument("--docker", default="docker", help="Docker command, e.g. 'sudo -n docker'")
    args = parser.parse_args()
    docker = shlex.split(args.docker)
    units = sorted(path for path in args.units_dir.glob("t4-*") if (path / "task.json").is_file())
    if len(units) != 11:
        raise SystemExit(f"Expected 11 public units, found {len(units)}")
    args.output_root.mkdir(parents=True, exist_ok=True)
    for unit in units:
        output = args.output_root / unit.name
        output.mkdir(parents=True, exist_ok=True)
        answer = output / "answer.json"
        answer.unlink(missing_ok=True)
        subprocess.run(
            docker
            + [
                "run", "--rm", "--network=none", "--platform=linux/amd64",
                "--user", f"{os.getuid()}:{os.getgid()}",
                "-v", f"{unit.resolve()}:/input:ro",
                "-v", f"{output.resolve()}:/output",
                args.image,
                "analyze", "--task", "/input/task.json",
                "--corpus", "/input/corpus",
                "--out", "/output/answer.json",
            ],
            check=True,
        )
        check_answer(unit, answer)
        print(f"PASS {unit.name}")
    print(f"PASS {len(units)} units")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
