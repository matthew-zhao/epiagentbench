"""Prepare or run the precommitted development-only three-system pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from epiagentbench.development_pilot import prepare_panel, run_panel


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "run"):
        child = subparsers.add_parser(name)
        child.add_argument("--private-manifest", required=True, type=Path)
        child.add_argument("--public-manifest", required=True, type=Path)
    prepare = subparsers.choices["prepare"]
    prepare.add_argument("--timeout", type=int, default=900)
    prepare.add_argument("--claude-max-budget-usd", type=float, default=2.0)
    run = subparsers.choices["run"]
    run.add_argument("--public-results", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.command == "prepare":
        payload = prepare_panel(
            root=root,
            private_manifest_path=args.private_manifest,
            public_manifest_path=args.public_manifest,
            timeout_seconds=args.timeout,
            claude_max_budget_usd=args.claude_max_budget_usd,
        )
    else:
        payload = run_panel(
            root=root,
            private_manifest_path=args.private_manifest,
            public_manifest_path=args.public_manifest,
            public_results_path=args.public_results,
        )
    print(
        json.dumps(
            {
                "panel_id": payload["panel_id"],
                "status": payload["status"],
                "planned_assignments": payload["planned_assignments"],
                "completed_assignments": len(payload["results"]),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
