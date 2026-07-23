"""Generate and control a one-shot persistent matched-panel LaunchAgent."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import sys
from pathlib import Path
from typing import Any, Sequence

# launchd intentionally supplies no PYTHONPATH or other environment.  Bootstrap
# this checked-in script from its own immutable repository location before the
# package import; the authenticated config later verifies the same root/path.
if __package__ in {None, ""}:
    _REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    _SOURCE_ROOT = str(_REPOSITORY_ROOT / "src")
    if _SOURCE_ROOT not in sys.path:
        sys.path.insert(0, _SOURCE_ROOT)

from epiagentbench.launchd_agent import (
    LaunchAgentError,
    finalize_launch_agent,
    generate_launch_agent,
    install_launch_agent,
    launch_agent_status,
    run_launch_agent_worker,
    start_launch_agent,
    uninstall_launch_agent,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control an owner-scoped, one-shot persistent panel runner"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate")
    generate.add_argument("--operation", required=True, choices=("preflight", "production"))
    generate.add_argument("--runtime-dir", required=True, type=Path)
    generate.add_argument("--repository-root", required=True, type=Path)
    generate.add_argument(
        "--python-executable", type=Path, default=Path(sys.executable).resolve()
    )
    generate.add_argument("--authentication-key", required=True, type=Path)
    generate.add_argument("--claude-secure-storage-dir", required=True, type=Path)
    generate.add_argument("--codex-secure-storage-dir", required=True, type=Path)
    generate.add_argument("--private-state", required=True, type=Path)
    generate.add_argument("--public-manifest", required=True, type=Path)
    output = generate.add_mutually_exclusive_group(required=True)
    output.add_argument("--public-preflight", type=Path)
    output.add_argument("--public-results", type=Path)
    generate.add_argument("--cursor-keychain-service", required=True)
    generate.add_argument(
        "--cursor-keychain-account", default=pwd.getpwuid(os.getuid()).pw_name
    )
    generate.add_argument("--instance-token", help=argparse.SUPPRESS)

    for name in ("install", "start", "status", "finalize", "uninstall"):
        command = commands.add_parser(name)
        command.add_argument("--runtime-dir", required=True, type=Path)
        command.add_argument("--authentication-key", required=True, type=Path)

    worker = commands.add_parser("worker", help=argparse.SUPPRESS)
    worker.add_argument("--config", required=True, type=Path)
    return parser


def _safe_print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            payload = generate_launch_agent(
                operation=args.operation,
                runtime_dir=args.runtime_dir,
                repository_root=args.repository_root,
                python_executable=args.python_executable,
                authentication_key_file=args.authentication_key,
                claude_secure_storage_dir=args.claude_secure_storage_dir,
                codex_secure_storage_dir=args.codex_secure_storage_dir,
                private_state_path=args.private_state,
                public_manifest_path=args.public_manifest,
                public_preflight_path=args.public_preflight,
                public_results_path=args.public_results,
                cursor_keychain_service=args.cursor_keychain_service,
                cursor_keychain_account=args.cursor_keychain_account,
                instance_token=args.instance_token,
            )
        elif args.command == "install":
            payload = install_launch_agent(
                args.runtime_dir,
                authentication_key_file=args.authentication_key,
            )
        elif args.command == "start":
            payload = start_launch_agent(
                args.runtime_dir,
                authentication_key_file=args.authentication_key,
            )
        elif args.command == "status":
            payload = launch_agent_status(
                args.runtime_dir,
                authentication_key_file=args.authentication_key,
            )
        elif args.command == "finalize":
            payload = finalize_launch_agent(
                args.runtime_dir,
                authentication_key_file=args.authentication_key,
            )
        elif args.command == "uninstall":
            payload = uninstall_launch_agent(
                args.runtime_dir,
                authentication_key_file=args.authentication_key,
            )
        else:
            # The launchd plist sends stdout/stderr to /dev/null.  The worker
            # also intentionally emits no provider output or exception detail.
            return run_launch_agent_worker(args.config)
    except LaunchAgentError:
        _safe_print({"status": "refused", "reason": "launch_agent_error"})
        return 2
    _safe_print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
