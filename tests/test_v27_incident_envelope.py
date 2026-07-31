from __future__ import annotations

import copy
from contextlib import nullcontext
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import epiagentbench.development_matched_panel as matched


AUTHENTICATION_KEY = b"v27 incident-envelope test key".ljust(32, b"!")
PRECOMMITMENT = "sha256:" + "a" * 64


class V27IncidentEnvelopeTests(unittest.TestCase):
    @staticmethod
    def _attempts() -> list[dict[str, object]]:
        return [
            {
                "profile_id": "codex-gpt-5.6-sol",
                "status": "passed",
                "model_invocation": {
                    "status": "finished",
                    "started_at_utc": "2026-07-30T20:00:00Z",
                    "finished_at_utc": "2026-07-30T20:01:00Z",
                },
            },
            {
                "profile_id": "codex-gpt-5.6-luna",
                "status": "started",
                "model_invocation": {
                    "status": "started",
                    "started_at_utc": "2026-07-30T20:02:00Z",
                },
            },
            {
                "profile_id": "claude-opus-4.8",
                "status": "failed",
            },
        ]

    def _sealed_fixture(
        self,
        *,
        phase: str = "provider_returned",
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        public: dict[str, object] = {
            "precommitment_sha256": PRECOMMITMENT,
        }
        attempts = self._attempts()
        preflight: dict[str, object] = {
            "status": "running",
            "attempts": attempts,
            "incident_envelope": matched._new_preflight_incident_envelope(),
        }
        matched._advance_preflight_incident_envelope(
            preflight,
            phase=phase,
            attempts=attempts,
        )
        private: dict[str, object] = {
            "environment_preflight": preflight,
        }
        candidate = matched._minimal_terminal_preflight_candidate(
            private=private,
            public=public,
        )
        preflight.update(
            {
                "status": "failed",
                "finished_at_utc": "2026-07-30T20:03:00Z",
                "terminal_public_receipt": candidate,
                "public_receipt_sha256": matched._component_hash(candidate),
            }
        )
        return private, public, candidate

    def _rich_sealed_fixture(
        self,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        public: dict[str, object] = {
            "precommitment_sha256": PRECOMMITMENT,
        }
        attempts = self._attempts()
        attempts[1]["status"] = "failed"
        preflight: dict[str, object] = {
            "status": "running",
            "attempts": attempts,
            "incident_envelope": matched._new_preflight_incident_envelope(),
        }
        matched._advance_preflight_incident_envelope(
            preflight,
            phase="final_supervisor_attestation",
            attempts=attempts,
        )
        matched._advance_preflight_incident_envelope(
            preflight,
            phase="terminal_candidate_commit",
            attempts=attempts,
            status="terminal",
            incident_code="supervisor_boundary_attestation_failed",
        )
        candidate: dict[str, object] = {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "status": "stopped_supervisor_incident",
            "development_only": True,
            "production_episodes_consumed": 0,
            "precommitment_sha256": PRECOMMITMENT,
            "profiles_terminal": 3,
            "model_invocations_conservatively_chargeable": 2,
            "failure_stage": "supervisor_attestation_final_completion",
            "incident_code": "supervisor_boundary_attestation_failed",
            "scores_reported": False,
        }
        preflight.update(
            {
                "status": "failed",
                "finished_at_utc": "2026-07-30T20:03:00Z",
                "terminal_public_receipt": candidate,
                "public_receipt_sha256": matched._component_hash(candidate),
            }
        )
        private: dict[str, object] = {
            "environment_preflight": preflight,
        }
        matched._terminal_preflight_candidate(private, public)
        return private, public, candidate

    def test_incident_envelope_schema_is_closed(self) -> None:
        envelope = matched._new_preflight_incident_envelope()
        envelope["provider_output"] = "must never be accepted"

        with self.assertRaisesRegex(
            ValueError,
            "Preflight incident envelope is invalid",
        ):
            matched._validate_preflight_incident_envelope(envelope)

    def test_minimal_candidate_preserves_actual_phase_and_durable_counts(
        self,
    ) -> None:
        private, public, candidate = self._sealed_fixture(
            phase="provider_returned"
        )

        self.assertEqual(candidate["incident_phase"], "provider_returned")
        self.assertEqual(candidate["profiles_recorded"], 3)
        self.assertEqual(candidate["profiles_terminal"], 2)
        self.assertEqual(
            candidate["model_invocations_conservatively_chargeable"],
            2,
        )
        preflight, validated = matched._terminal_preflight_candidate(
            private,
            public,
        )
        self.assertEqual(validated, candidate)
        self.assertEqual(
            preflight["incident_envelope"]["phase"],
            "terminal_candidate_commit",
        )

    def test_terminal_candidate_rejects_extra_keys(self) -> None:
        private, public, candidate = self._sealed_fixture()
        candidate["raw_provider_output"] = "must never cross the boundary"
        private["environment_preflight"]["public_receipt_sha256"] = (
            matched._component_hash(candidate)
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Terminal preflight control envelope is invalid",
        ):
            matched._terminal_preflight_candidate(private, public)

    def test_terminal_candidate_rejects_durable_count_mismatch(self) -> None:
        private, public, candidate = self._sealed_fixture()
        candidate["model_invocations_conservatively_chargeable"] = 1
        private["environment_preflight"]["public_receipt_sha256"] = (
            matched._component_hash(candidate)
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Terminal preflight control envelope is invalid",
        ):
            matched._terminal_preflight_candidate(private, public)

    def test_seal_persists_candidate_before_any_public_binding(self) -> None:
        public: dict[str, object] = {
            "precommitment_sha256": PRECOMMITMENT,
        }
        state: dict[str, object] = {
            "status": "prepared",
            "assignments": [],
            "environment_preflight": {
                "status": "claimed",
                "attempts": [],
                "incident_envelope": (
                    matched._new_preflight_incident_envelope()
                ),
            },
        }
        writes: list[dict[str, object]] = []

        def load_private_state(
            _path: Path,
            _key: bytes,
        ) -> dict[str, object]:
            return copy.deepcopy(state)

        def write_private_state(
            _path: Path,
            value: dict[str, object],
            _key: bytes,
        ) -> None:
            snapshot = copy.deepcopy(value)
            writes.append(snapshot)
            state.clear()
            state.update(snapshot)

        with (
            patch.object(
                matched,
                "_existing_path_without_final_symlink",
                side_effect=lambda path: path,
            ),
            patch.object(
                matched,
                "_read_authentication_key",
                return_value=AUTHENTICATION_KEY,
            ),
            patch.object(
                matched,
                "_exclusive_run_lock",
                return_value=nullcontext(),
            ),
            patch.object(
                matched,
                "_load_private_state",
                side_effect=load_private_state,
            ),
            patch.object(
                matched,
                "_write_private_state",
                side_effect=write_private_state,
            ),
            patch.object(matched, "_load_json", return_value=public),
            patch.object(matched, "_validate_public_hash"),
            patch.object(matched, "_assert_private_public_panel_binding"),
        ):
            candidate = (
                matched._seal_minimal_terminal_preflight_candidate(
                    authentication_key_file=Path("/unused/auth.key"),
                    private_state_path=Path("/unused/private.json"),
                    public_manifest_path=Path("/unused/manifest.json"),
                )
            )

        self.assertEqual(len(writes), 1)
        persisted = writes[0]["environment_preflight"]
        self.assertEqual(persisted["terminal_public_receipt"], candidate)
        self.assertEqual(
            persisted["public_receipt_sha256"],
            matched._component_hash(candidate),
        )
        self.assertNotIn("public_receipt_binding", persisted)
        self.assertEqual(
            persisted["incident_envelope"]["phase"],
            "terminal_candidate_commit",
        )

    def test_provider_free_audit_reconciles_and_returns_exact_contract(
        self,
    ) -> None:
        private, public, candidate = self._sealed_fixture(
            phase="aggregate_projection"
        )
        state = copy.deepcopy(private)
        writes: list[dict[str, object]] = []
        original_load_json = matched._load_json

        def load_private_state(
            _path: Path,
            _key: bytes,
        ) -> dict[str, object]:
            return copy.deepcopy(state)

        def write_private_state(
            _path: Path,
            value: dict[str, object],
            _key: bytes,
        ) -> None:
            snapshot = copy.deepcopy(value)
            writes.append(snapshot)
            state.clear()
            state.update(snapshot)

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = root / "results"
            results.mkdir()
            manifest_path = (
                results / f"{matched.PANEL_ID}.manifest.json"
            )
            output_path = (
                results / f"{matched.PANEL_ID}.preflight.json"
            )

            def load_json(path: Path) -> dict[str, object]:
                if Path(path) == manifest_path:
                    return copy.deepcopy(public)
                return original_load_json(Path(path))

            with (
                patch.object(
                    matched,
                    "_existing_path_without_final_symlink",
                    side_effect=lambda path: path,
                ),
                patch.object(
                    matched,
                    "_read_authentication_key",
                    return_value=AUTHENTICATION_KEY,
                ),
                patch.object(
                    matched,
                    "_exclusive_run_lock",
                    return_value=nullcontext(),
                ),
                patch.object(
                    matched,
                    "_load_private_state",
                    side_effect=load_private_state,
                ),
                patch.object(
                    matched,
                    "_write_private_state",
                    side_effect=write_private_state,
                ),
                patch.object(
                    matched,
                    "_load_json",
                    side_effect=load_json,
                ),
                patch.object(matched, "_validate_public_hash"),
                patch.object(
                    matched,
                    "_assert_private_public_panel_binding",
                ),
                patch.object(
                    matched,
                    "assert_durable_live_execution_paths",
                ),
                patch.object(
                    matched,
                    "evaluate_local_cli_agent",
                    side_effect=AssertionError(
                        "provider execution is forbidden during audit"
                    ),
                ) as provider_call,
            ):
                audit = matched.audit_terminal_incident(
                    root=root,
                    operation="preflight",
                    authentication_key_file=root / "auth.key",
                    private_state_path=root / "private.json",
                    public_manifest_path=manifest_path,
                    public_output_path=output_path,
                )

            expected_keys = {
                "schema_version",
                "panel_id",
                "operation",
                "status",
                "terminal_status",
                "incident_code",
                "incident_phase",
                "attempted_operation",
                "completed_operation",
                "contract_failure_code",
                "model_invocations_conservatively_chargeable",
                "file_sha256",
                "provider_processes_started",
                "authentication_processes_started",
                "model_calls_started",
            }
            self.assertEqual(set(audit), expected_keys)
            self.assertEqual(
                audit["incident_code"],
                "unexpected_control_path_failure",
            )
            self.assertEqual(audit["incident_phase"], "aggregate_projection")
            self.assertIsNone(audit["attempted_operation"])
            self.assertIsNone(audit["completed_operation"])
            self.assertIsNone(audit["contract_failure_code"])
            self.assertEqual(
                audit["model_invocations_conservatively_chargeable"],
                2,
            )
            self.assertEqual(audit["provider_processes_started"], 0)
            self.assertEqual(audit["authentication_processes_started"], 0)
            self.assertEqual(audit["model_calls_started"], 0)
            provider_call.assert_not_called()

            self.assertTrue(writes)
            reconciled_preflight = state["environment_preflight"]
            self.assertIn(
                "public_receipt_binding",
                reconciled_preflight,
            )
            self.assertEqual(
                reconciled_preflight["incident_envelope"]["phase"],
                "public_receipt_commit",
            )
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                candidate,
            )

    def test_rich_candidate_double_publication_failure_stays_auditable(
        self,
    ) -> None:
        private, public, candidate = self._rich_sealed_fixture()
        state = copy.deepcopy(private)

        def load_private_state(
            _path: Path,
            _key: bytes,
        ) -> dict[str, object]:
            return copy.deepcopy(state)

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = root / "results"
            results.mkdir()
            manifest_path = (
                results / f"{matched.PANEL_ID}.manifest.json"
            )
            output_path = (
                results / f"{matched.PANEL_ID}.preflight.json"
            )
            with (
                patch.dict(
                    os.environ,
                    {"CURSOR_API_KEY": "offline-test-key"},
                    clear=False,
                ),
                patch.object(
                    matched,
                    "_existing_path_without_final_symlink",
                    side_effect=lambda path: path,
                ),
                patch.object(
                    matched,
                    "_read_authentication_key",
                    return_value=AUTHENTICATION_KEY,
                ),
                patch.object(
                    matched,
                    "_exclusive_run_lock",
                    return_value=nullcontext(),
                ),
                patch.object(
                    matched,
                    "_load_private_state",
                    side_effect=load_private_state,
                ),
                patch.object(matched, "_load_json", return_value=public),
                patch.object(matched, "_validate_public_hash"),
                patch.object(
                    matched,
                    "_assert_private_public_panel_binding",
                ),
                patch.object(
                    matched,
                    "_claim_preflight_incident_envelope",
                ),
                patch.object(
                    matched,
                    "_run_environment_preflight_core_claimed",
                    side_effect=RuntimeError(
                        "first rich-candidate publication failure"
                    ),
                ),
                patch.object(
                    matched,
                    "_repository_receipt_binding",
                    side_effect=OSError(
                        "second rich-candidate publication failure"
                    ),
                ),
            ):
                payload = matched._run_environment_preflight_core(
                    root=root,
                    authentication_key_file=root / "auth.key",
                    claude_secure_storage_dir=root / "claude",
                    codex_secure_storage_dir=root / "codex",
                    private_state_path=root / "private.json",
                    public_manifest_path=manifest_path,
                    public_preflight_path=output_path,
                    acknowledge_unbounded_provider_spend=True,
                )
                sealed = matched.assert_terminal_incident_ready_for_exit(
                    root=root,
                    operation="preflight",
                    authentication_key_file=root / "auth.key",
                    private_state_path=root / "private.json",
                    public_manifest_path=manifest_path,
                    public_output_path=output_path,
                )

        self.assertEqual(payload["status"], "failed_incident_sealed")
        self.assertEqual(
            payload["incident_phase"],
            "final_supervisor_attestation",
        )
        self.assertEqual(payload["profiles_recorded"], 3)
        self.assertEqual(payload["profiles_terminal"], 3)
        self.assertEqual(
            payload["model_invocations_conservatively_chargeable"],
            2,
        )
        self.assertEqual(
            sealed["terminal_status"],
            candidate["status"],
        )
        self.assertEqual(
            sealed["incident_phase"],
            "final_supervisor_attestation",
        )

    def test_provider_free_audit_reconciles_rich_terminal_candidate(
        self,
    ) -> None:
        private, public, candidate = self._rich_sealed_fixture()
        state = copy.deepcopy(private)

        def load_private_state(
            _path: Path,
            _key: bytes,
        ) -> dict[str, object]:
            return copy.deepcopy(state)

        def write_private_state(
            _path: Path,
            value: dict[str, object],
            _key: bytes,
        ) -> None:
            state.clear()
            state.update(copy.deepcopy(value))

        original_load_json = matched._load_json
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = root / "results"
            results.mkdir()
            manifest_path = (
                results / f"{matched.PANEL_ID}.manifest.json"
            )
            output_path = (
                results / f"{matched.PANEL_ID}.preflight.json"
            )

            def load_json(path: Path) -> dict[str, object]:
                if Path(path) == manifest_path:
                    return copy.deepcopy(public)
                return original_load_json(Path(path))

            with (
                patch.object(
                    matched,
                    "_existing_path_without_final_symlink",
                    side_effect=lambda path: path,
                ),
                patch.object(
                    matched,
                    "_read_authentication_key",
                    return_value=AUTHENTICATION_KEY,
                ),
                patch.object(
                    matched,
                    "_exclusive_run_lock",
                    return_value=nullcontext(),
                ),
                patch.object(
                    matched,
                    "_load_private_state",
                    side_effect=load_private_state,
                ),
                patch.object(
                    matched,
                    "_write_private_state",
                    side_effect=write_private_state,
                ),
                patch.object(matched, "_load_json", side_effect=load_json),
                patch.object(matched, "_validate_public_hash"),
                patch.object(
                    matched,
                    "_assert_private_public_panel_binding",
                ),
                patch.object(
                    matched,
                    "assert_durable_live_execution_paths",
                ),
            ):
                audit = matched.audit_terminal_incident(
                    root=root,
                    operation="preflight",
                    authentication_key_file=root / "auth.key",
                    private_state_path=root / "private.json",
                    public_manifest_path=manifest_path,
                    public_output_path=output_path,
                )

            self.assertEqual(
                audit["terminal_status"],
                "stopped_supervisor_incident",
            )
            self.assertEqual(
                audit["incident_code"],
                "supervisor_boundary_attestation_failed",
            )
            self.assertEqual(
                audit["incident_phase"],
                "final_supervisor_attestation",
            )
            self.assertIsNone(audit["attempted_operation"])
            self.assertIsNone(audit["completed_operation"])
            self.assertIsNone(audit["contract_failure_code"])
            self.assertEqual(
                audit["model_invocations_conservatively_chargeable"],
                2,
            )
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                candidate,
            )


if __name__ == "__main__":
    unittest.main()
