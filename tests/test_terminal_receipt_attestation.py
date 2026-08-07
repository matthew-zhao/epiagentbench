from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from examples import run_development_matched_panel as matched_cli
import epiagentbench.development_matched_panel as matched
from epiagentbench.launchd_agent import (
    ReleaseValidationError,
    ReleaseValidationFailureCode,
)
from epiagentbench.persistent_supervisor import (
    HANDLED_TERMINAL_RECEIPT_EXIT_CODE,
)


class TerminalReceiptAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.results = self.root / "results"
        self.results.mkdir()
        self.authentication_key = self.root / "authentication.key"
        self.private_state = self.root / "private.json"
        self.public_manifest = (
            self.results / f"{matched.PANEL_ID}.manifest.json"
        )
        self.public_preflight = (
            self.results / f"{matched.PANEL_ID}.preflight.json"
        )
        self.public_results = self.results / f"{matched.PANEL_ID}.json"
        for path in (
            self.authentication_key,
            self.private_state,
            self.public_manifest,
            self.public_preflight,
            self.public_results,
        ):
            path.write_text("{}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _preflight_fixture(
        self,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        public = {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "status": "precommitted",
            "precommitment_sha256": "sha256:" + "a" * 64,
        }
        candidate: dict[str, object] = {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "status": "failed",
            "development_only": True,
            "production_episodes_consumed": 0,
            "precommitment_sha256": public["precommitment_sha256"],
            "failure_reason": "one_or_more_profile_failures",
            "model_invocations_conservatively_chargeable": 0,
            "scores_reported": False,
        }
        preflight: dict[str, object] = {
            "incident_envelope": matched._new_preflight_incident_envelope(),
            "status": "failed",
            "attempts": [],
            "terminal_public_receipt": candidate,
            "public_receipt_sha256": matched._component_hash(candidate),
            "public_receipt_binding": {"test": "binding"},
        }
        matched._advance_preflight_incident_envelope(
            preflight,
            phase="terminal_candidate_commit",
            attempts=[],
            status="terminal",
            incident_code="unexpected_control_path_failure",
        )
        private = {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "public_precommitment_sha256": public[
                "precommitment_sha256"
            ],
            "environment_preflight": preflight,
        }
        return private, public, candidate

    def _attest_preflight(
        self,
        *,
        private: dict[str, object],
        public: dict[str, object],
        observed: dict[str, object] | None,
        canonical_bytes: bool = True,
    ) -> dict[str, object]:
        if observed is None:
            self.public_preflight.unlink(missing_ok=True)
        else:
            encoded = (
                json.dumps(observed, indent=2, sort_keys=True) + "\n"
                if canonical_bytes
                else json.dumps(observed, sort_keys=True) + "  \n"
            )
            self.public_preflight.write_text(
                encoded,
                encoding="utf-8",
            )

        def load_json(path: Path, **_: object) -> dict[str, object]:
            if path == self.public_manifest:
                return copy.deepcopy(public)
            if path == self.public_preflight and observed is not None:
                return copy.deepcopy(observed)
            raise ValueError("terminal receipt unavailable")

        with (
            patch.object(matched, "_read_authentication_key", return_value=b"k"),
            patch.object(
                matched,
                "_load_private_state",
                return_value=copy.deepcopy(private),
            ),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(matched, "_validate_public_hash"),
            patch.object(
                matched,
                "_validate_repository_receipt_binding",
                return_value={
                    "file_sha256": matched._public_json_file_sha256(
                        private["environment_preflight"][
                            "terminal_public_receipt"
                        ]
                    )
                },
            ),
        ):
            return matched.assert_terminal_receipt_ready_for_exit(
                root=self.root,
                operation="preflight",
                authentication_key_file=self.authentication_key,
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_output_path=self.public_preflight,
            )

    def test_preflight_terminal_exit_requires_exact_authenticated_receipt(
        self,
    ) -> None:
        private, public, candidate = self._preflight_fixture()
        attestation = self._attest_preflight(
            private=private,
            public=public,
            observed=candidate,
        )
        self.assertEqual(attestation["status"], "attested")
        self.assertEqual(attestation["terminal_status"], "failed")
        self.assertEqual(attestation["model_calls_started"], 0)

        tampered = {**candidate, "failure_reason": "tampered"}
        with self.assertRaisesRegex(RuntimeError, "inconsistent"):
            self._attest_preflight(
                private=private,
                public=public,
                observed=tampered,
            )
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self._attest_preflight(
                private=private,
                public=public,
                observed=None,
            )

    def test_late_readiness_timeout_preserves_prior_chargeable_profile(
        self,
    ) -> None:
        private, public, candidate = self._preflight_fixture()
        profiles: list[dict[str, object]] = []
        for index, profile in enumerate(matched.PROFILES):
            if index == 0:
                profiles.append(
                    {
                        "profile_id": profile["profile_id"],
                        "model_invocation_state": "finished",
                        "pre_model_phase": "model_spawn_boundary",
                        "failed_pre_model_phase": None,
                        "outcome": "passed",
                        "timed_out": False,
                        "timeout_stage": None,
                        "conservative_chargeable": True,
                    }
                )
            elif index == 1:
                profiles.append(
                    {
                        "profile_id": profile["profile_id"],
                        "model_invocation_state": "not_started",
                        "pre_model_phase": "provider_cli_readiness",
                        "failed_pre_model_phase": (
                            "provider_cli_readiness"
                        ),
                        "outcome": (
                            "failed_provider_cli_readiness_timeout"
                        ),
                        "timed_out": True,
                        "timeout_stage": "provider_cli_readiness",
                        "conservative_chargeable": False,
                    }
                )
            else:
                profiles.append(
                    {
                        "profile_id": profile["profile_id"],
                        "model_invocation_state": "not_started",
                        "pre_model_phase": None,
                        "failed_pre_model_phase": None,
                        "outcome": "not_started_terminal_abort",
                        "timed_out": False,
                        "timeout_stage": None,
                        "conservative_chargeable": False,
                    }
                )
        candidate.update(
            {
                "failure_reason": "provider_cli_readiness_timeout",
                "failure_stage": "provider_cli_readiness",
                "incident_code": "provider_cli_readiness_timeout",
                "failed_profile_id": matched.PROFILES[1]["profile_id"],
                "failed_model_invocation_state": "not_started",
                "failed_pre_model_phase": "provider_cli_readiness",
                "model_invocations_conservatively_chargeable": 1,
                "timed_out": True,
                "timeout_stages": ["provider_cli_readiness"],
                "profiles": profiles,
            }
        )
        private["environment_preflight"]["terminal_public_receipt"] = (
            candidate
        )
        private["environment_preflight"]["public_receipt_sha256"] = (
            matched._component_hash(candidate)
        )
        attempts: list[dict[str, object]] = []
        for index in range(len(matched.PROFILES)):
            attempt: dict[str, object] = {
                "status": (
                    "passed"
                    if index == 0
                    else (
                        "failed"
                        if index == 1
                        else "not_started_terminal_abort"
                    )
                )
            }
            if index == 0:
                attempt["model_invocation"] = {
                    "status": "finished",
                    "started_at_utc": "2026-01-01T00:00:00+00:00",
                    "finished_at_utc": "2026-01-01T00:00:01+00:00",
                }
            attempts.append(attempt)
        preflight = private["environment_preflight"]
        preflight["attempts"] = attempts
        preflight["incident_envelope"] = (
            matched._new_preflight_incident_envelope()
        )
        matched._advance_preflight_incident_envelope(
            preflight,
            phase="before_model_spawn",
            attempts=attempts,
        )
        matched._advance_preflight_incident_envelope(
            preflight,
            phase="terminal_candidate_commit",
            attempts=attempts,
            status="terminal",
            incident_code="provider_cli_readiness_timeout",
        )

        attestation = self._attest_preflight(
            private=private,
            public=public,
            observed=candidate,
        )

        self.assertEqual(attestation["status"], "attested")
        self.assertEqual(
            candidate["model_invocations_conservatively_chargeable"], 1
        )

    def test_spoofed_incident_code_cannot_cross_terminal_boundary(self) -> None:
        private, public, candidate = self._preflight_fixture()
        candidate["incident_code"] = "provider_said_everything_is_fine"
        private["environment_preflight"]["terminal_public_receipt"] = candidate
        private["environment_preflight"][
            "public_receipt_sha256"
        ] = matched._component_hash(candidate)
        with self.assertRaisesRegex(RuntimeError, "incident code"):
            self._attest_preflight(
                private=private,
                public=public,
                observed=candidate,
            )

    def test_spoofed_failure_stage_cannot_cross_terminal_boundary(self) -> None:
        private, public, candidate = self._preflight_fixture()
        candidate["failure_stage"] = "provider_supplied_success_stage"
        private["environment_preflight"]["terminal_public_receipt"] = candidate
        private["environment_preflight"][
            "public_receipt_sha256"
        ] = matched._component_hash(candidate)
        with self.assertRaisesRegex(RuntimeError, "failure stage"):
            self._attest_preflight(
                private=private,
                public=public,
                observed=candidate,
            )

    def test_semantically_equal_noncanonical_preflight_bytes_are_rejected(
        self,
    ) -> None:
        private, public, candidate = self._preflight_fixture()
        with self.assertRaisesRegex(RuntimeError, "bytes are not canonical"):
            self._attest_preflight(
                private=private,
                public=public,
                observed=candidate,
                canonical_bytes=False,
            )

    def test_live_entrypoints_reject_noncanonical_output_before_evaluator(
        self,
    ) -> None:
        cursor_credential_loader = unittest.mock.Mock(
            side_effect=AssertionError(
                "noncanonical output reached Cursor Keychain loading"
            )
        )
        with (
            patch.object(matched, "assert_durable_live_execution_paths"),
            patch.object(matched, "_execution_evaluator") as evaluator,
            self.assertRaisesRegex(RuntimeError, "preflight.*not canonical"),
        ):
            matched.run_environment_preflight(
                root=self.root,
                authentication_key_file=self.authentication_key,
                claude_secure_storage_dir=self.root / "claude",
                codex_secure_storage_dir=self.root / "codex",
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_preflight_path=self.results / "wrong-preflight.json",
                cursor_credential_loader=cursor_credential_loader,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluator.assert_not_called()
        cursor_credential_loader.assert_not_called()

        with (
            patch.object(matched, "assert_durable_live_execution_paths"),
            patch.object(matched, "_execution_evaluator") as evaluator,
            self.assertRaisesRegex(RuntimeError, "production.*not canonical"),
        ):
            matched.run_panel(
                root=self.root,
                authentication_key_file=self.authentication_key,
                claude_secure_storage_dir=self.root / "claude",
                codex_secure_storage_dir=self.root / "codex",
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_results_path=self.results / "wrong-results.json",
                cursor_credential_loader=cursor_credential_loader,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluator.assert_not_called()
        cursor_credential_loader.assert_not_called()

    def test_finalizer_rejects_noncanonical_output_before_any_write(
        self,
    ) -> None:
        private_bytes = self.private_state.read_bytes()
        for operation in ("preflight", "production"):
            wrong_output = self.results / f"wrong-{operation}.json"
            with (
                self.subTest(operation=operation),
                patch.object(
                    matched, "assert_durable_live_execution_paths"
                ) as durable_paths,
                patch.object(
                    matched, "_read_authentication_key"
                ) as read_key,
                patch.object(matched, "_write_private_state") as write_private,
                patch.object(matched, "_atomic_json") as write_public,
                self.assertRaises(ReleaseValidationError) as refused,
            ):
                matched.finalize_supervised_release(
                    root=self.root,
                    authentication_key_file=self.authentication_key,
                    claude_secure_storage_dir=self.root / "claude",
                    codex_secure_storage_dir=self.root / "codex",
                    private_state_path=self.private_state,
                    public_manifest_path=self.public_manifest,
                    public_output_path=wrong_output,
                    supervisor_runtime_dir=self.root / "supervisor",
                    operation=operation,
                )
            self.assertEqual(
                refused.exception.failure_code,
                ReleaseValidationFailureCode.RUNTIME_BINDING_INVALID,
            )
            durable_paths.assert_not_called()
            read_key.assert_not_called()
            write_private.assert_not_called()
            write_public.assert_not_called()
            self.assertFalse(wrong_output.exists())
            self.assertEqual(self.private_state.read_bytes(), private_bytes)

    def test_incident_taxonomy_uses_only_trusted_exception_types(self) -> None:
        class SpoofedProviderError(RuntimeError):
            incident_code = "provider_spawn_failed"
            attestation_failure_code = "status_snapshot_unstable"

        self.assertEqual(
            matched._provider_incident_code(
                SpoofedProviderError("provider-controlled text"),
                fallback="provider_adapter_execution_failed",
            ),
            "provider_adapter_execution_failed",
        )
        self.assertEqual(
            matched._provider_incident_code(
                matched.ProviderSpawnIsolationError("safe internal error"),
                fallback="provider_adapter_execution_failed",
            ),
            "provider_spawn_failed",
        )
        self.assertEqual(
            matched._attestation_incident_fields(
                SpoofedProviderError("provider-controlled text")
            ),
            {},
        )
        trusted_attestation = matched._persistent_attestation_error(
            "status_snapshot_unstable"
        )
        self.assertEqual(
            matched._attestation_incident_fields(trusted_attestation),
            {"attestation_failure_code": "status_snapshot_unstable"},
        )

    def test_production_terminal_exit_requires_a_durable_incident(self) -> None:
        public = {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "status": "precommitted",
            "precommitment_sha256": "sha256:" + "c" * 64,
        }
        private: dict[str, object] = {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "public_precommitment_sha256": public[
                "precommitment_sha256"
            ],
            "panel_started_at_utc": "2026-01-01T00:00:00+00:00",
            "assignments": [{"status": "transport_void"}],
        }
        observed = matched._public_running(
            public,
            private,
            status="stopped_transport_void",
        )
        self.public_results.write_text(
            json.dumps(observed, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        def load_json(path: Path, **_: object) -> dict[str, object]:
            return copy.deepcopy(
                public if path == self.public_manifest else observed
            )

        patches = (
            patch.object(matched, "_read_authentication_key", return_value=b"k"),
            patch.object(matched, "_load_private_state", return_value=private),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(matched, "_validate_public_hash"),
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            self.assertRaisesRegex(RuntimeError, "no durable incident"),
        ):
            matched.assert_terminal_receipt_ready_for_exit(
                root=self.root,
                operation="production",
                authentication_key_file=self.authentication_key,
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_output_path=self.public_results,
            )

        private["execution_incident"] = {
            "status": "terminal",
            "assignment_index": 0,
            "failure_class": "interrupted_after_durable_start",
            "incident_code": "provider_interrupted_after_durable_attempt",
        }
        with (
            patch.object(matched, "_read_authentication_key", return_value=b"k"),
            patch.object(matched, "_load_private_state", return_value=private),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(matched, "_validate_public_hash"),
        ):
            attestation = matched.assert_terminal_receipt_ready_for_exit(
                root=self.root,
                operation="production",
                authentication_key_file=self.authentication_key,
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_output_path=self.public_results,
            )
        self.assertEqual(attestation["status"], "attested")

        self.public_results.write_text(
            json.dumps(observed, sort_keys=True) + "  \n",
            encoding="utf-8",
        )
        with (
            patch.object(matched, "_read_authentication_key", return_value=b"k"),
            patch.object(matched, "_load_private_state", return_value=private),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(matched, "_validate_public_hash"),
            self.assertRaisesRegex(RuntimeError, "bytes are not canonical"),
        ):
            matched.assert_terminal_receipt_ready_for_exit(
                root=self.root,
                operation="production",
                authentication_key_file=self.authentication_key,
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_output_path=self.public_results,
            )
        self.public_results.write_text(
            json.dumps(observed, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        private["panel_id"] = "wrong-panel"
        with (
            patch.object(matched, "_read_authentication_key", return_value=b"k"),
            patch.object(matched, "_load_private_state", return_value=private),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(matched, "_validate_public_hash"),
            self.assertRaisesRegex(RuntimeError, "not bound"),
        ):
            matched.assert_terminal_receipt_ready_for_exit(
                root=self.root,
                operation="production",
                authentication_key_file=self.authentication_key,
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_output_path=self.public_results,
            )
        private["panel_id"] = matched.PANEL_ID

        private["execution_incident"]["incident_code"] = (
            "provider_supplied_success"
        )
        with (
            patch.object(matched, "_read_authentication_key", return_value=b"k"),
            patch.object(matched, "_load_private_state", return_value=private),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(matched, "_validate_public_hash"),
            self.assertRaisesRegex(RuntimeError, "incident is invalid"),
        ):
            matched.assert_terminal_receipt_ready_for_exit(
                root=self.root,
                operation="production",
                authentication_key_file=self.authentication_key,
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_output_path=self.public_results,
            )

    def test_reconcile_restores_only_the_authenticated_private_candidate(
        self,
    ) -> None:
        private, public, candidate = self._preflight_fixture()
        self.public_preflight.unlink()
        original_load_json = matched._load_json

        def load_json(path: Path, **kwargs: object) -> dict[str, object]:
            if path == self.public_manifest:
                return copy.deepcopy(public)
            return original_load_json(path, **kwargs)

        with (
            patch.object(matched, "assert_durable_live_execution_paths"),
            patch.object(matched, "_read_authentication_key", return_value=b"k"),
            patch.object(
                matched,
                "_load_private_state",
                return_value=copy.deepcopy(private),
            ),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(matched, "_validate_public_hash"),
            patch.object(
                matched,
                "_validate_repository_receipt_binding",
                return_value={
                    "file_sha256": matched._public_json_file_sha256(
                        candidate
                    )
                },
            ),
        ):
            result = matched.reconcile_terminal_receipt(
                root=self.root,
                operation="preflight",
                authentication_key_file=self.authentication_key,
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_output_path=self.public_preflight,
            )
        self.assertEqual(result["status"], "reconciled")
        self.assertEqual(
            original_load_json(self.public_preflight),
            candidate,
        )

        original_load_json(self.public_preflight)["failure_reason"] = "unused"
        self.public_preflight.write_text(
            '{"conflict": true}\n', encoding="utf-8"
        )
        with (
            patch.object(matched, "assert_durable_live_execution_paths"),
            patch.object(matched, "_read_authentication_key", return_value=b"k"),
            patch.object(
                matched,
                "_load_private_state",
                return_value=copy.deepcopy(private),
            ),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(matched, "_validate_public_hash"),
            patch.object(
                matched,
                "_validate_repository_receipt_binding",
                return_value={
                    "file_sha256": matched._public_json_file_sha256(
                        candidate
                    )
                },
            ),
            self.assertRaisesRegex(RuntimeError, "conflicting"),
        ):
            matched.reconcile_terminal_receipt(
                root=self.root,
                operation="preflight",
                authentication_key_file=self.authentication_key,
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_output_path=self.public_preflight,
            )

    def test_production_reconcile_requires_a_durable_incident(self) -> None:
        public = {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "status": "precommitted",
            "precommitment_sha256": "sha256:" + "e" * 64,
        }
        private = {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "public_precommitment_sha256": public[
                "precommitment_sha256"
            ],
            "panel_started_at_utc": "2026-01-01T00:00:00+00:00",
            "assignments": [],
        }
        with self.assertRaisesRegex(ValueError, "No durable terminal incident"):
            matched._reconcile_terminal_incident_public_progress(
                root=self.root,
                public_manifest=public,
                private=private,
                public_results_path=self.public_results,
            )

        private["assignments"] = [{"status": "transport_void"}]
        private["execution_incident"] = {
            "status": "terminal",
            "assignment_index": 0,
            "failure_class": "interrupted_after_durable_start",
            "incident_code": "provider_interrupted_after_durable_attempt",
        }
        self.public_results.unlink()
        original_load_json = matched._load_json

        def load_json(path: Path, **kwargs: object) -> dict[str, object]:
            if path == self.public_manifest:
                return copy.deepcopy(public)
            return original_load_json(path, **kwargs)

        with (
            patch.object(matched, "assert_durable_live_execution_paths"),
            patch.object(matched, "_read_authentication_key", return_value=b"k"),
            patch.object(matched, "_load_private_state", return_value=private),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(matched, "_validate_public_hash"),
            patch.object(matched, "_git_output", return_value=""),
        ):
            reconciled = matched.reconcile_terminal_receipt(
                root=self.root,
                operation="production",
                authentication_key_file=self.authentication_key,
                private_state_path=self.private_state,
                public_manifest_path=self.public_manifest,
                public_output_path=self.public_results,
            )
        self.assertEqual(reconciled["status"], "reconciled")
        self.assertEqual(
            matched._fixed_file_sha256(
                self.public_results,
                label="offline production receipt",
            ),
            matched._public_json_file_sha256(
                matched._load_json(self.public_results)
            ),
        )

    def test_cli_emits_64_only_after_terminal_attestation(self) -> None:
        arguments = [
            "run_development_matched_panel.py",
            "preflight",
            "--authentication-key",
            str(self.authentication_key),
            "--claude-secure-storage-dir",
            str(self.root / "claude"),
            "--codex-secure-storage-dir",
            str(self.root / "codex"),
            "--private-state",
            str(self.private_state),
            "--public-manifest",
            str(self.public_manifest),
            "--public-preflight",
            str(self.public_preflight),
            "--supervisor-runtime",
            str(self.root / "supervisor"),
            "--cursor-keychain-service",
            "epiagentbench-cursor-v31",
            "--cursor-keychain-account",
            "test-account",
            "--acknowledge-unbounded-provider-spend",
        ]
        payload = {
            "panel_id": matched.PANEL_ID,
            "status": "failed",
            "profiles": [],
        }
        with (
            patch.object(matched_cli.sys, "argv", arguments),
            patch.object(
                matched_cli, "assert_durable_live_execution_paths"
            ),
            patch.object(
                matched_cli,
                "run_environment_preflight",
                return_value=payload,
            ),
            patch.object(
                matched_cli, "assert_terminal_receipt_ready_for_exit"
            ) as attest,
            patch("builtins.print"),
        ):
            self.assertEqual(
                matched_cli.main(),
                HANDLED_TERMINAL_RECEIPT_EXIT_CODE,
            )
        attest.assert_called_once()

        with (
            patch.object(matched_cli.sys, "argv", arguments),
            patch.object(
                matched_cli, "assert_durable_live_execution_paths"
            ),
            patch.object(
                matched_cli,
                "run_environment_preflight",
                return_value=payload,
            ),
            patch.object(
                matched_cli,
                "assert_terminal_receipt_ready_for_exit",
                side_effect=RuntimeError("receipt mismatch"),
            ),
            patch("builtins.print"),
            self.assertRaisesRegex(RuntimeError, "receipt mismatch"),
        ):
            matched_cli.main()


if __name__ == "__main__":
    unittest.main()
