#!/usr/bin/env python3
"""Walk-forward T4 surrogate from pre-cutoff public historical tables.

The generated task/corpus are the only files mounted into each candidate. Truth
stays in a sibling file and is never mounted. This is a screening test, not an
official score: no production faithfulness judge or House endpoint is available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path

FAMILIES = {
    "auction": "t4-auction-btc-202411-us7",
    "cpi": "t4-cpicomp-202410-us11",
    "macro": "t4-macrorev-20240930-us6",
    "macro_global": "t4-macrorev-20240930-us6",
}
AUCTION_ROW = re.compile(r"^(\d{4}-\d\d-\d\d) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+)$")
MONTH_ROW = re.compile(r"^(\d{4}-\d\d) \| (.*)$")
VINTAGE = re.compile(r"as_of_(\d{4}-\d\d-\d\d)")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def provenance(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def save_case(root: Path, family: str, case_id: str, task: dict, docs: list[dict], truth: dict,
              sources: list[dict]) -> None:
    case = root / family / case_id
    if case.exists():
        raise FileExistsError(f"Refusing to overwrite backtest case: {case}")
    task["task_id"] = case_id
    task["corpus_manifest"] = "corpus/manifest.json"
    docs_by_id = {}
    for doc in docs:
        if doc["doc_date"] > task["cutoff_date"]:
            raise ValueError(f"Post-cutoff document {doc['doc_id']}")
        if doc["doc_id"] in docs_by_id:
            raise ValueError(f"Duplicate document {doc['doc_id']}")
        docs_by_id[doc["doc_id"]] = doc
    # Fail closed on any exact target value or future date in inputs. A number
    # may legitimately recur in history, so date/row exclusion is the key audit.
    for doc in docs:
        if case_id.startswith("bt-auction"):
            for target_date in (v["date"] for v in truth.values()):
                if target_date in doc["text"]:
                    raise ValueError(f"Future auction date leaked: {target_date}")
        if case_id.startswith("bt-cpi"):
            target_month = next(iter(truth.values()))["month"]
            if re.search(rf"(?m)^{re.escape(target_month)} \|", doc["text"]):
                raise ValueError(f"Future CPI row leaked: {target_month}")
        if case_id.startswith("bt-macro"):
            for next_date in {v["next_vintage"] for v in truth.values()}:
                if next_date in doc["text"]:
                    raise ValueError(f"Future vintage leaked: {next_date}")
    manifest_files = []
    for doc in docs:
        path = case / "corpus" / (doc["doc_id"] + ".json")
        write(path, doc)
        manifest_files.append({"path": "corpus/" + path.name, "role": "corpus",
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write(case / "corpus" / "manifest.json",
          {"manifest_version": "2.0", "unit_id": case_id, "files": manifest_files})
    write(case / "task.json", task)
    write(case / "truth.json", {"values": truth, "sources": sources})
    (case / "card.toml").write_text(
        f'schema_version = "2.0"\n[task]\nid = "{case_id}"\n'
        f'track = "analysis"\nfamily = "{task["family"]}"\n'
        f'target_type = "{task["target"]["type"]}"\n'
        f'cutoff_date = "{task["cutoff_date"]}"\n'
        f'resolution_date = "{task["resolution_date"]}"\n'
        '[scoring.params]\nfaithfulness_threshold = 0.80\ninterval_level = 0.90\n'
        f'target_type = "{task["target"]["type"]}"\n'
        'composite_weights = [0.7, 0.3]\ntau_citation = 0.5\n',
        encoding="utf-8",
    )


def common_task(family: str, kind: str, target_name: str, cutoff: str,
                resolution: str, entities: list[dict], prompt: str) -> dict:
    target = {"name": target_name, "type": kind}
    if kind == "classification":
        target["labels"] = ["up", "down"]
    return {
        "schema_version": "3", "family": family, "target": target,
        "prompt": prompt, "cutoff_date": cutoff, "resolution_date": resolution,
        "interval_level": 0.9, "entities": entities,
    }


def build_auction(units: Path, out: Path) -> int:
    source_dir = units / FAMILIES["auction"] / "corpus"
    histories = {}
    source_files = []
    for tenor in (2, 3, 5, 7, 10, 20, 30):
        path = source_dir / f"TDIRECT_AUCTIONS_{tenor}Y_20241031.json"
        source_files.append(provenance(path))
        doc = load(path)
        rows = []
        for line in doc["text"].splitlines():
            match = AUCTION_ROW.match(line)
            if match:
                when, row_tenor, issue, offering, btc, high_yield, indirect = match.groups()
                if not row_tenor.strip().startswith((f"{tenor}-Year", f"{tenor - 1}-Year")):
                    raise ValueError("Auction tenor mismatch")
                rows.append((when, line, float(btc)))
        if len(rows) != 13:
            raise ValueError(f"Expected 13 auction rows for {tenor}Y; found {len(rows)}")
        histories[tenor] = (doc, rows)
    count = 0
    for target_index in range(6, 13):  # Apr-Oct 2024, each preceded by >=6 rows
        target_month = histories[2][1][target_index][0][:7]
        prior_dates = [rows[target_index - 1][0] for _, rows in histories.values()]
        cutoff = max(prior_dates)
        docs, entities, truth = [], [], {}
        for tenor, (source, rows) in histories.items():
            prior = rows[:target_index]
            future = rows[target_index]
            if future[0][:7] != target_month or any(r[0] > cutoff for r in prior):
                raise ValueError("Auction temporal alignment error")
            values = [r[2] for r in prior]
            lo, hi, avg = min(values), max(values), statistics.mean(values[-6:])
            doc = dict(source)
            doc["doc_id"] = f"TDIRECT_AUCTIONS_{tenor}Y_BACKTEST_{cutoff.replace('-', '')}"
            doc["doc_date"] = prior[-1][0]
            doc["title"] = f"Treasury {tenor}-Year auction results through {prior[-1][0]}"
            doc["text"] = (
                f"Treasury {tenor}-Year Note auction history through {prior[-1][0]}.\n"
                "Source: TreasuryDirect auction results. Bid-to-cover ratio = bids tendered / amount accepted.\n\n"
                "auction_date | term | new/reopen | offering_$B | bid_to_cover | high_yield_% | indirect_share_%\n"
                + "\n".join(r[1] for r in prior)
                + f"\n\nNOTES (derived from the table above): across the {len(prior)} auctions shown, "
                f"the bid-to-cover ratio ranged from {lo:.2f} to {hi:.2f}; "
                f"the average over the six most recent auctions is {avg:.3f}.\n"
            )
            docs.append(doc)
            eid = f"AUC_{tenor}Y_{target_month.replace('-', '')}"
            entities.append({"entity_id": eid, "name": f"{tenor}-Year Treasury auction",
                             "tenor": f"{tenor}-Year", "unit": "bid_to_cover_ratio"})
            truth[eid] = {"value": future[2], "date": future[0]}
        task = common_task("auction_demand", "regression", "bid_to_cover_ratio", cutoff,
                           max(x["date"] for x in truth.values()), entities,
                           "Forecast next month's Treasury auction bid-to-cover ratio for each tenor using only the frozen history. Cite evidence for every prediction.")
        save_case(out, "auction", f"bt-auction-{target_month}", task, docs, truth, source_files)
        count += 1
    return count


def fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def build_cpi(units: Path, out: Path) -> int:
    path = units / FAMILIES["cpi"] / "corpus" / "ALFRED_CPI_COMPONENTS_20241031.json"
    source = load(path)
    original_task = load(units / FAMILIES["cpi"] / "task.json")
    lines = source["text"].splitlines()
    header = next(line for line in lines if line.startswith("month | "))
    components = [x.strip() for x in header.split("|")[1:]]
    rows = []
    for line in lines:
        match = MONTH_ROW.match(line)
        if match:
            month = match.group(1)
            nums = [float(x.strip()) for x in match.group(2).split("|")]
            if len(nums) == len(components):
                rows.append((month, nums))
    if len(rows) != 9:
        raise ValueError(f"Expected 9 CPI rows, found {len(rows)}")
    roster = original_task["entities"]
    count = 0
    for target_index in range(3, len(rows)):  # Apr-Sep; prior prints known by ~20th
        target_month, realized = rows[target_index]
        prior = rows[:target_index]
        cutoff = target_month + "-20"  # prior-month CPI print typically released by then
        next_month = date(int(target_month[:4]), int(target_month[5:]) + 1, 20).isoformat()
        doc = dict(source)
        doc["doc_id"] = f"ALFRED_CPI_COMPONENTS_BACKTEST_{cutoff.replace('-', '')}"
        doc["doc_date"] = cutoff
        doc["title"] = f"Synthetic CPI component snapshot through {prior[-1][0]}"
        notes = []
        for j, component in enumerate(components):
            history = [r[1][j] for r in prior]
            lo, hi = min(history), max(history)
            avg = statistics.mean(history[-3:])
            notes.append(
                f"- {component}: {prior[-1][0]} archived value {fmt_pct(history[-1])}; "
                f"three-month average (latest three months) {fmt_pct(avg)}; "
                f"2024 range {fmt_pct(lo)} to {fmt_pct(hi)}."
            )
        doc["text"] = (
            f"CPI-U seasonally adjusted month-over-month changes through {prior[-1][0]}. "
            "Historical rows are transcribed from the public ALFRED snapshot; this is a synthetic backtest cutoff.\n\n"
            + header + "\n"
            + "\n".join(month + " | " + " | ".join(f"{v:+.2f}" for v in values) for month, values in prior)
            + "\n\nNOTES (derived from the table above):\n" + "\n".join(notes) + "\n"
        )
        by_name = {e["name"]: e for e in roster}
        entities, truth = [], {}
        for j, name in enumerate(components):
            entity = dict(by_name[name])
            entity["ref_month"] = target_month
            entity["latest_published_mom_pct"] = prior[-1][1][j]
            entity["latest_published_ref_month"] = prior[-1][0]
            entity["release_date"] = next_month
            entities.append(entity)
            truth[entity["entity_id"]] = {"value": realized[j], "month": target_month}
        task = common_task("cpi_component_nowcast", "regression", "cpi_component_mom_first_print",
                           cutoff, next_month, entities,
                           "Forecast the next monthly CPI component percent changes from this frozen historical snapshot. Cite evidence for every prediction.")
        save_case(out, "cpi", f"bt-cpi-{target_month}", task, [doc], truth, [provenance(path)])
        count += 1
    return count


def build_macro(units: Path, out: Path) -> int:
    source_dir = units / FAMILIES["macro"] / "corpus"
    count = 0
    for path in sorted(source_dir.glob("ALFRED_*_VINTAGES_*.json")):
        source = load(path)
        series = source["series_id"]
        lines = source["text"].splitlines()
        header = next(line for line in lines if line.startswith("reference_month | "))
        vintage_dates = VINTAGE.findall(header)
        if len(vintage_dates) < 3:
            continue
        rows = []
        for line in lines:
            if re.match(r"^\d{4}-\d\d \|", line):
                fields = [x.strip() for x in line.split("|")]
                if len(fields) == len(vintage_dates) + 1:
                    rows.append((fields[0], [None if x == "--" else float(x) for x in fields[1:]]))
        if not rows:
            raise ValueError(f"No vintage rows in {path}")
        # At least two prior vintages let the agent see one revision direction.
        for target_index in range(2, len(vintage_dates)):
            cutoff, next_date = vintage_dates[target_index - 1:target_index + 1]
            eligible = [(month, values[target_index - 1], values[target_index])
                        for month, values in rows
                        if values[target_index - 1] is not None and values[target_index] is not None
                        and values[target_index] != values[target_index - 1]]
            if not eligible:
                continue
            doc = dict(source)
            doc["doc_id"] = f"ALFRED_{series}_VINTAGES_BACKTEST_{cutoff.replace('-', '')}"
            doc["doc_date"] = cutoff
            doc["title"] = f"{series} vintages through {cutoff}"
            table = ["reference_month | " + " | ".join("as_of_" + d for d in vintage_dates[:target_index])]
            for month, values in rows:
                table.append(month + " | " + " | ".join("--" if v is None else str(v) for v in values[:target_index]))
            notes = []
            for month, values in rows:
                for j in range(1, target_index):
                    before, after = values[j - 1:j + 1]
                    if before is not None and after is not None and before != after:
                        direction = "UP" if after > before else "DOWN"
                        notes.append(f"- The {month} estimate was revised {direction} from {before} "
                                     f"(as of {vintage_dates[j - 1]}) to {after} (as of {vintage_dates[j]}).")
            doc["text"] = (
                f"{series} real-time ALFRED vintages through {cutoff}.\n"
                "Revision history available at this synthetic cutoff.\n\nVINTAGE TABLE\n"
                + "\n".join(table) + "\n\nREVISION NOTES (derived from the vintage table above):\n"
                + "\n".join(notes) + "\n"
            )
            entities, truth = [], {}
            for month, previous, realized in eligible:
                eid = f"{series}_{month}_{next_date.replace('-', '')}"
                entities.append({"entity_id": eid, "series_id": series, "ref_month": month,
                                 "latest_precutoff_estimate": previous,
                                 "latest_precutoff_vintage": cutoff,
                                 "resolving_release_date": next_date, "corpus_ref": "corpus/"})
                truth[eid] = {"label": "up" if realized > previous else "down",
                              "value": realized, "next_vintage": next_date}
            task = common_task("macro_revision_direction", "classification",
                               "next_estimate_revision_direction", cutoff, next_date, entities,
                               "Predict the next revision direction, revised value and interval for each row using only this vintage table. Cite evidence.")
            save_case(out, "macro", f"bt-macro-{series}-{cutoff}", task, [doc], truth,
                      [provenance(path)])
            count += 1
    return count


def build_macro_global(units: Path, out: Path) -> int:
    """Same mixed-series roster shape as the scored macro task, at Jul/Aug cutoffs."""
    source_dir = units / FAMILIES["macro"] / "corpus"
    sources = [p for p in sorted(source_dir.glob("ALFRED_*_VINTAGES_*.json"))]
    count = 0
    for cutoff in ("2024-07-31", "2024-08-31"):
        docs, entities, truth, provenance_rows = [], [], {}, []
        for path in sources:
            source = load(path)
            series = source["series_id"]
            lines = source["text"].splitlines()
            header = next(x for x in lines if x.startswith("reference_month | "))
            vintage_dates = VINTAGE.findall(header)
            prior_indexes = [j for j, day in enumerate(vintage_dates) if day <= cutoff]
            later_indexes = [j for j, day in enumerate(vintage_dates) if day > cutoff]
            if len(prior_indexes) < 2 or not later_indexes:
                continue
            prior_index, next_index = prior_indexes[-1], later_indexes[0]
            known_day, next_day = vintage_dates[prior_index], vintage_dates[next_index]
            rows = []
            for line in lines:
                if re.match(r"^\d{4}-\d\d \|", line):
                    fields = [x.strip() for x in line.split("|")]
                    if len(fields) == len(vintage_dates) + 1:
                        rows.append((fields[0], [None if x == "--" else float(x) for x in fields[1:]]))
            eligible = [(month, vals[prior_index], vals[next_index]) for month, vals in rows
                        if vals[prior_index] is not None and vals[next_index] is not None
                        and vals[prior_index] != vals[next_index]]
            if not eligible:
                continue
            doc = dict(source)
            doc["doc_id"] = f"ALFRED_{series}_VINTAGES_BACKTEST_{known_day.replace('-', '')}"
            doc["doc_date"] = known_day
            doc["title"] = f"{series} vintages through {known_day}"
            table = ["reference_month | " + " | ".join("as_of_" + d for d in vintage_dates[:prior_index + 1])]
            for month, vals in rows:
                table.append(month + " | " + " | ".join("--" if v is None else str(v)
                                                        for v in vals[:prior_index + 1]))
            notes = []
            for month, vals in rows:
                for j in range(1, prior_index + 1):
                    before, after = vals[j - 1:j + 1]
                    if before is not None and after is not None and before != after:
                        direction = "UP" if after > before else "DOWN"
                        notes.append(f"- The {month} estimate was revised {direction} from {before} "
                                     f"(as of {vintage_dates[j - 1]}) to {after} (as of {vintage_dates[j]}).")
            doc["text"] = (f"{series} ALFRED vintage table through {known_day}.\n\nVINTAGE TABLE\n"
                           + "\n".join(table) + "\n\nREVISION NOTES (derived from the table):\n"
                           + "\n".join(notes) + "\n")
            docs.append(doc)
            provenance_rows.append(provenance(path))
            for month, previous, realized in eligible:
                eid = f"{series}_{month}_{next_day.replace('-', '')}"
                entities.append({"entity_id": eid, "series_id": series, "ref_month": month,
                                 "latest_precutoff_estimate": previous,
                                 "latest_precutoff_vintage": known_day,
                                 "resolving_release_date": next_day, "corpus_ref": "corpus/"})
                truth[eid] = {"label": "up" if realized > previous else "down",
                              "value": realized, "next_vintage": next_day}
        if not entities:
            continue
        task = common_task("macro_revision_direction", "classification",
                           "next_estimate_revision_direction", cutoff,
                           max(v["next_vintage"] for v in truth.values()), entities,
                           "Predict next revision directions across all six macro series from frozen ALFRED vintages. Cite evidence.")
        save_case(out, "macro_global", f"bt-macro-all-{cutoff}", task, docs, truth, provenance_rows)
        count += 1
    return count


def validate_and_score(case: Path, answer: dict) -> dict:
    task, truth = load(case / "task.json"), load(case / "truth.json")["values"]
    if answer.get("task_id") != task["task_id"]:
        raise ValueError("Answer task_id mismatch")
    if answer.get("target_type") != task["target"]["type"]:
        raise ValueError("Answer target_type mismatch")
    docs = {d["doc_id"]: d for path in (case / "corpus").glob("*.json")
            if (d := load(path)).get("text") is not None}
    predictions = answer.get("entity_predictions")
    if not isinstance(predictions, list):
        raise ValueError("Missing predictions")
    by_id = {p["entity_id"]: p for p in predictions}
    ids = [e["entity_id"] for e in task["entities"]]
    if len(by_id) != len(ids) or set(by_id) != set(ids):
        raise ValueError("Roster missing, duplicated, or unknown")
    ys, ps, coverage, correct, cited = [], [], [], 0, 0
    for eid in ids:
        p = by_id[eid]
        point = p.get("point_forecast")
        interval = p.get("interval") or {}
        if not isinstance(point, (float, int)) or not math.isfinite(point):
            raise ValueError(f"Invalid point for {eid}")
        lo, hi = interval.get("lo"), interval.get("hi")
        if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in (lo, hi)):
            raise ValueError(f"Invalid interval for {eid}")
        if not (lo <= point <= hi and interval.get("level") == 0.9):
            raise ValueError(f"Invalid interval order/level for {eid}")
        claims = p.get("claims") or []
        if not claims:
            raise ValueError(f"No citation for {eid}")
        for claim in claims:
            doc = docs.get(claim.get("doc_id"))
            if doc is None or doc["doc_date"] > task["cutoff_date"]:
                raise ValueError(f"Unresolved/post-cutoff citation for {eid}")
            start, end = claim.get("span_start"), claim.get("span_end")
            if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(doc["text"]):
                raise ValueError(f"Bad citation span for {eid}")
        cited += 1
        y = truth[eid]
        if task["target"]["type"] == "classification":
            correct += p.get("label") == y["label"]
        else:
            ys.append(float(y["value"]))
            ps.append(float(point))
            coverage.append(lo <= y["value"] <= hi)
    if ys:
        mean_y = statistics.mean(ys)
        baseline_mae = statistics.mean(abs(y - mean_y) for y in ys)
        mae = statistics.mean(abs(y - p) for y, p in zip(ys, ps))
        quality = float(all(abs(y - p) <= 1e-12 for y, p in zip(ys, ps))) if baseline_mae == 0 else max(0.0, min(1.0, 1 - mae / baseline_mae))
        actual_coverage = statistics.mean(coverage)
        score = 0.7 * quality - 0.3 * abs(actual_coverage - 0.9)
    else:
        mae = None
        actual_coverage = None
        quality = correct / len(ids)
        score = 0.7 * quality
    return {"score_without_nli": round(score, 6), "quality": round(quality, 6),
            "coverage": None if actual_coverage is None else round(actual_coverage, 6),
            "mae": None if mae is None else round(mae, 6), "rows": len(ids),
            "citation_syntax_fraction": cited / len(ids)}


def run_one(case: Path, image: str, image_id: str, result_dir: Path) -> dict:
    case = case.resolve()
    result_dir = result_dir.resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    result_dir.chmod(0o777)
    answer_path = result_dir / "answer.json"
    image_record = result_dir / "image.txt"
    if answer_path.exists() and image_record.exists() and image_record.read_text() == image_id:
        return validate_and_score(case, load(answer_path))
    cmd = ["sudo", "-n", "docker", "run", "--rm", "--network=none", "--platform=linux/amd64",
           "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
           "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--user", "65534:65534",
           "--mount", f"type=bind,src={case / 'task.json'},dst=/input/task.json,readonly",
           "--mount", f"type=bind,src={case / 'corpus'},dst=/input/corpus,readonly",
           "--mount", f"type=bind,src={result_dir},dst=/output", image,
           "analyze", "--task", "/input/task.json", "--corpus", "/input/corpus",
           "--out", "/output/answer.json"]
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
    if run.returncode != 0:
        raise RuntimeError(f"Container failed ({run.returncode}): {run.stderr[-1000:]}")
    image_record.write_text(image_id, encoding="utf-8")
    return validate_and_score(case, load(answer_path))


def summarize(results: dict) -> None:
    print("candidate\tfamily\tcases\tmean_surrogate\tmean_quality\tmean_coverage")
    for candidate, families in results.items():
        for family, cases in families.items():
            valid = [x for x in cases.values() if "score_without_nli" in x]
            if len(valid) != len(cases):
                print(f"{candidate}\t{family}\tERRORS {len(cases) - len(valid)}; see results.json")
                continue
            if not valid:
                continue
            scores = [x["score_without_nli"] for x in valid]
            quality = [x["quality"] for x in valid]
            cover = [x["coverage"] for x in valid if x["coverage"] is not None]
            print(f"{candidate}\t{family}\t{len(valid)}\t{statistics.mean(scores):.4f}\t"
                  f"{statistics.mean(quality):.4f}\t"
                  f"{statistics.mean(cover):.4f}" if cover else
                  f"{candidate}\t{family}\t{len(valid)}\t{statistics.mean(scores):.4f}\t"
                  f"{statistics.mean(quality):.4f}\tNA")
    if len(results) == 2:
        first, second = results
        print(f"\npaired difference: {second} minus {first}")
        for family in results[first]:
            common = sorted(set(results[first][family]) & set(results[second].get(family, {})))
            deltas = [results[second][family][k]["score_without_nli"] -
                      results[first][family][k]["score_without_nli"] for k in common
                      if "score_without_nli" in results[first][family][k]
                      and "score_without_nli" in results[second][family][k]]
            if deltas:
                print(f"{family}: mean {statistics.mean(deltas):+.4f}; "
                      f"wins/losses/ties {sum(x>0 for x in deltas)}/{sum(x<0 for x in deltas)}/{sum(x==0 for x in deltas)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=Path, default=Path("/tmp/agenthon-t4/units"))
    parser.add_argument("--out", type=Path, default=Path("test-output/backtest"))
    parser.add_argument("--image", action="append", default=[], help="NAME=DOCKER_IMAGE; repeat")
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    args.out = args.out.resolve()
    cases = args.out / "cases"
    if not cases.exists():
        counts = {"auction": build_auction(args.units, cases),
                  "cpi": build_cpi(args.units, cases),
                  "macro": build_macro(args.units, cases),
                  "macro_global": build_macro_global(args.units, cases)}
        print("Generated cases:", counts)
    elif not (cases / "macro_global").exists():
        print("Generated macro_global cases:", build_macro_global(args.units, cases))
    if args.build_only:
        return
    images = dict(item.split("=", 1) for item in args.image)
    if not images:
        parser.error("At least one --image NAME=DOCKER_IMAGE is required unless --build-only")
    image_ids = {}
    for name, image in images.items():
        inspect = subprocess.run(
            ["sudo", "-n", "docker", "image", "inspect", image, "--format", "{{.Id}}"],
            capture_output=True, text=True, check=True,
        )
        image_ids[name] = inspect.stdout.strip()
    write(args.out / "images.json", {name: {"reference": images[name], "image_id": image_ids[name]}
                                     for name in images})
    results = {}
    for name, image in images.items():
        results[name] = defaultdict(dict)
        for family in FAMILIES:
            for case in sorted((cases / family).iterdir()):
                print(f"Running {name} {case.name}", flush=True)
                try:
                    metrics = run_one(case, image, image_ids[name],
                                      args.out / "answers" / name / case.name)
                except Exception as exc:
                    metrics = {"error": str(exc)}
                    print(f"  ERROR: {exc}", flush=True)
                results[name][family][case.name] = metrics
    write(args.out / "results.json", results)
    summarize(results)
    if any("error" in row for families in results.values() for cases in families.values()
           for row in cases.values()):
        raise SystemExit("Backtest contains failed cases; inspect results.json")


if __name__ == "__main__":
    main()
