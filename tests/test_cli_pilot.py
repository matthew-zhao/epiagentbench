from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epiagentbench.pilot import (
    ClaudeEffort,
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


class CliPilotTests(unittest.TestCase):
    def _command(
        self,
        system: str,
        *,
        model: str | None = None,
        claude_effort: str | ClaudeEffort | None = None,
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as temp:
            schema = Path(temp) / "schema.json"
            schema.write_text('{"type":"object"}', encoding="utf-8")
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

    def test_commands_pin_models_and_safe_modes(self):
        codex = self._command("codex")
        self.assertIn("gpt-5.6-sol", codex)
        self.assertIn("--ephemeral", codex)
        self.assertIn("--ignore-user-config", codex)
        self.assertIn("shell_tool", codex)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", codex)

        claude = self._command("claude")
        self.assertIn("claude-fable-5", claude)
        self.assertIn("--safe-mode", claude)
        self.assertIn("--strict-mcp-config", claude)
        self.assertIn("--no-session-persistence", claude)
        self.assertIn("--json-schema", claude)
        schema_index = claude.index("--json-schema")
        self.assertEqual(
            json.loads(claude[schema_index + 1]),
            {"type": "object"},
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
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "model": "claude-fable-5",
                    }
                ).encode(),
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

    def test_fable_to_opus_fallback_is_rejected(self):
        stream = json.dumps(
            {
                "type": "result",
                "structured_output": _submission(),
                "modelUsage": {"claude-opus-4-8": {}},
            }
        ).encode()
        submission, observed, audit = parse_agent_output(
            "claude", requested_model="claude-fable-5", stdout=stream
        )
        self.assertIsNone(submission)
        self.assertEqual(observed, ("claude-opus-4-8",))
        self.assertIn("agent_failure:model_fallback", audit)

    def test_exact_requested_opus_model_is_accepted(self):
        expected = _submission()
        stream = b"\n".join(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "model": "claude-opus-4-8",
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

    def test_other_opus_version_is_rejected_as_fallback(self):
        stream = json.dumps(
            {
                "type": "result",
                "structured_output": _submission(),
                "modelUsage": {"claude-opus-4-7": {}},
            }
        ).encode()
        submission, observed, audit = parse_agent_output(
            "claude", requested_model="claude-opus-4-8", stdout=stream
        )
        self.assertIsNone(submission)
        self.assertEqual(observed, ("claude-opus-4-7",))
        self.assertIn("agent_failure:model_fallback", audit)

    def test_unverified_claude_output_is_rejected(self):
        stream = json.dumps(
            {"type": "result", "structured_output": _submission()}
        ).encode()
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
