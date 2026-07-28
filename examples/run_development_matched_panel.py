"""Prepare, authorize, or run the 50-episode development panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _require_isolated_main_process() -> None:
    if (
        sys.flags.isolated != 1
        or sys.flags.no_site != 1
        or sys.flags.ignore_environment != 1
        or sys.flags.dont_write_bytecode != 1
        or not sys.flags.safe_path
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    _require_isolated_main_process()


# V17 invokes this script with ``-I -S -B``.  Build the only permitted import
# path explicitly: standard library first, then the frozen repository, then
# the bound virtual-environment packages.  Appending these directories does
# not execute .pth, sitecustomize, or usercustomize.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if sys.flags.isolated:
    if (
        sys.flags.no_site != 1
        or sys.flags.ignore_environment != 1
        or sys.flags.dont_write_bytecode != 1
        or not sys.flags.safe_path
    ):
        raise RuntimeError("Refusing a partially isolated V17 Python process")
    _SOURCE_ROOT = _REPOSITORY_ROOT / "src"
    _VENV_ROOT = Path(sys.executable).parent.parent
    _SITE_PACKAGES = (
        _VENV_ROOT
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    if (
        not (_VENV_ROOT / "pyvenv.cfg").is_file()
        or not _SITE_PACKAGES.is_dir()
    ):
        raise RuntimeError("V17 requires its bound virtual environment")
    sys.path.append(str(_SOURCE_ROOT))
    sys.path.append(str(_SITE_PACKAGES))

    from epiagentbench.launchd_agent import (
        _validate_isolated_python_process,
    )

    _validate_isolated_python_process(
        python_executable=Path(sys.executable),
        repository_root=_REPOSITORY_ROOT,
        binding=None,
        include_site_packages=True,
    )

from epiagentbench.development_matched_panel import (
    PANEL_ID,
    assert_durable_live_execution_paths,
    assert_terminal_receipt_ready_for_exit,
    authenticate_panel,
    authorize_panel_spend,
    bind_panel_receipt_commit,
    freeze_panel_cohort,
    panel_authentication_status,
    preflight_preparation_runtime,
    prepare_panel,
    reconcile_terminal_receipt,
    run_environment_preflight,
    run_panel,
    verify_preparation_runtime,
)
from epiagentbench.persistent_supervisor import (
    HANDLED_TERMINAL_RECEIPT_EXIT_CODE,
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
    panel_id = PANEL_ID if raw_panel_id == PANEL_ID else "unknown"
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
    preparation_preflight = commands.add_parser(
        "preflight-preparation-runtime",
        help=(
            "Attest the exact provider-free scientific runtime before "
            "creating any private panel artifact"
        ),
    )
    preparation_preflight.add_argument(
        "--expected-benchmark-base-commit", required=True
    )
    preparation_preflight.add_argument(
        "--runtime-cache-dir", required=True, type=Path
    )
    preparation_verify = commands.add_parser(
        "verify-preparation-runtime",
        help="Re-attest against the committed pre-private runtime receipt",
    )
    preparation_verify.add_argument(
        "--preparation-runtime-receipt", required=True, type=Path
    )
    preparation_verify.add_argument(
        "--expected-benchmark-base-commit", required=True
    )
    preparation_verify.add_argument(
        "--runtime-cache-dir", required=True, type=Path
    )
    freeze = commands.add_parser(
        "freeze",
        help="Freeze the one V17 cohort after runtime receipt verification",
    )
    freeze.add_argument(
        "--preparation-runtime-receipt", required=True, type=Path
    )
    freeze.add_argument(
        "--expected-benchmark-base-commit", required=True
    )
    freeze.add_argument("--runtime-cache-dir", required=True, type=Path)
    freeze.add_argument("--authentication-key", required=True, type=Path)
    freeze.add_argument("--output-directory", required=True, type=Path)
    freeze.add_argument("--freeze-claim", required=True, type=Path)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--cohort-manifest", required=True, type=Path)
    prepare.add_argument(
        "--preparation-runtime-receipt", required=True, type=Path
    )
    prepare.add_argument(
        "--expected-benchmark-base-commit", required=True
    )
    prepare.add_argument("--runtime-cache-dir", required=True, type=Path)
    prepare.add_argument("--authentication-key", required=True, type=Path)
    prepare.add_argument("--freeze-claim", required=True, type=Path)
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
    bind_receipt = commands.add_parser(
        "bind-receipt",
        help=(
            "Bind an already-committed authentication or preflight receipt "
            "to exact repository bytes without invoking a provider"
        ),
    )
    _add_panel_state_arguments(bind_receipt)
    bind_receipt.add_argument(
        "--operation",
        required=True,
        choices=("authentication", "preflight"),
    )
    reconcile_terminal = commands.add_parser(
        "reconcile-terminal-receipt",
        help=(
            "Publish an authenticated terminal receipt after a public-write "
            "failure without invoking any provider"
        ),
    )
    reconcile_terminal.add_argument(
        "--operation",
        required=True,
        choices=("preflight", "production"),
    )
    reconcile_terminal.add_argument(
        "--authentication-key", required=True, type=Path
    )
    reconcile_terminal.add_argument(
        "--private-state", required=True, type=Path
    )
    reconcile_terminal.add_argument(
        "--public-manifest", required=True, type=Path
    )
    reconcile_terminal.add_argument(
        "--public-output", required=True, type=Path
    )
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
    if args.command == "preflight-preparation-runtime":
        print(
            json.dumps(
                preflight_preparation_runtime(
                    root=root,
                    expected_benchmark_base_commit=(
                        args.expected_benchmark_base_commit
                    ),
                    runtime_cache_dir=args.runtime_cache_dir,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "verify-preparation-runtime":
        verification = verify_preparation_runtime(
            root=root,
            receipt_path=args.preparation_runtime_receipt,
            expected_benchmark_base_commit=(
                args.expected_benchmark_base_commit
            ),
            runtime_cache_dir=args.runtime_cache_dir,
        )
        public_verification = {
            name: value
            for name, value in verification.items()
            if name != "runtime_cache_contract"
        }
        print(
            json.dumps(
                public_verification,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "freeze":
        print(
            json.dumps(
                freeze_panel_cohort(
                    root=root,
                    preparation_runtime_receipt_path=(
                        args.preparation_runtime_receipt
                    ),
                    expected_benchmark_base_commit=(
                        args.expected_benchmark_base_commit
                    ),
                    runtime_cache_dir=args.runtime_cache_dir,
                    authentication_key_file=args.authentication_key,
                    output_directory=args.output_directory,
                    freeze_claim_path=args.freeze_claim,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    assert_durable_live_execution_paths(
        root=root,
        private_state_path=args.private_state,
    )
    if args.command == "prepare":
        payload = prepare_panel(
            root=root,
            cohort_manifest_path=args.cohort_manifest,
            preparation_runtime_receipt_path=(
                args.preparation_runtime_receipt
            ),
            expected_benchmark_base_commit=(
                args.expected_benchmark_base_commit
            ),
            runtime_cache_dir=args.runtime_cache_dir,
            authentication_key_file=args.authentication_key,
            freeze_claim_path=args.freeze_claim,
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
    elif args.command == "bind-receipt":
        payload = bind_panel_receipt_commit(
            root=root,
            operation=args.operation,
            authentication_key_file=args.authentication_key,
            claude_secure_storage_dir=args.claude_secure_storage_dir,
            codex_secure_storage_dir=args.codex_secure_storage_dir,
            private_state_path=args.private_state,
            public_manifest_path=args.public_manifest,
        )
    elif args.command == "reconcile-terminal-receipt":
        payload = reconcile_terminal_receipt(
            root=root,
            operation=args.operation,
            authentication_key_file=args.authentication_key,
            private_state_path=args.private_state,
            public_manifest_path=args.public_manifest,
            public_output_path=args.public_output,
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
        if payload["status"] == "passed_pending_supervisor_completion":
            return 0
        assert_terminal_receipt_ready_for_exit(
            root=root,
            operation="preflight",
            authentication_key_file=args.authentication_key,
            private_state_path=args.private_state,
            public_manifest_path=args.public_manifest,
            public_output_path=args.public_preflight,
        )
        return HANDLED_TERMINAL_RECEIPT_EXIT_CODE
    if args.command == "run":
        if payload["status"] == "complete_pending_supervisor_completion":
            return 0
        assert_terminal_receipt_ready_for_exit(
            root=root,
            operation="production",
            authentication_key_file=args.authentication_key,
            private_state_path=args.private_state,
            public_manifest_path=args.public_manifest,
            public_output_path=args.public_results,
        )
        return HANDLED_TERMINAL_RECEIPT_EXIT_CODE
    return 0


if __name__ == "__main__":
    _require_isolated_main_process()
    raise SystemExit(main())
