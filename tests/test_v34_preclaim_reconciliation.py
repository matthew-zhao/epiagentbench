from __future__ import annotations

import copy
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import epiagentbench.development_matched_panel as matched


_PREPARATION_OPERATIONS = matched._PREPARATION_RUNTIME_OPERATIONS


class V34PreclaimReconciliationTests(unittest.TestCase):
    @staticmethod
    def _public() -> dict[str, object]:
        preparation = {"contract": "test"}
        return {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "status": "precommitted",
            "precommitment_sha256": "sha256:" + "1" * 64,
            "contract_hashes": {
                "preparation_runtime_sha256": matched._component_hash(
                    preparation
                )
            },
            "preparation_runtime_contract": preparation,
        }

    @staticmethod
    def _private(public: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": matched.SCHEMA_VERSION,
            "panel_id": matched.PANEL_ID,
            "status": "prepared",
            "public_precommitment_sha256": public[
                "precommitment_sha256"
            ],
            "assignments": [],
            "environment_preflight": {
                "status": "required",
                "required_contract_hashes": {
                    "preparation_runtime_sha256": public[
                        "contract_hashes"
                    ]["preparation_runtime_sha256"]
                },
            },
        }

    @staticmethod
    def _prerequisites(
        public: dict[str, object],
    ) -> dict[str, object]:
        authentication_sha256 = "sha256:" + "2" * 64
        return {
            "schema_version": (
                matched._PROVIDER_FREE_PRECLAIM_PREREQUISITE_SCHEMA
            ),
            "panel_id": matched.PANEL_ID,
            "public_precommitment_sha256": public[
                "precommitment_sha256"
            ],
            "spend_authorization_receipt_sha256": (
                "sha256:" + "3" * 64
            ),
            "authentication_receipt_sha256": authentication_sha256,
            "authentication_repository_binding": {
                "schema_version": matched._PUBLIC_RECEIPT_BINDING_SCHEMA,
                "artifact_kind": "authentication",
                "repository_relative_path": (
                    f"results/{matched.PANEL_ID}.authentication.json"
                ),
                "file_sha256": "sha256:" + "4" * 64,
                "content_sha256": authentication_sha256,
                "published_commit": "5" * 40,
            },
            "supervisor_execution_binding": {
                "operation": "preflight",
                "label": "com.epiagentbench.preflight",
                "execution_context_sha256": "sha256:" + "6" * 64,
                "config_file_sha256": "sha256:" + "7" * 64,
                "panel_id": matched.PANEL_ID,
                "precommitment_sha256": public[
                    "precommitment_sha256"
                ],
            },
            "provider_processes_started": 0,
            "authentication_processes_started": 0,
            "model_calls_started": 0,
        }

    def test_offline_preflight_seam_rejects_nested_repository_namespace(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            namespace = Path(temporary)
            root = namespace / "repository"
            root.mkdir()
            (namespace / ".git").mkdir()
            with (
                patch.object(
                    matched, "_run_environment_preflight_core"
                ) as core,
                self.assertRaisesRegex(
                    RuntimeError, "forbidden in a repository namespace"
                ),
            ):
                matched._run_environment_preflight_for_offline_test(
                    root=root,
                    authentication_key_file=root / "auth.key",
                    claude_secure_storage_dir=namespace / "claude",
                    codex_secure_storage_dir=namespace / "codex",
                    private_state_path=root / "private.json",
                    public_manifest_path=root / "manifest.json",
                    public_preflight_path=root / "preflight.json",
                    offline_test_evaluator=lambda **_kwargs: None,
                )
        core.assert_not_called()

    def test_offline_preflight_seam_rejects_external_credentials(self) -> None:
        with TemporaryDirectory() as temporary:
            namespace = Path(temporary)
            root = namespace / "repository"
            root.mkdir()
            with (
                patch.object(
                    matched, "_run_environment_preflight_core"
                ) as core,
                self.assertRaisesRegex(
                    RuntimeError, "cannot target live credentials"
                ),
            ):
                matched._run_environment_preflight_for_offline_test(
                    root=root,
                    authentication_key_file=root / "auth.key",
                    claude_secure_storage_dir=(
                        Path.home() / ".live-claude-credentials"
                    ),
                    codex_secure_storage_dir=namespace / "codex",
                    private_state_path=root / "private.json",
                    public_manifest_path=root / "manifest.json",
                    public_preflight_path=root / "preflight.json",
                    offline_test_evaluator=lambda **_kwargs: None,
                )
        core.assert_not_called()

    def test_offline_run_seam_rejects_external_mutable_namespace(self) -> None:
        with TemporaryDirectory() as temporary:
            namespace = Path(temporary)
            root = namespace / "repository"
            root.mkdir()
            external_results = root.parent / "live-results.json"
            with (
                patch.object(matched, "_exclusive_run_lock") as lock,
                self.assertRaisesRegex(
                    RuntimeError, "cannot target a live namespace"
                ),
            ):
                matched._run_panel_for_offline_test(
                    root=root,
                    authentication_key_file=root / "auth.key",
                    claude_secure_storage_dir=namespace / "claude",
                    codex_secure_storage_dir=namespace / "codex",
                    private_state_path=root / "private.json",
                    public_manifest_path=root / "manifest.json",
                    public_results_path=external_results,
                    offline_test_evaluator=lambda **_kwargs: None,
                    acknowledge_unbounded_provider_spend=True,
                )
        lock.assert_not_called()

    def _claim_with_fault(
        self,
        *,
        fault_index: int | None,
        replace_before_error: bool,
    ) -> tuple[dict[str, object], list[dict[str, object]], object]:
        public = self._public()
        state = self._private(public)
        writes: list[dict[str, object]] = []
        write_index = 0

        def write(
            _path: Path,
            value: dict[str, object],
            _key: bytes,
        ) -> None:
            nonlocal write_index
            snapshot = copy.deepcopy(value)
            current_index = write_index
            write_index += 1
            writes.append(snapshot)
            if current_index == fault_index and not replace_before_error:
                raise OSError("before replace")
            state.clear()
            state.update(snapshot)
            if current_index == fault_index:
                raise OSError("after replace")

        def validate_contracts(**kwargs: object) -> None:
            recorder = kwargs["operation_recorder"]
            recorder("assignment_state")
            for operation in _PREPARATION_OPERATIONS:
                recorder(operation)

        with (
            TemporaryDirectory() as temporary,
            patch.object(
                matched,
                "_existing_path_without_final_symlink",
                side_effect=lambda path: Path(path),
            ),
            patch.object(
                matched, "_read_authentication_key", return_value=b"k" * 32
            ),
            patch.object(
                matched, "_exclusive_run_lock", return_value=nullcontext()
            ),
            patch.object(
                matched,
                "_load_private_state",
                side_effect=lambda *_args: copy.deepcopy(state),
            ),
            patch.object(matched, "_load_json", return_value=public),
            patch.object(matched, "_validate_public_hash"),
            patch.object(matched, "_assert_private_public_panel_binding"),
            patch.object(
                matched,
                "_provider_free_preclaim_prerequisite_bundle",
                return_value=self._prerequisites(public),
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
                matched, "_write_private_state", side_effect=write
            ),
        ):
            try:
                result: object = matched._claim_preflight_incident_envelope(
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
            except BaseException as error:
                result = error
        return state, writes, result

    def test_before_write_faults_take_one_finite_terminal_path(self) -> None:
        cases = {
            "initial": (0, "contract_internal"),
            "operation": (3, "preparation_runtime_bound_contract"),
            "passed": (8, "preparation_runtime_private_cache_binding"),
            "claim": (9, "preflight_state_claim"),
        }
        for name, (fault_index, attempted) in cases.items():
            with self.subTest(stage=name):
                state, _writes, result = self._claim_with_fault(
                    fault_index=fault_index,
                    replace_before_error=False,
                )
                self.assertIsInstance(
                    result, matched._PreflightControlBoundaryError
                )
                self.assertEqual(result.attempted_operation, attempted)
                self.assertEqual(
                    state["environment_preflight"]["status"], "failed"
                )
                _, candidate = matched._terminal_preflight_candidate(
                    state, self._public()
                )
                projection = matched._sealed_terminal_preflight_projection(
                    state["environment_preflight"], candidate
                )
                self.assertEqual(
                    projection[
                        "model_invocations_conservatively_chargeable"
                    ],
                    0,
                )
                if name == "claim":
                    self.assertEqual(
                        result.incident_code,
                        "preflight_state_claim_checkpoint_persist_failed",
                    )
                    self.assertEqual(
                        result.completed_operation,
                        _PREPARATION_OPERATIONS[-1],
                    )

    def test_exception_after_replace_reconciles_each_boundary(self) -> None:
        for name, fault_index in {
            "initial": 0,
            "operation": 3,
            "passed": 8,
            "claim": 9,
        }.items():
            with self.subTest(stage=name):
                state, writes, result = self._claim_with_fault(
                    fault_index=fault_index,
                    replace_before_error=True,
                )
                self.assertIsInstance(result, dict)
                self.assertEqual(result["status"], "passed")
                self.assertEqual(
                    state["environment_preflight"]["status"], "claimed"
                )
                self.assertEqual(len(writes), 10)

    def test_storage_ambiguity_has_no_follow_on_write(self) -> None:
        prior = {"state": "prior"}
        next_state = {"state": "next"}
        writes = 0

        def fail_write(*_args: object) -> None:
            nonlocal writes
            writes += 1
            raise OSError("write failed")

        with (
            patch.object(
                matched, "_write_private_state", side_effect=fail_write
            ),
            patch.object(
                matched,
                "_load_private_state",
                return_value={"state": "third"},
            ),
            self.assertRaises(matched._PreclaimStorageAmbiguityError),
        ):
            matched._persist_or_reconcile_preclaim_transition(
                private_state_path=Path("/unused/private.json"),
                authentication_key=b"k" * 32,
                prior_private=prior,
                next_private=next_state,
            )
        self.assertEqual(writes, 1)

        with (
            patch.object(
                matched,
                "_claim_preflight_incident_envelope",
                side_effect=matched._PreclaimStorageAmbiguityError(),
            ),
            patch.object(
                matched, "_seal_minimal_terminal_preflight_candidate"
            ) as seal,
            patch.object(
                matched, "_publish_terminal_preflight_candidate"
            ) as publish,
            patch.object(matched, "_assert_canonical_public_output_path"),
            self.assertRaises(matched._PreclaimStorageAmbiguityError),
        ):
            matched._run_environment_preflight_core(
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
        seal.assert_not_called()
        publish.assert_not_called()

    def test_live_preflight_cannot_enter_the_offline_claim_seam(self) -> None:
        with (
            patch.object(matched, "_assert_canonical_public_output_path"),
            patch.object(
                matched,
                "_claim_offline_test_preflight_incident_envelope",
            ) as offline_claim,
            patch.object(
                matched,
                "_claim_preflight_incident_envelope",
                side_effect=matched._PreclaimStorageAmbiguityError(),
            ) as live_claim,
            self.assertRaises(matched._PreclaimStorageAmbiguityError),
        ):
            matched._run_environment_preflight_core(
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
        live_claim.assert_called_once()
        offline_claim.assert_not_called()

    def test_pretrace_prerequisite_failure_has_no_follow_on_action(
        self,
    ) -> None:
        with (
            patch.object(matched, "_assert_canonical_public_output_path"),
            patch.object(
                matched,
                "_claim_preflight_incident_envelope",
                side_effect=RuntimeError("prerequisite mismatch"),
            ),
            patch.object(
                matched, "_seal_minimal_terminal_preflight_candidate"
            ) as seal,
            patch.object(
                matched, "_publish_terminal_preflight_candidate"
            ) as publish,
            patch.object(
                matched,
                "_authenticated_sealed_terminal_preflight_projection",
            ) as projection,
            self.assertRaisesRegex(RuntimeError, "prerequisite mismatch"),
        ):
            matched._run_environment_preflight_core(
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
        seal.assert_not_called()
        publish.assert_not_called()
        projection.assert_not_called()

    def test_offline_claim_seam_is_selected_only_for_injected_tests(
        self,
    ) -> None:
        sentinel = RuntimeError("offline claim sentinel")
        with TemporaryDirectory() as temporary:
            namespace = Path(temporary)
            root = namespace / "repository"
            root.mkdir()
            with (
                patch.object(
                    matched,
                    "_claim_offline_test_preflight_incident_envelope",
                    side_effect=sentinel,
                ) as offline_claim,
                patch.object(
                    matched,
                    "_claim_preflight_incident_envelope",
                ) as live_claim,
                self.assertRaisesRegex(
                    RuntimeError, "offline claim sentinel"
                ),
            ):
                matched._run_environment_preflight_core(
                    root=root,
                    authentication_key_file=root / "auth.key",
                    claude_secure_storage_dir=namespace / "claude",
                    codex_secure_storage_dir=namespace / "codex",
                    private_state_path=root / "private.json",
                    public_manifest_path=root / "manifest.json",
                    public_preflight_path=root / "preflight.json",
                    require_persistent_supervisor=False,
                    offline_test_evaluator=lambda *_args, **_kwargs: None,
                    acknowledge_unbounded_provider_spend=True,
                )
        offline_claim.assert_called_once()
        live_claim.assert_not_called()

    def test_prerequisite_failure_and_direct_invocation_do_not_mutate(self) -> None:
        public = self._public()
        state = self._private(public)
        with (
            patch.object(
                matched,
                "_existing_path_without_final_symlink",
                side_effect=lambda path: Path(path),
            ),
            patch.object(
                matched, "_read_authentication_key", return_value=b"k" * 32
            ),
            patch.object(
                matched, "_exclusive_run_lock", return_value=nullcontext()
            ),
            patch.object(
                matched, "_load_private_state", return_value=state
            ),
            patch.object(matched, "_load_json", return_value=public),
            patch.object(matched, "_validate_public_hash"),
            patch.object(matched, "_assert_private_public_panel_binding"),
            patch.object(
                matched,
                "_provider_free_preclaim_prerequisite_bundle",
                side_effect=RuntimeError("prerequisite failed"),
            ),
            patch.object(matched, "_write_private_state") as write,
            self.assertRaisesRegex(RuntimeError, "prerequisite failed"),
        ):
            matched._claim_preflight_incident_envelope(
                root=Path("/unused/root"),
                authentication_key_file=Path("/unused/auth.key"),
                claude_secure_storage_dir=Path("/unused/claude"),
                codex_secure_storage_dir=Path("/unused/codex"),
                private_state_path=Path("/unused/private.json"),
                public_manifest_path=Path("/unused/manifest.json"),
                public_preflight_path=Path("/unused/preflight.json"),
                supervisor_runtime_dir=Path("/unused/supervisor"),
                require_persistent_supervisor=True,
            )
        write.assert_not_called()

        with (
            patch.object(matched, "_read_authentication_key") as read_key,
            patch.object(matched, "_write_private_state") as direct_write,
            self.assertRaisesRegex(RuntimeError, "persistent supervisor"),
        ):
            matched._claim_preflight_incident_envelope(
                root=Path("/unused/root"),
                authentication_key_file=Path("/unused/auth.key"),
                claude_secure_storage_dir=Path("/unused/claude"),
                codex_secure_storage_dir=Path("/unused/codex"),
                private_state_path=Path("/unused/private.json"),
                public_manifest_path=Path("/unused/manifest.json"),
                public_preflight_path=Path("/unused/preflight.json"),
                supervisor_runtime_dir=None,
                require_persistent_supervisor=False,
            )
        read_key.assert_not_called()
        direct_write.assert_not_called()

    def test_prerequisite_bundle_is_read_only_and_byte_exact(self) -> None:
        public = self._public()
        private = self._private(public)
        prerequisites = self._prerequisites(public)
        receipt = {
            "receipt_sha256": prerequisites[
                "authentication_receipt_sha256"
            ]
        }
        setup = {
            "status": "passed",
            "public_receipt_sha256": receipt["receipt_sha256"],
            "public_receipt_binding": prerequisites[
                "authentication_repository_binding"
            ],
        }
        with (
            patch.object(
                matched,
                "_assert_spend_authorization",
                return_value={
                    "receipt_sha256": prerequisites[
                        "spend_authorization_receipt_sha256"
                    ]
                },
            ),
            patch.object(
                matched,
                "_require_completed_authentication_state",
                return_value=setup,
            ),
            patch.object(matched, "_load_json", return_value=receipt),
            patch.object(matched, "_validate_authentication_receipt"),
            patch.object(
                matched,
                "_validate_repository_receipt_binding",
                return_value=prerequisites[
                    "authentication_repository_binding"
                ],
            ),
            patch.object(
                matched,
                "_assert_exact_public_json_bytes",
                return_value=prerequisites[
                    "authentication_repository_binding"
                ]["file_sha256"],
            ) as exact_bytes,
            patch.object(
                matched,
                "_attest_required_persistent_execution",
                return_value=prerequisites[
                    "supervisor_execution_binding"
                ],
            ),
            patch.object(
                matched,
                "_attest_with_transient_snapshot_retry",
                side_effect=lambda attestation: attestation(),
            ),
            patch.object(
                matched, "_attest_authentication_credentials"
            ) as auth_helper,
            patch.object(
                matched, "_require_claude_credential_state"
            ) as keychain_path,
        ):
            observed = (
                matched._provider_free_preclaim_prerequisite_bundle(
                    root=Path("/repo"),
                    authentication_key_file=Path("/auth.key"),
                    private=private,
                    public=public,
                    public_manifest_path=Path(
                        f"/repo/results/{matched.PANEL_ID}.manifest.json"
                    ),
                    supervisor_runtime_dir=Path("/supervisor"),
                )
            )
        self.assertEqual(observed, prerequisites)
        exact_bytes.assert_called_once()
        auth_helper.assert_not_called()
        keychain_path.assert_not_called()

    def test_exact_passed_shape_and_terminal_regressions(self) -> None:
        public = self._public()
        trace = matched._new_provider_free_preclaim(
            public,
            prerequisite_bundle=self._prerequisites(public),
        )
        for operation in ("contract_internal", "assignment_state"):
            trace = matched._advance_provider_free_preclaim_operation(
                trace, operation=operation
            )
        first_preparation = (
            matched._advance_provider_free_preclaim_operation(
                trace, operation=_PREPARATION_OPERATIONS[0]
            )
        )
        with self.assertRaises(ValueError):
            matched._validate_provider_free_preclaim(
                {
                    **first_preparation,
                    "completed_operation": "contract_internal",
                },
                public_precommitment_sha256=public[
                    "precommitment_sha256"
                ],
                preparation_runtime_contract_sha256=public[
                    "contract_hashes"
                ]["preparation_runtime_sha256"],
                required_status="running",
            )
        for operation in _PREPARATION_OPERATIONS:
            trace = matched._advance_provider_free_preclaim_operation(
                trace, operation=operation
            )
        passed = matched._complete_provider_free_preclaim(trace)
        matched._validate_provider_free_preclaim(
            passed,
            public_precommitment_sha256=public["precommitment_sha256"],
            preparation_runtime_contract_sha256=public["contract_hashes"][
                "preparation_runtime_sha256"
            ],
            required_status="passed",
        )
        for mutation in (
            {"completed_operation": _PREPARATION_OPERATIONS[-2]},
            {
                "completed_preparation_operations": list(
                    _PREPARATION_OPERATIONS[:-1]
                )
            },
        ):
            with self.assertRaises(ValueError):
                matched._validate_provider_free_preclaim(
                    {**passed, **mutation},
                    public_precommitment_sha256=public[
                        "precommitment_sha256"
                    ],
                    preparation_runtime_contract_sha256=public[
                        "contract_hashes"
                    ]["preparation_runtime_sha256"],
                    required_status="passed",
                )
        with self.assertRaises(ValueError):
            matched._advance_provider_free_preclaim_operation(
                passed,
                operation=_PREPARATION_OPERATIONS[-1],
            )
        with self.assertRaises(ValueError):
            matched._fail_provider_free_preclaim(passed)
        failed = matched._fail_provider_free_preclaim(first_preparation)
        with self.assertRaises(ValueError):
            matched._advance_provider_free_preclaim_operation(
                failed,
                operation=_PREPARATION_OPERATIONS[1],
            )
        with self.assertRaises(ValueError):
            matched._complete_provider_free_preclaim(failed)


if __name__ == "__main__":
    unittest.main()
