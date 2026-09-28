#!/usr/bin/env python3
"""Create a T4 Development descriptor from the toolkit's frozen fixture."""

import argparse
import json
from pathlib import Path

import qfbench2_common
from qfbench2_common.contracts.descriptor import (
    SubmissionDescriptor,
    seal_descriptor_digest,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--house-model", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("submission.json"))
    args = parser.parse_args()

    fixture = (
        Path(qfbench2_common.__file__).parent
        / "contracts/fixtures/c5/analysis_dev.json"
    )
    descriptor = json.loads(fixture.read_text())
    descriptor.update(
        team_id=args.team_id,
        category="api",
        models=([{
            "name": "nvidia/nemotron-3-super-120b-a12b",
            "version": "rl-030326-fp8",
            "revision": "rl-030326-fp8",
            "training_cutoff": "unpublished",
            "access": "api",
        }] if args.house_model else []),
        license="MIT",
        image_access="public",
        image={
            "registry": "ghcr.io",
            "repository": "antonno5/agenthon-t4",
            "digest": args.digest,
        },
    )
    sealed = seal_descriptor_digest(descriptor)
    SubmissionDescriptor.from_mapping(sealed)
    args.out.write_text(json.dumps(sealed, indent=2) + "\n")
    print(f"Validated and wrote {args.out}")


if __name__ == "__main__":
    main()
