"""Agenthon T4 analyze entry point."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agent import run_entity
from .client import HTTPModelClient
from .config import Config
from .formatter import build_answer
from .indexer import build_index
from .retriever import BM25Index

MAX_MODEL_CALLS = 24  # House budget is 25 admitted requests per unit.


def run(task_path: Path, corpus_dir: Path, out_path: Path, *, offline: bool = False) -> dict:
    task = json.loads(task_path.read_text(encoding="utf-8"))
    corpus = build_index(corpus_dir)
    index = BM25Index(corpus.chunks, task["cutoff_date"])
    config = Config.from_env()
    client = None if offline or not config.model_endpoint else HTTPModelClient(config)

    entities = task.get("entities", [])

    def predict(index_and_entity):
        position, entity = index_and_entity
        row_client = client if position < MAX_MODEL_CALLS else None
        return run_entity(task, entity, index, corpus, row_client, config.top_k)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(predict, enumerate(entities)))
    answer = build_answer(task, results, corpus)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(answer, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return answer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verb", nargs="?", default="analyze", choices=["analyze"])
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--offline", action="store_true", help="Use deterministic fallback")
    args = parser.parse_args()
    run(args.task, args.corpus, args.out, offline=args.offline)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
