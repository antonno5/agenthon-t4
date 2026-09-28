#!/usr/bin/env python3
"""Run the published NLI diagnostic once across local public answers.

This script runs only inside the local checker/NLI image; it is not copied into
the competition image. The public units have no released resolution labels.
"""

import json
from pathlib import Path

from faithfulness.judge import build_ensemble_judge, build_unit_context, check_answer


def main() -> None:
    judge = build_ensemble_judge(cache_dir="/model-cache")
    for answer_path in sorted(Path("/answers").glob("t4-*/answer.json")):
        unit_dir = Path("/opt/track4/units") / answer_path.parent.name
        try:
            result = check_answer(
                json.loads(answer_path.read_text()), build_unit_context(unit_dir), judge
            )
            print(
                f"{answer_path.parent.name}: {result.faithfulness:.3f} "
                f"({'PASS' if result.gate_pass else 'FAIL'}), "
                f"{sum(p.supported for p in result.predictions)}/{result.roster_count}",
                flush=True,
            )
        except Exception as exc:
            print(f"{answer_path.parent.name}: ERROR {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
