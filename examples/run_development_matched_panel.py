"""Prepare, authorize, or run the 50-episode development panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from epiagentbench.development_matched_panel import (
    authorize_panel_spend,
    prepare_panel,
    run_environment_preflight,
    run_panel,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--cohort-manifest", required=True, type=Path)
    prepare.add_argument("--authentication-key", required=True, type=Path)
    prepare.add_argument("--claude-secure-storage-dir", required=True, type=Path)
    prepare.add_argument("--codex-secure-storage-dir", required=True, type=Path)
    prepare.add_argument("--private-state", required=True, type=Path)
    prepare.add_argument("--public-manifest", required=True, type=Path)
    prepare.add_argument("--timeout", type=int, default=900)
    prepare.add_argument("--claude-max-budget-usd", type=float, default=5.0)
    authorize = commands.add_parser("authorize")
    authorize.add_argument("--authentication-key", required=True, type=Path)
    authorize.add_argument("--claude-secure-storage-dir", required=True, type=Path)
    authorize.add_argument("--codex-secure-storage-dir", required=True, type=Path)
    authorize.add_argument("--private-state", required=True, type=Path)
    authorize.add_argument("--public-manifest", required=True, type=Path)
    authorize.add_argument("--acknowledgement-text", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--authentication-key", required=True, type=Path)
    preflight.add_argument("--claude-secure-storage-dir", required=True, type=Path)
    preflight.add_argument("--codex-secure-storage-dir", required=True, type=Path)
    preflight.add_argument("--private-state", required=True, type=Path)
    preflight.add_argument("--public-manifest", required=True, type=Path)
    preflight.add_argument("--public-preflight", required=True, type=Path)
    preflight.add_argument(
        "--acknowledge-unbounded-provider-spend", action="store_true", required=True
    )
    run = commands.add_parser("run")
    run.add_argument("--authentication-key", required=True, type=Path)
    run.add_argument("--claude-secure-storage-dir", required=True, type=Path)
    run.add_argument("--codex-secure-storage-dir", required=True, type=Path)
    run.add_argument("--private-state", required=True, type=Path)
    run.add_argument("--public-manifest", required=True, type=Path)
    run.add_argument("--public-results", required=True, type=Path)
    run.add_argument(
        "--acknowledge-unbounded-provider-spend", action="store_true", required=True
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.command == "prepare":
        payload = prepare_panel(
            root=root,
            cohort_manifest_path=args.cohort_manifest,
            authentication_key_file=args.authentication_key,
            claude_secure_storage_dir=args.claude_secure_storage_dir,
            codex_secure_storage_dir=args.codex_secure_storage_dir,
            private_state_path=args.private_state,
            public_manifest_path=args.public_manifest,
            timeout_seconds=args.timeout,
            claude_max_budget_usd=args.claude_max_budget_usd,
        )
    elif args.command == "authorize":
        payload = authorize_panel_spend(
            root=root,
            authentication_key_file=args.authentication_key,
            claude_secure_storage_dir=args.claude_secure_storage_dir,
            codex_secure_storage_dir=args.codex_secure_storage_dir,
            private_state_path=args.private_state,
            public_manifest_path=args.public_manifest,
            acknowledgement_text=args.acknowledgement_text,
        )
    elif args.command == "preflight":
        payload = run_environment_preflight(
            root=root,
            authentication_key_file=args.authentication_key,
            claude_secure_storage_dir=args.claude_secure_storage_dir,
            codex_secure_storage_dir=args.codex_secure_storage_dir,
            private_state_path=args.private_state,
            public_manifest_path=args.public_manifest,
            public_preflight_path=args.public_preflight,
            acknowledge_unbounded_provider_spend=(
                args.acknowledge_unbounded_provider_spend
            ),
        )
    else:
        payload = run_panel(
            root=root,
            authentication_key_file=args.authentication_key,
            claude_secure_storage_dir=args.claude_secure_storage_dir,
            codex_secure_storage_dir=args.codex_secure_storage_dir,
            private_state_path=args.private_state,
            public_manifest_path=args.public_manifest,
            public_results_path=args.public_results,
            acknowledge_unbounded_provider_spend=(
                args.acknowledge_unbounded_provider_spend
            ),
        )
    print(
        json.dumps(
            {
                "panel_id": payload["panel_id"],
                "status": payload["status"],
                "planned_assignments": payload.get("planned_assignments", 0),
                "terminal_assignments": payload.get("terminal_assignments", 0),
                "preflight_profiles": len(payload.get("profiles", [])),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
