from __future__ import annotations

from contextlib import nullcontext
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from examples import run_development_matched_panel as matched_cli
import epiagentbench.development_matched_panel as matched
import epiagentbench.launchd_agent as launchd


class V30DeferredCursorCredentialTests(unittest.TestCase):
    @staticmethod
    def _prerequisite_bundle(
        public: dict[str, object],
    ) -> dict[str, object]:
        authentication_sha256 = "sha256:" + "c" * 64
        return {
            "schema_version": (
                matched._PROVIDER_FREE_PRECLAIM_PREREQUISITE_SCHEMA
            ),
            "panel_id": matched.PANEL_ID,
            "public_precommitment_sha256": public[
                "precommitment_sha256"
            ],
            "spend_authorization_receipt_sha256": (
                "sha256:" + "d" * 64
            ),
            "authentication_receipt_sha256": authentication_sha256,
            "authentication_repository_binding": {
                "schema_version": matched._PUBLIC_RECEIPT_BINDING_SCHEMA,
                "artifact_kind": "authentication",
                "repository_relative_path": (
                    f"results/{matched.PANEL_ID}.authentication.json"
                ),
                "file_sha256": "sha256:" + "e" * 64,
                "content_sha256": authentication_sha256,
                "published_commit": "f" * 40,
            },
            "supervisor_execution_binding": {
                "operation": "preflight",
                "label": "com.epiagentbench.preflight",
                "execution_context_sha256": "sha256:" + "1" * 64,
                "config_file_sha256": "sha256:" + "2" * 64,
                "panel_id": matched.PANEL_ID,
                "precommitment_sha256": public[
                    "precommitment_sha256"
                ],
            },
            "provider_processes_started": 0,
            "authentication_processes_started": 0,
            "model_calls_started": 0,
        }

    def tearDown(self) -> None:
        os.environ.pop("CURSOR_API_KEY", None)

    def test_one_lazy_load_is_reused_only_for_cursor_calls(self) -> None:
        loads = 0
        observed: list[tuple[str, str | None]] = []

        def loader() -> str:
            nonlocal loads
            loads += 1
            self.assertNotIn("CURSOR_API_KEY", os.environ)
            return "test-cursor-key"

        def evaluator(system: str) -> str:
            observed.append((system, os.environ.get("CURSOR_API_KEY")))
            return system

        session = matched._DeferredCursorCredentialSession(loader)
        wrapped = matched._deferred_cursor_evaluator(evaluator, session)
        self.assertEqual(wrapped("claude"), "claude")
        self.assertEqual(wrapped("codex"), "codex")
        self.assertEqual(loads, 0)
        self.assertEqual(wrapped("cursor"), "cursor")
        self.assertEqual(wrapped("cursor"), "cursor")
        self.assertEqual(wrapped("claude"), "claude")
        self.assertEqual(loads, 1)
        self.assertEqual(
            observed,
            [
                ("claude", None),
                ("codex", None),
                ("cursor", "test-cursor-key"),
                ("cursor", "test-cursor-key"),
                ("claude", None),
            ],
        )
        self.assertNotIn("CURSOR_API_KEY", os.environ)
        session.close()
        self.assertIsNone(session._credential)
        self.assertNotIn("CURSOR_API_KEY", os.environ)

    def test_failed_load_is_typed_sanitized_and_not_retried(self) -> None:
        loads = 0
        secret = "crsr_must_not_escape"

        def loader() -> str:
            nonlocal loads
            loads += 1
            raise RuntimeError(secret)

        session = matched._DeferredCursorCredentialSession(loader)
        wrapped = matched._deferred_cursor_evaluator(
            lambda system: system, session
        )
        for _ in range(2):
            with self.assertRaises(
                matched._DeferredCursorCredentialError
            ) as raised:
                wrapped("cursor")
            self.assertNotIn(secret, str(raised.exception))
            self.assertNotIn("CURSOR_API_KEY", os.environ)
        self.assertEqual(loads, 1)
        session.close()

    def test_evaluator_failure_clears_environment_and_outer_cache(self) -> None:
        session = matched._DeferredCursorCredentialSession(
            lambda: "test-cursor-key"
        )
        wrapped = matched._deferred_cursor_evaluator(
            lambda _system: (_ for _ in ()).throw(RuntimeError("boom")),
            session,
        )
        try:
            with self.assertRaises(RuntimeError):
                wrapped("cursor")
            self.assertNotIn("CURSOR_API_KEY", os.environ)
            self.assertIsNotNone(session._credential)
        finally:
            session.close()
        self.assertIsNone(session._credential)
        self.assertNotIn("CURSOR_API_KEY", os.environ)

    def test_preflight_claim_precedes_first_load_and_outer_finally_wipes(
        self,
    ) -> None:
        loads = 0
        claim_seen = False

        def loader() -> str:
            nonlocal loads
            loads += 1
            self.assertTrue(claim_seen)
            return "test-cursor-key"

        def claim(**_kwargs: object) -> dict[str, object]:
            nonlocal claim_seen
            self.assertEqual(loads, 0)
            self.assertNotIn("CURSOR_API_KEY", os.environ)
            claim_seen = True
            return {"status": "passed"}

        def claimed(**kwargs: object) -> dict[str, object]:
            session = kwargs["cursor_credential_session"]
            self.assertIsInstance(
                session, matched._DeferredCursorCredentialSession
            )
            wrapped = matched._deferred_cursor_evaluator(
                lambda system: system, session
            )
            self.assertEqual(wrapped("claude"), "claude")
            self.assertEqual(loads, 0)
            self.assertEqual(wrapped("cursor"), "cursor")
            self.assertEqual(wrapped("cursor"), "cursor")
            raise RuntimeError("post-provider failure")

        with (
            patch.object(
                matched,
                "_claim_preflight_incident_envelope",
                side_effect=claim,
            ),
            patch.object(
                matched,
                "_claim_offline_test_preflight_incident_envelope",
            ) as offline_claim,
            patch.object(
                matched,
                "_assert_canonical_public_output_path",
            ),
            patch.object(
                matched,
                "_run_environment_preflight_core_claimed",
                side_effect=claimed,
            ),
            patch.object(
                matched,
                "_seal_minimal_terminal_preflight_candidate",
            ),
            patch.object(
                matched,
                "_publish_terminal_preflight_candidate",
                return_value={"panel_id": matched.PANEL_ID, "status": "failed"},
            ),
        ):
            matched._run_environment_preflight_core(
                root=Path("/tmp/root"),
                authentication_key_file=Path("/tmp/key"),
                claude_secure_storage_dir=Path("/tmp/claude"),
                codex_secure_storage_dir=Path("/tmp/codex"),
                private_state_path=Path("/tmp/private"),
                public_manifest_path=Path("/tmp/manifest"),
                public_preflight_path=Path("/tmp/preflight"),
                supervisor_runtime_dir=Path("/tmp/supervisor"),
                require_persistent_supervisor=True,
                cursor_credential_loader=loader,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(loads, 1)
        offline_claim.assert_not_called()
        self.assertNotIn("CURSOR_API_KEY", os.environ)

    def test_live_entry_rejects_inherited_key_before_claim_or_loader(self) -> None:
        loads = 0

        def loader() -> str:
            nonlocal loads
            loads += 1
            return "unused"

        os.environ["CURSOR_API_KEY"] = "inherited"
        with (
            patch.object(
                matched, "_claim_preflight_incident_envelope"
            ) as claim,
            self.assertRaises(RuntimeError),
        ):
            matched._run_environment_preflight_core(
                root=Path("/tmp/root"),
                authentication_key_file=Path("/tmp/key"),
                claude_secure_storage_dir=Path("/tmp/claude"),
                codex_secure_storage_dir=Path("/tmp/codex"),
                private_state_path=Path("/tmp/private"),
                public_manifest_path=Path("/tmp/manifest"),
                public_preflight_path=Path("/tmp/preflight"),
                supervisor_runtime_dir=Path("/tmp/supervisor"),
                cursor_credential_loader=loader,
                acknowledge_unbounded_provider_spend=True,
            )
        claim.assert_not_called()
        self.assertEqual(loads, 0)

    def test_production_outer_finally_wipes_one_shot_session(self) -> None:
        loads = 0
        captured: matched._DeferredCursorCredentialSession | None = None

        def loader() -> str:
            nonlocal loads
            loads += 1
            return "test-cursor-key"

        def locked(**kwargs: object) -> dict[str, object]:
            nonlocal captured
            captured = kwargs["cursor_credential_session"]
            wrapped = matched._deferred_cursor_evaluator(
                lambda system: system, captured
            )
            self.assertEqual(wrapped("codex"), "codex")
            self.assertEqual(loads, 0)
            self.assertEqual(wrapped("cursor"), "cursor")
            self.assertEqual(wrapped("cursor"), "cursor")
            raise RuntimeError("production failure")

        with (
            patch.object(matched, "assert_durable_live_execution_paths"),
            patch.object(
                matched, "_exclusive_run_lock", return_value=nullcontext()
            ),
            patch.object(matched, "_run_panel_locked", side_effect=locked),
            self.assertRaises(RuntimeError),
        ):
            matched.run_panel(
                root=Path("/tmp/root"),
                authentication_key_file=Path("/tmp/key"),
                claude_secure_storage_dir=Path("/tmp/claude"),
                codex_secure_storage_dir=Path("/tmp/codex"),
                private_state_path=Path("/tmp/private"),
                public_manifest_path=Path("/tmp/manifest"),
                public_results_path=Path("/tmp/results"),
                supervisor_runtime_dir=Path("/tmp/supervisor"),
                cursor_credential_loader=loader,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(loads, 1)
        self.assertIsNotNone(captured)
        self.assertIsNone(captured._credential)
        self.assertNotIn("CURSOR_API_KEY", os.environ)

    def test_launchd_command_contains_only_nonsecret_locator(self) -> None:
        config = {
            "operation": "preflight",
            "python_executable": "/usr/bin/python3",
            "runner_script": "/repo/examples/run_development_matched_panel.py",
            "authentication_key_file": "/private/auth.key",
            "claude_secure_storage_dir": "/private/claude",
            "codex_secure_storage_dir": "/private/codex",
            "private_state_path": "/private/state.json",
            "public_manifest_path": "/repo/results/manifest.json",
            "runtime_dir": "/private/runtime",
            "public_output_path": "/repo/results/preflight.json",
            "cursor_keychain": {
                "service": "epiagentbench-cursor-v30",
                "account": "test-account",
            },
        }
        command = launchd._runner_command(config)
        self.assertIn("--cursor-keychain-service", command)
        self.assertIn("epiagentbench-cursor-v30", command)
        self.assertIn("--cursor-keychain-account", command)
        self.assertNotIn("CURSOR_API_KEY", " ".join(command))
        self.assertFalse(any(value.startswith("crsr_") for value in command))

    def test_child_keychain_reader_is_exact_and_sanitized(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []

        def runner(arguments: list[str], **kwargs: object):
            calls.append((arguments, kwargs))
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"test-cursor-key\n",
                stderr=b"ignored",
            )

        credential = matched_cli._read_cursor_keychain_credential(
            service="epiagentbench-cursor-v30",
            account="test-account",
            command_runner=runner,
        )
        self.assertEqual(credential, "test-cursor-key")
        self.assertEqual(len(calls), 1)
        arguments, kwargs = calls[0]
        self.assertEqual(
            arguments,
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                "test-account",
                "-s",
                "epiagentbench-cursor-v30",
                "-w",
            ],
        )
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        self.assertNotIn("CURSOR_API_KEY", kwargs["env"])

        def failing(arguments: list[str], **_kwargs: object):
            return subprocess.CompletedProcess(
                arguments,
                1,
                stdout=b"crsr_must_not_escape",
                stderr=b"crsr_must_not_escape",
            )

        with self.assertRaises(RuntimeError) as raised:
            matched_cli._read_cursor_keychain_credential(
                service="epiagentbench-cursor-v30",
                account="test-account",
                command_runner=failing,
            )
        self.assertNotIn("crsr_must_not_escape", str(raised.exception))

    def _release_contract(
        self,
    ) -> tuple[dict[str, object], dict[str, object]]:
        preparation_hash = "sha256:" + "a" * 64
        public: dict[str, object] = {
            "precommitment_sha256": "sha256:" + "b" * 64,
            "contract_hashes": {
                "preparation_runtime_sha256": preparation_hash
            },
        }
        trace = matched._new_provider_free_preclaim(
            public,
            prerequisite_bundle=self._prerequisite_bundle(public),
        )
        trace = matched._advance_provider_free_preclaim_operation(
            trace, operation="contract_internal"
        )
        trace = matched._advance_provider_free_preclaim_operation(
            trace, operation="assignment_state"
        )
        for operation in matched._PREPARATION_RUNTIME_OPERATIONS:
            trace = matched._advance_provider_free_preclaim_operation(
                trace, operation=operation
            )
        trace = matched._complete_provider_free_preclaim(trace)
        return public, trace

    def test_release_rejects_missing_or_tampered_preclaim_before_mutation(
        self,
    ) -> None:
        public, passed = self._release_contract()
        for name, trace in (
            ("missing", None),
            (
                "tampered",
                {**passed, "model_calls_started": 1},
            ),
        ):
            private = {
                "environment_preflight": {
                    "status": matched._PENDING_PREFLIGHT_STATUS,
                    "provider_free_preclaim": trace,
                }
            }
            with (
                self.subTest(name=name),
                patch.object(matched, "_assert_canonical_public_output_path"),
                patch.object(matched, "assert_durable_live_execution_paths"),
                patch.object(matched, "_assert_distinct_paths"),
                patch.object(
                    matched, "_exclusive_run_lock", return_value=nullcontext()
                ),
                patch.object(
                    matched,
                    "_existing_path_without_final_symlink",
                    side_effect=lambda path: Path(path),
                ),
                patch.object(
                    matched, "_read_authentication_key", return_value=b"k" * 32
                ),
                patch.object(matched, "_load_private_state", return_value=private),
                patch.object(matched, "_load_json", return_value=public),
                patch.object(matched, "_validate_public_hash"),
                patch.object(matched, "_completed_supervisor_binding") as completed,
                patch.object(matched, "_write_private_state") as private_write,
                patch.object(matched, "_atomic_json") as public_write,
                self.assertRaises(launchd.ReleaseValidationError),
            ):
                matched.finalize_supervised_release(
                    root=Path("/tmp/root"),
                    authentication_key_file=Path("/tmp/key"),
                    claude_secure_storage_dir=Path("/tmp/claude"),
                    codex_secure_storage_dir=Path("/tmp/codex"),
                    private_state_path=Path("/tmp/private"),
                    public_manifest_path=Path("/tmp/manifest"),
                    public_output_path=Path("/tmp/preflight"),
                    supervisor_runtime_dir=Path("/tmp/supervisor"),
                    operation="preflight",
                )
            completed.assert_not_called()
            private_write.assert_not_called()
            public_write.assert_not_called()

    def test_released_preflight_preserves_passed_preclaim(self) -> None:
        public, passed = self._release_contract()
        candidate = {
            "panel_id": matched.PANEL_ID,
            "status": "passed",
            "precommitment_sha256": public["precommitment_sha256"],
        }
        candidate_sha256 = matched._component_hash(candidate)
        preflight = {
            "status": "passed",
            "provider_free_preclaim": passed,
            "pending_public_receipt": candidate,
            "pending_public_receipt_sha256": candidate_sha256,
            "public_receipt_sha256": candidate_sha256,
            "public_receipt_binding": {"published_commit": None},
            "public_release": {
                "status": "released",
                "operation": "preflight",
            },
        }
        private = {
            "environment_preflight": preflight,
            "execution_incident": None,
            "codex_auth_incident": None,
        }

        def load_json(path: Path) -> dict[str, object]:
            return public if Path(path).name == "manifest" else candidate

        with (
            patch.object(matched, "_assert_canonical_public_output_path"),
            patch.object(matched, "assert_durable_live_execution_paths"),
            patch.object(matched, "_assert_distinct_paths"),
            patch.object(
                matched, "_exclusive_run_lock", return_value=nullcontext()
            ),
            patch.object(
                matched,
                "_existing_path_without_final_symlink",
                side_effect=lambda path: Path(path),
            ),
            patch.object(
                matched, "_read_authentication_key", return_value=b"k" * 32
            ),
            patch.object(matched, "_load_private_state", return_value=private),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(matched, "_validate_public_hash"),
            patch.object(
                matched,
                "_completed_supervisor_binding",
                return_value={"binding": "complete"},
            ),
            patch.object(
                matched, "_require_existing_persistent_execution_binding"
            ),
            patch.object(
                matched,
                "_validate_claude_secure_storage_dir",
                return_value=Path("/tmp/claude"),
            ),
            patch.object(
                matched,
                "_validate_codex_secure_storage_dir",
                return_value=Path("/tmp/codex"),
            ),
            patch.object(matched, "_validate_contracts", return_value=({}, {}, [])),
            patch.object(matched, "_public_preflight_pending", return_value={}),
            patch.object(matched, "_validate_repository_receipt_binding"),
            patch.object(matched, "_assert_exact_public_json_bytes"),
            patch.object(matched, "_write_private_state") as private_write,
            patch.object(matched, "_atomic_json") as public_write,
        ):
            released = matched.finalize_supervised_release(
                root=Path("/tmp/root"),
                authentication_key_file=Path("/tmp/key"),
                claude_secure_storage_dir=Path("/tmp/claude"),
                codex_secure_storage_dir=Path("/tmp/codex"),
                private_state_path=Path("/tmp/private"),
                public_manifest_path=Path("/tmp/manifest"),
                public_output_path=Path("/tmp/preflight"),
                supervisor_runtime_dir=Path("/tmp/supervisor"),
                operation="preflight",
            )
        self.assertEqual(released, candidate)
        self.assertEqual(preflight["provider_free_preclaim"], passed)
        private_write.assert_not_called()
        public_write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
