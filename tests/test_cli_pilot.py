from __future__ import annotations

import hashlib
import json
import os
import selectors
from dataclasses import asdict
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from epiagentbench.pilot import (
    CodexAuthenticationIncidentError,
    ClaudeEffort,
    ProviderOutputOverflowError,
    ProviderProcessIsolationError,
    ProviderStateIsolationError,
    _ProviderTemporaryDirectory,
    _CLAUDE_EXPECTED_TOOLS,
    _CLAUDE_MCP_TOOL_NAMES,
    _CLAUDE_UNSUPPORTED_SCHEMA_KEYS,
    _MAX_CAPTURE_BYTES,
    _attest_claude_secure_storage_keychain,
    _attest_codex_auth_home_link,
    _attest_codex_auth_storage,
    _attest_managed_glean_home_link,
    _advance_exact_byte_match,
    _canonical_codex_auth_storage_path,
    _claude_provider_schema,
    _claude_secure_storage_keychain_service,
    _cursor_host_persistence_audit,
    _diagnostic,
    _isolate_claude_environment,
    _isolate_codex_environment,
    _isolate_cursor_environment,
    _isolate_identity_environment,
    _prepare_workspace,
    _reject_claude_plaintext_fallback,
    _read_provider_final_output,
    _run_provider_process_group,
    _snapshot_cursor_host_chat_metadata,
    _snapshot_cursor_host_state,
    build_agent_command,
    evaluate_local_cli_agent,
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
        self.assertIn('cli_auth_credentials_store="file"', codex)
        self.assertEqual(
            codex.count('cli_auth_credentials_store="file"'), 1
        )
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

    def test_claude_environment_is_private_and_scrubs_inherited_routing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            secure = root / "explicit-secure-storage"
            secure.mkdir(mode=0o700)
            environment = {
                "HOME": "/inherited/home",
                "CLAUDE_CONFIG_DIR": "/inherited/claude",
                "XDG_CONFIG_HOME": "/inherited/xdg",
                "CLAUDE_CODE_SAFE_MODE": "1",
                "CLAUDE_CODE_OAUTH_TOKEN": "hostile-token",
                "CLAUDE_SECURESTORAGE_CONFIG_DIR": "/inherited/secure",
                "ANTHROPIC_API_KEY": "hostile-token",
                "ANTHROPIC_BASE_URL": "https://attacker.invalid",
                "GLEAN_API_TOKEN": "hostile-token",
                "GLEAN_BASE_URL": "https://attacker.invalid",
                "GLEAN_HELPER_OAUTH_CLIENT_ID": "hostile-client-id",
                "GLEAN_HELPER_OAUTH_ISSUER": "https://attacker.invalid",
                "SCIO_API_URL": "https://attacker.invalid",
                "NODE_OPTIONS": "--require=/inherited/inject.js",
                "SSH_AUTH_SOCK": "/inherited/agent.sock",
                "PATH": "/bin",
                "HTTPS_PROXY": "https://proxy.invalid",
                "SSL_CERT_FILE": "/etc/ssl/cert.pem",
                "USER": "pilot-user",
                "LC_ALL": "C.UTF-8",
                "LC_INJECTION": "credential-routing",
            }
            glean_link = _isolate_claude_environment(
                environment,
                root,
                secure,
                "expected-client-id",
            )
            self.assertEqual(environment["PATH"], "/bin")
            self.assertEqual(environment["HTTPS_PROXY"], "https://proxy.invalid")
            self.assertEqual(environment["SSL_CERT_FILE"], "/etc/ssl/cert.pem")
            self.assertEqual(environment["USER"], "pilot-user")
            self.assertEqual(environment["LC_ALL"], "C.UTF-8")
            self.assertEqual(
                environment["CLAUDE_SECURESTORAGE_CONFIG_DIR"], str(secure)
            )
            self.assertEqual(
                environment["GLEAN_HELPER_OAUTH_CLIENT_ID"],
                "expected-client-id",
            )
            self.assertIsNotNone(glean_link)
            assert glean_link is not None
            self.assertTrue(glean_link.is_symlink())
            self.assertEqual(os.readlink(glean_link), str(secure))
            self.assertEqual(glean_link.resolve(), secure.resolve())
            for name in (
                "CLAUDE_CODE_SAFE_MODE",
                "CLAUDE_CODE_OAUTH_TOKEN",
                "ANTHROPIC_API_KEY",
                "ANTHROPIC_BASE_URL",
                "GLEAN_API_TOKEN",
                "GLEAN_BASE_URL",
                "GLEAN_HELPER_OAUTH_ISSUER",
                "SCIO_API_URL",
                "NODE_OPTIONS",
                "SSH_AUTH_SOCK",
                "LC_INJECTION",
            ):
                self.assertNotIn(name, environment)
            for name in (
                "HOME",
                "CLAUDE_CONFIG_DIR",
                "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME",
                "XDG_DATA_HOME",
                "XDG_STATE_HOME",
                "XDG_RUNTIME_DIR",
                "TMPDIR",
                "TMP",
                "TEMP",
                "NODE_COMPILE_CACHE",
            ):
                path = Path(environment[name])
                self.assertTrue(path.is_dir())
                self.assertTrue(path.is_relative_to(root))
                self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_claude_explicit_secure_storage_is_reused_across_disposable_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            secure = base / "persistent-secure-storage"
            secure.mkdir()
            roots = (base / "run-one", base / "run-two")
            environments = []
            for root in roots:
                root.mkdir()
                environment = {"PATH": "/bin"}
                _isolate_claude_environment(environment, root, secure)
                environments.append(environment)

            self.assertEqual(
                environments[0]["CLAUDE_SECURESTORAGE_CONFIG_DIR"], str(secure)
            )
            self.assertEqual(
                environments[1]["CLAUDE_SECURESTORAGE_CONFIG_DIR"], str(secure)
            )
            self.assertNotEqual(environments[0]["HOME"], environments[1]["HOME"])
            self.assertNotEqual(
                environments[0]["CLAUDE_CONFIG_DIR"],
                environments[1]["CLAUDE_CONFIG_DIR"],
            )
            for environment in environments:
                link = Path(environment["HOME"]) / ".glean-llm-gateway"
                self.assertTrue(link.is_symlink())
                self.assertEqual(os.readlink(link), str(secure.resolve()))

    def test_identity_environment_preserves_only_path_locale_and_fresh_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            environment = {
                "PATH": "/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "LC_INJECTION": "credential-routing",
                "CURSOR_API_KEY": "cursor-secret",
                "OPENAI_API_KEY": "openai-secret",
                "ANTHROPIC_API_KEY": "anthropic-secret",
                "GLEAN_HELPER_OAUTH_CLIENT_ID": "glean-routing",
                "NODE_OPTIONS": "--require=/tmp/inject.js",
                "PYTHONPATH": "/tmp/inject",
                "SSH_AUTH_SOCK": "/tmp/agent.sock",
                "DYLD_INSERT_LIBRARIES": "/tmp/inject.dylib",
                "LD_PRELOAD": "/tmp/inject.so",
                "HTTPS_PROXY": "https://proxy.invalid",
            }
            _isolate_identity_environment(environment, root)
            self.assertEqual(environment["PATH"], "/bin")
            self.assertEqual(environment["LANG"], "C.UTF-8")
            self.assertEqual(environment["LC_ALL"], "C.UTF-8")
            for forbidden in (
                "CURSOR_API_KEY",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "GLEAN_HELPER_OAUTH_CLIENT_ID",
                "NODE_OPTIONS",
                "PYTHONPATH",
                "SSH_AUTH_SOCK",
                "DYLD_INSERT_LIBRARIES",
                "LD_PRELOAD",
                "HTTPS_PROXY",
                "LC_INJECTION",
            ):
                self.assertNotIn(forbidden, environment)
            for name in (
                "HOME",
                "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME",
                "XDG_DATA_HOME",
                "XDG_STATE_HOME",
                "XDG_RUNTIME_DIR",
                "TMPDIR",
                "TMP",
                "TEMP",
                "NODE_COMPILE_CACHE",
            ):
                path = Path(environment[name])
                self.assertTrue(path.is_dir())
                self.assertTrue(path.is_relative_to(root))
                self.assertEqual(path.stat().st_mode & 0o077, 0)

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_process_group_captures_output_and_applies_umask(self):
        with tempfile.TemporaryDirectory() as temp:
            result = _run_provider_process_group(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os,sys; "
                        "current=os.umask(0); os.umask(current); "
                        "sys.stdout.write(oct(current)); "
                        "sys.stderr.write('provider-stderr')"
                    ),
                ],
                cwd=Path(temp),
                environment={"PATH": os.defpath},
                timeout_seconds=5,
                umask=0o077,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"0o77")
        self.assertEqual(result.stderr, b"provider-stderr")

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_process_group_timeout_kills_descendants(self):
        with tempfile.TemporaryDirectory() as temp:
            script = (
                "import subprocess,sys,time; "
                "child=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(60)']); "
                "print(child.pid,flush=True); time.sleep(60)"
            )
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                _run_provider_process_group(
                    [sys.executable, "-c", script],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=1,
                    umask=0o077,
                )

        child_pid = int((caught.exception.stdout or b"").strip())
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_process_group_bounds_captured_output(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ProviderOutputOverflowError) as caught:
                _run_provider_process_group(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import sys; sys.stdout.buffer.write(b'x' * "
                            f"{_MAX_CAPTURE_BYTES + 65_536})"
                        ),
                    ],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=5,
                    umask=0o077,
                )

        self.assertEqual(caught.exception.returncode, 0)
        self.assertEqual(len(caught.exception.stdout), _MAX_CAPTURE_BYTES)

    def test_exact_byte_match_spans_chunks_but_not_streams(self):
        secret = b"cursor-exact-secret"
        matched, stdout_tail = _advance_exact_byte_match(
            b"", b"prefix-cursor-exact-", (secret,)
        )
        self.assertFalse(matched)
        matched, _ = _advance_exact_byte_match(
            stdout_tail, b"secret-suffix", (secret,)
        )
        self.assertTrue(matched)

        matched, stdout_tail = _advance_exact_byte_match(
            b"", b"cursor-exact-", (secret,)
        )
        self.assertFalse(matched)
        matched, _ = _advance_exact_byte_match(
            b"", b"secret", (secret,)
        )
        self.assertFalse(matched)
        self.assertEqual(stdout_tail, b"cursor-exact-")

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_process_group_detects_secret_after_capture_limit(self):
        secret = b"cursor-key-only-in-discarded-output"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ProviderStateIsolationError) as caught:
                _run_provider_process_group(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import sys; "
                            "sys.stdout.buffer.write("
                            f"b'x'*{_MAX_CAPTURE_BYTES + 65_536}); "
                            f"sys.stdout.buffer.write({secret!r}); "
                            "sys.stdout.buffer.flush()"
                        ),
                    ],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=5,
                    umask=0o077,
                    forbidden_exact_bytes=(secret,),
                )

        self.assertEqual(
            str(caught.exception), "Provider credential isolation failed"
        )
        self.assertNotIn(secret.decode(), str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_process_group_continuous_output_cannot_starve_timeout(self):
        with tempfile.TemporaryDirectory() as temp:
            started = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                _run_provider_process_group(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import os; chunk=b'x'*65536; "
                            "exec(\"while True:\\n os.write(1,chunk)\")"
                        ),
                    ],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=1,
                    umask=0o077,
                )

        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual(len(caught.exception.stdout or b""), _MAX_CAPTURE_BYTES)

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_pipe_read_failure_is_terminal_and_reaped(self):
        spawned: list[subprocess.Popen[bytes]] = []
        real_popen = subprocess.Popen

        def launch(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            spawned.append(process)
            return process

        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "epiagentbench.pilot.subprocess.Popen",
                    side_effect=launch,
                ),
                patch(
                    "epiagentbench.pilot._read_provider_pipe",
                    side_effect=OSError("test capture failure"),
                ),
                self.assertRaisesRegex(
                    ProviderProcessIsolationError,
                    "output capture failed",
                ),
            ):
                _run_provider_process_group(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import sys,time; sys.stdout.write('x'); "
                            "sys.stdout.flush(); time.sleep(60)"
                        ),
                    ],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=5,
                    umask=0o077,
                )

        self.assertEqual(len(spawned), 1)
        self.assertIsNotNone(spawned[0].poll())

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_selector_select_failure_is_terminal_and_reaped(self):
        spawned: list[subprocess.Popen[bytes]] = []
        real_popen = subprocess.Popen
        delegate = selectors.DefaultSelector()

        def launch(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            spawned.append(process)
            return process

        class SelectFailingSelector:
            def __getattr__(self, name):
                return getattr(delegate, name)

            def select(self, _timeout):
                raise OSError("test selector failure")

            def close(self):
                delegate.close()

        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "epiagentbench.pilot.subprocess.Popen",
                    side_effect=launch,
                ),
                patch(
                    "epiagentbench.pilot.selectors.DefaultSelector",
                    return_value=SelectFailingSelector(),
                ),
                self.assertRaisesRegex(
                    ProviderProcessIsolationError,
                    "output selector failed",
                ),
            ):
                _run_provider_process_group(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=5,
                    umask=0o077,
                )

        self.assertEqual(len(spawned), 1)
        self.assertIsNotNone(spawned[0].poll())

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_selector_unregister_failure_is_terminal(self):
        delegate = selectors.DefaultSelector()

        class UnregisterFailingSelector:
            def __getattr__(self, name):
                return getattr(delegate, name)

            def unregister(self, _descriptor):
                raise OSError("test unregister failure")

            def close(self):
                delegate.close()

        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "epiagentbench.pilot.selectors.DefaultSelector",
                    return_value=UnregisterFailingSelector(),
                ),
                self.assertRaisesRegex(
                    ProviderProcessIsolationError,
                    "output selector failed",
                ),
            ):
                _run_provider_process_group(
                    [sys.executable, "-c", "pass"],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=5,
                    umask=0o077,
                )

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_poll_failure_is_terminal_and_reaped(self):
        delegates: list[subprocess.Popen[bytes]] = []
        real_popen = subprocess.Popen

        class PollFailingProcess:
            def __init__(self, delegate):
                self._delegate = delegate
                self._failed = False

            def __getattr__(self, name):
                return getattr(self._delegate, name)

            def poll(self):
                if not self._failed:
                    self._failed = True
                    raise OSError("test poll failure")
                return self._delegate.poll()

        def launch(*args, **kwargs):
            delegate = real_popen(*args, **kwargs)
            delegates.append(delegate)
            return PollFailingProcess(delegate)

        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "epiagentbench.pilot.subprocess.Popen",
                    side_effect=launch,
                ),
                self.assertRaisesRegex(
                    ProviderProcessIsolationError,
                    "process state could not be verified",
                ),
            ):
                _run_provider_process_group(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=5,
                    umask=0o077,
                )

        self.assertEqual(len(delegates), 1)
        self.assertIsNotNone(delegates[0].poll())

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_wait_failure_is_terminal(self):
        delegate: subprocess.Popen[bytes] | None = None
        real_popen = subprocess.Popen

        class WaitFailingProcess:
            def __init__(self, process):
                self._process = process

            def __getattr__(self, name):
                return getattr(self._process, name)

            def wait(self, *_args, **_kwargs):
                raise OSError("test wait failure")

        def launch(*args, **kwargs):
            nonlocal delegate
            delegate = real_popen(*args, **kwargs)
            return WaitFailingProcess(delegate)

        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "epiagentbench.pilot.subprocess.Popen",
                    side_effect=launch,
                ),
                self.assertRaisesRegex(
                    ProviderProcessIsolationError,
                    "leader state could not be verified",
                ),
            ):
                _run_provider_process_group(
                    [sys.executable, "-c", "pass"],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=5,
                    umask=0o077,
                )

        assert delegate is not None
        self.assertIsNotNone(delegate.poll())

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_process_group_setup_failure_still_reaps_spawn(self):
        spawned: list[subprocess.Popen[bytes]] = []
        real_popen = subprocess.Popen

        def launch(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            spawned.append(process)
            return process

        class FailingSelector:
            def register(self, *_args, **_kwargs):
                raise OSError("test selector exhaustion")

            def close(self):
                raise OSError("test selector cleanup failure")

        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "epiagentbench.pilot.subprocess.Popen",
                    side_effect=launch,
                ),
                patch(
                    "epiagentbench.pilot.selectors.DefaultSelector",
                    return_value=FailingSelector(),
                ),
                self.assertRaisesRegex(
                    ProviderProcessIsolationError,
                    "capture could not be initialized",
                ),
            ):
                _run_provider_process_group(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=5,
                    umask=0o077,
                )

        self.assertEqual(len(spawned), 1)
        self.assertIsNotNone(spawned[0].poll())

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_selector_cleanup_failure_is_typed_and_reaped(self):
        spawned: list[subprocess.Popen[bytes]] = []
        real_popen = subprocess.Popen
        delegate = selectors.DefaultSelector()

        def launch(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            spawned.append(process)
            return process

        class CloseFailingSelector:
            def __getattr__(self, name):
                return getattr(delegate, name)

            def close(self):
                delegate.close()
                raise OSError("test selector cleanup failure")

        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "epiagentbench.pilot.subprocess.Popen",
                    side_effect=launch,
                ),
                patch(
                    "epiagentbench.pilot.selectors.DefaultSelector",
                    return_value=CloseFailingSelector(),
                ),
                self.assertRaisesRegex(
                    ProviderProcessIsolationError,
                    "selector could not be closed",
                ),
            ):
                _run_provider_process_group(
                    [sys.executable, "-c", "pass"],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=5,
                    umask=0o077,
                )

        self.assertEqual(len(spawned), 1)
        self.assertIsNotNone(spawned[0].poll())

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_stream_cleanup_failure_is_typed_and_reaped(self):
        delegate: subprocess.Popen[bytes] | None = None
        real_popen = subprocess.Popen

        class CloseFailingStream:
            def __init__(self, stream):
                self._stream = stream

            def fileno(self):
                return self._stream.fileno()

            def close(self):
                self._stream.close()
                raise OSError("test stream cleanup failure")

        class WrappedProcess:
            def __init__(self, process):
                self._process = process
                self.stdout = CloseFailingStream(process.stdout)
                self.stderr = process.stderr

            def __getattr__(self, name):
                return getattr(self._process, name)

        def launch(*args, **kwargs):
            nonlocal delegate
            delegate = real_popen(*args, **kwargs)
            return WrappedProcess(delegate)

        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "epiagentbench.pilot.subprocess.Popen",
                    side_effect=launch,
                ),
                self.assertRaisesRegex(
                    ProviderProcessIsolationError,
                    "output stream could not be closed",
                ),
            ):
                _run_provider_process_group(
                    [sys.executable, "-c", "pass"],
                    cwd=Path(temp),
                    environment={"PATH": os.defpath},
                    timeout_seconds=5,
                    umask=0o077,
                )

        assert delegate is not None
        self.assertIsNotNone(delegate.poll())

    def test_provider_final_output_reader_accepts_only_stable_owner_file(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "final.json"
            output.write_bytes(b'{"safe":true}')
            output.chmod(0o600)

            self.assertEqual(
                _read_provider_final_output(output),
                b'{"safe":true}',
            )

    def test_provider_final_output_reader_rejects_symlink_without_reading_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            secret = root / "opaque-auth.json"
            secret.write_bytes(b"credential-must-not-be-read")
            secret.chmod(0o600)
            output = root / "final.json"
            output.symlink_to(secret)

            with self.assertRaises(ProviderStateIsolationError) as caught:
                _read_provider_final_output(output)

        self.assertNotIn(str(secret), str(caught.exception))
        self.assertNotIn("credential-must-not-be-read", str(caught.exception))

    def test_provider_final_output_reader_does_not_read_stable_oversize_file(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "final.json"
            output.write_bytes(b"x" * (_MAX_CAPTURE_BYTES + 1))
            output.chmod(0o600)
            with patch("epiagentbench.pilot.os.read") as read:
                final_output = _read_provider_final_output(output)
                self.assertIsNone(final_output)
            read.assert_not_called()
            submission, _, audit = parse_agent_output(
                "codex",
                requested_model="gpt-5.6-sol",
                stdout=json.dumps(
                    {"type": "result", "result": _submission()}
                ).encode(),
                final_output=final_output,
            )
            self.assertIsNone(submission)
            self.assertIn("agent_failure:invalid_submission", audit)

    def test_provider_final_output_reader_rejects_in_place_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "final.json"
            output.write_bytes(b"before-mutation")
            output.chmod(0o600)
            real_read = os.read
            changed = False

            def read_and_change(descriptor, size):
                nonlocal changed
                value = real_read(descriptor, size)
                if not changed:
                    changed = True
                    output.write_bytes(b"after--mutation")
                    output.chmod(0o600)
                return value

            with (
                patch(
                    "epiagentbench.pilot.os.read",
                    side_effect=read_and_change,
                ),
                self.assertRaisesRegex(
                    ProviderStateIsolationError,
                    "changed while being read",
                ),
            ):
                _read_provider_final_output(output)

    def test_provider_temporary_cleanup_failure_is_typed(self):
        class FailingTemporary:
            def __init__(self, name):
                self.name = name

            def cleanup(self):
                raise OSError("secret cleanup detail")

        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "epiagentbench.pilot.tempfile.TemporaryDirectory",
                    return_value=FailingTemporary(temp),
                ),
                self.assertRaises(ProviderStateIsolationError) as caught,
            ):
                with _ProviderTemporaryDirectory():
                    pass

        self.assertEqual(
            str(caught.exception),
            "Disposable provider state could not be removed",
        )
        self.assertNotIn("secret cleanup detail", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_provider_temporary_cleanup_requires_directory_absence(self):
        class IncompleteTemporary:
            def __init__(self, name):
                self.name = name

            def cleanup(self):
                return None

        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "epiagentbench.pilot.tempfile.TemporaryDirectory",
                    return_value=IncompleteTemporary(temp),
                ),
                self.assertRaisesRegex(
                    ProviderStateIsolationError,
                    "could not be removed",
                ),
            ):
                with _ProviderTemporaryDirectory():
                    pass

    def test_provider_temporary_cleanup_surfaces_leak_and_chains_terminal_incident(self):
        class FailingTemporary:
            def __init__(self, name):
                self.name = name

            def cleanup(self):
                raise OSError("secondary cleanup failure")

        terminal_errors = (
            CodexAuthenticationIncidentError("primary auth incident"),
            ProviderProcessIsolationError("primary process incident"),
        )
        with tempfile.TemporaryDirectory() as temp:
            for primary in terminal_errors:
                with (
                    self.subTest(error=type(primary).__name__),
                    patch(
                        "epiagentbench.pilot.tempfile.TemporaryDirectory",
                        return_value=FailingTemporary(temp),
                    ),
                    self.assertRaises(ProviderStateIsolationError) as caught,
                ):
                    with _ProviderTemporaryDirectory():
                        raise primary
                self.assertEqual(
                    str(caught.exception),
                    "Disposable provider state could not be removed",
                )
                self.assertIs(caught.exception.__cause__, primary)
                self.assertNotIn(
                    "secondary cleanup failure", str(caught.exception)
                )

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "killpg"),
        "provider process groups require POSIX",
    )
    def test_provider_process_group_detects_detached_pipe_holder(self):
        with tempfile.TemporaryDirectory() as temp:
            pid_path = Path(temp) / "detached.pid"
            script = (
                "import pathlib,subprocess,sys,time; "
                "child=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(60)'],start_new_session=True); "
                f"pathlib.Path({str(pid_path)!r}).write_text(str(child.pid)); "
                "time.sleep(60)"
            )
            started = time.monotonic()
            try:
                with self.assertRaisesRegex(
                    ProviderProcessIsolationError,
                    "output pipes remained open",
                ):
                    _run_provider_process_group(
                        [sys.executable, "-c", script],
                        cwd=Path(temp),
                        environment={"PATH": os.defpath},
                        timeout_seconds=1,
                        umask=0o077,
                    )
            finally:
                if pid_path.is_file():
                    child_pid = int(pid_path.read_text(encoding="utf-8"))
                    try:
                        os.killpg(child_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    deadline = time.monotonic() + 2.0
                    while time.monotonic() < deadline:
                        try:
                            os.kill(child_pid, 0)
                        except ProcessLookupError:
                            break
                        time.sleep(0.01)
            self.assertLess(time.monotonic() - started, 5.0)

    def test_codex_auth_attestation_failure_has_typed_generic_error(self):
        with tempfile.TemporaryDirectory() as temp:
            storage = Path(temp) / "stable-auth"
            storage.mkdir(mode=0o700)
            (storage / "auth.json").write_bytes(b"opaque-test-auth")
            (storage / "auth.json").chmod(0o600)
            with (
                patch("epiagentbench.pilot.shutil.which", return_value="/codex"),
                patch(
                    "epiagentbench.pilot._isolate_codex_environment",
                    side_effect=RuntimeError("secret-path-or-token"),
                ),
                patch("epiagentbench.pilot.subprocess.run") as run,
                self.assertRaises(CodexAuthenticationIncidentError) as caught,
            ):
                evaluate_local_cli_agent(
                    "codex",
                    seed=17,
                    codex_auth_storage_dir=storage,
                )

        run.assert_not_called()
        self.assertEqual(
            str(caught.exception),
            "Isolated Codex authentication state became ambiguous",
        )
        self.assertIsNone(caught.exception.__cause__)

    def test_isolation_error_survives_post_call_guards_and_session_close(self):
        class Session:
            def close(self):
                raise RuntimeError("secondary episode close failure")

        primary = ProviderProcessIsolationError(
            "Provider process group remained alive after termination"
        )
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            patch("epiagentbench.pilot.shutil.which", return_value="/cursor"),
            patch(
                "epiagentbench.pilot.subprocess.run",
            ) as run,
            patch(
                "epiagentbench.pilot._run_provider_process_group",
                side_effect=(
                    subprocess.CompletedProcess(
                        [], 0, stdout=b"cursor 1", stderr=b""
                    ),
                    subprocess.CompletedProcess(
                        [], 0, stdout=b"", stderr=b""
                    ),
                    primary,
                ),
            ),
            patch(
                "epiagentbench.pilot._snapshot_cursor_host_state",
                side_effect=("stable", "stable", "changed"),
            ),
            patch(
                "epiagentbench.pilot.launch_socket_episode",
                return_value=Session(),
            ),
            self.assertRaises(ProviderProcessIsolationError) as caught,
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )

        run.assert_not_called()
        self.assertIs(caught.exception, primary)

    def test_codex_environment_links_only_stable_auth_into_disposable_home(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            storage = base / "stable-auth"
            storage.mkdir(mode=0o700)
            target = storage / "auth.json"
            target.write_bytes(b"opaque-test-auth")
            target.chmod(0o600)
            root = base / "episode"
            root.mkdir(mode=0o700)
            environment = {
                "PATH": "/bin",
                "LANG": "C.UTF-8",
                "HOME": "/inherited/home",
                "CURSOR_API_KEY": "cursor-secret",
                "OPENAI_API_KEY": "openai-secret",
                "ANTHROPIC_BASE_URL": "https://routing.invalid",
                "CLAUDE_CONFIG_DIR": "/tmp/claude",
                "GLEAN_HELPER_OAUTH_CLIENT_ID": "glean-routing",
                "NODE_OPTIONS": "--require=/tmp/inject.js",
                "PYTHONHOME": "/tmp/python",
                "SSH_AUTH_SOCK": "/tmp/agent.sock",
            }
            link = _isolate_codex_environment(environment, root, storage)
            codex_home = Path(environment["CODEX_HOME"])
            self.assertTrue(codex_home.is_dir())
            self.assertFalse(codex_home.is_symlink())
            self.assertEqual(codex_home.stat().st_mode & 0o777, 0o700)
            self.assertEqual({entry.name for entry in os.scandir(codex_home)}, {"auth.json"})
            self.assertEqual(link, codex_home / "auth.json")
            self.assertTrue(link.is_symlink())
            self.assertEqual(os.readlink(link), str(target))
            self.assertEqual(link.resolve(), target)
            _attest_codex_auth_home_link(link, target)
            self.assertTrue(_attest_codex_auth_storage(storage))
            self.assertTrue(codex_home.is_relative_to(root))
            self.assertNotIn(str(storage), json.dumps(environment))
            for forbidden in (
                "CURSOR_API_KEY",
                "OPENAI_API_KEY",
                "ANTHROPIC_BASE_URL",
                "CLAUDE_CONFIG_DIR",
                "GLEAN_HELPER_OAUTH_CLIENT_ID",
                "NODE_OPTIONS",
                "PYTHONHOME",
                "SSH_AUTH_SOCK",
            ):
                self.assertNotIn(forbidden, environment)

    def test_codex_environment_rejects_unsafe_auth_metadata_without_path_leak(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            storage = base / "host-secret"
            storage.mkdir(mode=0o700)
            source = storage / "auth.json"
            source.write_bytes(b"opaque-test-auth")
            source.chmod(0o644)
            root = base / "episode"
            root.mkdir(mode=0o700)
            with self.assertRaises((RuntimeError, ValueError)) as caught:
                _isolate_codex_environment({"PATH": "/bin"}, root, storage)
            self.assertNotIn(str(source), str(caught.exception))
            self.assertNotIn("opaque-test-auth", str(caught.exception))

    def test_codex_auth_storage_rejects_unsafe_shapes_and_aliases(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()

            empty = base / "empty"
            empty.mkdir(mode=0o700)

            extra = base / "extra"
            extra.mkdir(mode=0o700)
            (extra / "auth.json").write_bytes(b"auth")
            (extra / "auth.json").chmod(0o600)
            (extra / "unexpected").write_bytes(b"side-state")

            external_symlink_target = base / "symlink-source"
            external_symlink_target.write_bytes(b"auth")
            external_symlink_target.chmod(0o600)
            symlink = base / "symlink"
            symlink.mkdir(mode=0o700)
            (symlink / "auth.json").symlink_to(external_symlink_target)

            external_hardlink_target = base / "hardlink-source"
            external_hardlink_target.write_bytes(b"auth")
            external_hardlink_target.chmod(0o600)
            hardlink = base / "hardlink"
            hardlink.mkdir(mode=0o700)
            os.link(external_hardlink_target, hardlink / "auth.json")

            zero_length = base / "zero-length"
            zero_length.mkdir(mode=0o700)
            (zero_length / "auth.json").write_bytes(b"")
            (zero_length / "auth.json").chmod(0o600)

            oversized = base / "oversized"
            oversized.mkdir(mode=0o700)
            (oversized / "auth.json").write_bytes(
                b"x" * (1024 * 1024 + 1)
            )
            (oversized / "auth.json").chmod(0o600)

            directory = base / "directory"
            directory.mkdir(mode=0o700)
            (directory / "auth.json").mkdir(mode=0o700)

            for storage in (
                empty,
                extra,
                symlink,
                hardlink,
                zero_length,
                oversized,
                directory,
            ):
                with (
                    self.subTest(storage=storage.name),
                    self.assertRaises(RuntimeError),
                ):
                    _attest_codex_auth_storage(storage)

            valid = base / "valid"
            valid.mkdir(mode=0o700)
            (valid / "auth.json").write_bytes(b"auth")
            (valid / "auth.json").chmod(0o600)
            alias = base / "alias"
            alias.symlink_to(valid, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Invalid Codex"):
                _canonical_codex_auth_storage_path(alias)

    def test_codex_auth_storage_persists_atomic_refresh_across_disposable_homes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            storage = base / "stable-auth"
            storage.mkdir(mode=0o700)
            target = storage / "auth.json"
            target.write_bytes(b"auth-generation-one")
            target.chmod(0o600)
            self.assertEqual(
                _canonical_codex_auth_storage_path(storage), storage
            )

            first_root = base / "first"
            first_root.mkdir(mode=0o700)
            first_link = _isolate_codex_environment(
                {"PATH": "/bin"}, first_root, storage
            )
            replacement = storage / "replacement"
            replacement.write_bytes(b"auth-generation-two")
            replacement.chmod(0o600)
            os.replace(replacement, target)
            self.assertTrue(_attest_codex_auth_storage(storage))
            _attest_codex_auth_home_link(first_link, target)
            self.assertEqual(first_link.read_bytes(), b"auth-generation-two")

            second_root = base / "second"
            second_root.mkdir(mode=0o700)
            second_link = _isolate_codex_environment(
                {"PATH": "/bin"}, second_root, storage
            )
            _attest_codex_auth_home_link(second_link, target)
            self.assertEqual(second_link.read_bytes(), b"auth-generation-two")

    def test_codex_auth_home_link_rejects_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            storage = base / "stable-auth"
            storage.mkdir(mode=0o700)
            target = storage / "auth.json"
            target.write_bytes(b"opaque-auth")
            target.chmod(0o600)
            root = base / "episode"
            root.mkdir(mode=0o700)
            link = _isolate_codex_environment(
                {"PATH": "/bin"}, root, storage
            )
            replacement = base / "replacement-auth.json"
            replacement.write_bytes(b"replacement")
            replacement.chmod(0o600)
            link.unlink()
            link.symlink_to(replacement)
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                _attest_codex_auth_home_link(link, target)

    def test_codex_version_and_paid_call_receive_only_isolated_environments(self):
        class Session:
            closed = False

            def score_with_replay_request_fits(self, *_args, **_kwargs):
                return True

            def score_with_replay(self, *_args, **_kwargs):
                return {
                    "scorecard": {
                        "valid": False,
                        "total": 0.0,
                        "dimensions": {},
                        "metrics": {},
                        "violations": ["invalid_submission"],
                    },
                    "replay_trace": {},
                }

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            storage = base / "stable-private"
            storage.mkdir(mode=0o700)
            target = storage / "auth.json"
            target.write_bytes(b"opaque-e2e-auth-secret")
            target.chmod(0o600)
            target_identity = (target.stat().st_dev, target.stat().st_ino)
            environments: list[dict[str, str]] = []
            auth_link_checks: list[tuple[bool, int, bytes]] = []
            disposable_side_state_seen: list[bool] = []

            def cli(command, **kwargs):
                environment = dict(
                    kwargs["env"]
                    if "env" in kwargs
                    else kwargs["environment"]
                )
                environments.append(environment)
                if command[-1] == "--version":
                    return subprocess.CompletedProcess(
                        command, 0, stdout=b"codex 1", stderr=b""
                    )
                auth_link = Path(environment["CODEX_HOME"]) / "auth.json"
                auth_link_checks.append(
                    (
                        auth_link.is_symlink(),
                        auth_link.stat().st_mode & 0o777,
                        auth_link.read_bytes(),
                    )
                )
                auth_link.write_bytes(b"refreshed-e2e-auth-secret")
                side_state = Path(environment["CODEX_HOME"]) / "session.json"
                side_state.write_text("{}", encoding="utf-8")
                disposable_side_state_seen.append(side_state.is_file())
                self.assertEqual(kwargs["umask"], 0o077)
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps(
                        {"type": "result", "result": _submission()}
                    ).encode(),
                    stderr=b"",
                )

            session = Session()
            toxic_environment = {
                "PATH": "/bin",
                "LANG": "C.UTF-8",
                "LC_INJECTION": "credential-routing",
                "HOME": "/inherited/home",
                "CURSOR_API_KEY": "cursor-secret",
                "OPENAI_API_KEY": "openai-secret",
                "ANTHROPIC_API_KEY": "anthropic-secret",
                "ANTHROPIC_BASE_URL": "https://routing.invalid",
                "CLAUDE_CONFIG_DIR": "/tmp/claude",
                "GLEAN_HELPER_OAUTH_CLIENT_ID": "glean-routing",
                "NODE_OPTIONS": "--require=/tmp/inject.js",
                "PYTHONPATH": "/tmp/python",
                "PYTHONHOME": "/tmp/python-home",
                "SSH_AUTH_SOCK": "/tmp/agent.sock",
                "DYLD_INSERT_LIBRARIES": "/tmp/inject.dylib",
                "LD_PRELOAD": "/tmp/inject.so",
            }
            with (
                patch.dict(os.environ, toxic_environment, clear=True),
                patch(
                    "epiagentbench.pilot.shutil.which",
                    return_value="/codex",
                ),
                patch(
                    "epiagentbench.pilot.subprocess.run"
                ) as run,
                patch(
                    "epiagentbench.pilot._run_provider_process_group",
                    side_effect=cli,
                ) as provider_run,
                patch(
                    "epiagentbench.pilot.launch_socket_episode",
                    return_value=session,
                ),
            ):
                result = evaluate_local_cli_agent(
                    "codex", seed=17, codex_auth_storage_dir=storage
                )

            run.assert_not_called()
            self.assertEqual(provider_run.call_count, 2)
            self.assertEqual(len(environments), 2)
            self.assertEqual(
                auth_link_checks,
                [(True, 0o600, b"opaque-e2e-auth-secret")],
            )
            self.assertEqual(target.read_bytes(), b"refreshed-e2e-auth-secret")
            self.assertEqual(
                (target.stat().st_dev, target.stat().st_ino), target_identity
            )
            self.assertEqual(disposable_side_state_seen, [True])
            self.assertEqual(
                {entry.name for entry in os.scandir(storage)}, {"auth.json"}
            )
            forbidden = {
                "CURSOR_API_KEY",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "ANTHROPIC_BASE_URL",
                "CLAUDE_CONFIG_DIR",
                "GLEAN_HELPER_OAUTH_CLIENT_ID",
                "NODE_OPTIONS",
                "PYTHONPATH",
                "PYTHONHOME",
                "SSH_AUTH_SOCK",
                "DYLD_INSERT_LIBRARIES",
                "LD_PRELOAD",
                "LC_INJECTION",
            }
            for environment in environments:
                self.assertTrue(forbidden.isdisjoint(environment))
                self.assertNotIn(str(storage), json.dumps(environment))
            self.assertNotIn("CODEX_HOME", environments[0])
            self.assertIn("CODEX_HOME", environments[1])
            self.assertFalse(Path(environments[1]["HOME"]).exists())
            encoded_result = json.dumps(asdict(result), default=list)
            self.assertNotIn(str(storage), encoded_result)
            self.assertNotIn("opaque-e2e-auth-secret", encoded_result)
            self.assertNotIn("refreshed-e2e-auth-secret", encoded_result)
            self.assertEqual(result.submission, {})
            self.assertIn(
                "agent_failure:invalid_submission", result.audit_events
            )
            self.assertTrue(session.closed)

    def test_codex_negative_returncode_is_terminal_auth_incident(self):
        class Session:
            closed = False

            def score_with_replay_request_fits(self, *_args, **_kwargs):
                raise AssertionError("signalled Codex call must not reach scoring")

            def score_with_replay(self, *_args, **_kwargs):
                raise AssertionError("signalled Codex call must not reach scoring")

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as temp:
            storage = Path(temp).resolve() / "stable-auth"
            storage.mkdir(mode=0o700)
            auth = storage / "auth.json"
            auth.write_bytes(b"opaque-test-auth")
            auth.chmod(0o600)
            session = Session()
            with (
                patch("epiagentbench.pilot.shutil.which", return_value="/codex"),
                patch(
                    "epiagentbench.pilot.subprocess.run",
                ) as run,
                patch(
                    "epiagentbench.pilot._run_provider_process_group",
                    side_effect=(
                        subprocess.CompletedProcess(
                            [], 0, stdout=b"", stderr=b"codex 1"
                        ),
                        subprocess.CompletedProcess(
                            [], -signal.SIGKILL, stdout=b"", stderr=b""
                        ),
                    ),
                ) as provider_run,
                patch(
                    "epiagentbench.pilot.launch_socket_episode",
                    return_value=session,
                ),
                self.assertRaises(CodexAuthenticationIncidentError) as caught,
            ):
                evaluate_local_cli_agent(
                    "codex",
                    seed=17,
                    codex_auth_storage_dir=storage,
                )

        run.assert_not_called()
        self.assertEqual(provider_run.call_count, 2)
        self.assertEqual(
            str(caught.exception),
            "Isolated Codex authentication state became ambiguous",
        )
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(session.closed)

    def test_codex_requires_explicit_auth_storage_before_cli_lookup(self):
        with (
            patch("epiagentbench.pilot.shutil.which") as which,
            self.assertRaisesRegex(RuntimeError, "explicit stable auth storage"),
        ):
            evaluate_local_cli_agent("codex", seed=17)
        which.assert_not_called()

    def test_codex_auth_storage_argument_is_rejected_for_non_codex(self):
        with (
            patch("epiagentbench.pilot.shutil.which") as which,
            self.assertRaisesRegex(ValueError, "only valid for the Codex"),
        ):
            evaluate_local_cli_agent(
                "claude",
                seed=17,
                codex_auth_storage_dir="/explicit/codex-auth",
            )
        which.assert_not_called()

    def test_claude_disposable_home_link_is_attested_and_cleaned_up(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            secure = base / "persistent-auth"
            secure.mkdir(mode=0o700)
            with tempfile.TemporaryDirectory(dir=base) as disposable:
                root = Path(disposable)
                environment = {"PATH": "/bin"}
                link = _isolate_claude_environment(
                    environment, root, secure, "expected-client-id"
                )
                assert link is not None
                _attest_managed_glean_home_link(link, secure)
                self.assertTrue(link.is_symlink())
            self.assertFalse(link.exists())
            self.assertFalse(link.is_symlink())
            self.assertTrue(secure.is_dir())

    def test_claude_disposable_home_link_rejects_target_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            secure = root / "persistent-auth"
            replacement = root / "replacement-auth"
            secure.mkdir(mode=0o700)
            replacement.mkdir(mode=0o700)
            environment = {"PATH": "/bin"}
            link = _isolate_claude_environment(environment, root, secure)
            assert link is not None
            link.unlink()
            link.symlink_to(replacement, target_is_directory=True)
            with self.assertRaisesRegex(
                ProviderStateIsolationError, "identity changed"
            ):
                _attest_managed_glean_home_link(link, secure)

    def test_claude_without_explicit_secure_storage_remains_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            environment = {
                "PATH": "/bin",
                "CLAUDE_SECURESTORAGE_CONFIG_DIR": "/inherited/secure",
            }
            _isolate_claude_environment(environment, Path(temp))
            self.assertNotIn("CLAUDE_SECURESTORAGE_CONFIG_DIR", environment)

    def test_claude_plaintext_secure_storage_fallback_is_rejected_without_leak(self):
        with tempfile.TemporaryDirectory() as temp:
            secure = Path(temp) / "secret-host-path"
            secure.mkdir()
            (secure / ".credentials.json").write_text(
                '{"token":"must-not-leak"}', encoding="utf-8"
            )
            with self.assertRaises(ProviderStateIsolationError) as caught:
                _reject_claude_plaintext_fallback(secure)
            diagnostic = str(caught.exception)
            self.assertNotIn(str(secure), diagnostic)
            self.assertNotIn("must-not-leak", diagnostic)

    def test_claude_secure_storage_path_is_redacted_from_diagnostics(self):
        secure = Path.home() / ".stable-claude-secure-storage"
        diagnostic = _diagnostic(
            b"",
            f"credential error at {secure}/.credentials.json".encode(),
            temporary_root="/tmp/disposable-pilot",
            returncode=1,
            redacted_paths=(str(secure),),
        )
        self.assertNotIn(str(secure), diagnostic)
        self.assertNotIn("~/.stable-claude-secure-storage", diagnostic)
        self.assertIn("<secure-storage>/.credentials.json", diagnostic)

    def test_claude_glean_auth_diagnostics_are_fully_generic(self):
        sensitive = (
            b"https://issuer.invalid/oauth?state=private-state "
            b"access_token=private-access refresh_token=private-refresh"
        )
        diagnostic = _diagnostic(
            b"",
            sensitive,
            temporary_root="/private/tmp/episode",
            returncode=1,
            redacted_paths=("/private/auth-home",),
            redact_provider_auth=True,
        )
        self.assertEqual(
            diagnostic, "Claude/Glean provider diagnostic redacted"
        )
        self.assertNotIn("issuer.invalid", diagnostic)
        self.assertNotIn("private-state", diagnostic)
        self.assertNotIn("private-access", diagnostic)
        self.assertNotIn("private-refresh", diagnostic)

    def test_claude_command_exposes_no_persistent_auth_inputs(self):
        command = self._command("claude")
        encoded = json.dumps(command)
        self.assertNotIn("/private/persistent-auth", encoded)
        self.assertNotIn("private-client-id", encoded)
        allowed = command[command.index("--allowedTools") + 1]
        self.assertNotIn("Read", allowed)
        self.assertNotIn("Bash", allowed)
        self.assertNotIn("Shell", allowed)

    def test_claude_keychain_service_uses_resolved_path_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            secure = Path(temp).resolve() / "secure-storage"
            secure.mkdir()
            resolved = secure.resolve()
            suffix = hashlib.sha256(
                str(resolved).encode("utf-8")
            ).hexdigest()[:8]
            self.assertEqual(
                _claude_secure_storage_keychain_service(secure),
                f"Claude Code-credentials-{suffix}",
            )

    def test_claude_keychain_service_rejects_symlink_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            secure = root / "secure-storage"
            secure.mkdir()
            alias = root / "secure-alias"
            alias.symlink_to(secure, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Invalid Claude"):
                _claude_secure_storage_keychain_service(alias)

    def test_claude_keychain_service_normalizes_unicode_to_nfc(self):
        decomposed = Path("/tmp/epiagentbench-e\u0301")
        normalized = "/tmp/epiagentbench-\u00e9"
        suffix = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
        with patch(
            "epiagentbench.pilot._canonical_claude_secure_storage_path",
            return_value=decomposed,
        ):
            service = _claude_secure_storage_keychain_service(decomposed)
        self.assertEqual(service, f"Claude Code-credentials-{suffix}")

    def test_claude_keychain_attestation_reports_present_or_absent_metadata_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            secure = root / "secure-storage"
            secure.mkdir()
            security = root / "security"
            security.write_text("test executable", encoding="utf-8")
            security.chmod(0o700)
            service = _claude_secure_storage_keychain_service(secure)

            for returncode, expected in ((0, True), (44, False)):
                with (
                    self.subTest(returncode=returncode),
                    patch("epiagentbench.pilot.sys.platform", "darwin"),
                    patch.dict(os.environ, {"USER": "ambient-attacker"}),
                    patch(
                        "epiagentbench.pilot.pwd.getpwuid",
                        return_value=SimpleNamespace(
                            pw_name="pilot-account"
                        ),
                    ) as getpwuid,
                    patch(
                        "epiagentbench.pilot.subprocess.run",
                        return_value=subprocess.CompletedProcess(
                            [], returncode
                        ),
                    ) as run,
                ):
                    present = _attest_claude_secure_storage_keychain(
                        secure,
                        security_executable=security,
                    )
                self.assertIs(present, expected)
                getpwuid.assert_called_once_with(os.getuid())
                command = run.call_args.args[0]
                self.assertEqual(
                    command,
                    [
                        str(security.resolve()),
                        "find-generic-password",
                        "-s",
                        service,
                        "-a",
                        "pilot-account",
                    ],
                )
                self.assertNotIn("-w", command)
                self.assertNotIn("-g", command)
                self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
                self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
                self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)
                self.assertFalse(run.call_args.kwargs["check"])

    def test_claude_keychain_attestation_fails_closed_without_path_or_password(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            secure = root / "secret-secure-storage"
            secure.mkdir()
            security = root / "security"
            security.write_text("test executable", encoding="utf-8")
            security.chmod(0o700)

            failures = (
                subprocess.CompletedProcess([], 45),
                OSError(f"{secure}: password=must-not-leak"),
            )
            for failure in failures:
                outcome = (
                    {"return_value": failure}
                    if isinstance(failure, subprocess.CompletedProcess)
                    else {"side_effect": failure}
                )
                with (
                    self.subTest(failure=type(failure).__name__),
                    patch("epiagentbench.pilot.sys.platform", "darwin"),
                    patch.dict(os.environ, {"USER": "ambient-attacker"}),
                    patch(
                        "epiagentbench.pilot.pwd.getpwuid",
                        return_value=SimpleNamespace(
                            pw_name="pilot-account"
                        ),
                    ),
                    patch("epiagentbench.pilot.subprocess.run", **outcome),
                    self.assertRaises(RuntimeError) as caught,
                ):
                    _attest_claude_secure_storage_keychain(
                        secure,
                        security_executable=security,
                    )
                diagnostic = str(caught.exception)
                self.assertNotIn(str(secure), diagnostic)
                self.assertNotIn("must-not-leak", diagnostic)
                self.assertIsNone(caught.exception.__cause__)

    def test_claude_keychain_attestation_requires_darwin_and_safe_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            secure = root / "secret-secure-storage"
            secure.mkdir()
            unsafe_security = root / "security"
            unsafe_security.write_text("not executable", encoding="utf-8")
            unsafe_security.chmod(0o600)

            with (
                patch("epiagentbench.pilot.sys.platform", "linux"),
                patch("epiagentbench.pilot.subprocess.run") as run,
                self.assertRaises(RuntimeError) as caught,
            ):
                _attest_claude_secure_storage_keychain(secure)
            run.assert_not_called()
            self.assertNotIn(str(secure), str(caught.exception))

            with (
                patch("epiagentbench.pilot.sys.platform", "darwin"),
                patch.dict(os.environ, {"USER": "ambient-attacker"}),
                patch(
                    "epiagentbench.pilot.pwd.getpwuid",
                    return_value=SimpleNamespace(pw_name="pilot-account"),
                ),
                patch("epiagentbench.pilot.subprocess.run") as run,
                self.assertRaises(RuntimeError) as caught,
            ):
                _attest_claude_secure_storage_keychain(
                    secure,
                    security_executable=unsafe_security,
                )
            run.assert_not_called()
            self.assertNotIn(str(unsafe_security), str(caught.exception))

    def test_claude_keychain_attestation_never_falls_back_to_ambient_user(self):
        with (
            patch("epiagentbench.pilot.sys.platform", "darwin"),
            patch.dict(os.environ, {"USER": "ambient-attacker"}),
            patch(
                "epiagentbench.pilot.pwd.getpwuid",
                side_effect=KeyError("missing account"),
            ),
            patch("epiagentbench.pilot.subprocess.run") as run,
            self.assertRaisesRegex(RuntimeError, "account is unavailable"),
        ):
            _attest_claude_secure_storage_keychain("/unused")
        run.assert_not_called()

    def test_claude_readiness_plaintext_fallback_stops_before_episode(self):
        with tempfile.TemporaryDirectory() as temp:
            secure = Path(temp).resolve() / "secure-storage"
            secure.mkdir()

            def readiness(command, **kwargs):
                self.assertEqual(kwargs["umask"], 0o077)
                (secure / ".credentials.json").write_text(
                    '{"token":"test-only"}', encoding="utf-8"
                )
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"claude 1", stderr=b""
                )

            with (
                patch("epiagentbench.pilot.shutil.which", return_value="/claude"),
                patch("epiagentbench.pilot.subprocess.run") as run,
                patch(
                    "epiagentbench.pilot._run_provider_process_group",
                    side_effect=readiness,
                ),
                patch("epiagentbench.pilot.launch_socket_episode") as launch,
                self.assertRaises(ProviderStateIsolationError) as caught,
            ):
                evaluate_local_cli_agent(
                    "claude",
                    seed=17,
                    claude_secure_storage_dir=secure,
                )
            run.assert_not_called()
            launch.assert_not_called()
            self.assertEqual(
                str(caught.exception),
                "Claude credential persistence isolation failed",
            )
            self.assertNotIn("test-only", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)

    def test_claude_agent_plaintext_fallback_closes_episode(self):
        class Session:
            closed = False

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as temp:
            secure = Path(temp).resolve() / "secure-storage"
            secure.mkdir()
            call_count = 0

            def cli(command, **kwargs):
                nonlocal call_count
                call_count += 1
                self.assertEqual(kwargs["umask"], 0o077)
                if call_count == 1:
                    return subprocess.CompletedProcess(
                        command, 0, stdout=b"claude 1", stderr=b""
                    )
                (secure / ".credentials.json").write_text(
                    '{"token":"test-only"}', encoding="utf-8"
                )
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"", stderr=b""
                )

            session = Session()
            with (
                patch("epiagentbench.pilot.shutil.which", return_value="/claude"),
                patch("epiagentbench.pilot.subprocess.run") as run,
                patch(
                    "epiagentbench.pilot._run_provider_process_group",
                    side_effect=cli,
                ),
                patch(
                    "epiagentbench.pilot.launch_socket_episode",
                    return_value=session,
                ),
                self.assertRaises(ProviderStateIsolationError) as caught,
            ):
                evaluate_local_cli_agent(
                    "claude",
                    seed=17,
                    claude_secure_storage_dir=secure,
                )
            run.assert_not_called()
            self.assertEqual(call_count, 2)
            self.assertTrue(session.closed)
            self.assertEqual(
                str(caught.exception),
                "Claude credential persistence isolation failed",
            )
            self.assertNotIn("test-only", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)

    def test_claude_agent_managed_glean_link_drift_is_terminal(self):
        class Session:
            closed = False

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            secure = root / "secure-storage"
            replacement = root / "replacement-storage"
            secure.mkdir()
            replacement.mkdir()
            call_count = 0

            def cli(command, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    home_link = (
                        Path(kwargs["environment"]["HOME"])
                        / ".glean-llm-gateway"
                    )
                    home_link.unlink()
                    home_link.symlink_to(
                        replacement, target_is_directory=True
                    )
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=b"claude 1" if call_count == 1 else b"",
                    stderr=b"",
                )

            session = Session()
            with (
                patch("epiagentbench.pilot.shutil.which", return_value="/claude"),
                patch("epiagentbench.pilot.subprocess.run") as run,
                patch(
                    "epiagentbench.pilot._run_provider_process_group",
                    side_effect=cli,
                ),
                patch(
                    "epiagentbench.pilot.launch_socket_episode",
                    return_value=session,
                ),
                self.assertRaises(ProviderStateIsolationError) as caught,
            ):
                evaluate_local_cli_agent(
                    "claude",
                    seed=17,
                    claude_secure_storage_dir=secure,
                )

            run.assert_not_called()
            self.assertEqual(call_count, 2)
            self.assertTrue(session.closed)
            self.assertEqual(
                str(caught.exception),
                "Claude credential persistence isolation failed",
            )
            self.assertNotIn(str(secure), str(caught.exception))
            self.assertNotIn(str(replacement), str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)

    def test_claude_credential_guard_does_not_mask_process_incident(self):
        class Session:
            def close(self):
                raise RuntimeError("secondary episode cleanup failure")

        primary = ProviderProcessIsolationError(
            "Provider process group remained alive after termination"
        )
        secondary = ProviderStateIsolationError(
            "Claude credential persistence isolation failed"
        )
        with (
            patch("epiagentbench.pilot.shutil.which", return_value="/claude"),
            patch("epiagentbench.pilot.subprocess.run") as run,
            patch(
                "epiagentbench.pilot._run_provider_process_group",
                side_effect=(
                    subprocess.CompletedProcess(
                        [], 0, stdout=b"claude 1", stderr=b""
                    ),
                    primary,
                ),
            ),
            patch(
                "epiagentbench.pilot."
                "_attest_runtime_claude_credential_state",
                side_effect=(None, None, None, None, secondary),
            ),
            patch(
                "epiagentbench.pilot.launch_socket_episode",
                return_value=Session(),
            ),
            self.assertRaises(ProviderProcessIsolationError) as caught,
        ):
            evaluate_local_cli_agent("claude", seed=17)

        run.assert_not_called()
        self.assertIs(caught.exception, primary)

    def test_claude_secure_storage_argument_is_rejected_for_non_claude(self):
        with (
            patch("epiagentbench.pilot.shutil.which") as which,
            self.assertRaisesRegex(ValueError, "only valid for the Claude"),
        ):
            evaluate_local_cli_agent(
                "codex",
                seed=17,
                claude_secure_storage_dir="/explicit/secure-storage",
            )
        which.assert_not_called()

    def test_claude_secure_storage_symlink_is_rejected_before_cli_lookup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            secure = root / "secure-storage"
            secure.mkdir()
            alias = root / "secure-alias"
            alias.symlink_to(secure, target_is_directory=True)
            with (
                patch("epiagentbench.pilot.shutil.which") as which,
                self.assertRaisesRegex(ValueError, "Invalid Claude"),
            ):
                evaluate_local_cli_agent(
                    "claude",
                    seed=17,
                    claude_secure_storage_dir=alias,
                )
            which.assert_not_called()

    def test_cursor_environment_uses_only_disposable_storage_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            environment = {
                "HOME": "/inherited/home",
                "CURSOR_DATA_DIR": "/inherited/cursor",
                "CURSOR_CONFIG_DIR": "/inherited/cursor-config",
                "CURSOR_PROJECTS_DIR": "/inherited/projects",
                "CURSOR_EXEC_DAEMON_DATA_DIR": "/inherited/daemon",
                "CURSOR_WORKTREES_ROOT": "/inherited/worktrees",
                "CURSOR_API_URL": "https://attacker.invalid",
                "CURSOR_API_KEY": "test-only",
                "AGENT_CLI_CREDENTIAL_STORE": "file",
                "XDG_CONFIG_HOME": "/inherited/config",
                "XDG_CACHE_HOME": "/inherited/cache",
                "XDG_DATA_HOME": "/inherited/data",
                "XDG_STATE_HOME": "/inherited/state",
                "XDG_RUNTIME_DIR": "/inherited/runtime",
                "TMPDIR": "/inherited/tmp",
                "NODE_COMPILE_CACHE": "/inherited/node-cache",
                "NODE_OPTIONS": "--require=/inherited/inject.js",
                "SSH_AUTH_SOCK": "/inherited/agent.sock",
                "PATH": "/bin",
                "HTTPS_PROXY": "https://proxy.invalid",
                "SSL_CERT_FILE": "/etc/ssl/cert.pem",
                "LC_ALL": "C.UTF-8",
                "LC_INJECTION": "credential-routing",
            }
            _isolate_cursor_environment(environment, root)
            self.assertEqual(environment["PATH"], "/bin")
            self.assertEqual(environment["CURSOR_API_KEY"], "test-only")
            self.assertEqual(environment["AGENT_CLI_CREDENTIAL_STORE"], "memory")
            self.assertEqual(environment["HTTPS_PROXY"], "https://proxy.invalid")
            self.assertEqual(environment["SSL_CERT_FILE"], "/etc/ssl/cert.pem")
            self.assertEqual(environment["LC_ALL"], "C.UTF-8")
            self.assertNotIn("CURSOR_API_URL", environment)
            self.assertNotIn("NODE_OPTIONS", environment)
            self.assertNotIn("SSH_AUTH_SOCK", environment)
            self.assertNotIn("LC_INJECTION", environment)
            for name in (
                "HOME",
                "CURSOR_DATA_DIR",
                "CURSOR_CONFIG_DIR",
                "CURSOR_PROJECTS_DIR",
                "CURSOR_EXEC_DAEMON_DATA_DIR",
                "CURSOR_WORKTREES_ROOT",
                "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME",
                "XDG_DATA_HOME",
                "XDG_STATE_HOME",
                "XDG_RUNTIME_DIR",
                "TMPDIR",
                "TMP",
                "TEMP",
                "NODE_COMPILE_CACHE",
            ):
                path = Path(environment[name])
                self.assertTrue(path.is_dir())
                self.assertTrue(path.is_relative_to(root))
                self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_cursor_provider_credential_echo_is_terminal_and_secret_free(self):
        class Session:
            closed = False

            def score_with_replay_request_fits(self, *_args, **_kwargs):
                raise AssertionError("credential echo must not reach scoring")

            def score_with_replay(self, *_args, **_kwargs):
                raise AssertionError("credential echo must not reach scoring")

            def close(self):
                self.closed = True

        secret = "cursor-secret-must-not-persist"
        completed = [
            subprocess.CompletedProcess([], 0, stdout=b"cursor 1", stderr=b""),
            subprocess.CompletedProcess([], 0, stdout=b"", stderr=b""),
            subprocess.CompletedProcess(
                [],
                7,
                stdout=json.dumps(
                    {
                        "type": "result",
                        "result": f"Authorization: Bearer {secret}",
                    }
                ).encode(),
                stderr=f"Authorization: Bearer {secret}".encode(),
            ),
        ]
        session = Session()
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": secret}, clear=True),
            patch("epiagentbench.pilot.shutil.which", return_value="/cursor"),
            patch("epiagentbench.pilot.subprocess.run") as run,
            patch(
                "epiagentbench.pilot._run_provider_process_group",
                side_effect=completed,
            ) as provider_run,
            patch(
                "epiagentbench.pilot._snapshot_cursor_host_state",
                side_effect=("stable", "stable", "stable"),
            ),
            patch(
                "epiagentbench.pilot.launch_socket_episode",
                return_value=session,
            ),
            self.assertRaises(ProviderStateIsolationError) as caught,
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )

        run.assert_not_called()
        self.assertEqual(
            provider_run.call_args_list[2].kwargs["forbidden_exact_bytes"],
            (secret.encode(),),
        )
        self.assertEqual(
            str(caught.exception), "Provider credential isolation failed"
        )
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn("Authorization", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(session.closed)

    def test_cursor_mcp_readiness_credential_echo_is_terminal(self):
        secret = "cursor-readiness-secret"
        completed = (
            subprocess.CompletedProcess(
                [], 0, stdout=b"cursor 1", stderr=b""
            ),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=f"Authorization: Bearer {secret}".encode(),
                stderr=b"",
            ),
        )
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": secret}, clear=True),
            patch("epiagentbench.pilot.shutil.which", return_value="/cursor"),
            patch("epiagentbench.pilot.subprocess.run") as run,
            patch(
                "epiagentbench.pilot._run_provider_process_group",
                side_effect=completed,
            ) as provider_run,
            patch(
                "epiagentbench.pilot._snapshot_cursor_host_state",
                side_effect=("stable", "stable"),
            ),
            patch("epiagentbench.pilot.launch_socket_episode") as launch,
            self.assertRaises(ProviderStateIsolationError) as caught,
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )

        run.assert_not_called()
        self.assertEqual(provider_run.call_count, 2)
        launch.assert_not_called()
        self.assertEqual(
            str(caught.exception), "Provider credential isolation failed"
        )
        self.assertNotIn(secret, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_cursor_invalid_final_file_credential_echo_is_terminal(self):
        class Session:
            closed = False

            def score_with_replay_request_fits(self, *_args, **_kwargs):
                raise AssertionError("credential echo must not reach scoring")

            def score_with_replay(self, *_args, **_kwargs):
                raise AssertionError("credential echo must not reach scoring")

            def close(self):
                self.closed = True

        secret = "cursor-invalid-final-secret"
        call_count = 0

        def cli(command, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"cursor 1", stderr=b""
                )
            if call_count == 2:
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"", stderr=b""
                )
            final_path = Path(kwargs["cwd"]) / "final.json"
            final_path.write_bytes(f"not-json:{secret}".encode())
            final_path.chmod(0o600)
            return subprocess.CompletedProcess(
                command, 0, stdout=b"", stderr=b""
            )

        session = Session()
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": secret}, clear=True),
            patch("epiagentbench.pilot.shutil.which", return_value="/cursor"),
            patch("epiagentbench.pilot.subprocess.run") as run,
            patch(
                "epiagentbench.pilot._run_provider_process_group",
                side_effect=cli,
            ),
            patch(
                "epiagentbench.pilot._snapshot_cursor_host_state",
                side_effect=("stable", "stable", "stable"),
            ),
            patch(
                "epiagentbench.pilot.launch_socket_episode",
                return_value=session,
            ),
            self.assertRaises(ProviderStateIsolationError) as caught,
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )

        run.assert_not_called()
        self.assertEqual(call_count, 3)
        self.assertEqual(
            str(caught.exception), "Provider credential isolation failed"
        )
        self.assertNotIn(secret, str(caught.exception))
        self.assertTrue(session.closed)

    def test_cursor_host_chat_metadata_detection_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            chats = Path(temp) / "chats"
            before = _snapshot_cursor_host_chat_metadata(chats)
            self.assertEqual(before, "absent")
            self.assertEqual(_cursor_host_persistence_audit(before, before), ())

            chats.mkdir()
            (chats / "session.json").write_text("{}", encoding="utf-8")
            after = _snapshot_cursor_host_chat_metadata(chats)
            expected = ("infrastructure_failure:cursor_host_state_changed",)
            self.assertEqual(
                _cursor_host_persistence_audit(before, after), expected
            )
            unverifiable = (
                "infrastructure_failure:cursor_host_state_unverifiable",
            )
            self.assertEqual(
                _cursor_host_persistence_audit(None, after), unverifiable
            )
            self.assertEqual(
                _cursor_host_persistence_audit(after, None), unverifiable
            )

    def test_cursor_host_state_covers_known_non_chat_persistence_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            cursor = home / ".cursor"
            for directory in ("chats", "projects", "ai-tracking"):
                (cursor / directory).mkdir(parents=True, exist_ok=True)
            (cursor / "agent-cli-state.json").write_text("{}")
            (cursor / "cli-config.json").write_text("{}")
            with patch("epiagentbench.pilot.Path.home", return_value=home):
                before = _snapshot_cursor_host_state()
                (cursor / "projects" / "persisted.json").write_text("{}")
                after = _snapshot_cursor_host_state()
            self.assertIsNotNone(before)
            self.assertIsNotNone(after)
            self.assertNotEqual(before, after)

    def test_cursor_host_change_raises_infrastructure_guard(self):
        class Session:
            closed = False

            def score_request_fits(self, *args, **kwargs):
                raise AssertionError("isolation failure must not reach scoring")

            def score(self, submission, *, audit_events, agent_artifacts):
                raise AssertionError("isolation failure must not reach scoring")

            def close(self):
                self.closed = True

        stream = b"\n".join(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "model": "GLM 5.2 High",
                    }
                ).encode(),
                json.dumps({"type": "result", "result": _submission()}).encode(),
            ]
        )
        completed = [
            subprocess.CompletedProcess([], 0, stdout=b"cursor 1", stderr=b""),
            subprocess.CompletedProcess([], 0, stdout=b"", stderr=b""),
            subprocess.CompletedProcess([], 0, stdout=stream, stderr=b""),
        ]
        session = Session()
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            patch("epiagentbench.pilot.shutil.which", return_value="/cursor"),
            patch("epiagentbench.pilot.launch_socket_episode", return_value=session),
            patch("epiagentbench.pilot.subprocess.run") as run,
            patch(
                "epiagentbench.pilot._run_provider_process_group",
                side_effect=completed,
            ) as provider_run,
            patch(
                "epiagentbench.pilot._snapshot_cursor_host_state",
                side_effect=("stable", "stable", "changed"),
            ),
            self.assertRaisesRegex(RuntimeError, "cursor_host_state_changed"),
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )
        run.assert_not_called()
        self.assertEqual(provider_run.call_count, 3)
        self.assertTrue(session.closed)

    def test_cursor_unverifiable_initial_snapshot_stops_before_subprocess(self):
        class Session:
            def close(self):
                return None

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            patch("epiagentbench.pilot.shutil.which", return_value="/cursor"),
            patch("epiagentbench.pilot.launch_socket_episode", return_value=Session()) as launch,
            patch("epiagentbench.pilot.subprocess.run") as run,
            patch(
                "epiagentbench.pilot._snapshot_cursor_host_state",
                return_value=None,
            ),
            self.assertRaisesRegex(RuntimeError, "could not verify host chat"),
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )
        run.assert_not_called()
        launch.assert_not_called()

    def test_provider_version_output_overflow_is_terminal(self):
        overflow = ProviderOutputOverflowError(
            returncode=0,
            stdout=b"x" * _MAX_CAPTURE_BYTES,
            stderr=b"",
        )
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            patch("epiagentbench.pilot.shutil.which", return_value="/cursor"),
            patch("epiagentbench.pilot.subprocess.run") as run,
            patch(
                "epiagentbench.pilot._run_provider_process_group",
                side_effect=overflow,
            ) as provider_run,
            patch(
                "epiagentbench.pilot._snapshot_cursor_host_state",
                side_effect=("stable", "stable"),
            ),
            patch("epiagentbench.pilot.launch_socket_episode") as launch,
            self.assertRaisesRegex(
                ProviderStateIsolationError,
                "version preflight exceeded",
            ),
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )

        run.assert_not_called()
        provider_run.assert_called_once()
        launch.assert_not_called()

    def test_cursor_mcp_output_overflow_is_terminal_without_paid_fallback(self):
        overflow = ProviderOutputOverflowError(
            returncode=0,
            stdout=b"x" * _MAX_CAPTURE_BYTES,
            stderr=b"",
        )
        secret = "cursor-readiness-key"
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": secret}, clear=True),
            patch("epiagentbench.pilot.shutil.which", return_value="/cursor"),
            patch(
                "epiagentbench.pilot._run_provider_process_group",
                side_effect=(
                    subprocess.CompletedProcess(
                        [], 0, stdout=b"cursor 1", stderr=b""
                    ),
                    overflow,
                ),
            ) as provider_run,
            patch(
                "epiagentbench.pilot._snapshot_cursor_host_state",
                side_effect=("stable", "stable"),
            ),
            patch("epiagentbench.pilot.launch_socket_episode") as launch,
            self.assertRaises(ProviderStateIsolationError) as caught,
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )

        self.assertEqual(provider_run.call_count, 2)
        self.assertEqual(
            provider_run.call_args_list[1].kwargs["forbidden_exact_bytes"],
            (secret.encode(),),
        )
        launch.assert_not_called()
        self.assertEqual(
            str(caught.exception),
            "Cursor MCP readiness output exceeded its capture limit",
        )
        self.assertNotIn(secret, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_cursor_mcp_enable_failure_stops_before_paid_agent(self):
        class Session:
            def close(self):
                return None

        completed = [
            subprocess.CompletedProcess([], 0, stdout=b"cursor 1", stderr=b""),
            subprocess.CompletedProcess([], 2, stdout=b"", stderr=b"failed"),
        ]
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            patch("epiagentbench.pilot.shutil.which", return_value="/cursor"),
            patch("epiagentbench.pilot.launch_socket_episode", return_value=Session()) as launch,
            patch("epiagentbench.pilot.subprocess.run") as run,
            patch(
                "epiagentbench.pilot._run_provider_process_group",
                side_effect=completed,
            ) as provider_run,
            patch(
                "epiagentbench.pilot._snapshot_cursor_host_state",
                side_effect=("stable", "stable"),
            ),
            self.assertRaisesRegex(RuntimeError, "MCP enablement failed"),
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )
        run.assert_not_called()
        self.assertEqual(provider_run.call_count, 2)
        launch.assert_not_called()

    def test_cursor_mcp_enable_exception_stops_before_paid_agent(self):
        class Session:
            def close(self):
                return None

        error = subprocess.TimeoutExpired(["cursor", "mcp", "enable"], 30)
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            patch("epiagentbench.pilot.shutil.which", return_value="/cursor"),
            patch("epiagentbench.pilot.launch_socket_episode", return_value=Session()) as launch,
            patch("epiagentbench.pilot.subprocess.run") as run,
            patch(
                "epiagentbench.pilot._run_provider_process_group",
                side_effect=(
                    subprocess.CompletedProcess(
                        [], 0, stdout=b"cursor 1", stderr=b""
                    ),
                    error,
                ),
            ) as provider_run,
            patch(
                "epiagentbench.pilot._snapshot_cursor_host_state",
                side_effect=("stable", "stable"),
            ),
            self.assertRaises(subprocess.TimeoutExpired),
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )
        run.assert_not_called()
        self.assertEqual(provider_run.call_count, 2)
        launch.assert_not_called()

    def test_cursor_assignment_requires_explicit_api_key_before_launch(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("epiagentbench.pilot.launch_socket_episode") as launch,
            self.assertRaisesRegex(RuntimeError, "requires CURSOR_API_KEY"),
        ):
            evaluate_local_cli_agent(
                "cursor",
                seed=17,
                family="reporting_artifact",
                backend="starsim-ltc-v3",
            )
        launch.assert_not_called()

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

    def test_paired_run_threads_system_specific_auth_and_effort(self):
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
                codex_auth_storage_dir="/stable/codex-auth",
            )
        self.assertEqual(results, (sentinel, sentinel, sentinel))
        calls = evaluate.call_args_list
        self.assertIsNone(calls[0].kwargs["claude_effort"])
        self.assertEqual(calls[1].kwargs["claude_effort"], "high")
        self.assertIsNone(calls[2].kwargs["claude_effort"])
        self.assertEqual(
            calls[0].kwargs["codex_auth_storage_dir"],
            "/stable/codex-auth",
        )
        self.assertIsNone(calls[1].kwargs["codex_auth_storage_dir"])
        self.assertIsNone(calls[2].kwargs["codex_auth_storage_dir"])

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

    def test_codex_event_stream_cannot_rescue_invalid_designated_final(self):
        stream = json.dumps(
            {"type": "result", "result": _submission()}
        ).encode()
        for name, final_output in (
            ("missing", None),
            ("empty", b""),
            ("invalid_json", b"not-json"),
            ("invalid_utf8", b"\xff"),
        ):
            with self.subTest(name=name):
                submission, observed, audit = parse_agent_output(
                    "codex",
                    requested_model="gpt-5.6-sol",
                    stdout=stream,
                    final_output=final_output,
                )
                self.assertIsNone(submission)
                self.assertEqual(observed, ())
                self.assertIn("agent_failure:invalid_submission", audit)

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
