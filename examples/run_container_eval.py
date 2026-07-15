"""Launch the client-only example agent through the Linux Docker runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from epiagentbench.trusted.sandbox import evaluate_container_agent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="epiagentbench-agent")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    agent_script = Path(__file__).with_name("random_agent.py").resolve()
    result = evaluate_container_agent(
        image=args.image,
        agent_script=str(agent_script),
        seed=args.seed,
    )
    print(json.dumps(result.scorecard, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
