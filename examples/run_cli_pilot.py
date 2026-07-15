"""Run a development-only cloud-agent smoke episode."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from epiagentbench.pilot import evaluate_local_cli_agent, evaluate_paired_cli_agents


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("system", choices=("codex", "claude", "cursor", "all"))
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--family")
    parser.add_argument("--backend", choices=("reference", "starsim"), default="starsim")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--claude-max-budget-usd", type=float, default=1.0)
    args = parser.parse_args()
    if args.system == "all":
        results = evaluate_paired_cli_agents(
            seed=args.seed,
            family=args.family,
            backend=args.backend,
            timeout_seconds=args.timeout,
            claude_max_budget_usd=args.claude_max_budget_usd,
        )
        payload = [asdict(result) for result in results]
    else:
        result = evaluate_local_cli_agent(
            args.system,
            seed=args.seed,
            family=args.family,
            backend=args.backend,
            timeout_seconds=args.timeout,
            claude_max_budget_usd=args.claude_max_budget_usd,
        )
        payload = asdict(result)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
