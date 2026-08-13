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


_PREPARATION_OPERATIONS = (
    "preparation_runtime_bound_contract",
    "preparation_runtime_starsim_smoke",
    "preparation_runtime_episode_startup_smoke",
    "preparation_runtime_cache_identity",
    "preparation_runtime_private_cache_binding",
)


class V48PreparationSubstageTests(unittest.TestCase):
    @staticmethod
    def _prerequisite_bundle(
        public: dict[str, object],
    ) -> dict[str, object]:
        authentication_sha256 = "sha256:" + "5" * 64
        return {
            "schema_version": (matched._PROVIDER_FREE_PRECLAIM_PREREQUISITE_SCHEMA),
            "panel_id": matched.PANEL_ID,
            "public_precommitment_sha256": public["precommitment_sha256"],
            "spend_authorization_receipt_sha256": ("sha256:" + "6" * 64),
            "authentication_receipt_sha256": authentication_sha256,
            "authentication_repository_binding": {
                "schema_version": matched._PUBLIC_RECEIPT_BINDING_SCHEMA,
                "artifact_kind": "authentication",
                "repository_relative_path": (
                    f"results/{matched.PANEL_ID}.authentication.json"
                ),
                "file_sha256": "sha256:" + "7" * 64,
                "content_sha256": authentication_sha256,
                "published_commit": "8" * 40,
            },
            "supervisor_execution_binding": {
                "operation": "preflight",
                "label": "com.epiagentbench.preflight",
                "execution_context_sha256": "sha256:" + "9" * 64,
                "config_file_sha256": "sha256:" + "a" * 64,
                "panel_id": matched.PANEL_ID,
                "precommitment_sha256": public["precommitment_sha256"],
            },
            "provider_processes_started": 0,
            "authentication_processes_started": 0,
            "model_calls_started": 0,
        }

    @staticmethod
    def _public_contract() -> tuple[dict[str, object], dict[str, object]]:
        source_contract = {"source": "test"}
        cli_contract = {"cli": "test"}
        runtime_contract = {"runtime": "test"}
        provider_free_environment = {"environment": "test"}
        starsim_smoke = {"smoke": "starsim"}
        episode_startup_smoke = {"smoke": "episode-startup"}
        runtime_cache = {"cache": "identity"}
        bound: dict[str, object] = {
            "schema_version": matched._BOUND_PREPARATION_RUNTIME_SCHEMA,
            "panel_id": matched.PANEL_ID,
            "required_starsim_version": matched.REQUIRED_STARSIM_VERSION,
            "published_receipt_path": (f"results/{matched.PANEL_ID}.runtime.json"),
            "published_receipt_file_sha256": "sha256:" + "1" * 64,
            "published_benchmark_base_commit": "2" * 40,
            "verified_benchmark_base_commit": "3" * 40,
            "source_contract_sha256": matched._component_hash(source_contract),
            "cli_contract_sha256": matched._component_hash(cli_contract),
            "provider_free_environment_contract": (provider_free_environment),
            "provider_free_environment_contract_sha256": (
                matched._component_hash(provider_free_environment)
            ),
            "runtime_contract_sha256": matched._component_hash(runtime_contract),
            "runtime_cache_contract_sha256": matched._component_hash(runtime_cache),
            "starsim_smoke_contract": starsim_smoke,
            "starsim_smoke_contract_sha256": matched._component_hash(starsim_smoke),
            "episode_startup_smoke_contract": episode_startup_smoke,
            "episode_startup_smoke_contract_sha256": (
                matched._component_hash(episode_startup_smoke)
            ),
            "runtime_identity_sha256": "sha256:" + "0" * 64,
        }
        bound["runtime_identity_sha256"] = matched._preparation_runtime_identity(bound)
        public: dict[str, object] = {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "status": "precommitted",
            "benchmark_base_commit": "3" * 40,
            "precommitment_sha256": "sha256:" + "4" * 64,
            "source_contract": source_contract,
            "cli_contract": cli_contract,
            "runtime_contract": runtime_contract,
            "preparation_runtime_contract": bound,
            "contract_hashes": {
                "preparation_runtime_sha256": matched._component_hash(bound)
            },
        }
        return public, runtime_cache

    @staticmethod
    def _passed_preclaim(public: dict[str, object]) -> dict[str, object]:
        trace = matched._new_provider_free_preclaim(
            public,
            prerequisite_bundle=(
                V48PreparationSubstageTests._prerequisite_bundle(public)
            ),
        )
        trace = matched._advance_provider_free_preclaim_operation(
            trace,
            operation="contract_internal",
        )
        trace = matched._advance_provider_free_preclaim_operation(
            trace,
            operation="assignment_state",
        )
        for operation in _PREPARATION_OPERATIONS:
            trace = matched._advance_provider_free_preclaim_operation(
                trace,
                operation=operation,
            )
        trace = matched._complete_provider_free_preclaim(trace)
        return matched._validate_provider_free_preclaim(
            trace,
            public_precommitment_sha256=public["precommitment_sha256"],
            preparation_runtime_contract_sha256=public["contract_hashes"][
                "preparation_runtime_sha256"
            ],
            required_status="passed",
        )

    @staticmethod
    def _private_state(public: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "status": "prepared",
            "public_precommitment_sha256": public["precommitment_sha256"],
            "assignments": [],
            "environment_preflight": {
                "status": "required",
                "required_contract_hashes": {
                    "preparation_runtime_sha256": public["contract_hashes"][
                        "preparation_runtime_sha256"
                    ]
                },
            },
        }

    def test_substage_completion_is_recorded_only_after_success(self) -> None:
        public, _ = self._public_contract()
        trace = matched._new_provider_free_preclaim(
            public,
            prerequisite_bundle=self._prerequisite_bundle(public),
        )
        trace = matched._advance_provider_free_preclaim_operation(
            trace,
            operation="contract_internal",
        )
        trace = matched._advance_provider_free_preclaim_operation(
            trace,
            operation="assignment_state",
        )

        for index, operation in enumerate(_PREPARATION_OPERATIONS):
            trace = matched._advance_provider_free_preclaim_operation(
                trace,
                operation=operation,
            )
            self.assertEqual(trace["attempted_operation"], operation)
            self.assertEqual(
                trace["completed_preparation_operations"],
                list(_PREPARATION_OPERATIONS[:index]),
            )

        trace = matched._complete_provider_free_preclaim(trace)
        self.assertEqual(trace["status"], "passed")
        self.assertEqual(
            trace["completed_preparation_operations"],
            list(_PREPARATION_OPERATIONS),
        )

    def test_exact_cache_inventory_runs_once_and_stages_are_finite(
        self,
    ) -> None:
        public, runtime_cache = self._public_contract()
        operations: list[str] = []
        with (
            patch.object(
                matched,
                "_valid_provider_free_preparation_environment_contract",
                return_value=True,
            ),
            patch.object(
                matched,
                "_valid_preparation_episode_startup_smoke",
                return_value=True,
            ),
            patch.object(
                matched,
                "_runtime_cache_root_path_from_environment",
                return_value=Path("/private/runtime-cache"),
            ),
            patch.object(
                matched,
                "_runtime_cache_contract",
                return_value=runtime_cache,
            ) as inventory,
            patch.object(
                matched,
                "_preparation_runtime_smoke",
                return_value=public["preparation_runtime_contract"][
                    "starsim_smoke_contract"
                ],
            ),
            patch.object(
                matched,
                "_preparation_episode_startup_smoke",
                return_value=public["preparation_runtime_contract"][
                    "episode_startup_smoke_contract"
                ],
            ),
        ):
            matched._validate_bound_preparation_runtime(
                public,
                rerun_smoke=True,
                operation_recorder=operations.append,
            )

        self.assertEqual(
            operations,
            list(_PREPARATION_OPERATIONS[:4]),
        )
        inventory.assert_called_once_with(Path("/private/runtime-cache"))

    def test_passed_preclaim_reuses_cache_and_smoke_attestations(self) -> None:
        public, _ = self._public_contract()
        trace = self._passed_preclaim(public)
        operations: list[str] = []
        forbidden = AssertionError("expensive preparation check was rerun")
        with (
            patch.object(
                matched,
                "_valid_provider_free_preparation_environment_contract",
                return_value=True,
            ),
            patch.object(
                matched,
                "_valid_preparation_episode_startup_smoke",
                return_value=True,
            ),
            patch.object(
                matched,
                "_runtime_cache_contract",
                side_effect=forbidden,
            ) as inventory,
            patch.object(
                matched,
                "_preparation_runtime_smoke",
                side_effect=forbidden,
            ) as starsim,
            patch.object(
                matched,
                "_preparation_episode_startup_smoke",
                side_effect=forbidden,
            ) as episode_startup,
        ):
            matched._validate_bound_preparation_runtime(
                public,
                rerun_smoke=True,
                operation_recorder=operations.append,
                provider_free_preclaim=trace,
            )

        self.assertEqual(operations, list(_PREPARATION_OPERATIONS[:4]))
        inventory.assert_not_called()
        starsim.assert_not_called()
        episode_startup.assert_not_called()

    def test_claim_is_after_persisted_provider_free_pass(self) -> None:
        public, _ = self._public_contract()
        state = self._private_state(public)
        writes: list[dict[str, object]] = []

        def write_state(
            _path: Path,
            value: dict[str, object],
            _key: bytes,
        ) -> None:
            snapshot = copy.deepcopy(value)
            writes.append(snapshot)
            state.clear()
            state.update(snapshot)

        def validate_contracts(**kwargs: object) -> None:
            recorder = kwargs["operation_recorder"]
            recorder("assignment_state")
            for operation in _PREPARATION_OPERATIONS:
                recorder(operation)
                durable_trace = writes[-1]["environment_preflight"][
                    "provider_free_preclaim"
                ]
                self.assertEqual(durable_trace["attempted_operation"], operation)
            self.assertNotIn(
                operation,
                durable_trace["completed_preparation_operations"],
            )

        forbidden = AssertionError("provider boundary crossed")
        with (
            TemporaryDirectory() as temporary,
            patch.object(
                matched,
                "_existing_path_without_final_symlink",
                side_effect=lambda path: Path(path),
            ),
            patch.object(
                matched,
                "_read_authentication_key",
                return_value=b"k" * 32,
            ),
            patch.object(
                matched,
                "_exclusive_run_lock",
                return_value=nullcontext(),
            ),
            patch.object(
                matched,
                "_load_private_state",
                return_value=state,
            ),
            patch.object(matched, "_load_json", return_value=public),
            patch.object(matched, "_validate_public_hash"),
            patch.object(matched, "_assert_private_public_panel_binding"),
            patch.object(
                matched,
                "_provider_free_preclaim_prerequisite_bundle",
                return_value=self._prerequisite_bundle(public),
            ),
            patch.object(
                matched,
                "_validate_claude_secure_storage_dir",
                return_value=Path(temporary) / "claude",
            ),
            patch.object(
                matched,
                "_validate_codex_secure_storage_dir",
                return_value=Path(temporary) / "codex",
            ),
            patch.object(
                matched,
                "_validate_contracts",
                side_effect=validate_contracts,
            ),
            patch.object(
                matched,
                "_write_private_state",
                side_effect=write_state,
            ),
            patch.object(
                matched,
                "evaluate_local_cli_agent",
                side_effect=forbidden,
            ) as evaluator,
            patch.object(
                matched,
                "resolve_provider_cli",
                side_effect=forbidden,
            ) as provider_cli,
        ):
            trace = matched._claim_preflight_incident_envelope(
                root=Path(temporary),
                authentication_key_file=Path(temporary) / "auth.key",
                claude_secure_storage_dir=Path(temporary) / "claude",
                codex_secure_storage_dir=Path(temporary) / "codex",
                private_state_path=Path(temporary) / "private.json",
                public_manifest_path=Path(temporary) / "manifest.json",
                public_preflight_path=Path(temporary) / "preflight.json",
                supervisor_runtime_dir=Path(temporary) / "supervisor",
                require_persistent_supervisor=True,
            )

        self.assertEqual(trace["status"], "passed")
        self.assertEqual(
            trace["completed_preparation_operations"],
            list(_PREPARATION_OPERATIONS),
        )
        self.assertEqual(state["environment_preflight"]["status"], "claimed")
        self.assertEqual(
            state["environment_preflight"]["provider_free_preclaim"],
            trace,
        )
        self.assertTrue(
            all(
                snapshot["environment_preflight"]["status"] == "required"
                for snapshot in writes[:-1]
            )
        )
        evaluator.assert_not_called()
        provider_cli.assert_not_called()

    def test_each_preparation_failure_is_zero_call_and_not_claimed(self) -> None:
        public, _ = self._public_contract()
        forbidden_secret = "/hidden/private/episode-047.json"
        forbidden = AssertionError("provider boundary crossed")

        for failed_operation in _PREPARATION_OPERATIONS:
            with self.subTest(failed_operation=failed_operation):
                state = self._private_state(public)

                def write_state(
                    _path: Path,
                    value: dict[str, object],
                    _key: bytes,
                ) -> None:
                    snapshot = copy.deepcopy(value)
                    state.clear()
                    state.update(snapshot)

                def validate_contracts(**kwargs: object) -> None:
                    recorder = kwargs["operation_recorder"]
                    recorder("assignment_state")
                    for operation in _PREPARATION_OPERATIONS:
                        recorder(operation)
                        if operation == failed_operation:
                            raise RuntimeError(forbidden_secret)

                with (
                    TemporaryDirectory() as temporary,
                    patch.object(
                        matched,
                        "_existing_path_without_final_symlink",
                        side_effect=lambda path: Path(path),
                    ),
                    patch.object(
                        matched,
                        "_read_authentication_key",
                        return_value=b"k" * 32,
                    ),
                    patch.object(
                        matched,
                        "_exclusive_run_lock",
                        return_value=nullcontext(),
                    ),
                    patch.object(
                        matched,
                        "_load_private_state",
                        return_value=state,
                    ),
                    patch.object(matched, "_load_json", return_value=public),
                    patch.object(matched, "_validate_public_hash"),
                    patch.object(
                        matched,
                        "_assert_private_public_panel_binding",
                    ),
                    patch.object(
                        matched,
                        "_provider_free_preclaim_prerequisite_bundle",
                        return_value=self._prerequisite_bundle(public),
                    ),
                    patch.object(
                        matched,
                        "_validate_claude_secure_storage_dir",
                        return_value=Path(temporary) / "claude",
                    ),
                    patch.object(
                        matched,
                        "_validate_codex_secure_storage_dir",
                        return_value=Path(temporary) / "codex",
                    ),
                    patch.object(
                        matched,
                        "_validate_contracts",
                        side_effect=validate_contracts,
                    ),
                    patch.object(
                        matched,
                        "_write_private_state",
                        side_effect=write_state,
                    ),
                    patch.object(
                        matched,
                        "evaluate_local_cli_agent",
                        side_effect=forbidden,
                    ) as evaluator,
                    patch.object(
                        matched,
                        "resolve_provider_cli",
                        side_effect=forbidden,
                    ) as provider_cli,
                    self.assertRaises(matched._PreflightControlBoundaryError) as raised,
                ):
                    matched._claim_preflight_incident_envelope(
                        root=Path(temporary),
                        authentication_key_file=(Path(temporary) / "auth.key"),
                        claude_secure_storage_dir=(Path(temporary) / "claude"),
                        codex_secure_storage_dir=(Path(temporary) / "codex"),
                        private_state_path=(Path(temporary) / "private.json"),
                        public_manifest_path=(Path(temporary) / "manifest.json"),
                        public_preflight_path=(Path(temporary) / "preflight.json"),
                        supervisor_runtime_dir=(Path(temporary) / "supervisor"),
                        require_persistent_supervisor=True,
                    )

                error = raised.exception
                self.assertEqual(
                    error.attempted_operation,
                    failed_operation,
                )
                self.assertNotIn(forbidden_secret, str(error))
                preflight = state["environment_preflight"]
                self.assertEqual(preflight["status"], "failed")
                self.assertNotIn("incident_envelope", preflight)
                candidate = preflight["terminal_public_receipt"]
                self.assertEqual(candidate["profiles_recorded"], 0)
                self.assertEqual(
                    candidate["model_invocations_conservatively_chargeable"],
                    0,
                )
                self.assertNotIn(
                    forbidden_secret,
                    json.dumps(candidate, sort_keys=True),
                )
                _, validated_candidate = matched._terminal_preflight_candidate(
                    state, public
                )
                projection = matched._sealed_terminal_preflight_projection(
                    preflight,
                    validated_candidate,
                )
                self.assertEqual(
                    projection["incident_phase"],
                    "provider_free_preclaim_validation",
                )
                evaluator.assert_not_called()
                provider_cli.assert_not_called()

    def test_outer_publishes_preclaim_failure_without_paid_claim_seal(
        self,
    ) -> None:
        error = matched._PreflightControlBoundaryError(
            incident_code="contract_attestation_failed",
            attempted_operation=("preparation_runtime_episode_startup_smoke"),
            completed_operation="preparation_runtime_starsim_smoke",
            contract_failure_code=("preparation_runtime_episode_startup_smoke_failed"),
        )
        expected = {
            "status": "failed",
            "model_invocations_conservatively_chargeable": 0,
        }
        with (
            patch.dict(
                os.environ,
                {},
                clear=True,
            ),
            patch.object(
                matched,
                "_claim_preflight_incident_envelope",
                side_effect=error,
            ) as claim,
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
            ) as paid_preflight,
            patch.object(
                matched,
                "_seal_minimal_terminal_preflight_candidate",
            ) as paid_claim_seal,
            patch.object(
                matched,
                "_publish_terminal_preflight_candidate",
                return_value=expected,
            ) as publish,
        ):
            result = matched._run_environment_preflight_core(
                root=Path("/unused/root"),
                authentication_key_file=Path("/unused/auth.key"),
                claude_secure_storage_dir=Path("/unused/claude"),
                codex_secure_storage_dir=Path("/unused/codex"),
                private_state_path=Path("/unused/private.json"),
                public_manifest_path=Path("/unused/manifest.json"),
                public_preflight_path=Path("/unused/preflight.json"),
                supervisor_runtime_dir=Path("/unused/supervisor"),
                require_persistent_supervisor=True,
                cursor_credential_loader=lambda: "unused",
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertIs(result, expected)
        claim.assert_called_once()
        offline_claim.assert_not_called()
        paid_preflight.assert_not_called()
        paid_claim_seal.assert_not_called()
        publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
