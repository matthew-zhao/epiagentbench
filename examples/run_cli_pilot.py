"""Run a development-only cloud-agent smoke episode."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from epiagentbench.pilot import (
    ClaudeEffort,
    evaluate_local_cli_agent,
    evaluate_paired_cli_agents,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("system", choices=("codex", "claude", "cursor", "all"))
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--family")
    parser.add_argument(
        "--backend",
        choices=("reference", "starsim", "starsim-ltc-v3"),
        default="starsim",
    )
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--model",
        help="exact model id for a single-system run (not valid with 'all')",
    )
    parser.add_argument(
        "--claude-effort",
        choices=tuple(item.value for item in ClaudeEffort),
        help="Claude reasoning effort; with 'all', affects only the Claude member",
    )
    parser.add_argument("--claude-max-budget-usd", type=float, default=1.0)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="print score/attribution metadata without submissions or diagnostics",
    )
    args = parser.parse_args()
    if args.system == "all" and args.model is not None:
        parser.error("--model cannot be used with 'all'; run each system explicitly")
    if args.claude_effort is not None and args.system not in {"claude", "all"}:
        parser.error("--claude-effort is only valid for Claude")
    if args.system == "all":
        results = evaluate_paired_cli_agents(
            seed=args.seed,
            family=args.family,
            backend=args.backend,
            timeout_seconds=args.timeout,
            claude_max_budget_usd=args.claude_max_budget_usd,
            claude_effort=args.claude_effort,
        )
        payload = [asdict(result) for result in results]
    else:
        result = evaluate_local_cli_agent(
            args.system,
            seed=args.seed,
            family=args.family,
            backend=args.backend,
            model=args.model,
            timeout_seconds=args.timeout,
            claude_max_budget_usd=args.claude_max_budget_usd,
            claude_effort=args.claude_effort,
        )
        payload = asdict(result)
    if args.summary_only:
        rows = payload if isinstance(payload, list) else [payload]
        payload = [
            {
                "system": row["system"],
                "requested_model": row["requested_model"],
                "observed_models": row["observed_models"],
                "cli_version": row["cli_version"],
                "returncode": row["returncode"],
                "elapsed_seconds": row["elapsed_seconds"],
                "audit_events": row["audit_events"],
                "valid": row["scorecard"].get("valid", False),
                "total": row["scorecard"].get("total", 0.0),
                "tool_calls": row["scorecard"].get("metrics", {}).get(
                    "tool_calls", 0
                ),
            }
            for row in rows
        ]
        if args.system != "all":
            payload = payload[0]
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
