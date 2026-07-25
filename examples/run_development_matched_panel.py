"""Prepare, authorize, or run the 50-episode development panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from epiagentbench.development_matched_panel import (
    assert_durable_live_execution_paths,
    authenticate_panel,
    authorize_panel_spend,
    panel_authentication_status,
    prepare_panel,
    run_environment_preflight,
    run_panel,
)

_AUTHENTICATION_STATUSES = frozenset(
    {
        "required",
        "running",
        "retryable_failed",
        "terminal_failed",
        "pending_publication",
        "passed",
    }
)
_AUTHENTICATION_PROVIDER_STATUSES = frozenset(
    {
        "required",
        "running",
        "retryable_failed",
        "terminal_failed",
        "passed",
    }
)


def _add_panel_state_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--authentication-key", required=True, type=Path)
    command.add_argument("--claude-secure-storage-dir", required=True, type=Path)
    command.add_argument("--codex-secure-storage-dir", required=True, type=Path)
    command.add_argument("--private-state", required=True, type=Path)
    command.add_argument("--public-manifest", required=True, type=Path)


def _safe_authentication_summary(payload: dict[str, object]) -> dict[str, object]:
    raw_status = payload.get("status")
    status = (
        raw_status
        if isinstance(raw_status, str) and raw_status in _AUTHENTICATION_STATUSES
        else "unknown"
    )
    raw_providers = payload.get("providers")
    providers = raw_providers if isinstance(raw_providers, dict) else {}

    def provider_status(name: str) -> str:
        raw_provider = providers.get(name)
        provider = raw_provider if isinstance(raw_provider, dict) else {}
        raw_provider_status = provider.get("status")
        if (
            isinstance(raw_provider_status, str)
            and raw_provider_status in _AUTHENTICATION_PROVIDER_STATUSES
        ):
            return raw_provider_status
        return "unknown"

    raw_model_calls_started = payload.get("model_calls_started")
    model_calls_started = (
        raw_model_calls_started
        if isinstance(raw_model_calls_started, int)
        and not isinstance(raw_model_calls_started, bool)
        and raw_model_calls_started >= 0
        else 0
    )
    raw_panel_id = payload.get("panel_id")
    panel_id = raw_panel_id if isinstance(raw_panel_id, str) else "unknown"
    return {
        "panel_id": panel_id,
        "status": status,
        "authentication_ready": status == "passed",
        "codex_status": provider_status("codex"),
        "managed_glean_status": provider_status("managed_glean"),
        "model_calls_started": model_calls_started,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--cohort-manifest", required=True, type=Path)
    prepare.add_argument("--authentication-key", required=True, type=Path)
    prepare.add_argument("--claude-secure-storage-dir", required=True, type=Path)
    prepare.add_argument("--codex-secure-storage-dir", required=True, type=Path)
    prepare.add_argument("--private-state", required=True, type=Path)
    prepare.add_argument("--public-manifest", required=True, type=Path)
    prepare.add_argument("--timeout", type=int, default=1800)
    prepare.add_argument("--claude-max-budget-usd", type=float, default=5.0)
    authorize = commands.add_parser("authorize")
    _add_panel_state_arguments(authorize)
    authorize.add_argument("--acknowledgement-text", required=True)
    authenticate = commands.add_parser(
        "authenticate",
        help="Run the operator-visible, zero-model authentication ceremony",
    )
    _add_panel_state_arguments(authenticate)
    authenticate.add_argument(
        "--acknowledge-interactive-authentication",
        action="store_true",
        required=True,
        help=(
            "Acknowledge that provider authentication instructions will be "
            "shown in this foreground terminal"
        ),
    )
    authentication_status = commands.add_parser(
        "auth-status",
        help="Read the sanitized authentication state without invoking a provider",
    )
    _add_panel_state_arguments(authentication_status)
    preflight = commands.add_parser("preflight")
    _add_panel_state_arguments(preflight)
    preflight.add_argument("--public-preflight", required=True, type=Path)
    preflight.add_argument("--supervisor-runtime", required=True, type=Path)
    preflight.add_argument(
        "--acknowledge-unbounded-provider-spend", action="store_true", required=True
    )
    run = commands.add_parser("run")
    _add_panel_state_arguments(run)
    run.add_argument("--public-results", required=True, type=Path)
    run.add_argument("--supervisor-runtime", required=True, type=Path)
    run.add_argument(
        "--acknowledge-unbounded-provider-spend", action="store_true", required=True
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    assert_durable_live_execution_paths(
        root=root,
        private_state_path=args.private_state,
    )
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
    elif args.command == "authenticate":
        payload = authenticate_panel(
            root=root,
            authentication_key_file=args.authentication_key,
            claude_secure_storage_dir=args.claude_secure_storage_dir,
            codex_secure_storage_dir=args.codex_secure_storage_dir,
            private_state_path=args.private_state,
            public_manifest_path=args.public_manifest,
            acknowledge_interactive_authentication=(
                args.acknowledge_interactive_authentication
            ),
        )
    elif args.command == "auth-status":
        payload = panel_authentication_status(
            root=root,
            authentication_key_file=args.authentication_key,
            claude_secure_storage_dir=args.claude_secure_storage_dir,
            codex_secure_storage_dir=args.codex_secure_storage_dir,
            private_state_path=args.private_state,
            public_manifest_path=args.public_manifest,
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
            supervisor_runtime_dir=args.supervisor_runtime,
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
            supervisor_runtime_dir=args.supervisor_runtime,
            acknowledge_unbounded_provider_spend=(
                args.acknowledge_unbounded_provider_spend
            ),
        )
    if args.command in {"authenticate", "auth-status"}:
        print(
            json.dumps(
                _safe_authentication_summary(payload),
                indent=2,
                sort_keys=True,
            )
        )
    else:
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
    if args.command == "authenticate":
        return 0 if payload.get("status") == "passed" else 1
    if args.command == "preflight":
        return (
            0
            if payload["status"]
            == "passed_pending_supervisor_completion"
            else 1
        )
    if args.command == "run":
        return (
            0
            if payload["status"]
            == "complete_pending_supervisor_completion"
            else 1
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
