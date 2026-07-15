"""Development-only runner for cloud-backed coding-agent smoke tests.

This module does not weaken the production sandbox.  It runs locally installed
agent CLIs from a fresh, public-only workspace while the simulator and scorer
remain behind :func:`launch_socket_episode`.  Because the CLI still has host
and provider-network access, every result is explicitly non-hermetic and must
not be published as a leaderboard score.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence

from .trusted.service import launch_socket_episode


DEFAULT_MODELS = {
    "codex": "gpt-5.6-sol",
    "claude": "claude-fable-5",
    "cursor": "glm-5.2-high",
}

DEFAULT_EXECUTABLES = {
    "codex": "codex",
    "claude": "claude",
    "cursor": "cursor-agent",
}

_MAX_CAPTURE_BYTES = 2_097_152
_SUBMISSION_KEYS = {
    "incident_assessment",
    "case_definition",
    "line_list",
    "hypotheses",
    "recommended_actions",
    "uncertainties",
    "next_evidence",
    "executive_brief",
}

_PUBLIC_TOOL_NAMES = (
    "get_manifest",
    "initial_observations",
    "search_observations",
    "request_interview",
    "order_confirmatory_test",
    "request_inspection",
    "advance_time",
    "recommend_action",
    "set_institution_control",
    "set_response_control",
    "submit_forecast",
    "get_clock_and_budget",
)


@dataclass(frozen=True, slots=True)
class PilotRunResult:
    system: str
    requested_model: str
    observed_models: tuple[str, ...]
    cli_version: str
    development_only: bool
    hermetic: bool
    returncode: int
    elapsed_seconds: float
    submission: dict[str, Any]
    scorecard: dict[str, Any]
    audit_events: tuple[str, ...]
    stdout_bytes: int
    stderr_bytes: int
    diagnostic: str


def _task_prompt() -> str:
    return """You are the on-call public-health surveillance investigator.

Investigate the synthetic alert using only the epiagent MCP tools. Determine
whether this is an outbreak, distinguish the plausible transmission/reporting
mechanisms, acquire discriminating evidence, make prospective encounter
forecasts, and execute the least harmful justified controls. Advance simulated
time and reassess; controls and forecasts count only when made through tools.

Return one final JSON object conforming exactly to submission.schema.json. Cite
only public observation IDs you actually received. Your final recommended
control state must match the last control state you executed for each target.
Do not browse the web, inspect parent directories, search for benchmark source,
or use any tool other than the epiagent MCP tools.

The required top-level fields are incident_assessment, case_definition,
line_list, hypotheses, recommended_actions, uncertainties, next_evidence, and
executive_brief. incident_assessment includes outbreak_probability (0 to 1),
status (outbreak, indeterminate, or not_outbreak), and evidence_ids. Each line
list item has patient_id, classification, and evidence_ids; classification must
be exactly suspected, probable, confirmed, or excluded. case_definition is
an object with the five string fields clinical, person, place, time, and
laboratory. Each hypothesis has type, nullable target_id, probability,
supporting_evidence_ids, and contradicting_evidence_ids. Each recommended
action has action_type, nullable target_id, urgency, evidence_ids, and
control_level when it reports a control. urgency must be exactly immediate,
within_24h, or monitor. Report only actions whose tool calls succeeded, and for
each control report the last successfully executed level. If the public
manifest contains hypothesis_catalog, submit every catalog option exactly once:
the hypothesis type is its catalog id, probabilities across all options must
sum to one, and options marked target_required need a public target_id.
"""


def _json_string(value: str) -> str:
    """JSON strings are valid TOML basic strings for Codex overrides."""

    return json.dumps(value, ensure_ascii=True)


def _mcp_definition(
    *, python: str, public_root: str, socket_path: str
) -> dict[str, Any]:
    return {
        "command": python,
        "args": ["-m", "epiagentbench_client.mcp_server"],
        "env": {
            "EPIAGENT_SOCKET": socket_path,
            "PYTHONPATH": public_root,
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    }


def build_agent_command(
    system: str,
    *,
    executable: str,
    model: str,
    workspace: str,
    schema_path: str,
    mcp_path: str,
    final_output_path: str,
    python: str,
    public_root: str,
    socket_path: str,
    claude_max_budget_usd: float = 1.0,
) -> list[str]:
    """Build a shell-free invocation for one supported local agent CLI."""

    if system not in DEFAULT_MODELS:
        raise ValueError("Unsupported pilot system")
    if not model or not executable:
        raise ValueError("Invalid pilot configuration")
    prompt = _task_prompt()
    if system == "codex":
        mcp = _mcp_definition(
            python=python, public_root=public_root, socket_path=socket_path
        )
        args_toml = json.dumps(mcp["args"], ensure_ascii=True)
        env_toml = "{" + ",".join(
            f"{key}={_json_string(value)}" for key, value in mcp["env"].items()
        ) + "}"
        return [
            executable,
            "exec",
            "--model",
            model,
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--disable",
            "shell_tool",
            "--disable",
            "apps",
            "--disable",
            "multi_agent",
            "--json",
            "--output-last-message",
            final_output_path,
            "--cd",
            workspace,
            "-c",
            'approval_policy="never"',
            "-c",
            'model_reasoning_effort="medium"',
            "-c",
            f"mcp_servers.epiagent.command={_json_string(python)}",
            "-c",
            f"mcp_servers.epiagent.args={args_toml}",
            "-c",
            f"mcp_servers.epiagent.env={env_toml}",
            "-c",
            "mcp_servers.epiagent.required=true",
            "-c",
            'mcp_servers.epiagent.default_tools_approval_mode="approve"',
            prompt,
        ]
    if system == "claude":
        if not math.isfinite(claude_max_budget_usd) or not (
            0 < claude_max_budget_usd <= 100
        ):
            raise ValueError("Invalid Claude budget")
        return [
            executable,
            "--safe-mode",
            "--print",
            "--model",
            model,
            "--no-session-persistence",
            "--no-chrome",
            "--tools",
            "",
            "--strict-mcp-config",
            "--mcp-config",
            mcp_path,
            "--allowedTools",
            "mcp__epiagent__*",
            "--output-format",
            "stream-json",
            "--verbose",
            "--max-budget-usd",
            str(claude_max_budget_usd),
            prompt,
        ]
    return [
        executable,
        "--print",
        "--trust",
        "--sandbox",
        "enabled",
        # Current Cursor CLI fail-closed filter: expose MCP calls, not its
        # built-in shell, filesystem, browser, search, or subagent tools.
        "--allowed-tools",
        # Cursor 2026.07 uses snake-case CLI enum values even though its JSONL
        # event payloads continue to use camel-case ``mcpToolCall`` keys.
        "mcp_tool_call",
        # Cursor's cloud agent may need a separate read-only discovery call
        # before it can issue the actual MCP call. The fresh CURSOR_DATA_DIR
        # and workspace contain only the public epiagent server.
        "get_mcp_tools_tool_call",
        "--model",
        model,
        "--output-format",
        "stream-json",
        "--workspace",
        workspace,
        prompt,
    ]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = child
    return value


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite JSON number")


def _decode_json(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )


def _submission_candidate(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and _SUBMISSION_KEYS.issubset(value):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    try:
        decoded = _decode_json(text)
    except (UnicodeError, ValueError, RecursionError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _jsonl_records(stdout: bytes) -> list[dict[str, Any]]:
    if len(stdout) > _MAX_CAPTURE_BYTES:
        return []
    records: list[dict[str, Any]] = []
    for raw_line in stdout.splitlines():
        if not raw_line.strip():
            continue
        try:
            value = _decode_json(raw_line.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _find_submission(records: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    for record in reversed(records):
        for key in ("structured_output", "result", "final_output", "text"):
            candidate = _submission_candidate(record.get(key))
            if candidate is not None:
                return candidate
        message = record.get("message")
        if isinstance(message, dict):
            candidate = _submission_candidate(message.get("content"))
            if candidate is not None:
                return candidate
            content = message.get("content")
            if isinstance(content, list):
                for block in reversed(content):
                    if isinstance(block, dict):
                        candidate = _submission_candidate(block.get("text"))
                        if candidate is not None:
                            return candidate
    return None


def _observed_models(records: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    values: list[str] = []
    for record in records:
        if record.get("type") == "system" and record.get("subtype") == "init":
            model = record.get("model")
            if isinstance(model, str):
                values.append(model)
        message = record.get("message")
        if isinstance(message, dict) and isinstance(message.get("model"), str):
            values.append(message["model"])
        usage = record.get("modelUsage") or record.get("model_usage")
        if isinstance(usage, dict):
            values.extend(key for key in usage if isinstance(key, str))
    return tuple(dict.fromkeys(values))


def _cursor_tool_audit(
    records: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Reject any Cursor tool attempt outside the public episode MCP."""

    def identity(value: Mapping[str, Any]) -> tuple[object, object]:
        arguments = value.get("args")
        nested = arguments if isinstance(arguments, dict) else {}
        provider = value.get("providerIdentifier", nested.get("providerIdentifier"))
        tool_name = value.get("toolName", nested.get("toolName"))
        return provider, tool_name

    for record in records:
        if record.get("type") == "getMcpToolsToolCall":
            continue
        if record.get("type") == "mcpToolCall":
            provider, tool_name = identity(record)
            if provider != "epiagent" or tool_name not in _PUBLIC_TOOL_NAMES:
                return ("agent_failure:unauthorized_tool",)
        if record.get("type") != "tool_call" or record.get("subtype") not in {
            "started",
            "completed",
        }:
            continue
        tool_call = record.get("tool_call")
        if not isinstance(tool_call, dict):
            return ("agent_failure:unauthorized_tool",)
        call_keys = [key for key in tool_call if key.endswith("ToolCall")]
        if call_keys == ["getMcpToolsToolCall"]:
            continue
        if call_keys != ["mcpToolCall"]:
            return ("agent_failure:unauthorized_tool",)
        mcp_call = tool_call["mcpToolCall"]
        if not isinstance(mcp_call, dict):
            return ("agent_failure:unauthorized_tool",)
        provider, tool_name = identity(mcp_call)
        if provider != "epiagent" or tool_name not in _PUBLIC_TOOL_NAMES:
            return ("agent_failure:unauthorized_tool",)
    return ()


def _model_matches(requested: str, observed: str) -> bool:
    requested_key = re.sub(r"[^a-z0-9]+", "", requested.lower())
    observed_key = re.sub(r"[^a-z0-9]+", "", observed.lower())
    if "fable" in requested_key:
        return "fable" in observed_key
    if "glm52" in requested_key:
        return "glm52" in observed_key
    if "gpt56sol" in requested_key:
        return "gpt56sol" in observed_key or observed_key == "gpt56"
    return requested_key == observed_key


def _record_shape_summary(stdout: bytes) -> str:
    shapes: list[dict[str, Any]] = []
    for record in _jsonl_records(stdout)[-12:]:
        shape: dict[str, Any] = {
            "type": record.get("type"),
            "subtype": record.get("subtype"),
            "keys": sorted(record)[:20],
        }
        message = record.get("message")
        if isinstance(message, dict):
            shape["message_keys"] = sorted(message)[:20]
        tool_call = record.get("tool_call")
        if isinstance(tool_call, dict):
            shape["tool_call"] = {
                key: tool_call.get(key)
                for key in ("name", "status", "error")
                if key in tool_call
            }
            shape["tool_call_keys"] = sorted(tool_call)[:20]
        if record.get("type") == "result":
            result = record.get("result")
            if isinstance(result, str):
                shape["result_preview"] = result[:1_500]
            elif isinstance(result, dict):
                shape["result_keys"] = sorted(result)[:20]
        shapes.append(shape)
    return "stream shapes: " + json.dumps(shapes, ensure_ascii=True)


def parse_agent_output(
    system: str,
    *,
    requested_model: str,
    stdout: bytes,
    final_output: bytes | None = None,
) -> tuple[dict[str, Any] | None, tuple[str, ...], tuple[str, ...]]:
    """Parse final output and detect provider-side model substitution."""

    records = _jsonl_records(stdout)
    observed = _observed_models(records)
    submission = None
    if final_output:
        try:
            submission = _submission_candidate(final_output.decode("utf-8"))
        except UnicodeError:
            submission = None
    if submission is None:
        submission = _find_submission(records)

    audit: list[str] = []
    if submission is None:
        audit.append("agent_failure:invalid_submission")
    if system == "cursor":
        audit.extend(_cursor_tool_audit(records))
    mismatches = [
        model for model in observed if not _model_matches(requested_model, model)
    ]
    if mismatches:
        audit.append("agent_failure:model_fallback")
        submission = None
    elif system == "claude" and not observed:
        # A Fable result is not attributable if the actual answering model is
        # absent; Claude Code may automatically switch life-science requests.
        audit.append("agent_failure:model_unverified")
        submission = None
    return submission, observed, tuple(audit)


def _prepare_workspace(root: Path, socket_path: str) -> tuple[Path, Path, Path, Path]:
    workspace = root / "workspace"
    public_root = root / "public"
    workspace.mkdir()
    public_root.mkdir()
    public_package = Path(__file__).resolve().parents[1] / "epiagentbench_client"
    shutil.copytree(public_package, public_root / "epiagentbench_client")

    schema_source = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "submission.schema.json"
    )
    schema_path = workspace / "submission.schema.json"
    shutil.copyfile(schema_source, schema_path)
    (workspace / "TASK.md").write_text(_task_prompt(), encoding="utf-8")

    mcp = _mcp_definition(
        python=sys.executable,
        public_root=str(public_root),
        socket_path=socket_path,
    )
    mcp_payload = {"mcpServers": {"epiagent": mcp}}
    mcp_path = workspace / "mcp.json"
    mcp_path.write_text(json.dumps(mcp_payload), encoding="utf-8")
    cursor_dir = workspace / ".cursor"
    cursor_dir.mkdir()
    (cursor_dir / "mcp.json").write_text(
        json.dumps(mcp_payload), encoding="utf-8"
    )
    (cursor_dir / "cli.json").write_text(
        json.dumps(
            {
                "permissions": {
                    "allow": [
                        f"Mcp(epiagent:{tool_name})"
                        for tool_name in _PUBLIC_TOOL_NAMES
                    ],
                    "deny": [
                        "Shell(*)",
                        "Read(**)",
                        "Write(**)",
                        "WebFetch(*)",
                    ],
                }
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return workspace, public_root, schema_path, mcp_path


def _bounded(value: bytes) -> bytes:
    return value[:_MAX_CAPTURE_BYTES]


def _diagnostic(
    stdout: bytes, stderr: bytes, *, temporary_root: str, returncode: int
) -> str:
    """Return a bounded path-redacted startup diagnostic, never environment data."""

    event_lines: list[str] = []
    for record in _jsonl_records(stdout):
        if record.get("type") in {"error", "turn.failed"}:
            event_lines.append(json.dumps(record, ensure_ascii=True)[:1_500])
        item = record.get("item")
        if isinstance(item, dict) and "mcp" in str(item.get("type", "")):
            status = item.get("status")
            if status in {"failed", "cancelled"} or item.get("error"):
                event_lines.append(
                    json.dumps(
                        {
                            "type": item.get("type"),
                            "server": item.get("server"),
                            "tool": item.get("tool") or item.get("name"),
                            "status": status,
                            "error": item.get("error"),
                        },
                        ensure_ascii=True,
                    )
                )
    if returncode == 0:
        text = "\n".join(event_lines[-8:])
    else:
        stdout_text = stdout.decode("utf-8", errors="replace")[-4_000:]
        stderr_text = stderr.decode("utf-8", errors="replace")[-2_000:]
        text = f"stdout:\n{stdout_text}\nstderr:\n{stderr_text}"
    text = text.replace(temporary_root, "<pilot>")
    home = str(Path.home())
    if home:
        text = text.replace(home, "~")
    return text.strip()


def evaluate_local_cli_agent(
    system: str,
    *,
    seed: int,
    family: str | None = None,
    backend: str = "starsim",
    episode_secret: bytes | None = None,
    model: str | None = None,
    executable: str | None = None,
    timeout_seconds: int = 600,
    claude_max_budget_usd: float = 1.0,
) -> PilotRunResult:
    """Run and score one explicitly non-hermetic local CLI smoke episode."""

    if system not in DEFAULT_MODELS:
        raise ValueError("Unsupported pilot system")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
        raise ValueError("Invalid pilot timeout")
    requested_model = model or DEFAULT_MODELS[system]
    executable_name = executable or DEFAULT_EXECUTABLES[system]
    resolved = shutil.which(executable_name)
    if resolved is None:
        raise RuntimeError(f"Required CLI is unavailable: {executable_name}")

    with tempfile.TemporaryDirectory(prefix="eabp-", dir="/tmp") as temp:
        # Cursor binds project-scoped approvals to the canonical workspace path.
        # On macOS /tmp aliases /private/tmp, so use one identity for enable/run.
        root = Path(temp).resolve()
        socket_path = str(root / "episode.sock")
        session = launch_socket_episode(
            public_socket_path=socket_path,
            seed=seed,
            family=family,
            backend=backend,
            episode_secret=episode_secret,
        )
        try:
            workspace, public_root, schema_path, mcp_path = _prepare_workspace(
                root, socket_path
            )
            final_path = workspace / "final.json"
            command = build_agent_command(
                system,
                executable=resolved,
                model=requested_model,
                workspace=str(workspace),
                schema_path=str(schema_path),
                mcp_path=str(mcp_path),
                final_output_path=str(final_path),
                python=sys.executable,
                public_root=str(public_root),
                socket_path=socket_path,
                claude_max_budget_usd=claude_max_budget_usd,
            )
            environment = os.environ.copy()
            environment.pop("EPIAGENT_SOCKET", None)
            if system == "cursor":
                environment["CURSOR_DATA_DIR"] = str(root / "cursor-data")
            version = subprocess.run(
                [resolved, "--version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=environment,
                timeout=15,
                check=False,
            ).stdout.decode("utf-8", errors="replace").strip()[:200]

            audit: list[str] = []
            if system == "cursor":
                enabled = subprocess.run(
                    [resolved, "mcp", "enable", "epiagent"],
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                    timeout=30,
                    check=False,
                )
                if enabled.returncode != 0:
                    audit.append("agent_failure:mcp_enable")
            started = time.monotonic()
            try:
                process = subprocess.run(
                    command,
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                    timeout=timeout_seconds,
                    check=False,
                )
                returncode = process.returncode
                stdout = _bounded(process.stdout)
                stderr = _bounded(process.stderr)
            except subprocess.TimeoutExpired as exc:
                returncode = 124
                stdout = _bounded(exc.stdout or b"")
                stderr = _bounded(exc.stderr or b"")
                audit.append("agent_failure:timeout")
            elapsed = time.monotonic() - started
            if returncode != 0:
                audit.append("agent_failure:nonzero_exit")

            final_output = None
            if final_path.is_file() and final_path.stat().st_size <= _MAX_CAPTURE_BYTES:
                final_output = final_path.read_bytes()
            submission, observed, parse_audit = parse_agent_output(
                system,
                requested_model=requested_model,
                stdout=stdout,
                final_output=final_output,
            )
            audit.extend(parse_audit)
            diagnostic = _diagnostic(
                stdout,
                stderr,
                temporary_root=str(root),
                returncode=returncode,
            )
            if submission is None:
                diagnostic = "\n".join(
                    part for part in (diagnostic, _record_shape_summary(stdout)) if part
                )
            accepted = submission if not any(
                event.startswith("agent_failure:") for event in audit
            ) else {}
            if not session.score_request_fits(
                accepted,
                audit_events=audit,
                agent_artifacts=(json.dumps(accepted),),
            ):
                audit.append("agent_failure:oversize_submission")
                accepted = {}
            scorecard = session.score(
                accepted,
                audit_events=audit,
                agent_artifacts=(json.dumps(accepted),),
            )
            return PilotRunResult(
                system=system,
                requested_model=requested_model,
                observed_models=observed,
                cli_version=version,
                development_only=True,
                hermetic=False,
                returncode=returncode,
                elapsed_seconds=round(elapsed, 3),
                submission=accepted,
                scorecard=scorecard,
                audit_events=tuple(audit),
                stdout_bytes=len(stdout),
                stderr_bytes=len(stderr),
                diagnostic=diagnostic,
            )
        finally:
            session.close()


def evaluate_paired_cli_agents(
    *,
    seed: int,
    systems: Sequence[str] = ("codex", "claude", "cursor"),
    family: str | None = None,
    backend: str = "starsim",
    episode_secret: bytes | None = None,
    timeout_seconds: int = 600,
    claude_max_budget_usd: float = 1.0,
) -> tuple[PilotRunResult, ...]:
    """Replay one private episode independently across full agent systems."""

    secret = episode_secret or secrets.token_bytes(32)
    return tuple(
        evaluate_local_cli_agent(
            system,
            seed=seed,
            family=family,
            backend=backend,
            episode_secret=secret,
            timeout_seconds=timeout_seconds,
            claude_max_budget_usd=claude_max_budget_usd,
        )
        for system in systems
    )
