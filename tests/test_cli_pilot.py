from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epiagentbench.pilot import (
    ClaudeEffort,
    _CLAUDE_EXPECTED_TOOLS,
    _CLAUDE_MCP_TOOL_NAMES,
    _CLAUDE_UNSUPPORTED_SCHEMA_KEYS,
    _claude_provider_schema,
    _isolate_claude_environment,
    _prepare_workspace,
    build_agent_command,
    evaluate_paired_cli_agents,
    parse_agent_output,
)


def _submission() -> dict:
    return {
        "incident_assessment": {"outbreak_probability": 0.5},
        "case_definition": {
            "clinical": "GI illness",
            "person": "alert-associated person",
            "place": "jurisdiction",
            "time": "alert window",
            "laboratory": "compatible result",
        },
        "line_list": [],
        "hypotheses": [],
        "recommended_actions": [],
        "uncertainties": [],
        "next_evidence": [],
        "executive_brief": "Indeterminate.",
    }


def _claude_init(
    model: str | None,
    *,
    tools: list[str] | None = None,
    mcp_servers: list[dict[str, str]] | None = None,
) -> dict:
    record = {
        "type": "system",
        "subtype": "init",
        "tools": list(_CLAUDE_EXPECTED_TOOLS) if tools is None else tools,
        "mcp_servers": (
            [{"name": "epiagent", "status": "connected"}]
            if mcp_servers is None
            else mcp_servers
        ),
    }
    if model is not None:
        record["model"] = model
    return record


class CliPilotTests(unittest.TestCase):
    def _command(
        self,
        system: str,
        *,
        model: str | None = None,
        claude_effort: str | ClaudeEffort | None = None,
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as temp:
            schema = (
                Path(__file__).resolve().parents[1]
                / "schemas"
                / "submission.schema.json"
            )
            return build_agent_command(
                system,
                executable=system,
                model=model or {
                    "codex": "gpt-5.6-sol",
                    "claude": "claude-fable-5",
                    "cursor": "glm-5.2-high",
                }[system],
                workspace=temp,
                schema_path=str(schema),
                mcp_path=str(Path(temp) / "mcp.json"),
                final_output_path=str(Path(temp) / "final.json"),
                python="/usr/bin/python3",
                public_root=str(Path(temp) / "public"),
                socket_path=str(Path(temp) / "episode.sock"),
                claude_effort=claude_effort,
            )

    def test_commands_pin_models_and_isolated_modes(self):
        codex = self._command("codex")
        self.assertIn("gpt-5.6-sol", codex)
        self.assertIn("--ephemeral", codex)
        self.assertIn("--ignore-user-config", codex)
        self.assertIn("shell_tool", codex)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", codex)

        claude = self._command("claude")
        self.assertIn("claude-fable-5", claude)
        self.assertNotIn("--safe-mode", claude)
        self.assertIn("--strict-mcp-config", claude)
        self.assertIn("--no-session-persistence", claude)
        self.assertIn("--no-chrome", claude)
        self.assertEqual(claude[claude.index("--tools") + 1], "Read")
        self.assertEqual(
            claude[claude.index("--disallowedTools") + 1],
            "Read",
        )
        self.assertEqual(
            claude[claude.index("--permission-mode") + 1],
            "dontAsk",
        )
        self.assertEqual(
            claude[claude.index("--setting-sources") + 1],
            "project",
        )
        self.assertIn("--disable-slash-commands", claude)
        self.assertEqual(
            claude[claude.index("--allowedTools") + 1],
            "mcp__epiagent__*",
        )
        self.assertIn("--json-schema", claude)
        schema_index = claude.index("--json-schema")
        self.assertEqual(
            json.loads(claude[schema_index + 1]),
            _claude_provider_schema(
                str(
                    Path(__file__).resolve().parents[1]
                    / "schemas"
                    / "submission.schema.json"
                )
            ),
        )

        cursor = self._command("cursor")
        self.assertIn("glm-5.2-high", cursor)
        self.assertIn("--sandbox", cursor)
        self.assertIn("--allowed-tools", cursor)
        self.assertIn("mcp_tool_call", cursor)
        self.assertIn("get_mcp_tools_tool_call", cursor)
        self.assertEqual(cursor.count("--allowed-tools"), 2)
        self.assertNotIn("--auto-review", cursor)
        self.assertNotIn("--mode", cursor)
        self.assertNotIn("--approve-mcps", cursor)
        self.assertNotIn("--force", cursor)
        self.assertNotIn("--yolo", cursor)

    def test_claude_provider_schema_projects_then_trusted_scorer_revalidates(self):
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "submission.schema.json"
        )
        source = json.loads(schema_path.read_text(encoding="utf-8"))
        projected = _claude_provider_schema(str(schema_path))
        encoded = json.dumps(projected, sort_keys=True)
        for keyword in _CLAUDE_UNSUPPORTED_SCHEMA_KEYS:
            self.assertNotIn(f'"{keyword}"', encoded)
        self.assertNotIn('"$ref"', encoded)
        self.assertNotIn('"$defs"', encoded)
        self.assertEqual(set(projected["properties"]), set(source["properties"]))
        self.assertEqual(set(projected["required"]), set(source["required"]))
        self.assertEqual(
            source["properties"]["executive_brief"]["maxLength"], 4000
        )
        self.assertNotIn(
            "maxLength", projected["properties"]["executive_brief"]
        )

    def test_claude_environment_is_private_and_clears_safe_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            environment = {
                "HOME": "/inherited/home",
                "CLAUDE_CONFIG_DIR": "/inherited/claude",
                "XDG_CONFIG_HOME": "/inherited/xdg",
                "CLAUDE_CODE_SAFE_MODE": "1",
                "PATH": "/bin",
            }
            _isolate_claude_environment(environment, root)
            self.assertNotIn("CLAUDE_CODE_SAFE_MODE", environment)
            self.assertEqual(environment["PATH"], "/bin")
            for name in (
                "HOME",
                "CLAUDE_CONFIG_DIR",
                "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME",
                "XDG_DATA_HOME",
                "XDG_STATE_HOME",
            ):
                path = Path(environment[name])
                self.assertTrue(path.is_dir())
                self.assertTrue(path.is_relative_to(root))

    def test_claude_high_effort_is_emitted_exactly(self):
        command = self._command(
            "claude",
            model="claude-opus-4-8",
            claude_effort=ClaudeEffort.HIGH,
        )
        effort_index = command.index("--effort")
        self.assertEqual(command[effort_index : effort_index + 2], ["--effort", "high"])
        self.assertEqual(command.count("--effort"), 1)

    def test_claude_effort_is_validated_and_scoped(self):
        with self.assertRaisesRegex(ValueError, "Invalid Claude effort"):
            self._command("claude", claude_effort="ultra")
        with self.assertRaisesRegex(ValueError, "only valid for the Claude"):
            self._command("codex", claude_effort="high")

    def test_claude_schema_must_be_valid_json_object(self):
        with tempfile.TemporaryDirectory() as temp:
            schema = Path(temp) / "schema.json"
            schema.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid Claude JSON schema"):
                build_agent_command(
                    "claude",
                    executable="claude",
                    model="claude-opus-4-8",
                    workspace=temp,
                    schema_path=str(schema),
                    mcp_path=str(Path(temp) / "mcp.json"),
                    final_output_path=str(Path(temp) / "final.json"),
                    python="/usr/bin/python3",
                    public_root=str(Path(temp) / "public"),
                    socket_path=str(Path(temp) / "episode.sock"),
                    claude_effort="high",
                )

    def test_paired_run_threads_effort_only_to_claude(self):
        sentinel = object()
        with patch(
            "epiagentbench.pilot.evaluate_local_cli_agent",
            return_value=sentinel,
        ) as evaluate:
            results = evaluate_paired_cli_agents(
                seed=17,
                systems=("codex", "claude", "cursor"),
                episode_secret=b"s" * 32,
                claude_effort="high",
            )
        self.assertEqual(results, (sentinel, sentinel, sentinel))
        calls = evaluate.call_args_list
        self.assertIsNone(calls[0].kwargs["claude_effort"])
        self.assertEqual(calls[1].kwargs["claude_effort"], "high")
        self.assertIsNone(calls[2].kwargs["claude_effort"])

    def test_cursor_workspace_allowlists_only_public_mcp_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace, _, _, _ = _prepare_workspace(
                Path(temp), str(Path(temp) / "episode.sock")
            )
            cli = json.loads((workspace / ".cursor" / "cli.json").read_text())
            allowlist = cli["permissions"]["allow"]
            self.assertEqual(len(allowlist), 12)
            self.assertTrue(
                all(item.startswith("Mcp(epiagent:") for item in allowlist)
            )
            self.assertEqual(
                cli["permissions"]["deny"],
                ["Shell(*)", "Read(**)", "Write(**)", "WebFetch(*)"],
            )

    def test_codex_final_file_parses(self):
        expected = _submission()
        submission, observed, audit = parse_agent_output(
            "codex",
            requested_model="gpt-5.6-sol",
            stdout=b'{"type":"turn.completed"}\n',
            final_output=json.dumps(expected).encode(),
        )
        self.assertEqual(submission, expected)
        self.assertEqual(observed, ())
        self.assertEqual(audit, ())

    def test_claude_structured_output_and_model_are_verified(self):
        expected = _submission()
        stream = b"\n".join(
            [
                json.dumps(_claude_init("claude-fable-5")).encode(),
                json.dumps(
                    {
                        "type": "result",
                        "structured_output": expected,
                        "modelUsage": {"claude-fable-5": {}},
                    }
                ).encode(),
            ]
        )
        submission, observed, audit = parse_agent_output(
            "claude", requested_model="claude-fable-5", stdout=stream
        )
        self.assertEqual(submission, expected)
        self.assertEqual(observed, ("claude-fable-5",))
        self.assertEqual(audit, ())

    def test_claude_old_no_mcp_initialization_is_rejected(self):
        stream = b"\n".join(
            [
                json.dumps(
                    _claude_init(
                        "claude-opus-4-8",
                        tools=["StructuredOutput"],
                        mcp_servers=[],
                    )
                ).encode(),
                json.dumps(
                    {
                        "type": "result",
                        "structured_output": _submission(),
                        "modelUsage": {"claude-opus-4-8": {}},
                    }
                ).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "claude", requested_model="claude-opus-4-8", stdout=stream
        )
        self.assertIsNone(submission)
        self.assertIn("agent_failure:mcp_unavailable", audit)

    def test_claude_mcp_without_structured_output_is_infrastructure(self):
        stream = b"\n".join(
            [
                json.dumps(
                    _claude_init(
                        "claude-opus-4-8",
                        tools=list(_CLAUDE_MCP_TOOL_NAMES),
                    )
                ).encode(),
                json.dumps(
                    {
                        "type": "result",
                        "result": json.dumps(_submission()),
                        "modelUsage": {"claude-opus-4-8": {}},
                    }
                ).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "claude", requested_model="claude-opus-4-8", stdout=stream
        )
        self.assertIsNone(submission)
        self.assertIn("agent_failure:structured_output_unavailable", audit)
        self.assertNotIn("agent_failure:mcp_unavailable", audit)

    def test_claude_exact_inventory_and_public_tool_use_are_accepted(self):
        expected = _submission()
        stream = b"\n".join(
            [
                json.dumps(_claude_init("claude-opus-4-8")).encode(),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "model": "claude-opus-4-8",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "mcp__epiagent__get_manifest",
                                    "input": {},
                                }
                            ],
                        },
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "result",
                        "structured_output": expected,
                        "modelUsage": {"claude-opus-4-8": {}},
                    }
                ).encode(),
            ]
        )
        submission, observed, audit = parse_agent_output(
            "claude", requested_model="claude-opus-4-8", stdout=stream
        )
        self.assertEqual(submission, expected)
        self.assertEqual(observed, ("claude-opus-4-8",))
        self.assertEqual(audit, ())

    def test_claude_builtin_tool_attempt_is_rejected(self):
        stream = b"\n".join(
            [
                json.dumps(_claude_init("claude-opus-4-8")).encode(),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "model": "claude-opus-4-8",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Read",
                                    "input": {"file_path": "TASK.md"},
                                }
                            ],
                        },
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "result",
                        "structured_output": _submission(),
                        "modelUsage": {"claude-opus-4-8": {}},
                    }
                ).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "claude", requested_model="claude-opus-4-8", stdout=stream
        )
        self.assertIsNone(submission)
        self.assertIn("agent_failure:unauthorized_tool", audit)

    def test_fable_to_opus_fallback_is_rejected(self):
        stream = b"\n".join(
            [
                json.dumps(_claude_init("claude-fable-5")).encode(),
                json.dumps(
                    {
                        "type": "result",
                        "structured_output": _submission(),
                        "modelUsage": {"claude-opus-4-8": {}},
                    }
                ).encode(),
            ]
        )
        submission, observed, audit = parse_agent_output(
            "claude", requested_model="claude-fable-5", stdout=stream
        )
        self.assertIsNone(submission)
        self.assertEqual(observed, ("claude-fable-5", "claude-opus-4-8"))
        self.assertIn("agent_failure:model_fallback", audit)

    def test_exact_requested_opus_model_is_accepted(self):
        expected = _submission()
        stream = b"\n".join(
            [
                json.dumps(_claude_init("claude-opus-4-8")).encode(),
                json.dumps(
                    {
                        "type": "result",
                        "structured_output": expected,
                        "modelUsage": {"claude-opus-4-8": {}},
                    }
                ).encode(),
            ]
        )
        submission, observed, audit = parse_agent_output(
            "claude", requested_model="claude-opus-4-8", stdout=stream
        )
        self.assertEqual(submission, expected)
        self.assertEqual(observed, ("claude-opus-4-8",))
        self.assertEqual(audit, ())

    def test_other_opus_version_is_rejected_as_fallback(self):
        stream = b"\n".join(
            [
                json.dumps(_claude_init("claude-opus-4-8")).encode(),
                json.dumps(
                    {
                        "type": "result",
                        "structured_output": _submission(),
                        "modelUsage": {"claude-opus-4-7": {}},
                    }
                ).encode(),
            ]
        )
        submission, observed, audit = parse_agent_output(
            "claude", requested_model="claude-opus-4-8", stdout=stream
        )
        self.assertIsNone(submission)
        self.assertEqual(observed, ("claude-opus-4-8", "claude-opus-4-7"))
        self.assertIn("agent_failure:model_fallback", audit)

    def test_unverified_claude_output_is_rejected(self):
        stream = b"\n".join(
            [
                json.dumps(_claude_init(None)).encode(),
                json.dumps(
                    {"type": "result", "structured_output": _submission()}
                ).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "claude", requested_model="claude-fable-5", stdout=stream
        )
        self.assertIsNone(submission)
        self.assertIn("agent_failure:model_unverified", audit)

    def test_cursor_display_model_and_public_mcp_are_accepted(self):
        expected = _submission()
        stream = b"\n".join(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "model": "GLM 5.2 High",
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "tool_call",
                        "subtype": "completed",
                        "tool_call": {
                            "toolCallId": "call-1",
                            "startedAtMs": 1,
                            "mcpToolCall": {
                                "args": {
                                    "providerIdentifier": "epiagent",
                                    "toolName": "get_manifest",
                                }
                            },
                        },
                    }
                ).encode(),
                json.dumps({"type": "result", "result": expected}).encode(),
            ]
        )
        submission, observed, audit = parse_agent_output(
            "cursor", requested_model="glm-5.2-high", stdout=stream
        )
        self.assertEqual(submission, expected)
        self.assertEqual(observed, ("GLM 5.2 High",))
        self.assertEqual(audit, ())

    def test_cursor_single_fenced_submission_with_prose_is_accepted(self):
        expected = _submission()
        result_text = (
            "Investigation complete.\n```json\n"
            + json.dumps(expected)
            + "\n```\nBrief note follows."
        )
        stream = b"\n".join(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "model": "GLM 5.2 High",
                    }
                ).encode(),
                json.dumps({"type": "result", "result": result_text}).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "cursor", requested_model="glm-5.2-high", stdout=stream
        )
        self.assertEqual(submission, expected)
        self.assertEqual(audit, ())

    def test_cursor_ambiguous_or_arbitrary_json_recovery_is_rejected(self):
        encoded = json.dumps(_submission())
        for result_text in (
            f"First:\n```json\n{encoded}\n```\nSecond:\n```json\n{encoded}\n```",
            f"Unfenced prose before {encoded} and after",
            'Prose\n```json\n{"incomplete":true}\n```',
        ):
            with self.subTest(result_text=result_text[:30]):
                stream = json.dumps(
                    {"type": "result", "result": result_text}
                ).encode()
                submission, _, audit = parse_agent_output(
                    "cursor", requested_model="glm-5.2-high", stdout=stream
                )
                self.assertIsNone(submission)
                self.assertIn("agent_failure:invalid_submission", audit)

    def test_cursor_does_not_fall_back_from_malformed_terminal_result(self):
        stream = b"\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": json.dumps(_submission()),
                            "role": "assistant",
                        },
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "result",
                        "result": "Final submission: ```json\n{malformed}\n```",
                    }
                ).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "cursor", requested_model="glm-5.2-high", stdout=stream
        )
        self.assertIsNone(submission)
        self.assertIn("agent_failure:invalid_submission", audit)

    def test_cursor_multiple_terminal_results_are_ambiguous(self):
        stream = b"\n".join(
            json.dumps({"type": "result", "result": _submission()}).encode()
            for _ in range(2)
        )
        submission, _, audit = parse_agent_output(
            "cursor", requested_model="glm-5.2-high", stdout=stream
        )
        self.assertIsNone(submission)
        self.assertIn("agent_failure:invalid_submission", audit)

    def test_cursor_identityless_completions_inherit_authorized_start(self):
        stream = b"\n".join(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "model": "GLM 5.2 High",
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "tool_call",
                        "subtype": "started",
                        "tool_call": {
                            "toolCallId": "call-1",
                            "mcpToolCall": {
                                "args": {
                                    "providerIdentifier": "epiagent",
                                    "toolName": "get_manifest",
                                }
                            },
                        },
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "tool_call",
                        "subtype": "completed",
                        "tool_call": {
                            "toolCallId": "call-1",
                            "error": "provider-formatted completion",
                        },
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "tool_call",
                        "subtype": "started",
                        "tool_call": {
                            "toolCallId": "call-2",
                            "mcpToolCall": {
                                "providerIdentifier": "epiagent",
                                "toolName": "get_clock_and_budget",
                            },
                        },
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "tool_call",
                        "subtype": "completed",
                        "tool_call": {
                            "toolCallId": "call-2",
                            "mcpToolCall": {"result": {"isError": False}},
                        },
                    }
                ).encode(),
                json.dumps(
                    {"type": "result", "result": _submission()}
                ).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "cursor", requested_model="glm-5.2-high", stdout=stream
        )
        self.assertEqual(submission, _submission())
        self.assertNotIn("agent_failure:unauthorized_tool", audit)
        self.assertNotIn(
            "agent_failure:tool_transport_unverifiable", audit
        )

    def test_cursor_uncorrelated_identityless_completion_fails_integrity(self):
        stream = b"\n".join(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "model": "GLM 5.2 High",
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "tool_call",
                        "subtype": "completed",
                        "tool_call": {
                            "toolCallId": "unseen-call",
                            "mcpToolCall": {"error": "completion only"},
                        },
                    }
                ).encode(),
                json.dumps(
                    {"type": "result", "result": _submission()}
                ).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "cursor", requested_model="glm-5.2-high", stdout=stream
        )
        self.assertEqual(submission, _submission())
        self.assertNotIn("agent_failure:unauthorized_tool", audit)
        self.assertIn(
            "agent_failure:tool_transport_unverifiable", audit
        )

    def test_cursor_unknown_tool_event_subtype_fails_integrity(self):
        stream = b"\n".join(
            [
                json.dumps(
                    {
                        "type": "tool_call",
                        "subtype": "mystery",
                        "tool_call": {
                            "readToolCall": {"path": "/grader/oracle.json"}
                        },
                    }
                ).encode(),
                json.dumps(
                    {"type": "result", "result": _submission()}
                ).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "cursor", requested_model="glm-5.2-high", stdout=stream
        )
        self.assertEqual(submission, _submission())
        self.assertIn("agent_failure:tool_transport_unverifiable", audit)

    def test_cursor_builtin_tool_attempt_is_rejected(self):
        stream = b"\n".join(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "model": "GLM 5.2 High",
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "tool_call",
                        "subtype": "started",
                        "tool_call": {"readToolCall": {"args": {"path": "x"}}},
                    }
                ).encode(),
                json.dumps(
                    {"type": "result", "result": _submission()}
                ).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "cursor", requested_model="glm-5.2-high", stdout=stream
        )
        self.assertEqual(submission, _submission())
        self.assertIn("agent_failure:unauthorized_tool", audit)

    def test_cursor_public_mcp_discovery_is_accepted(self):
        stream = b"\n".join(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "model": "GLM 5.2 High",
                    }
                ).encode(),
                json.dumps(
                    {
                        "type": "tool_call",
                        "subtype": "completed",
                        "tool_call": {
                            "getMcpToolsToolCall": {"args": {}}
                        },
                    }
                ).encode(),
                json.dumps({"type": "result", "result": _submission()}).encode(),
            ]
        )
        submission, _, audit = parse_agent_output(
            "cursor", requested_model="glm-5.2-high", stdout=stream
        )
        self.assertEqual(submission, _submission())
        self.assertEqual(audit, ())


if __name__ == "__main__":
    unittest.main()
