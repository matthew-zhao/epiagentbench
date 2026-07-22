"""Development-only runner for cloud-backed coding-agent smoke tests.

This module does not weaken the production sandbox.  It runs locally installed
agent CLIs from a fresh, public-only workspace while the simulator and scorer
remain behind :func:`launch_socket_episode`.  Because the CLI still has host
and provider-network access, every result is explicitly non-hermetic and must
not be published as a leaderboard score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import pwd
import re
import selectors
import signal
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
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


class ClaudeEffort(str, Enum):
    """Reasoning-effort levels accepted by the Claude Code CLI."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


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

_CLAUDE_MCP_TOOL_NAMES = tuple(
    f"mcp__epiagent__{tool_name}" for tool_name in _PUBLIC_TOOL_NAMES
)
_CLAUDE_EXPECTED_TOOLS = (*_CLAUDE_MCP_TOOL_NAMES, "StructuredOutput")
_CLAUDE_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {
        "$id",
        "$schema",
        "allOf",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "multipleOf",
        "title",
        "uniqueItems",
    }
)
_FENCED_JSON_BLOCK = re.compile(
    r"```(?:json)?[ \t]*\r?\n(?P<body>.*?)\r?\n?[ \t]*```",
    re.IGNORECASE | re.DOTALL,
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
    captured_stdout_sha256: str = ""
    captured_stderr_sha256: str = ""
    command_sha256: str = ""
    replay_trace: dict[str, Any] = field(default_factory=dict)


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


def _validate_claude_effort(
    value: str | ClaudeEffort | None,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid Claude effort")
    try:
        return ClaudeEffort(value).value
    except ValueError as error:
        choices = ", ".join(item.value for item in ClaudeEffort)
        raise ValueError(f"Invalid Claude effort; choose one of: {choices}") from error


def _compact_json_schema(schema_path: str) -> str:
    try:
        raw_schema = Path(schema_path).read_text(encoding="utf-8")
        schema = _decode_json(raw_schema)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("Invalid Claude JSON schema") from error
    if not isinstance(schema, dict):
        raise ValueError("Invalid Claude JSON schema")
    return json.dumps(
        schema,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _claude_provider_schema(schema_path: str) -> dict[str, Any]:
    """Project the evaluator schema onto Claude's supported output subset.

    Anthropic documents that unsupported constraints should be removed from the
    provider schema and enforced again by the application's original-schema
    validator.  Local references are inlined and every object remains closed;
    the trusted benchmark scorer still enforces the complete source schema.
    """

    try:
        source = _decode_json(Path(schema_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("Invalid Claude JSON schema") from error
    if not isinstance(source, dict):
        raise ValueError("Invalid Claude JSON schema")
    properties = source.get("properties")
    required = source.get("required")
    definitions = source.get("$defs")
    if (
        not isinstance(properties, dict)
        or set(properties) != _SUBMISSION_KEYS
        or not isinstance(required, list)
        or set(required) != _SUBMISSION_KEYS
        or not isinstance(definitions, dict)
    ):
        raise ValueError("Claude projection requires the complete submission schema")

    def project(value: Any) -> Any:
        if isinstance(value, list):
            return [project(item) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        if reference is not None:
            prefix = "#/$defs/"
            if not isinstance(reference, str) or not reference.startswith(prefix):
                raise ValueError("Unsupported Claude schema reference")
            name = reference[len(prefix) :]
            target = definitions.get(name)
            if not isinstance(target, dict):
                raise ValueError("Unknown Claude schema reference")
            return project(target)
        projected = {
            key: project(child)
            for key, child in value.items()
            if key not in _CLAUDE_UNSUPPORTED_SCHEMA_KEYS and key != "$defs"
        }
        if projected.get("type") == "object":
            projected["additionalProperties"] = False
        return projected

    projected = project(source)
    if not isinstance(projected, dict):
        raise ValueError("Invalid Claude provider schema")
    return projected


def _compact_claude_provider_schema(schema_path: str) -> str:
    return json.dumps(
        _claude_provider_schema(schema_path),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


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
    claude_effort: str | ClaudeEffort | None = None,
) -> list[str]:
    """Build a shell-free invocation for one supported local agent CLI."""

    if system not in DEFAULT_MODELS:
        raise ValueError("Unsupported pilot system")
    if not model or not executable:
        raise ValueError("Invalid pilot configuration")
    effort = _validate_claude_effort(claude_effort)
    if effort is not None and system != "claude":
        raise ValueError("Claude effort is only valid for the Claude system")
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
            'cli_auth_credentials_store="file"',
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
        compact_schema = _compact_claude_provider_schema(schema_path)
        command = [
            executable,
            "--print",
            "--model",
            model,
        ]
        if effort is not None:
            command.extend(("--effort", effort))
        command.extend(
            [
                "--no-session-persistence",
                "--no-chrome",
                "--tools",
                "Read",
                "--disallowedTools",
                "Read",
                "--permission-mode",
                "dontAsk",
                "--setting-sources",
                "project",
                "--disable-slash-commands",
                "--strict-mcp-config",
                "--mcp-config",
                mcp_path,
                "--allowedTools",
                "mcp__epiagent__*",
                "--output-format",
                "stream-json",
                "--json-schema",
                compact_schema,
                "--verbose",
                "--max-budget-usd",
                str(claude_max_budget_usd),
                prompt,
            ]
        )
        return command
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
        "--allowed-tools",
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
    try:
        decoded = _decode_json(text)
    except (UnicodeError, ValueError, RecursionError):
        decoded = None
    if isinstance(decoded, dict):
        return decoded

    # Cursor's terminal result is the full assistant text. Accept surrounding
    # prose only when there is exactly one unambiguous fenced JSON candidate;
    # never scan arbitrary prose for braces or choose among competing objects.
    matches = list(_FENCED_JSON_BLOCK.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    outside = text[: match.start()] + text[match.end() :]
    if "```" in outside:
        return None
    try:
        fenced = _decode_json(match.group("body").strip())
    except (UnicodeError, ValueError, RecursionError):
        return None
    if not isinstance(fenced, dict) or not _SUBMISSION_KEYS.issubset(fenced):
        return None
    return fenced


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


def _find_cursor_submission(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Parse only Cursor's single designated terminal result record."""

    terminal = [record for record in records if record.get("type") == "result"]
    if len(terminal) != 1:
        return None
    return _submission_candidate(terminal[0].get("result"))


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

    def call_id(*values: Mapping[str, Any]) -> str | None:
        for value in values:
            for key in ("toolCallId", "tool_call_id", "call_id", "id"):
                identifier = value.get(key)
                if isinstance(identifier, (str, int)) and not isinstance(
                    identifier, bool
                ):
                    return str(identifier)
        return None

    authorized_call_ids: set[str] = set()
    transport_unverifiable = False
    for record in records:
        if record.get("type") == "getMcpToolsToolCall":
            continue
        if record.get("type") == "mcpToolCall":
            provider, tool_name = identity(record)
            identifier = call_id(record)
            if provider is None and tool_name is None:
                if identifier is None or identifier not in authorized_call_ids:
                    transport_unverifiable = True
                continue
            if provider != "epiagent" or tool_name not in _PUBLIC_TOOL_NAMES:
                return ("agent_failure:unauthorized_tool",)
            if identifier is not None:
                authorized_call_ids.add(identifier)
        if record.get("type") != "tool_call":
            continue
        if record.get("subtype") not in {"started", "completed"}:
            transport_unverifiable = True
            continue
        tool_call = record.get("tool_call")
        subtype = record.get("subtype")
        if not isinstance(tool_call, dict):
            if subtype == "completed":
                transport_unverifiable = True
                continue
            return ("agent_failure:unauthorized_tool",)
        identifier = call_id(tool_call, record)
        call_keys = [key for key in tool_call if key.endswith("ToolCall")]
        if call_keys == ["getMcpToolsToolCall"]:
            continue
        if not call_keys and subtype == "completed":
            if identifier is None or identifier not in authorized_call_ids:
                transport_unverifiable = True
            continue
        if call_keys != ["mcpToolCall"]:
            return ("agent_failure:unauthorized_tool",)
        mcp_call = tool_call["mcpToolCall"]
        if not isinstance(mcp_call, dict):
            if subtype == "completed" and identifier in authorized_call_ids:
                continue
            if subtype == "completed":
                transport_unverifiable = True
                continue
            return ("agent_failure:unauthorized_tool",)
        identifier = call_id(mcp_call, tool_call, record)
        provider, tool_name = identity(mcp_call)
        if provider is None and tool_name is None:
            if subtype == "completed" and identifier in authorized_call_ids:
                continue
            if subtype == "completed":
                transport_unverifiable = True
                continue
            return ("agent_failure:unauthorized_tool",)
        if provider != "epiagent" or tool_name not in _PUBLIC_TOOL_NAMES:
            return ("agent_failure:unauthorized_tool",)
        if identifier is not None:
            authorized_call_ids.add(identifier)
    return (
        ("agent_failure:tool_transport_unverifiable",)
        if transport_unverifiable
        else ()
    )


def _claude_tool_audit(
    records: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Require the isolated public MCP inventory and reject other tool use."""

    initializations = [
        record
        for record in records
        if record.get("type") == "system" and record.get("subtype") == "init"
    ]
    if len(initializations) != 1:
        return ("agent_failure:mcp_unavailable",)
    initialization = initializations[0]
    tools = initialization.get("tools")
    if not isinstance(tools, list) or not all(
        isinstance(tool, str) for tool in tools
    ):
        return ("agent_failure:mcp_unavailable",)
    servers = initialization.get("mcp_servers")
    if (
        not isinstance(servers, list)
        or len(servers) != 1
        or not isinstance(servers[0], dict)
        or servers[0].get("name") != "epiagent"
        or servers[0].get("status") != "connected"
    ):
        return ("agent_failure:mcp_unavailable",)

    tool_inventory = set(tools)
    expected_mcp = set(_CLAUDE_MCP_TOOL_NAMES)
    if not expected_mcp.issubset(tool_inventory):
        return ("agent_failure:mcp_unavailable",)
    if tool_inventory - set(_CLAUDE_EXPECTED_TOOLS):
        return ("agent_failure:unauthorized_tool",)
    if "StructuredOutput" not in tool_inventory:
        return ("agent_failure:structured_output_unavailable",)
    if len(tools) != len(_CLAUDE_EXPECTED_TOOLS):
        return ("agent_failure:unauthorized_tool",)

    allowed = set(_CLAUDE_EXPECTED_TOOLS)
    for record in records:
        blocks: object = None
        message = record.get("message")
        if isinstance(message, dict):
            blocks = message.get("content")
        elif record.get("type") == "tool_use":
            blocks = [record]
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") not in allowed:
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
    submission: dict[str, Any] | None = None
    if system == "cursor":
        submission = _find_cursor_submission(records)
    elif system == "codex":
        # ``--output-last-message`` designates this file as Codex's only
        # scoreable answer. The event stream remains diagnostic evidence and
        # must never rescue a missing, oversized, or invalid final artifact.
        if final_output is not None:
            try:
                submission = _submission_candidate(final_output.decode("utf-8"))
            except UnicodeError:
                submission = None
    else:
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
    if system == "claude":
        claude_audit = _claude_tool_audit(records)
        audit.extend(claude_audit)
        if claude_audit:
            submission = None
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


def _redact_exact_secret_bytes(value: bytes, secret: str | None) -> bytes:
    if not secret:
        return value
    encoded = secret.encode("utf-8")
    if not encoded:
        return value
    return value.replace(encoded, b"<provider-secret-redacted>")


class CodexAuthenticationIncidentError(RuntimeError):
    """Raised when isolated Codex credential state becomes ambiguous."""


class ProviderExecutionIsolationError(RuntimeError):
    """Raised when provider execution isolation becomes ambiguous."""


class ProviderProcessIsolationError(ProviderExecutionIsolationError):
    """Raised when the provider's original process group cannot be quiesced."""


class ProviderStateIsolationError(ProviderExecutionIsolationError):
    """Raised when provider state-persistence isolation becomes ambiguous."""


class ProviderOutputOverflowError(RuntimeError):
    """Raised after safely draining output that exceeded the capture limit."""

    def __init__(
        self,
        *,
        returncode: int,
        stdout: bytes,
        stderr: bytes,
    ) -> None:
        super().__init__("Provider output exceeded the evaluator capture limit")
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _ProviderTemporaryDirectory:
    """Dispose provider state without downgrading terminal incidents."""

    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(
            prefix="eabp-", dir="/tmp"
        )

    def __enter__(self) -> str:
        return self._temporary.name

    def __exit__(
        self,
        _error_type: object,
        error: BaseException | None,
        _traceback: object,
    ) -> bool:
        cleanup_failed = False
        try:
            self._temporary.cleanup()
        except BaseException:
            cleanup_failed = True
        if not cleanup_failed:
            try:
                Path(self._temporary.name).lstat()
            except FileNotFoundError:
                pass
            except OSError:
                cleanup_failed = True
            else:
                cleanup_failed = True
        if cleanup_failed:
            cleanup_error = ProviderStateIsolationError(
                "Disposable provider state could not be removed"
            )
            if error is not None:
                raise cleanup_error from error
            raise cleanup_error from None
        return False


_PROVIDER_OUTPUT_METADATA_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_uid",
    "st_gid",
    "st_nlink",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)


def _same_provider_output_metadata(
    left: os.stat_result, right: os.stat_result
) -> bool:
    return all(
        getattr(left, field) == getattr(right, field)
        for field in _PROVIDER_OUTPUT_METADATA_FIELDS
    )


def _safe_provider_output_metadata(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == os.getuid()
        and metadata.st_nlink == 1
        and stat.S_IMODE(metadata.st_mode) & 0o077 == 0
        and metadata.st_size >= 0
    )


def _read_provider_final_output(path: Path) -> bytes | None:
    """Read one owner-only regular output without following or racing links."""

    try:
        initial_metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        raise ProviderStateIsolationError(
            "Provider final output could not be verified"
        ) from None
    if not _safe_provider_output_metadata(initial_metadata):
        raise ProviderStateIsolationError(
            "Provider final output metadata was unsafe"
        )
    required_flags = ("O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")
    if any(not hasattr(os, name) for name in required_flags):
        raise ProviderStateIsolationError(
            "Provider final output isolation is unavailable"
        )
    flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | os.O_CLOEXEC
        | os.O_NONBLOCK
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise ProviderStateIsolationError(
            "Provider final output could not be opened safely"
        ) from None
    try:
        try:
            opened_metadata = os.fstat(descriptor)
        except OSError:
            raise ProviderStateIsolationError(
                "Provider final output could not be verified"
            ) from None
        if (
            not _safe_provider_output_metadata(opened_metadata)
            or not _same_provider_output_metadata(
                initial_metadata, opened_metadata
            )
        ):
            raise ProviderStateIsolationError(
                "Provider final output identity changed"
            )

        value: bytes | None
        if opened_metadata.st_size > _MAX_CAPTURE_BYTES:
            value = None
        else:
            captured = bytearray()
            while len(captured) <= _MAX_CAPTURE_BYTES:
                request_size = min(
                    65_536,
                    _MAX_CAPTURE_BYTES + 1 - len(captured),
                )
                try:
                    chunk = os.read(descriptor, request_size)
                except OSError:
                    raise ProviderStateIsolationError(
                        "Provider final output could not be read safely"
                    ) from None
                if not chunk:
                    break
                captured.extend(chunk)
            if len(captured) > _MAX_CAPTURE_BYTES:
                raise ProviderStateIsolationError(
                    "Provider final output changed while being read"
                )
            value = bytes(captured)

        try:
            final_descriptor_metadata = os.fstat(descriptor)
            final_path_metadata = path.lstat()
        except OSError:
            raise ProviderStateIsolationError(
                "Provider final output changed while being read"
            ) from None
        if (
            not _safe_provider_output_metadata(final_descriptor_metadata)
            or not _safe_provider_output_metadata(final_path_metadata)
            or not _same_provider_output_metadata(
                opened_metadata, final_descriptor_metadata
            )
            or not _same_provider_output_metadata(
                opened_metadata, final_path_metadata
            )
            or (
                value is not None
                and len(value) != opened_metadata.st_size
            )
        ):
            raise ProviderStateIsolationError(
                "Provider final output changed while being read"
            )
        return value
    finally:
        active_error = sys.exception()
        try:
            os.close(descriptor)
        except OSError:
            if not isinstance(active_error, ProviderExecutionIsolationError):
                raise ProviderStateIsolationError(
                    "Provider final output could not be closed safely"
                ) from None


def _process_group_exists(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        raise ProviderProcessIsolationError(
            "Provider process-group state could not be verified"
        ) from None
    return True


def _wait_for_process_group_exit(group_id: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _process_group_exists(group_id):
            return True
        time.sleep(0.01)
    return not _process_group_exists(group_id)


def _read_provider_pipe(descriptor: int) -> bytes:
    return os.read(descriptor, 65_536)


def _advance_exact_byte_match(
    tail: bytes, chunk: bytes, forbidden_exact_bytes: Sequence[bytes]
) -> tuple[bool, bytes]:
    """Scan one stream chunk while retaining only cross-chunk overlap."""

    if not forbidden_exact_bytes:
        return False, b""
    window = tail + chunk
    matched = any(secret in window for secret in forbidden_exact_bytes)
    overlap = max(len(secret) for secret in forbidden_exact_bytes) - 1
    return matched, window[-overlap:] if overlap else b""


def _quiesce_provider_process_group(
    process: subprocess.Popen[bytes], *, force: bool
) -> None:
    """Terminate and verify the provider's original POSIX process group."""

    group_id = process.pid
    if not _process_group_exists(group_id):
        return
    first_signal = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(group_id, first_signal)
    except ProcessLookupError:
        return
    except OSError:
        raise ProviderProcessIsolationError(
            "Provider process group could not be terminated"
        ) from None
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        raise ProviderProcessIsolationError(
            "Provider process leader state could not be verified"
        ) from None
    if _wait_for_process_group_exit(group_id, 0.5):
        return
    try:
        os.killpg(group_id, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        raise ProviderProcessIsolationError(
            "Provider process group could not be terminated"
        ) from None
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        raise ProviderProcessIsolationError(
            "Provider process leader state could not be verified"
        ) from None
    if not _wait_for_process_group_exit(group_id, 1.0):
        raise ProviderProcessIsolationError(
            "Provider process group remained alive after termination"
        )


def _run_provider_process_group(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
    umask: int,
    forbidden_exact_bytes: Sequence[bytes] = (),
) -> subprocess.CompletedProcess[bytes]:
    """Run one provider CLI with bounded capture in a new POSIX session."""

    if any(
        not isinstance(secret, bytes) or not secret
        for secret in forbidden_exact_bytes
    ):
        raise ValueError("Forbidden provider output bytes must be nonempty")
    forbidden_exact_bytes = tuple(forbidden_exact_bytes)
    if os.name != "posix" or not hasattr(os, "killpg"):
        raise ProviderProcessIsolationError(
            "Provider process-group isolation is unavailable"
        )
    selector = selectors.DefaultSelector()
    process: subprocess.Popen[bytes] | None = None
    streams: dict[str, Any] = {}
    captures = {"stdout": bytearray(), "stderr": bytearray()}
    overflowed = {"stdout": False, "stderr": False}
    match_tails = {"stdout": b"", "stderr": b""}
    forbidden_output_detected = False
    try:
        try:
            process = subprocess.Popen(
                list(command),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=dict(environment),
                start_new_session=True,
                umask=umask,
            )
        except OSError:
            raise ProviderProcessIsolationError(
                "Provider process could not be started in an isolated group"
            ) from None
        streams = {
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
        if any(stream is None for stream in streams.values()):
            raise ProviderProcessIsolationError(
                "Provider output capture could not be established"
            )
        for name, stream in streams.items():
            assert stream is not None
            try:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream.fileno(), selectors.EVENT_READ, name)
            except (OSError, ValueError):
                raise ProviderProcessIsolationError(
                    "Provider output capture could not be initialized"
                ) from None
        deadline = time.monotonic() + timeout_seconds
        drain_deadline: float | None = None
        timed_out = False
        group_quiesced = False
        while True:
            now = time.monotonic()
            if not group_quiesced and now >= deadline:
                timed_out = True
                _quiesce_provider_process_group(process, force=True)
                group_quiesced = True
                drain_deadline = time.monotonic() + 1.0
            elif not group_quiesced:
                try:
                    process_finished = process.poll() is not None
                except OSError:
                    raise ProviderProcessIsolationError(
                        "Provider process state could not be verified"
                    ) from None
                if process_finished:
                    _quiesce_provider_process_group(process, force=False)
                    group_quiesced = True
                    drain_deadline = time.monotonic() + 1.0

            if group_quiesced:
                try:
                    selector_empty = not selector.get_map()
                except (OSError, ValueError):
                    raise ProviderProcessIsolationError(
                        "Provider output selector failed"
                    ) from None
                if selector_empty:
                    break
            if (
                group_quiesced
                and drain_deadline is not None
                and time.monotonic() >= drain_deadline
            ):
                raise ProviderProcessIsolationError(
                    "Provider output pipes remained open after process-group "
                    "termination"
                )

            next_deadline = drain_deadline if group_quiesced else deadline
            wait_seconds = max(
                0.0,
                min(0.25, next_deadline - time.monotonic()),
            )
            try:
                ready = selector.select(wait_seconds)
            except (OSError, ValueError):
                raise ProviderProcessIsolationError(
                    "Provider output selector failed"
                ) from None
            for key, _ in ready:
                name = str(key.data)
                if name not in captures:
                    raise ProviderProcessIsolationError(
                        "Provider output selector failed"
                    )
                try:
                    chunk = _read_provider_pipe(int(key.fd))
                except BlockingIOError:
                    continue
                except (OSError, TypeError, ValueError):
                    raise ProviderProcessIsolationError(
                        "Provider output capture failed"
                    ) from None
                if not chunk:
                    try:
                        selector.unregister(key.fd)
                    except (KeyError, ValueError):
                        pass
                    except OSError:
                        raise ProviderProcessIsolationError(
                            "Provider output selector failed"
                        ) from None
                    continue
                matched, match_tails[name] = _advance_exact_byte_match(
                    match_tails[name], chunk, forbidden_exact_bytes
                )
                if matched and not forbidden_output_detected:
                    forbidden_output_detected = True
                    for captured in captures.values():
                        captured[:] = b"\x00" * len(captured)
                        captured.clear()
                    if not group_quiesced:
                        _quiesce_provider_process_group(process, force=True)
                        group_quiesced = True
                        drain_deadline = time.monotonic() + 1.0
                if forbidden_output_detected:
                    continue
                remaining = _MAX_CAPTURE_BYTES - len(captures[name])
                if remaining > 0:
                    captures[name].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflowed[name] = True

        if forbidden_output_detected:
            raise ProviderStateIsolationError(
                "Provider credential isolation failed"
            ) from None
        stdout = bytes(captures["stdout"])
        stderr = bytes(captures["stderr"])
        if timed_out:
            raise subprocess.TimeoutExpired(
                list(command),
                timeout_seconds,
                output=stdout,
                stderr=stderr,
            ) from None
        if any(overflowed.values()):
            raise ProviderOutputOverflowError(
                returncode=int(process.returncode),
                stdout=stdout,
                stderr=stderr,
            )
        return subprocess.CompletedProcess(
            list(command), process.returncode, stdout=stdout, stderr=stderr
        )
    finally:
        active_error = sys.exception()
        selector_cleanup_error: ProviderProcessIsolationError | None = None
        process_cleanup_error: ProviderProcessIsolationError | None = None
        stream_cleanup_error: ProviderProcessIsolationError | None = None
        try:
            selector.close()
        except BaseException:
            selector_cleanup_error = ProviderProcessIsolationError(
                "Provider output selector could not be closed"
            )
        try:
            if process is not None:
                poll_failed = False
                try:
                    process_running = process.poll() is None
                except OSError:
                    poll_failed = True
                    process_running = True
                if process_running:
                    _quiesce_provider_process_group(process, force=True)
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    raise ProviderProcessIsolationError(
                        "Provider process leader could not be reaped"
                    ) from None
                except OSError:
                    raise ProviderProcessIsolationError(
                        "Provider process leader state could not be verified"
                    ) from None
                if poll_failed:
                    raise ProviderProcessIsolationError(
                        "Provider process state could not be verified"
                    )
        except ProviderProcessIsolationError as error:
            process_cleanup_error = error
        finally:
            for stream in streams.values():
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException:
                        stream_cleanup_error = ProviderProcessIsolationError(
                            "Provider output stream could not be closed"
                        )
        if not isinstance(active_error, ProviderExecutionIsolationError):
            if process_cleanup_error is not None:
                raise process_cleanup_error from None
            if selector_cleanup_error is not None:
                raise selector_cleanup_error from None
            if stream_cleanup_error is not None:
                raise stream_cleanup_error from None


def _diagnostic(
    stdout: bytes,
    stderr: bytes,
    *,
    temporary_root: str,
    returncode: int,
    redacted_paths: Sequence[str] = (),
    redact_provider_auth: bool = False,
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
    for path in redacted_paths:
        if path:
            text = text.replace(path, "<secure-storage>")
    home = str(Path.home())
    if home:
        text = text.replace(home, "~")
    if redact_provider_auth and text.strip():
        return "Claude/Glean provider diagnostic redacted"
    return text.strip()


def _reject_claude_plaintext_fallback(
    secure_storage_dir: Path | None,
) -> None:
    """Fail closed if Claude falls back to a plaintext credential file.

    Only metadata for the fixed fallback filename is inspected.  The error is
    deliberately generic so neither credential material nor its host path can
    enter runner diagnostics.
    """

    if secure_storage_dir is None:
        return
    try:
        (secure_storage_dir / ".credentials.json").lstat()
    except FileNotFoundError:
        return
    except (OSError, ValueError):
        raise ProviderStateIsolationError(
            "Claude secure-storage guard could not verify credential isolation"
        ) from None
    raise ProviderStateIsolationError(
        "Claude secure-storage guard detected a plaintext credential fallback"
    )


def _claude_secure_storage_keychain_service(
    secure_storage_dir: str | os.PathLike[str],
) -> str:
    """Derive Claude Code's Keychain service from one canonical real path."""

    resolved_path = _canonical_claude_secure_storage_path(secure_storage_dir)
    normalized = unicodedata.normalize("NFC", str(resolved_path))
    suffix = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"Claude Code-credentials-{suffix}"


def _canonical_claude_secure_storage_path(
    secure_storage_dir: str | os.PathLike[str],
) -> Path:
    """Reject aliases instead of silently switching credential namespaces."""

    try:
        raw_path = os.fspath(secure_storage_dir)
    except TypeError:
        raise ValueError("Invalid Claude secure-storage directory") from None
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("Invalid Claude secure-storage directory")
    try:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise ValueError
        resolved_path = candidate.resolve(strict=True)
        metadata = candidate.stat()
    except (OSError, RuntimeError, ValueError):
        raise ValueError("Invalid Claude secure-storage directory") from None
    if candidate != resolved_path or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Invalid Claude secure-storage directory")
    return candidate


def _resolve_macos_security_executable(
    executable: str | os.PathLike[str],
) -> Path:
    """Resolve a non-writable regular executable without exposing its path."""

    try:
        raw_executable = os.fspath(executable)
    except TypeError:
        raise RuntimeError("macOS Keychain executable is unavailable") from None
    if not isinstance(raw_executable, str) or not raw_executable.strip():
        raise RuntimeError("macOS Keychain executable is unavailable")
    try:
        candidate = Path(raw_executable).expanduser()
        if not candidate.is_absolute():
            located = shutil.which(raw_executable)
            if located is None:
                raise FileNotFoundError
            candidate = Path(located)
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, RuntimeError, ValueError):
        raise RuntimeError("macOS Keychain executable is unavailable") from None
    executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    unsafe_write_bits = stat.S_IWGRP | stat.S_IWOTH
    if (
        not stat.S_ISREG(metadata.st_mode)
        or not metadata.st_mode & executable_bits
        or metadata.st_mode & unsafe_write_bits
    ):
        raise RuntimeError("macOS Keychain executable is unavailable")
    return resolved


def _attest_claude_secure_storage_keychain(
    secure_storage_dir: str | os.PathLike[str],
    *,
    security_executable: str | os.PathLike[str] = "/usr/bin/security",
) -> bool:
    """Return whether Claude's expected generic-password item exists.

    The password value is never requested or captured.  Exit status 44 is the
    only condition classified as absence; platform, executable, account, and
    all other command failures are fail-closed infrastructure errors.
    """

    if sys.platform != "darwin":
        raise RuntimeError("Claude Keychain attestation requires macOS")
    try:
        account = str(pwd.getpwuid(os.getuid()).pw_name).strip()
    except (KeyError, OSError, TypeError, ValueError):
        account = ""
    if not account:
        raise RuntimeError("Claude Keychain attestation account is unavailable")
    executable = _resolve_macos_security_executable(security_executable)
    service = _claude_secure_storage_keychain_service(secure_storage_dir)
    try:
        process = subprocess.run(
            [
                str(executable),
                "find-generic-password",
                "-s",
                service,
                "-a",
                account,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("Claude Keychain attestation failed") from None
    if process.returncode == 0:
        return True
    if process.returncode == 44:
        return False
    raise RuntimeError("Claude Keychain attestation failed")


def _attest_managed_glean_home_link(link: Path, target: Path) -> None:
    """Verify the evaluator-owned Glean home link without reading credentials."""

    try:
        parent_metadata = link.parent.lstat()
        link_metadata = link.lstat()
        link_text = os.readlink(link)
        resolved = link.resolve(strict=True)
        final_link_metadata = link.lstat()
        final_parent_metadata = link.parent.lstat()
    except (OSError, RuntimeError):
        raise ProviderStateIsolationError(
            "Managed Glean home link is unavailable"
        ) from None
    stable_parent_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    stable_link_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if (
        link.name != ".glean-llm-gateway"
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or stat.S_ISLNK(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
        or not stat.S_ISLNK(link_metadata.st_mode)
        or link_text != str(target)
        or resolved != target
        or any(
            getattr(final_parent_metadata, field)
            != getattr(parent_metadata, field)
            for field in stable_parent_fields
        )
        or any(
            getattr(final_link_metadata, field)
            != getattr(link_metadata, field)
            for field in stable_link_fields
        )
    ):
        raise ProviderStateIsolationError(
            "Managed Glean home link identity changed"
        )


_MAX_CODEX_AUTH_BYTES = 1024 * 1024
_SAFE_LOCALE_ENVIRONMENT_NAMES = frozenset(
    {
        "LANG",
        "LANGUAGE",
        "LC_ADDRESS",
        "LC_ALL",
        "LC_COLLATE",
        "LC_CTYPE",
        "LC_IDENTIFICATION",
        "LC_MEASUREMENT",
        "LC_MESSAGES",
        "LC_MONETARY",
        "LC_NAME",
        "LC_NUMERIC",
        "LC_PAPER",
        "LC_TELEPHONE",
        "LC_TIME",
    }
)


def _retain_path_and_locale(environment: dict[str, str]) -> None:
    """Drop credentials, routing overrides, and process-injection variables."""

    preserved = {
        name: value
        for name, value in environment.items()
        if name == "PATH" or name in _SAFE_LOCALE_ENVIRONMENT_NAMES
    }
    environment.clear()
    environment.update(preserved)


def _install_disposable_storage_roots(
    environment: dict[str, str], root: Path, *, namespace: str
) -> dict[str, Path]:
    isolated_paths = {
        "HOME": root / f"{namespace}-home",
        "XDG_CONFIG_HOME": root / f"{namespace}-xdg" / "config",
        "XDG_CACHE_HOME": root / f"{namespace}-xdg" / "cache",
        "XDG_DATA_HOME": root / f"{namespace}-xdg" / "data",
        "XDG_STATE_HOME": root / f"{namespace}-xdg" / "state",
        "XDG_RUNTIME_DIR": root / f"{namespace}-xdg" / "runtime",
        "TMPDIR": root / f"{namespace}-tmp",
        "TMP": root / f"{namespace}-tmp",
        "TEMP": root / f"{namespace}-tmp",
        "NODE_COMPILE_CACHE": root / f"{namespace}-node-cache",
    }
    for name, path in isolated_paths.items():
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        path.chmod(0o700)
        environment[name] = str(path)
    return isolated_paths


def _isolate_identity_environment(
    environment: dict[str, str], root: Path
) -> None:
    """Create a credential-free environment for CLI identity/readiness checks."""

    _retain_path_and_locale(environment)
    _install_disposable_storage_roots(
        environment, root, namespace="identity"
    )


def _attest_codex_auth_storage(
    path: Path, *, allow_empty: bool = False
) -> bool:
    """Validate an auth-only Codex namespace using metadata, never contents."""

    try:
        root_metadata = path.lstat()
    except OSError:
        raise RuntimeError("Codex auth storage is unavailable") from None
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or root_metadata.st_uid != os.getuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise RuntimeError("Codex auth storage metadata is unsafe")
    try:
        names = {entry.name for entry in os.scandir(path)}
    except OSError:
        raise RuntimeError("Codex auth storage is unavailable") from None
    if not names:
        if not allow_empty:
            raise RuntimeError("Codex auth storage is empty")
        try:
            final_names = {entry.name for entry in os.scandir(path)}
            final_root_metadata = path.lstat()
        except OSError:
            raise RuntimeError("Codex auth storage changed") from None
        root_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if final_names or any(
            getattr(final_root_metadata, field)
            != getattr(root_metadata, field)
            for field in root_fields
        ):
            raise RuntimeError("Codex auth storage changed")
        return False
    if names != {"auth.json"}:
        raise RuntimeError("Codex auth storage has unexpected entries")

    auth_path = path / "auth.json"
    try:
        metadata = auth_path.lstat()
    except OSError:
        raise RuntimeError("Codex auth metadata is unavailable") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or not 1 <= metadata.st_size <= _MAX_CODEX_AUTH_BYTES
    ):
        raise RuntimeError("Codex auth metadata is unsafe")

    file_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    root_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    try:
        final_names = {entry.name for entry in os.scandir(path)}
        final_metadata = auth_path.lstat()
        final_root_metadata = path.lstat()
    except OSError:
        raise RuntimeError("Codex auth storage changed") from None
    if (
        final_names != names
        or any(
            getattr(final_root_metadata, field)
            != getattr(root_metadata, field)
            for field in root_fields
        )
        or any(
            getattr(final_metadata, field) != getattr(metadata, field)
            for field in file_fields
        )
    ):
        raise RuntimeError("Codex auth storage changed")
    return True


def _canonical_codex_auth_storage_path(
    auth_storage_dir: str | os.PathLike[str], *, allow_empty: bool = False
) -> Path:
    """Resolve one real auth-only namespace and reject path aliases."""

    try:
        raw_path = os.fspath(auth_storage_dir)
    except TypeError:
        raise ValueError("Invalid Codex auth storage directory") from None
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("Invalid Codex auth storage directory")
    try:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise ValueError
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise ValueError("Invalid Codex auth storage directory") from None
    if candidate != resolved:
        raise ValueError("Invalid Codex auth storage directory")
    try:
        _attest_codex_auth_storage(resolved, allow_empty=allow_empty)
    except RuntimeError:
        raise ValueError("Invalid Codex auth storage directory") from None
    return resolved


def _attest_codex_auth_home_link(link: Path, target: Path) -> None:
    """Attest the exact auth.json link in real disposable Codex storage."""

    try:
        parent_metadata = link.parent.lstat()
        link_metadata = link.lstat()
        link_text = os.readlink(link)
        resolved = link.resolve(strict=True)
        final_link_metadata = link.lstat()
        final_parent_metadata = link.parent.lstat()
    except (OSError, RuntimeError):
        raise RuntimeError("Codex auth home link is unavailable") from None
    stable_parent_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    stable_link_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if (
        link.name != "auth.json"
        or target.name != "auth.json"
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or stat.S_ISLNK(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
        or not stat.S_ISLNK(link_metadata.st_mode)
        or link_metadata.st_uid != os.getuid()
        or link_metadata.st_nlink != 1
        or link_text != str(target)
        or resolved != target
        or any(
            getattr(final_parent_metadata, field)
            != getattr(parent_metadata, field)
            for field in stable_parent_fields
        )
        or any(
            getattr(final_link_metadata, field)
            != getattr(link_metadata, field)
            for field in stable_link_fields
        )
    ):
        raise RuntimeError("Codex auth home link identity changed")


def _attest_runtime_codex_auth(link: Path, storage: Path) -> None:
    """Classify credential/link drift without exposing its path or contents."""

    try:
        _attest_codex_auth_home_link(link, storage / "auth.json")
        _attest_codex_auth_storage(storage)
    except (OSError, RuntimeError, ValueError):
        raise CodexAuthenticationIncidentError(
            "Isolated Codex authentication state became ambiguous"
        ) from None


def _attest_runtime_claude_credential_state(
    link: Path | None,
    storage: Path | None,
) -> None:
    """Classify Claude credential persistence drift as a terminal incident."""

    try:
        _reject_claude_plaintext_fallback(storage)
        if link is not None and storage is not None:
            _attest_managed_glean_home_link(link, storage)
    except (OSError, RuntimeError, ValueError):
        raise ProviderStateIsolationError(
            "Claude credential persistence isolation failed"
        ) from None


def _isolate_codex_environment(
    environment: dict[str, str], root: Path, auth_storage_dir: Path
) -> Path:
    """Link only stable auth.json into otherwise disposable Codex storage."""

    storage = _canonical_codex_auth_storage_path(auth_storage_dir)
    _retain_path_and_locale(environment)
    isolated_paths = _install_disposable_storage_roots(
        environment, root, namespace="codex"
    )
    codex_home = isolated_paths["HOME"] / ".codex"
    try:
        codex_home.mkdir(mode=0o700)
        codex_home.chmod(0o700)
        auth_link = codex_home / "auth.json"
        auth_target = storage / "auth.json"
        auth_link.symlink_to(auth_target)
    except OSError:
        raise RuntimeError("Unable to create Codex auth home link") from None
    _attest_codex_auth_home_link(auth_link, auth_target)
    try:
        initial_entries = {entry.name for entry in os.scandir(codex_home)}
    except OSError:
        raise RuntimeError("Unable to verify Codex auth home link") from None
    if initial_entries != {"auth.json"}:
        raise RuntimeError("Codex auth home has unexpected initial entries")
    environment["CODEX_HOME"] = str(codex_home)
    return auth_link


def _isolate_claude_environment(
    environment: dict[str, str],
    root: Path,
    secure_storage_dir: Path | None = None,
    glean_oauth_client_id: str | None = None,
) -> Path | None:
    """Build a minimal Claude environment with disposable ordinary storage.

    Claude, Anthropic, and Glean authentication or routing values are not
    inherited.  A persistent secure-storage configuration is available only
    when the caller supplies it explicitly.  The managed Glean helper's one
    persistent home entry is an evaluator-owned link to that directory.
    """

    passthrough_names = {
        "ALL_PROXY",
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LANG",
        "LANGUAGE",
        "LOGNAME",
        "NO_PROXY",
        "NODE_EXTRA_CA_CERTS",
        "PATH",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "USER",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
    preserved = {
        name: value
        for name, value in environment.items()
        if name in passthrough_names or name in _SAFE_LOCALE_ENVIRONMENT_NAMES
    }
    environment.clear()
    environment.update(preserved)
    isolated_paths = {
        "HOME": root / "claude-home",
        "CLAUDE_CONFIG_DIR": root / "claude-config",
        "XDG_CONFIG_HOME": root / "xdg" / "config",
        "XDG_CACHE_HOME": root / "xdg" / "cache",
        "XDG_DATA_HOME": root / "xdg" / "data",
        "XDG_STATE_HOME": root / "xdg" / "state",
        "XDG_RUNTIME_DIR": root / "xdg" / "runtime",
        "TMPDIR": root / "claude-tmp",
        "TMP": root / "claude-tmp",
        "TEMP": root / "claude-tmp",
        "NODE_COMPILE_CACHE": root / "node-compile-cache",
    }
    for name, path in isolated_paths.items():
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        path.chmod(0o700)
        environment[name] = str(path)
    if secure_storage_dir is not None:
        resolved_secure_storage = _canonical_claude_secure_storage_path(
            secure_storage_dir
        )
        glean_home_link = isolated_paths["HOME"] / ".glean-llm-gateway"
        try:
            glean_home_link.symlink_to(
                resolved_secure_storage, target_is_directory=True
            )
        except OSError:
            raise RuntimeError(
                "Unable to create managed Glean home isolation link"
            ) from None
        _attest_managed_glean_home_link(
            glean_home_link, resolved_secure_storage
        )
        environment["CLAUDE_SECURESTORAGE_CONFIG_DIR"] = str(
            resolved_secure_storage
        )
        if glean_oauth_client_id is not None:
            if (
                not glean_oauth_client_id
                or len(glean_oauth_client_id) > 2048
                or any(character.isspace() for character in glean_oauth_client_id)
            ):
                raise ValueError("Invalid managed Glean OAuth client identifier")
            environment["GLEAN_HELPER_OAUTH_CLIENT_ID"] = glean_oauth_client_id
        return glean_home_link
    if glean_oauth_client_id is not None:
        raise ValueError(
            "Managed Glean OAuth client identifier requires stable storage"
        )
    return None


def _isolate_cursor_environment(
    environment: dict[str, str], root: Path
) -> None:
    """Build a minimal Cursor environment rooted in one disposable directory.

    Cursor is a Node application and can inherit storage or code-injection
    locations from both Cursor-specific and general-purpose environment
    variables.  Preserve only the explicit API credential plus ordinary
    executable, locale, certificate, and proxy settings needed to reach the
    provider.  Everything else is dropped before private roots are installed.
    """

    passthrough_names = {
        "ALL_PROXY",
        "CURL_CA_BUNDLE",
        "CURSOR_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LANG",
        "LANGUAGE",
        "NO_PROXY",
        "NODE_EXTRA_CA_CERTS",
        "PATH",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
    preserved = {
        name: value
        for name, value in environment.items()
        if name in passthrough_names or name in _SAFE_LOCALE_ENVIRONMENT_NAMES
    }
    environment.clear()
    environment.update(preserved)
    environment["AGENT_CLI_CREDENTIAL_STORE"] = "memory"

    isolated_paths = {
        "HOME": root / "cursor-home",
        "XDG_CONFIG_HOME": root / "cursor-xdg" / "config",
        "XDG_CACHE_HOME": root / "cursor-xdg" / "cache",
        "XDG_DATA_HOME": root / "cursor-xdg" / "data",
        "XDG_STATE_HOME": root / "cursor-xdg" / "state",
        "XDG_RUNTIME_DIR": root / "cursor-xdg" / "runtime",
        "TMPDIR": root / "cursor-tmp",
        "TMP": root / "cursor-tmp",
        "TEMP": root / "cursor-tmp",
        "NODE_COMPILE_CACHE": root / "node-compile-cache",
        "CURSOR_DATA_DIR": root / "cursor-data",
        "CURSOR_CONFIG_DIR": root / "cursor-config",
        "CURSOR_PROJECTS_DIR": root / "cursor-projects",
        "CURSOR_EXEC_DAEMON_DATA_DIR": root / "cursor-exec-daemon",
        "CURSOR_WORKTREES_ROOT": root / "cursor-worktrees",
    }
    for name, path in isolated_paths.items():
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        path.chmod(0o700)
        environment[name] = str(path)


def _snapshot_cursor_host_chat_metadata(chats_root: Path) -> str | None:
    """Hash host Cursor chat metadata without reading any chat contents.

    ``None`` means the tree could not be completely inspected. Callers treat
    that state as a persistence failure rather than assuming isolation held.
    """

    try:
        root_metadata = chats_root.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError:
        return None
    if not (
        stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISREG(root_metadata.st_mode)
    ):
        return None

    digest = hashlib.sha256()
    pending = [(".", chats_root)]
    while pending:
        relative, path = pending.pop()
        try:
            metadata = path.lstat()
        except OSError:
            return None
        if stat.S_ISLNK(metadata.st_mode):
            return None
        record = (
            relative,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_uid,
            metadata.st_gid,
        )
        digest.update(
            json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode(
                "ascii"
            )
        )
        digest.update(b"\n")
        if not stat.S_ISDIR(metadata.st_mode):
            continue
        try:
            children = sorted(path.iterdir(), key=lambda child: child.name)
        except OSError:
            return None
        pending.extend(
            (str(Path(relative) / child.name), child)
            for child in reversed(children)
        )
    return "sha256:" + digest.hexdigest()


def _snapshot_cursor_host_state() -> str | None:
    """Commit metadata for known Cursor CLI persistence roots, never contents."""

    home = Path.home()
    paths = (
        home / ".cursor" / "chats",
        home / ".cursor" / "projects",
        home / ".cursor" / "ai-tracking",
        home / ".cursor" / "agent-cli-state.json",
        home / ".cursor" / "cli-config.json",
    )
    digest = hashlib.sha256()
    for path in paths:
        snapshot = _snapshot_cursor_host_chat_metadata(path)
        if snapshot is None:
            return None
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(snapshot.encode("ascii"))
        digest.update(b"\n")
    return "sha256:" + digest.hexdigest()


def _cursor_host_persistence_audit(
    before: str | None, after: str | None
) -> tuple[str, ...]:
    """Classify host-state uncertainty as infrastructure, never model conduct."""

    if before is None or after is None:
        return ("infrastructure_failure:cursor_host_state_unverifiable",)
    if before != after:
        return ("infrastructure_failure:cursor_host_state_changed",)
    return ()


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
    claude_effort: str | ClaudeEffort | None = None,
    codex_auth_storage_dir: str | os.PathLike[str] | None = None,
    claude_secure_storage_dir: str | os.PathLike[str] | None = None,
    claude_glean_oauth_client_id: str | None = None,
) -> PilotRunResult:
    """Run and score one explicitly non-hermetic local CLI smoke episode."""

    if system not in DEFAULT_MODELS:
        raise ValueError("Unsupported pilot system")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
        raise ValueError("Invalid pilot timeout")
    effort = _validate_claude_effort(claude_effort)
    if effort is not None and system != "claude":
        raise ValueError("Claude effort is only valid for the Claude system")
    if codex_auth_storage_dir is not None and system != "codex":
        raise ValueError("Codex auth storage is only valid for the Codex system")
    if claude_secure_storage_dir is not None and system != "claude":
        raise ValueError(
            "Claude secure storage is only valid for the Claude system"
        )
    if claude_glean_oauth_client_id is not None and system != "claude":
        raise ValueError(
            "Managed Glean OAuth client identifier is only valid for Claude"
        )
    codex_auth_storage_path: Path | None = None
    if system == "codex":
        if codex_auth_storage_dir is None:
            raise RuntimeError(
                "Isolated Codex evaluation requires explicit stable auth storage"
            )
        try:
            codex_auth_storage_path = _canonical_codex_auth_storage_path(
                codex_auth_storage_dir
            )
        except ValueError:
            raise CodexAuthenticationIncidentError(
                "Isolated Codex authentication state became ambiguous"
            ) from None
    secure_storage_path: Path | None = None
    if claude_secure_storage_dir is not None:
        try:
            secure_storage_value = os.fspath(claude_secure_storage_dir)
        except TypeError as error:
            raise ValueError("Invalid Claude secure-storage directory") from error
        if (
            not isinstance(secure_storage_value, str)
            or not secure_storage_value.strip()
        ):
            raise ValueError("Invalid Claude secure-storage directory")
        try:
            secure_storage_path = _canonical_claude_secure_storage_path(
                secure_storage_value
            )
        except ValueError:
            raise ValueError(
                "Invalid Claude secure-storage directory"
            ) from None
    cursor_api_key: str | None = None
    if system == "cursor":
        cursor_api_key = os.environ.get("CURSOR_API_KEY", "").strip()
        if not cursor_api_key:
            raise RuntimeError(
                "Isolated Cursor evaluation requires CURSOR_API_KEY; refusing to "
                "reuse login state from the host home directory"
            )
    requested_model = model or DEFAULT_MODELS[system]
    executable_name = executable or DEFAULT_EXECUTABLES[system]
    resolved = shutil.which(executable_name)
    if resolved is None:
        raise RuntimeError(f"Required CLI is unavailable: {executable_name}")

    with _ProviderTemporaryDirectory() as temp:
        # Cursor binds project-scoped approvals to the canonical workspace path.
        # On macOS /tmp aliases /private/tmp, so use one identity for enable/run.
        root = Path(temp).resolve()
        socket_path = str(root / "episode.sock")
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
            claude_effort=effort,
        )
        environment = os.environ.copy()
        environment.pop("EPIAGENT_SOCKET", None)
        audit: list[str] = []
        cursor_host_audit = False
        cursor_host_state_before: str | None = None
        codex_home_link: Path | None = None
        glean_home_link: Path | None = None
        if system == "cursor":
            cursor_host_audit = True
            cursor_host_state_before = _snapshot_cursor_host_state()
            if cursor_host_state_before is None:
                raise ProviderStateIsolationError(
                    "Cursor isolation preflight could not verify host chat "
                    "metadata; refusing to launch the provider CLI"
                )
            _isolate_cursor_environment(environment, root)
        elif system == "codex":
            assert codex_auth_storage_path is not None
            try:
                codex_home_link = _isolate_codex_environment(
                    environment, root, codex_auth_storage_path
                )
            except (OSError, RuntimeError, ValueError):
                raise CodexAuthenticationIncidentError(
                    "Isolated Codex authentication state became ambiguous"
                ) from None
        elif system == "claude":
            glean_home_link = _isolate_claude_environment(
                environment,
                root,
                secure_storage_path,
                claude_glean_oauth_client_id,
            )
            _attest_runtime_claude_credential_state(
                glean_home_link, secure_storage_path
            )

        readiness_terminal_error: Exception | None = None
        try:
            if codex_home_link is not None and codex_auth_storage_path is not None:
                _attest_runtime_codex_auth(
                    codex_home_link, codex_auth_storage_path
                )
            if system == "claude":
                _attest_runtime_claude_credential_state(
                    glean_home_link, secure_storage_path
                )
            version_environment = os.environ.copy()
            _isolate_identity_environment(
                version_environment, root / "identity-readiness"
            )
            try:
                version_process = _run_provider_process_group(
                    [resolved, "--version"],
                    cwd=workspace,
                    environment=version_environment,
                    timeout_seconds=15,
                    umask=0o077,
                )
            except ProviderOutputOverflowError:
                raise ProviderStateIsolationError(
                    "Provider CLI version preflight exceeded its output limit"
                ) from None
            version_output = _bounded(
                version_process.stdout + b"\n" + version_process.stderr
            )
            version = version_output.decode(
                "utf-8", errors="replace"
            ).strip()[:200]
            if version_process.returncode != 0 or not version:
                raise RuntimeError(
                    "Provider CLI version preflight failed before episode launch"
                )
            if system == "cursor":
                assert cursor_api_key is not None
                cursor_key_bytes = cursor_api_key.encode("utf-8")
                try:
                    enabled = _run_provider_process_group(
                        [resolved, "mcp", "enable", "epiagent"],
                        cwd=workspace,
                        environment=environment,
                        timeout_seconds=30,
                        umask=0o077,
                        forbidden_exact_bytes=(cursor_key_bytes,),
                    )
                except ProviderOutputOverflowError:
                    cursor_key_bytes = b""
                    environment.pop("CURSOR_API_KEY", None)
                    cursor_api_key = None
                    raise ProviderStateIsolationError(
                        "Cursor MCP readiness output exceeded its capture limit"
                    ) from None
                if (
                    cursor_key_bytes in enabled.stdout
                    or cursor_key_bytes in enabled.stderr
                ):
                    enabled = subprocess.CompletedProcess(
                        enabled.args,
                        enabled.returncode,
                        stdout=_redact_exact_secret_bytes(
                            enabled.stdout, cursor_api_key
                        ),
                        stderr=_redact_exact_secret_bytes(
                            enabled.stderr, cursor_api_key
                        ),
                    )
                    cursor_key_bytes = b""
                    environment.pop("CURSOR_API_KEY", None)
                    cursor_api_key = None
                    raise ProviderStateIsolationError(
                        "Provider credential isolation failed"
                    ) from None
                if enabled.returncode != 0:
                    raise RuntimeError(
                        "Cursor MCP enablement failed before the paid agent call"
                    )
        except (
            CodexAuthenticationIncidentError,
            ProviderExecutionIsolationError,
        ) as error:
            readiness_terminal_error = error
            raise
        finally:
            try:
                if system == "codex":
                    assert codex_home_link is not None
                    assert codex_auth_storage_path is not None
                    _attest_runtime_codex_auth(
                        codex_home_link, codex_auth_storage_path
                    )
                if system == "claude":
                    _attest_runtime_claude_credential_state(
                        glean_home_link, secure_storage_path
                    )
                if cursor_host_audit:
                    readiness_after = _snapshot_cursor_host_state()
                    isolation_events = _cursor_host_persistence_audit(
                        cursor_host_state_before, readiness_after
                    )
                    if isolation_events:
                        raise ProviderStateIsolationError(
                            "Cursor readiness isolation guard failed: "
                            + isolation_events[0]
                        )
                    cursor_host_state_before = readiness_after
            except Exception:
                if readiness_terminal_error is None:
                    raise

        session = launch_socket_episode(
            public_socket_path=socket_path,
            seed=seed,
            family=family,
            backend=backend,
            episode_secret=episode_secret,
        )
        session_terminal_error: Exception | None = None
        try:
            call_terminal_error: Exception | None = None
            try:
                if system == "codex":
                    assert codex_home_link is not None
                    assert codex_auth_storage_path is not None
                    _attest_runtime_codex_auth(
                        codex_home_link, codex_auth_storage_path
                    )
                if system == "claude":
                    _attest_runtime_claude_credential_state(
                        glean_home_link, secure_storage_path
                    )
                started = time.monotonic()
                try:
                    forbidden_output = (
                        (cursor_api_key.encode("utf-8"),)
                        if cursor_api_key is not None
                        else ()
                    )
                    process = _run_provider_process_group(
                        command,
                        cwd=workspace,
                        environment=environment,
                        timeout_seconds=timeout_seconds,
                        umask=0o077,
                        forbidden_exact_bytes=forbidden_output,
                    )
                    returncode = process.returncode
                    stdout = _bounded(process.stdout)
                    stderr = _bounded(process.stderr)
                except subprocess.TimeoutExpired as exc:
                    returncode = 124
                    stdout = _bounded(exc.stdout or b"")
                    stderr = _bounded(exc.stderr or b"")
                    audit.append("agent_failure:timeout")
                except ProviderOutputOverflowError as exc:
                    returncode = exc.returncode
                    stdout = exc.stdout
                    stderr = exc.stderr
                    audit.append("agent_failure:output_overflow")
                if system == "codex" and returncode < 0:
                    raise CodexAuthenticationIncidentError(
                        "Isolated Codex authentication state became ambiguous"
                    )
            except (
                CodexAuthenticationIncidentError,
                ProviderExecutionIsolationError,
            ) as error:
                call_terminal_error = error
                raise
            finally:
                try:
                    if system == "codex":
                        assert codex_home_link is not None
                        assert codex_auth_storage_path is not None
                        _attest_runtime_codex_auth(
                            codex_home_link, codex_auth_storage_path
                        )
                    if system == "claude":
                        _attest_runtime_claude_credential_state(
                            glean_home_link, secure_storage_path
                        )
                    if cursor_host_audit:
                        isolation_events = _cursor_host_persistence_audit(
                            cursor_host_state_before,
                            _snapshot_cursor_host_state(),
                        )
                        if isolation_events:
                            raise ProviderStateIsolationError(
                                "Cursor isolation guard failed: "
                                + isolation_events[0]
                            )
                except Exception:
                    if call_terminal_error is None:
                        raise
            elapsed = time.monotonic() - started
            if returncode != 0:
                audit.append("agent_failure:nonzero_exit")

            final_output = _read_provider_final_output(final_path)
            credential_echo = bool(
                cursor_api_key
                and (
                    cursor_api_key.encode("utf-8") in stdout
                    or cursor_api_key.encode("utf-8") in stderr
                    or cursor_api_key.encode("utf-8")
                    in (final_output or b"")
                )
            )
            if credential_echo:
                stdout = _redact_exact_secret_bytes(stdout, cursor_api_key)
                stderr = _redact_exact_secret_bytes(stderr, cursor_api_key)
                final_output = _redact_exact_secret_bytes(
                    final_output or b"", cursor_api_key
                )
                process = None
                environment.pop("CURSOR_API_KEY", None)
                cursor_api_key = None
                raise ProviderStateIsolationError(
                    "Provider credential isolation failed"
                ) from None
            submission, observed, parse_audit = parse_agent_output(
                system,
                requested_model=requested_model,
                stdout=stdout,
                final_output=final_output,
            )
            audit.extend(parse_audit)
            credential_echo = False
            if cursor_api_key is not None:
                parsed_surface = json.dumps(
                    {
                        "submission": submission,
                        "observed_models": observed,
                    },
                    ensure_ascii=False,
                    default=str,
                )
                if cursor_api_key in parsed_surface:
                    credential_echo = True
                if credential_echo:
                    submission = None
                    observed = ()
                    audit.append(
                        "infrastructure_failure:provider_credential_echo"
                    )
            evidence_stdout = _redact_exact_secret_bytes(
                stdout, cursor_api_key
            )
            evidence_stderr = _redact_exact_secret_bytes(
                stderr, cursor_api_key
            )
            if credential_echo:
                stdout = evidence_stdout
                stderr = evidence_stderr
                final_output = _redact_exact_secret_bytes(
                    final_output or b"", cursor_api_key
                )
                submission = None
                observed = ()
                parsed_surface = ""
                process = None
                environment.pop("CURSOR_API_KEY", None)
                cursor_api_key = None
                raise ProviderStateIsolationError(
                    "Provider credential isolation failed"
                ) from None
            diagnostic = _diagnostic(
                evidence_stdout,
                evidence_stderr,
                temporary_root=str(root),
                returncode=returncode,
                redacted_paths=(
                    tuple(
                        str(path)
                        for path in (
                            codex_auth_storage_path,
                            secure_storage_path,
                        )
                        if path is not None
                    )
                ),
                redact_provider_auth=(
                    system == "claude" and secure_storage_path is not None
                ),
            )
            if submission is None and not (
                system == "claude" and secure_storage_path is not None
            ):
                diagnostic = "\n".join(
                    part
                    for part in (
                        diagnostic,
                        _record_shape_summary(evidence_stdout),
                    )
                    if part
                )
            if system in {"codex", "cursor"} and diagnostic.strip():
                diagnostic = f"{system.title()} provider diagnostic redacted"
            accepted = (
                submission
                if not credential_echo
                and not any(
                    event.startswith("agent_failure:") for event in audit
                )
                else {}
            )
            if not session.score_with_replay_request_fits(
                accepted,
                audit_events=audit,
                agent_artifacts=(json.dumps(accepted),),
            ):
                audit.append("agent_failure:oversize_submission")
                accepted = {}
            terminal = session.score_with_replay(
                accepted,
                audit_events=audit,
                agent_artifacts=(json.dumps(accepted),),
            )
            scorecard = terminal["scorecard"]
            replay_trace = terminal["replay_trace"]
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
                captured_stdout_sha256=(
                    "sha256:" + hashlib.sha256(evidence_stdout).hexdigest()
                ),
                captured_stderr_sha256=(
                    "sha256:" + hashlib.sha256(evidence_stderr).hexdigest()
                ),
                command_sha256=(
                    "sha256:"
                    + hashlib.sha256(
                        json.dumps(
                            command,
                            ensure_ascii=True,
                            separators=(",", ":"),
                        ).encode("ascii")
                    ).hexdigest()
                ),
                replay_trace=replay_trace,
            )
        except (
            CodexAuthenticationIncidentError,
            ProviderExecutionIsolationError,
        ) as error:
            session_terminal_error = error
            raise
        finally:
            try:
                session.close()
            except Exception:
                if session_terminal_error is None:
                    raise ProviderExecutionIsolationError(
                        "Episode service cleanup could not be verified"
                    ) from None


def evaluate_paired_cli_agents(
    *,
    seed: int,
    systems: Sequence[str] = ("codex", "claude", "cursor"),
    family: str | None = None,
    backend: str = "starsim",
    episode_secret: bytes | None = None,
    timeout_seconds: int = 600,
    claude_max_budget_usd: float = 1.0,
    claude_effort: str | ClaudeEffort | None = None,
    codex_auth_storage_dir: str | os.PathLike[str] | None = None,
) -> tuple[PilotRunResult, ...]:
    """Replay one private episode independently across full agent systems."""

    secret = episode_secret or secrets.token_bytes(32)
    effort = _validate_claude_effort(claude_effort)
    return tuple(
        evaluate_local_cli_agent(
            system,
            seed=seed,
            family=family,
            backend=backend,
            episode_secret=secret,
            timeout_seconds=timeout_seconds,
            claude_max_budget_usd=claude_max_budget_usd,
            claude_effort=effort if system == "claude" else None,
            codex_auth_storage_dir=(
                codex_auth_storage_dir if system == "codex" else None
            ),
        )
        for system in systems
    )
