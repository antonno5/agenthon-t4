#!/usr/bin/env python3
"""Check synthetic backtest answers with the published Track 4 NLI judge.

Run inside the pinned checker/NLI image. The result is diagnostic, because
synthetic docs differ from the organizer's hidden task evidence.
"""

import argparse
import json
from pathlib import Path

from faithfulness.judge import build_ensemble_judge, build_unit_context, check_answer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/backtest"))
    parser.add_argument("--case", action="append", required=True,
                        help="FAMILY/CASE_ID; repeat for selected cases")
    parser.add_argument("--candidate", action="append", required=True)
    args = parser.parse_args()
    judge = build_ensemble_judge(cache_dir="/model-cache")
    for case_ref in args.case:
        family, case_id = case_ref.split("/", 1)
        case_dir = args.root / "cases" / family / case_id
        ctx = build_unit_context(case_dir)
        for candidate in args.candidate:
            answer_path = args.root / "answers" / candidate / case_id / "answer.json"
            try:
                answer = json.loads(answer_path.read_text(encoding="utf-8"))
                result = check_answer(answer, ctx, judge)
                row = {"case": case_ref, "candidate": candidate,
                       "faithfulness": result.faithfulness,
                       "gate_pass": result.gate_pass,
                       "supported": sum(x.supported for x in result.predictions),
                       "roster": result.roster_count}
            except Exception as exc:
                row = {"case": case_ref, "candidate": candidate,
                       "error": f"{type(exc).__name__}: {exc}"}
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
