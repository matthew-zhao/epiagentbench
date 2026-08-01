from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import epiagentbench.development_matched_panel as matched


class V28TypedContractAttestationTests(unittest.TestCase):
    @staticmethod
    @contextmanager
    def _forbid_provider_and_auth_helpers():
        forbidden = AssertionError(
            "typed contract-attestation handling crossed a provider/auth boundary"
        )
        with (
            patch.object(
                matched,
                "evaluate_local_cli_agent",
                side_effect=forbidden,
            ) as evaluator,
            patch.object(
                matched,
                "_execution_evaluator",
                side_effect=forbidden,
            ) as select_evaluator,
            patch.object(
                matched,
                "resolve_provider_cli",
                side_effect=forbidden,
            ) as resolve_provider,
            patch.object(
                matched,
                "authenticate_panel",
                side_effect=forbidden,
            ) as authenticate,
            patch.object(
                matched,
                "assert_panel_authentication_ready",
                side_effect=forbidden,
            ) as attest_authentication,
            patch.object(
                matched,
                "_validate_claude_auth_binding",
                side_effect=forbidden,
            ) as validate_claude_binding,
            patch.object(
                matched,
                "_validate_codex_auth_binding",
                side_effect=forbidden,
            ) as validate_codex_binding,
            patch.object(
                matched,
                "_require_claude_credential_state",
                side_effect=forbidden,
            ) as require_claude,
            patch.object(
                matched,
                "_require_codex_credential_state",
                side_effect=forbidden,
            ) as require_codex,
        ):
            yield (
                evaluator,
                select_evaluator,
                resolve_provider,
                authenticate,
                attest_authentication,
                validate_claude_binding,
                validate_codex_binding,
                require_claude,
                require_codex,
            )

    def test_contract_validation_failure_has_finite_content_free_code(
        self,
    ) -> None:
        persisted: list[dict[str, object]] = []
        secret = "private-path=/hidden/cohort/episode-019.json"

        def persist_control_state(**fields: object) -> None:
            persisted.append(dict(fields))

        def validate_contracts(record_operation: Callable[[str], None]):
            record_operation("public_manifest")
            raise RuntimeError(secret)

        with (
            self._forbid_provider_and_auth_helpers() as forbidden_helpers,
            self.assertRaises(
                matched._PreflightControlBoundaryError
            ) as raised,
        ):
            matched._run_preflight_contract_attestation_boundary(
                persist_control_state=persist_control_state,
                validate_contracts=validate_contracts,
            )

        error = raised.exception
        self.assertEqual(error.incident_code, "contract_attestation_failed")
        self.assertEqual(error.contract_failure_code, "public_manifest_failed")
        self.assertEqual(error.attempted_operation, "public_manifest")
        self.assertEqual(error.completed_operation, "artifact_separation")
        self.assertIsNone(error.__cause__)
        self.assertNotIn(secret, str(error))
        self.assertNotIn(secret, json.dumps(persisted, sort_keys=True))
        self.assertEqual(
            persisted[-1],
            {
                "phase": "contract_attestation",
                "attempted_operation": "public_manifest",
                "completed_operation": "artifact_separation",
                "incident_code": "contract_attestation_failed",
                "contract_failure_code": "public_manifest_failed",
            },
        )
        for helper in forbidden_helpers:
            helper.assert_not_called()

    def test_checkpoint_transition_failure_has_distinct_typed_code(
        self,
    ) -> None:
        persisted: list[dict[str, object]] = []
        secret = "private checkpoint write failed at /hidden/private-state.json"

        def persist_control_state(**fields: object) -> None:
            persisted.append(dict(fields))
            if fields["phase"] == "one_shot_state_validation":
                raise OSError(secret)

        def validate_contracts(record_operation: Callable[[str], None]):
            record_operation("assignment_state")
            return "validated-contracts"

        with (
            self._forbid_provider_and_auth_helpers() as forbidden_helpers,
            self.assertRaises(
                matched._PreflightControlBoundaryError
            ) as raised,
        ):
            matched._run_preflight_contract_attestation_boundary(
                persist_control_state=persist_control_state,
                validate_contracts=validate_contracts,
            )

        error = raised.exception
        self.assertEqual(
            error.incident_code,
            "control_phase_checkpoint_persist_failed",
        )
        self.assertIsNone(error.contract_failure_code)
        self.assertEqual(
            error.attempted_operation,
            "one_shot_state_validation_checkpoint",
        )
        self.assertEqual(error.completed_operation, "contract_attestation")
        self.assertIsNone(error.__cause__)
        self.assertNotIn(secret, str(error))
        self.assertNotIn(secret, json.dumps(persisted, sort_keys=True))
        self.assertEqual(
            persisted[-1],
            {
                "phase": "contract_attestation",
                "attempted_operation": "one_shot_state_validation_checkpoint",
                "completed_operation": "contract_attestation",
                "incident_code": "control_phase_checkpoint_persist_failed",
                "contract_failure_code": None,
            },
        )
        for helper in forbidden_helpers:
            helper.assert_not_called()

    def test_outer_preflight_seal_receives_typed_error_when_diagnostic_write_fails(
        self,
    ) -> None:
        secret = "unavailable diagnostic store at /hidden/private-state.json"

        def persist_control_state(**fields: object) -> None:
            if (
                fields["phase"] == "one_shot_state_validation"
                or fields["incident_code"] is not None
            ):
                raise OSError(secret)

        with self.assertRaises(
            matched._PreflightControlBoundaryError
        ) as raised:
            matched._run_preflight_contract_attestation_boundary(
                persist_control_state=persist_control_state,
                validate_contracts=lambda _record_operation: "validated",
            )
        control_error = raised.exception
        expected_payload = {"status": "failed", "incident_code": "typed"}

        with (
            patch.dict(os.environ, {}, clear=True),
            self._forbid_provider_and_auth_helpers() as forbidden_helpers,
            patch.object(
                matched,
                "_claim_offline_test_preflight_incident_envelope",
            ) as claim,
            patch.object(
                matched,
                "_assert_ephemeral_offline_test_namespace",
            ),
            patch.object(
                matched,
                "_run_environment_preflight_core_claimed",
                side_effect=control_error,
            ),
            patch.object(
                matched,
                "_seal_minimal_terminal_preflight_candidate",
            ) as seal,
            patch.object(
                matched,
                "_publish_terminal_preflight_candidate",
                return_value=expected_payload,
            ) as publish,
        ):
            payload = matched._run_environment_preflight_core(
                root=Path("/unused/root"),
                authentication_key_file=Path("/unused/auth.key"),
                claude_secure_storage_dir=Path("/unused/claude"),
                codex_secure_storage_dir=Path("/unused/codex"),
                private_state_path=Path("/unused/private.json"),
                public_manifest_path=Path("/unused/manifest.json"),
                public_preflight_path=Path("/unused/preflight.json"),
                require_persistent_supervisor=False,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertIs(payload, expected_payload)
        claim.assert_called_once()
        seal.assert_called_once()
        self.assertIs(seal.call_args.kwargs["control_error"], control_error)
        publish.assert_called_once()
        self.assertEqual(
            control_error.incident_code,
            "control_phase_checkpoint_persist_failed",
        )
        self.assertNotIn(secret, str(control_error))
        for helper in forbidden_helpers:
            helper.assert_not_called()

    def test_terminal_projection_preserves_only_typed_safe_diagnostics(
        self,
    ) -> None:
        public = {"precommitment_sha256": "sha256:" + "a" * 64}
        preflight = {
            "status": "claimed",
            "attempts": [],
            "incident_envelope": matched._new_preflight_incident_envelope(),
        }
        matched._advance_preflight_incident_envelope(
            preflight,
            phase="artifact_separation",
            attempted_operation="artifact_separation",
            completed_operation="credential_binding",
        )
        private = {"environment_preflight": preflight}
        control_error = matched._PreflightControlBoundaryError(
            incident_code="contract_attestation_failed",
            attempted_operation="episode_pack_integrity",
            completed_operation="cohort_retirement",
            contract_failure_code="episode_pack_integrity_failed",
        )

        candidate = matched._minimal_terminal_preflight_candidate(
            private=private,
            public=public,
            control_error=control_error,
        )
        projection = matched._sealed_terminal_preflight_projection(
            preflight,
            candidate,
        )

        self.assertEqual(
            projection["incident_code"],
            "contract_attestation_failed",
        )
        self.assertEqual(
            projection["attempted_operation"],
            "episode_pack_integrity",
        )
        self.assertEqual(
            projection["completed_operation"],
            "cohort_retirement",
        )
        self.assertEqual(
            projection["contract_failure_code"],
            "episode_pack_integrity_failed",
        )
        serialized = json.dumps(projection, sort_keys=True)
        for forbidden in ("/hidden/", "exception", "provider_output"):
            self.assertNotIn(forbidden, serialized)

    def test_v29_live_incident_envelope_schema_remains_closed(self) -> None:
        envelope = matched._new_preflight_incident_envelope()
        self.assertEqual(
            envelope["schema_version"],
            "epiagentbench.preflight_incident_envelope.v3",
        )
        self.assertEqual(
            set(envelope),
            {
                "schema_version",
                "status",
                "phase",
                "phase_history",
                "claimed_at_utc",
                "finished_at_utc",
                "profiles_recorded",
                "profiles_terminal",
                "model_invocations_conservatively_chargeable",
                "incident_code",
                "attempted_operation",
                "completed_operation",
                "contract_failure_code",
            },
        )
        self.assertEqual(
            matched._validate_preflight_incident_envelope(envelope),
            envelope,
        )
        envelope["exception_text"] = "must never cross the public boundary"

        with self.assertRaisesRegex(
            ValueError,
            "Preflight incident envelope is invalid",
        ):
            matched._validate_preflight_incident_envelope(envelope)


if __name__ == "__main__":
    unittest.main()
