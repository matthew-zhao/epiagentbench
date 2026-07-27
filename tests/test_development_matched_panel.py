from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from contextlib import contextmanager, ExitStack
import copy
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from examples import run_development_matched_panel as matched_cli
import epiagentbench.development_matched_panel as matched
from epiagentbench.development_matched_panel import (
    ASSIGNMENT_COUNT,
    COHORT_ID,
    EPISODE_COUNT,
    FAMILIES,
    PROFILES,
    REQUIRED_SPEND_ACKNOWLEDGEMENT,
    aggregate_complete_results,
    authorize_panel_spend,
    prepare_panel,
    run_environment_preflight,
    run_panel,
)
from epiagentbench.pilot import (
    CodexAuthenticationIncidentError,
    PilotRunResult,
    ProviderExecutionIsolationError,
    ProviderProcessIsolationError,
    ProviderStateIsolationError,
)
from epiagentbench.replay_trace import replay_trace_sha256
from epiagentbench.trusted.episode_pack import (
    PrivateEpisodeCohortManifest,
    PrivateEpisodePack,
)


GENERATOR = "sha256:" + "a" * 64
AUTHENTICATION_KEY = b"matched panel authentication key".ljust(32, b"!")
SOURCE_CONTRACT = {
    "tracked_runtime_file_count": 40,
    "tracked_runtime_surface_sha256": "sha256:" + "b" * 64,
    "task_prompt_sha256": "sha256:" + "c" * 64,
}
CLI_CONTRACT = {
    "executables": [
        {"name": "claude", "executable_sha256": "sha256:" + "1" * 64},
        {"name": "codex", "executable_sha256": "sha256:" + "2" * 64},
        {
            "name": "cursor-agent",
            "executable_sha256": "sha256:" + "3" * 64,
        },
    ]
}
AUTHENTICATION_DEPENDENCY_IDENTITY = {
    "schema_version": "epiagentbench.authentication_dependency_freeze.v1",
    "glean_helper": {
        "path": "/usr/local/bin/glean-helper",
        "sha256": "sha256:" + "4" * 64,
        "policy": (
            "root_owned_root_group_single_link_regular_nonwritable_executable"
        ),
    },
    "glean_llm_gateway_token_wrapper": {
        "path": "/usr/local/bin/glean-llm-gateway-token",
        "entrypoint_kind": "regular_file",
        "link_text": None,
        "resolved_path": "/usr/local/bin/glean-llm-gateway-token",
        "target_sha256": "sha256:" + "5" * 64,
        "policy": (
            "root_owned_root_group_single_link_regular_nonwritable_executable"
        ),
        "dispatch_contract": {
            "argv0_basename": "glean-llm-gateway-token",
            "arguments": [],
            "option_source": "glean.DefaultOptions",
            "oauth_client_id_source": "explicit_GLEAN_HELPER_OAUTH_CLIENT_ID",
            "credential_path": "$HOME/.glean-llm-gateway/credentials.json",
        },
    },
}
RUNTIME_CONTRACT = {
    "python": "test-python",
    "python_entrypoint_kind": "regular_file",
    "python_executable_sha256": "sha256:" + "d" * 64,
    "starsim": "3.5.1",
    "platform": "test-platform",
    "machine": "test-machine",
}
CLI_VERSIONS = {
    "claude": "claude-test",
    "codex": "codex-test",
    "cursor-agent": "cursor-test",
}

# Production entry points always require authenticated supervision and expose
# no evaluator injection.  This test module routes legacy offline cases
# through private test-only seams; the delegate refuses to call the real
# evaluator if a test forgot to replace it with a fake.  Tests of the live
# supervised path explicitly opt into the unwrapped public API here.
_RUN_PANEL_API = run_panel
_RUN_PREFLIGHT_API = run_environment_preflight
_REAL_EVALUATOR = matched.evaluate_local_cli_agent


def _offline_test_evaluator(*args, **kwargs):
    evaluator = matched.evaluate_local_cli_agent
    if evaluator is _REAL_EVALUATOR:
        raise AssertionError("offline test attempted to invoke the real evaluator")
    return evaluator(*args, **kwargs)


def run_panel(**kwargs):
    supervised = kwargs.pop("require_persistent_supervisor", False)
    evaluator = kwargs.pop("offline_test_evaluator", _offline_test_evaluator)
    if supervised:
        if evaluator is not None and evaluator is not _offline_test_evaluator:
            raise AssertionError("supervised test cannot inject an evaluator")
        return _RUN_PANEL_API(**kwargs)
    kwargs.pop("supervisor_runtime_dir", None)
    return matched._run_panel_for_offline_test(
        **kwargs,
        offline_test_evaluator=evaluator,
    )


def run_environment_preflight(**kwargs):
    supervised = kwargs.pop("require_persistent_supervisor", False)
    evaluator = kwargs.pop("offline_test_evaluator", _offline_test_evaluator)
    if supervised:
        if evaluator is not None and evaluator is not _offline_test_evaluator:
            raise AssertionError("supervised test cannot inject an evaluator")
        return _RUN_PREFLIGHT_API(**kwargs)
    kwargs.pop("supervisor_runtime_dir", None)
    return matched._run_environment_preflight_for_offline_test(
        **kwargs,
        offline_test_evaluator=evaluator,
    )


class MatchedPanelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.secure_temporary = TemporaryDirectory(
            prefix="epiagentbench-claude-auth-", dir=Path.home()
        )
        self.codex_secure_temporary = TemporaryDirectory(
            prefix="epiagentbench-codex-auth-", dir=Path.home()
        )
        self.root = Path(self.temporary.name)
        self.claude_secure_storage_dir = Path(self.secure_temporary.name)
        os.chmod(self.claude_secure_storage_dir, 0o700)
        self.codex_secure_storage_dir = Path(self.codex_secure_temporary.name)
        os.chmod(self.codex_secure_storage_dir, 0o700)
        self.key_path = self.root / "authentication.key"
        self.key_path.write_bytes(AUTHENTICATION_KEY)
        os.chmod(self.key_path, 0o600)
        self.private_path = self.root / "run_artifacts" / "private.json"
        self.public_path = self.root / "results" / "manifest.json"
        self.results_path = self.root / "results" / "results.json"
        self.keychain_present = False

    def tearDown(self) -> None:
        self.temporary.cleanup()
        self.secure_temporary.cleanup()
        self.codex_secure_temporary.cleanup()

    def _cohort(
        self, count: int = EPISODE_COUNT, *, cohort_id: str = COHORT_ID
    ) -> Path:
        cohort = self.root / f"cohort-{count}-{cohort_id}"
        cohort.mkdir(mode=0o700)
        packs: list[PrivateEpisodePack] = []
        for index in range(count):
            family = FAMILIES[index % len(FAMILIES)]
            packs.append(
                PrivateEpisodePack.create(
                    cohort_id=cohort_id,
                    episode_index=index,
                    backend="starsim-ltc-v3",
                    family=family,
                    seed=index + 100,
                    generator_fingerprint=GENERATOR,
                    episode_secret=hashlib.sha256(f"secret-{index}".encode()).digest(),
                    commitment_nonce=hashlib.sha256(
                        f"nonce-{index}".encode()
                    ).digest(),
                )
            )
        manifest = PrivateEpisodeCohortManifest.create(
            packs, manifest_nonce=hashlib.sha256(b"manifest").digest()
        )
        for pack in packs:
            pack.write(cohort / f"episode-{pack.episode_index:06d}.pack", AUTHENTICATION_KEY)
        manifest_path = cohort / "cohort.manifest"
        manifest.write(manifest_path, AUTHENTICATION_KEY)
        return manifest_path

    @staticmethod
    def _git_output(_: Path, *arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return "d" * 40
        if arguments == (
            "ls-files",
            "--error-unmatch",
            "results/manifest.json",
        ):
            return "results/manifest.json"
        if arguments == (
            "ls-files",
            "--error-unmatch",
            "results/development-matched-50x6-v14.authentication.json",
        ):
            return "results/development-matched-50x6-v14.authentication.json"
        return ""

    @staticmethod
    def _glean_config_fixture(
        gateway_url: str = "https://gateway.test/api/v1",
    ) -> dict:
        return {
            "gateway_url": gateway_url,
            "oauth": {
                "claude": {"client_id": "claude-test"},
                "codex": {"client_id": "codex-test"},
            },
        }

    @staticmethod
    def _managed_settings_fixture() -> dict:
        return {
            "apiKeyHelper": str(matched._GLEAN_GATEWAY_TOKEN_WRAPPER_PATH),
            "env": {
                "ANTHROPIC_BASE_URL": (
                    "https://gateway.test/api/v1/anthropic"
                ),
                "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "1800000",
                "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
                "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
                "CLAUDE_CODE_ENABLE_TELEMETRY": 1,
                "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
                "CLAUDE_CODE_USE_VERTEX": 0,
                "ENABLE_TOOL_SEARCH": 1,
                "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.test",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
                "OTEL_LOGS_EXPORTER": "otlp",
                "OTEL_LOGS_EXPORT_INTERVAL": "5000",
                "OTEL_METRICS_EXPORTER": "otlp",
                "OTEL_METRICS_INCLUDE_ACCOUNT_UUID": "true",
                "OTEL_METRIC_EXPORT_INTERVAL": "60000",
                "OTEL_RESOURCE_ATTRIBUTES": "user.email=tester@example.test",
                "USE_CLAUDE_PROJECT_DIR": "1",
            },
            "otelHeadersHelper": str(matched._CLAUDE_OTEL_HELPER_PATH),
        }

    @staticmethod
    def _bootstrap_codex_fixture(path: Path, **kwargs) -> None:
        launch_pending = kwargs.get("invocation_launch_pending")
        started = kwargs.get("invocation_started")
        returned = kwargs.get("invocation_returned")
        if launch_pending is not None:
            launch_pending()
        if started is not None:
            started()
        credential = path / "auth.json"
        credential.write_text('{"test":"opaque"}', encoding="utf-8")
        credential.chmod(0o600)
        if returned is not None:
            returned(0)

    def _bootstrap_glean_fixture(self, *_args, **kwargs) -> None:
        launch_pending = kwargs.get("invocation_launch_pending")
        started = kwargs.get("invocation_started")
        returned = kwargs.get("invocation_returned")
        if launch_pending is not None:
            launch_pending()
        if started is not None:
            started()
        path = _args[0] if _args else self.claude_secure_storage_dir
        credential = Path(path) / "credentials.json"
        if not credential.exists():
            credential.write_text('{"test":"opaque"}', encoding="utf-8")
            credential.chmod(0o600)
        self.keychain_present = True
        if returned is not None:
            returned(0)

    @contextmanager
    def _contracts(self):
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel."
                    "assert_durable_live_execution_paths"
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel._git_output",
                    side_effect=self._git_output,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel._source_contract",
                    return_value=SOURCE_CONTRACT,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel._cli_contract",
                    return_value=CLI_CONTRACT,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel."
                    "_current_glean_auth_dependency_identity",
                    return_value=AUTHENTICATION_DEPENDENCY_IDENTITY,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel._runtime_contract",
                    return_value=RUNTIME_CONTRACT,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel.compute_generator_fingerprint",
                    return_value=GENERATOR,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel."
                    "_attest_claude_secure_storage_keychain",
                    return_value=False,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel."
                    "_attest_managed_glean_credentials",
                    side_effect=lambda _path: self.keychain_present,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel."
                    "_bootstrap_managed_glean_credentials",
                    side_effect=self._bootstrap_glean_fixture,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel."
                    "_bootstrap_codex_credentials",
                    side_effect=self._bootstrap_codex_fixture,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel."
                    "_glean_claude_oauth_client_id",
                    return_value="test-glean-client-id",
                )
            )
            yield

    def _prepare(
        self,
        manifest_path: Path | None = None,
        *,
        authorize: bool = True,
        authenticate: bool = True,
    ) -> dict:
        manifest_path = manifest_path or self._cohort()
        with self._contracts(), patch(
            "epiagentbench.development_matched_panel.secrets.token_bytes",
            return_value=b"s" * 32,
        ):
            public = prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                timeout_seconds=1800,
                claude_max_budget_usd=5.0,
            )
            if authorize:
                authorize_panel_spend(
                    root=self.root,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=self.claude_secure_storage_dir,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
                )
                if authenticate:
                    self._prime_authentication()
            return public

    @staticmethod
    def _result(system: str, model: str, executable: str, total: float) -> PilotRunResult:
        replay_trace = {
            "schema_version": "epiagentbench.aggregate-replay-trace.v1",
            "frame_interval_minutes": 360,
            "frames": [
                {
                    "minute": minute,
                    "active_currently_infected": 2,
                    "active_cumulative_infections": 2,
                    "active_reporting_artifacts": 0,
                    "no_action_currently_infected": 2,
                    "no_action_cumulative_infections": 2,
                    "no_action_reporting_artifacts": 0,
                    "effective_controls": {
                        "infection_control": "off",
                        "source_control": "off",
                        "entry_control": "off",
                        "audit_reporting": "off",
                    },
                }
                for minute in (0, 360)
            ],
            "agent_events": [],
        }
        return PilotRunResult(
            system=system,
            requested_model=model,
            observed_models=() if system == "codex" else (model,),
            cli_version=CLI_VERSIONS[executable],
            development_only=True,
            hermetic=False,
            returncode=0,
            elapsed_seconds=1.0,
            submission={"private": "retained only in private checkpoint"},
            scorecard={
                "valid": True,
                "total": total,
                "dimensions": {name: 0.0 for name in matched.DIMENSION_MAXIMA},
                "metrics": {
                    "integrity_pass": True,
                    "tool_calls": 2,
                    "realized_active_infections": 2,
                    "counterfactual_no_action_infections": 2,
                    "realized_active_artifact_emissions": 0,
                    "counterfactual_no_action_artifact_emissions": 0,
                },
                "violations": [],
            },
            audit_events=(),
            stdout_bytes=10,
            stderr_bytes=0,
            diagnostic="",
            replay_trace=replay_trace,
            timed_out=False,
            progress_telemetry={
                "schema_version": "epiagentbench.provider_progress.v1",
                "observed_elapsed_bucket": "lt_30s",
                "output_seen": True,
                "first_output_elapsed_bucket": "lt_30s",
                "last_output_elapsed_bucket": "lt_30s",
                "combined_output_bytes_bucket": "1_4095",
            },
        )

    @staticmethod
    def _supervisor_attestation(
        operation: str,
        precommitment_sha256: str,
        *,
        label: str = "org.epiagentbench.panel.test.runtime",
        lifecycle: str = "running",
        context_character: str = "7",
        config_character: str = "8",
    ) -> dict:
        return {
            "attested": True,
            "lifecycle": lifecycle,
            "operation": operation,
            "panel_id": matched.PANEL_ID,
            "precommitment_sha256": precommitment_sha256,
            "label": label,
            "execution_context_sha256": (
                "sha256:" + context_character * 64
            ),
            "config_file_sha256": "sha256:" + config_character * 64,
        }

    def _stage_authentication_pending_publication(
        self,
    ) -> tuple[dict, dict]:
        if not (self.codex_secure_storage_dir / "auth.json").exists():
            self._bootstrap_codex_fixture(self.codex_secure_storage_dir)
        if not (
            self.claude_secure_storage_dir / "credentials.json"
        ).exists():
            self._bootstrap_glean_fixture(
                self.claude_secure_storage_dir
            )
        self.keychain_present = True
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        public = matched._load_json(self.public_path)
        private["codex_auth_file_identity"] = matched._codex_auth_file_identity(
            self.codex_secure_storage_dir
        )
        private["managed_glean_auth_file_identity"] = (
            matched._managed_glean_auth_file_identity(
                self.claude_secure_storage_dir
            )
        )
        setup = private["authentication_setup"]
        for provider in ("codex", "managed_glean"):
            setup[provider] = {
                "status": "passed",
                "attempts": [
                    {
                        "status": "passed",
                        "launch_pending_at_utc": "test",
                        "started_at_utc": "test",
                        "returned_at_utc": "test",
                        "returncode": 0,
                        "finished_at_utc": "test",
                    }
                ],
            }
        setup["status"] = "pending_publication"
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        return private, public

    def _prime_authentication(self) -> None:
        private, public = self._stage_authentication_pending_publication()
        matched._publish_authentication_receipt(
            private=private,
            public=public,
            private_state_path=self.private_path,
            public_manifest_path=self.public_path,
            authentication_key=AUTHENTICATION_KEY,
        )

    def _prime_codex_auth(self) -> None:
        self._prime_authentication()

    def _run_with(self, side_effect):
        self._prime_codex_auth()
        self.keychain_present = True
        with patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}), self._contracts(), patch(
            "epiagentbench.development_matched_panel._preflight_execution"
        ), patch(
            "epiagentbench.development_matched_panel._assert_environment_preflight"
        ), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
            side_effect=side_effect,
        ) as evaluate:
            payload = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                require_persistent_supervisor=False,
                offline_test_evaluator=evaluate,
                acknowledge_unbounded_provider_spend=True,
            )
        return payload, evaluate

    def test_supervisor_loss_after_provider_is_terminal_before_next_call(self):
        from epiagentbench.launchd_agent import (
            LiveAttestationError,
            LiveAttestationFailureCode,
        )

        public = self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True

        def evaluate(system, **kwargs):
            return self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                1.0,
            )

        runtime = self.root / "supervisor-runtime"
        attested = self._supervisor_attestation(
            "production", public["precommitment_sha256"]
        )
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=(
                    attested,
                    attested,
                    attested,
                    LiveAttestationError(
                        LiveAttestationFailureCode.HEARTBEAT_STALE
                    ),
                ),
            ) as attestation,
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
        ):
            payload = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(payload["status"], "stopped_supervisor_incident")
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(attestation.call_count, 4)
        sleep.assert_not_called()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["execution_incident"]["status"], "terminal")
        self.assertEqual(
            private["execution_incident"]["failure_class"],
            "ProviderExecutionIsolationError",
        )
        self.assertEqual(
            private["execution_incident"]["boundary"],
            "clean_before_assignment",
        )
        self.assertEqual(
            private["execution_incident"]["attestation_failure_code"],
            "heartbeat_stale",
        )
        self.assertNotIn("stale private", self.results_path.read_text())

    def test_clean_boundary_retries_only_transient_attestation_reads(self):
        from epiagentbench.launchd_agent import (
            LiveAttestationError,
            LiveAttestationFailureCode,
        )

        public = self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True
        self._set_terminal_assignment_prefix(ASSIGNMENT_COUNT - 1)
        runtime = self.root / "supervisor-runtime"
        live = self._supervisor_attestation(
            "production", public["precommitment_sha256"]
        )
        transient = lambda: LiveAttestationError(
            LiveAttestationFailureCode.STATUS_SNAPSHOT_UNSTABLE
        )

        def evaluate(system, **kwargs):
            return self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                1.0,
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=(
                    live,
                    transient(),
                    transient(),
                    live,
                    live,
                    live,
                ),
            ) as attestation,
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
        ):
            payload = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(payload["status"], matched._PENDING_PRODUCTION_STATUS)
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(attestation.call_count, 6)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.05, 0.10])
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(len(private["assignments"]), ASSIGNMENT_COUNT)
        self.assertIsNone(private.get("execution_incident"))

    def test_snapshot_retry_deadline_overrun_does_not_reattest(self):
        attestation_calls = 0

        def attest():
            nonlocal attestation_calls
            attestation_calls += 1
            raise matched._persistent_attestation_error(
                "status_snapshot_unstable"
            )

        with (
            patch(
                "epiagentbench.development_matched_panel.time.monotonic",
                side_effect=(0.0, 0.0, 0.3),
            ),
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
            self.assertRaises(ProviderExecutionIsolationError) as caught,
        ):
            matched._attest_with_transient_snapshot_retry(attest)

        self.assertEqual(attestation_calls, 1)
        self.assertEqual(
            caught.exception.attestation_failure_code,
            "status_snapshot_unstable",
        )
        sleep.assert_called_once_with(0.05)

    def test_snapshot_retry_invariant_change_stops_before_reattest(self):
        attestation_calls = 0
        invariant_checks = 0

        def attest():
            nonlocal attestation_calls
            attestation_calls += 1
            raise matched._persistent_attestation_error(
                "status_snapshot_unstable"
            )

        def invariant():
            nonlocal invariant_checks
            invariant_checks += 1
            return invariant_checks == 1

        with (
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
            self.assertRaises(ProviderExecutionIsolationError) as caught,
        ):
            matched._attest_with_transient_snapshot_retry(
                attest,
                invariant=invariant,
            )

        self.assertEqual(attestation_calls, 1)
        self.assertEqual(invariant_checks, 2)
        self.assertEqual(
            caught.exception.attestation_failure_code,
            "private_binding_invalid",
        )
        sleep.assert_called_once_with(0.05)

    def test_production_initial_binding_retries_only_snapshot_read(self):
        from epiagentbench.launchd_agent import (
            LiveAttestationError,
            LiveAttestationFailureCode,
        )

        public = self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True
        self._set_terminal_assignment_prefix(ASSIGNMENT_COUNT - 1)
        runtime = self.root / "supervisor-runtime"
        live = self._supervisor_attestation(
            "production", public["precommitment_sha256"]
        )
        transient = LiveAttestationError(
            LiveAttestationFailureCode.STATUS_SNAPSHOT_UNSTABLE
        )

        def evaluate(system, **kwargs):
            return self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                1.0,
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=(transient, live, live, live, live),
            ) as attestation,
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
        ):
            pending = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(pending["status"], matched._PENDING_PRODUCTION_STATUS)
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(attestation.call_count, 5)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [0.05],
        )

    def test_clean_boundary_transient_exhaustion_stops_before_provider(self):
        from epiagentbench.launchd_agent import (
            LiveAttestationError,
            LiveAttestationFailureCode,
        )

        public = self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True
        self._set_terminal_assignment_prefix(ASSIGNMENT_COUNT - 1)
        runtime = self.root / "supervisor-runtime"
        live = self._supervisor_attestation(
            "production", public["precommitment_sha256"]
        )
        transient = lambda: LiveAttestationError(
            LiveAttestationFailureCode.STATUS_SNAPSHOT_UNSTABLE
        )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=(live, transient(), transient(), transient()),
            ) as attestation,
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
            ) as invoked,
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
        ):
            payload = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(payload["status"], "stopped_supervisor_incident")
        invoked.assert_not_called()
        self.assertEqual(attestation.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.05, 0.10])
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(len(private["assignments"]), ASSIGNMENT_COUNT - 1)
        self.assertEqual(
            private["execution_incident"]["attestation_failure_code"],
            "status_snapshot_unstable",
        )
        self.assertEqual(
            payload["failure_stage"],
            "supervisor_attestation_before_provider",
        )
        self.assertEqual(
            payload["attestation_failure_code"],
            "status_snapshot_unstable",
        )

    def test_post_provider_snapshot_exhaustion_is_public_and_never_replays(
        self,
    ):
        from epiagentbench.launchd_agent import (
            LiveAttestationError,
            LiveAttestationFailureCode,
        )

        public = self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True
        self._set_terminal_assignment_prefix(ASSIGNMENT_COUNT - 1)
        runtime = self.root / "supervisor-runtime"
        live = self._supervisor_attestation(
            "production", public["precommitment_sha256"]
        )

        def transient():
            return LiveAttestationError(
                LiveAttestationFailureCode.STATUS_SNAPSHOT_UNSTABLE
            )

        def evaluate(system, **kwargs):
            return self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                1.0,
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=(
                    live,
                    live,
                    transient(),
                    transient(),
                    transient(),
                ),
            ) as attestation,
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
        ):
            stopped = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(stopped["status"], "stopped_supervisor_incident")
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(attestation.call_count, 5)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [0.05, 0.10],
        )
        self.assertEqual(
            stopped["failure_stage"],
            "supervisor_attestation_after_provider",
        )
        self.assertEqual(
            stopped["attestation_failure_code"],
            "status_snapshot_unstable",
        )
        self.assertEqual(stopped["results"], [])
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(len(private["assignments"]), ASSIGNMENT_COUNT)
        self.assertEqual(
            private["assignments"][-1]["status"],
            "transport_void",
        )

    def _set_terminal_assignment_prefix(
        self, count: int
    ) -> list[tuple[str, str]]:
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        keys = matched._assignment_keys(private["schedule"])
        private["status"] = "running"
        private["panel_started_at_utc"] = "test-panel-start"
        private["assignments"] = [
            {
                "episode_ref": episode_ref,
                "profile_id": profile_id,
                "status": "transport_void",
                "started_at_utc": "test-assignment-start",
                "finished_at_utc": "test-assignment-finish",
                "void_reason": "test_prefix_checkpoint",
            }
            for episode_ref, profile_id in keys[:count]
        ]
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        return keys

    def _stage_signed_isolation_incident(
        self,
        incident: Mapping[str, object],
    ) -> dict:
        public = self._prepare()
        self._set_terminal_assignment_prefix(1)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        private["assignments"][0]["void_reason"] = str(
            incident["failure_class"]
        )
        private["execution_incident"] = dict(incident)
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        running = matched._public_running(public, private)
        matched._atomic_json(self.results_path, running)
        return running

    def _assert_signed_isolation_incident_refused(
        self,
        incident: Mapping[str, object],
        message: str,
    ) -> None:
        running = self._stage_signed_isolation_incident(incident)
        with (
            patch.dict(os.environ, {}, clear=True),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluator,
            self.assertRaisesRegex(ValueError, message),
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluator.assert_not_called()
        observed = matched._load_json(self.results_path)
        self.assertEqual(observed, running)
        self.assertNotIn(
            "provider-output-DO-NOT-LEAK",
            json.dumps(observed, sort_keys=True),
        )

    def _assert_signed_raw_incident_refused(
        self,
        incident_name: str,
        incident: object,
        message: str,
    ) -> None:
        public = self._prepare()
        self._set_terminal_assignment_prefix(1)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        private[incident_name] = incident
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        running = matched._public_running(public, private)
        matched._atomic_json(self.results_path, running)
        with (
            patch.dict(os.environ, {}, clear=True),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluator,
            self.assertRaisesRegex(ValueError, message),
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluator.assert_not_called()
        observed = matched._load_json(self.results_path)
        self.assertEqual(observed, running)
        self.assertNotIn(
            "provider-output-DO-NOT-LEAK",
            json.dumps(observed, sort_keys=True),
        )

    def _stage_pending_production(
        self,
        *,
        lose_final_attestation: bool = False,
    ) -> tuple[dict, Path, dict, dict]:
        public = self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True
        keys = self._set_terminal_assignment_prefix(ASSIGNMENT_COUNT - 1)
        final_profile = matched._PROFILE_BY_ID[keys[-1][1]]
        runtime = self.root / "supervisor-runtime"
        live = self._supervisor_attestation(
            "production", public["precommitment_sha256"]
        )
        side_effects = [live, live, live]
        side_effects.append(
            ValueError("lost before outer completion")
            if lose_final_attestation
            else live
        )

        def evaluate(system: str, **kwargs):
            return self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                25.0,
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=side_effects,
            ),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
        ):
            payload = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(final_profile["system"], invoked.call_args.args[0])
        return public, runtime, payload, live

    def test_execution_is_supervised_by_default_and_offline_fake_is_explicit(self):
        fake = lambda *_args, **_kwargs: self.fail("fake must not run")
        self.assertIs(
            matched._execution_evaluator(
                require_persistent_supervisor=False,
                offline_test_evaluator=fake,
            ),
            fake,
        )
        with self.assertRaisesRegex(
            RuntimeError, "explicitly injected offline test evaluator"
        ):
            matched._execution_evaluator(
                require_persistent_supervisor=False,
                offline_test_evaluator=None,
            )
        self.assertIs(
            matched._execution_evaluator(
                require_persistent_supervisor=True,
                offline_test_evaluator=None,
            ),
            matched.evaluate_local_cli_agent,
        )

    def test_public_run_entrypoints_refuse_unsupervised_defaults_zero_call(self):
        self._prepare()
        preflight_path = self.root / "results" / "default-preflight.json"
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
            ) as evaluator,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "live persistent supervisor"
            ):
                matched.run_panel(
                    root=self.root,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=self.claude_secure_storage_dir,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    public_results_path=self.results_path,
                    acknowledge_unbounded_provider_spend=True,
                )
            with self.assertRaisesRegex(
                RuntimeError, "live persistent supervisor"
            ):
                matched.run_environment_preflight(
                    root=self.root,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=self.claude_secure_storage_dir,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    public_preflight_path=preflight_path,
                    acknowledge_unbounded_provider_spend=True,
                )
        evaluator.assert_not_called()

    def test_public_run_entrypoints_reject_all_test_hooks_zero_call(self):
        common = {
            "root": self.root,
            "authentication_key_file": self.key_path,
            "claude_secure_storage_dir": self.claude_secure_storage_dir,
            "codex_secure_storage_dir": self.codex_secure_storage_dir,
            "private_state_path": self.private_path,
            "public_manifest_path": self.public_path,
            "supervisor_runtime_dir": self.root / "supervisor-runtime",
            "acknowledge_unbounded_provider_spend": True,
        }
        entrypoints = (
            (
                matched.run_environment_preflight,
                {
                    **common,
                    "public_preflight_path": (
                        self.root / "results" / "injection-preflight.json"
                    ),
                },
            ),
            (
                matched.run_panel,
                {
                    **common,
                    "public_results_path": self.results_path,
                },
            ),
        )
        with patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
        ) as direct_evaluator:
            def wrapped_evaluator(*args, **kwargs):
                return direct_evaluator(*args, **kwargs)

            injections = (
                {"require_persistent_supervisor": False},
                {"offline_test_evaluator": direct_evaluator},
                {"offline_test_evaluator": wrapped_evaluator},
            )
            for entrypoint, arguments in entrypoints:
                for injection in injections:
                    with (
                        self.subTest(
                            entrypoint=entrypoint.__name__,
                            injection=next(iter(injection)),
                            wrapped=(
                                injection.get("offline_test_evaluator")
                                is wrapped_evaluator
                            ),
                        ),
                        self.assertRaisesRegex(
                            TypeError, "unexpected keyword argument"
                        ),
                    ):
                        entrypoint(**arguments, **injection)
        direct_evaluator.assert_not_called()

    def test_create_once_supervisor_binding_refuses_replacement(self):
        precommitment = "sha256:" + "9" * 64
        first = matched._normalized_supervisor_binding(
            self._supervisor_attestation("production", precommitment),
            operation="production",
            public_manifest={
                "panel_id": matched.PANEL_ID,
                "precommitment_sha256": precommitment,
            },
        )
        private: dict = {}
        self.assertTrue(
            matched._claim_persistent_execution_binding(
                private,
                operation="production",
                binding=first,
            )
        )
        self.assertFalse(
            matched._claim_persistent_execution_binding(
                private,
                operation="production",
                binding=first,
            )
        )
        replacement = {
            **first,
            "label": "org.epiagentbench.panel.test.replacement",
            "config_file_sha256": "sha256:" + "a" * 64,
        }
        with self.assertRaisesRegex(RuntimeError, "replacement was refused"):
            matched._claim_persistent_execution_binding(
                private,
                operation="production",
                binding=replacement,
            )

    def test_supervised_production_stages_trace_free_pending_then_finalizes(self):
        public, runtime, pending, live = self._stage_pending_production()
        self.assertEqual(
            pending["status"], matched._PENDING_PRODUCTION_STATUS
        )
        self.assertEqual(pending["results"], [])
        self.assertEqual(pending["summary"], {"primary_estimand": "pending"})
        self.assertNotIn("replay_trace", json.dumps(pending))
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            private["status"], matched._PENDING_PRODUCTION_STATUS
        )
        retirement = matched._cohort_retirement_path(
            Path(private["cohort_manifest_path"])
        )
        self.assertFalse(retirement.exists())

        completed = {**live, "lifecycle": "completed"}

        with self._contracts(), patch(
            "epiagentbench.launchd_agent.attest_completed_launch_agent",
            return_value=completed,
        ):
            artifact = matched.finalize_supervised_release(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_output_path=self.results_path,
                supervisor_runtime_dir=runtime,
                operation="production",
            )
        self.assertEqual(artifact["status"], "complete_with_transport_voids")
        self.assertEqual(json.loads(self.results_path.read_text()), artifact)
        self.assertTrue(retirement.exists())
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["status"], "complete")
        self.assertEqual(private["public_release"]["status"], "released")
        self.assertEqual(
            private["persistent_execution_bindings"]["production"]["label"],
            completed["label"],
        )

    def test_supervised_finalizer_is_pure_local_publication(self):
        _, runtime, _, live = self._stage_pending_production()
        completed = {**live, "lifecycle": "completed"}
        forbidden = AssertionError("release finalizer invoked a live boundary")

        with (
            self._contracts(),
            patch(
                "epiagentbench.launchd_agent.attest_completed_launch_agent",
                return_value=completed,
            ),
            patch(
                "epiagentbench.development_matched_panel._cli_contract",
                side_effect=forbidden,
            ),
            patch(
                "epiagentbench.development_matched_panel._source_contract",
                side_effect=forbidden,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_run_provider_process_group",
                side_effect=forbidden,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=forbidden,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials",
                side_effect=forbidden,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials",
                side_effect=forbidden,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_attest_claude_secure_storage_keychain",
                side_effect=forbidden,
            ),
            patch(
                "epiagentbench.development_matched_panel.subprocess.run",
                side_effect=forbidden,
            ),
            patch(
                "epiagentbench.development_matched_panel.subprocess.Popen",
                side_effect=forbidden,
            ),
        ):
            artifact = matched.finalize_supervised_release(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_output_path=self.results_path,
                supervisor_runtime_dir=runtime,
                operation="production",
            )

        self.assertTrue(artifact["status"].startswith("complete"))

    def test_supervised_production_continues_after_ordinary_void_in_same_child(self):
        public = self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True
        keys = self._set_terminal_assignment_prefix(ASSIGNMENT_COUNT - 2)
        runtime = self.root / "supervisor-runtime"
        live = self._supervisor_attestation(
            "production", public["precommitment_sha256"]
        )
        calls = 0

        def evaluate(system: str, **kwargs):
            nonlocal calls
            calls += 1
            result = self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                25.0,
            )
            return replace(result, returncode=7) if calls == 1 else result

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                return_value=live,
            ),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
        ):
            pending = matched.run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                supervisor_runtime_dir=runtime,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(invoked.call_count, 2)
        self.assertEqual(calls, 2)
        self.assertEqual(
            pending["status"], matched._PENDING_PRODUCTION_STATUS
        )
        self.assertEqual(pending["terminal_assignments"], ASSIGNMENT_COUNT)
        self.assertEqual(pending["transport_voids"], ASSIGNMENT_COUNT - 1)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            [item["status"] for item in private["assignments"][-2:]],
            ["transport_void", "complete"],
        )
        self.assertEqual(
            [
                (item["episode_ref"], item["profile_id"])
                for item in private["assignments"][-2:]
            ],
            keys[-2:],
        )
        self.assertIsNone(private.get("execution_incident"))
        self.assertIsNone(private.get("codex_auth_incident"))

    def test_supervised_preflight_stages_trace_free_pending_then_finalizes(self):
        public = self._prepare()
        runtime = self.root / "preflight-supervisor-runtime"
        preflight_path = self.root / "results" / "preflight-pending.json"
        live = self._supervisor_attestation(
            "preflight", public["precommitment_sha256"]
        )

        def evaluate(system: str, **kwargs):
            return self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                0.0,
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                return_value=live,
            ),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
        ):
            pending = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(invoked.call_count, len(PROFILES))
        self.assertEqual(pending["status"], matched._PENDING_PREFLIGHT_STATUS)
        self.assertNotIn("profiles", pending)
        serialized_pending = json.dumps(pending)
        for forbidden in (
            "observed_models",
            "raw_result",
            "replay_trace",
            "progress_telemetry",
        ):
            self.assertNotIn(forbidden, serialized_pending)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            private["environment_preflight"]["status"],
            matched._PENDING_PREFLIGHT_STATUS,
        )
        completed = {**live, "lifecycle": "completed"}
        with self._contracts(), patch(
            "epiagentbench.launchd_agent.attest_completed_launch_agent",
            return_value=completed,
        ):
            receipt = matched.finalize_supervised_release(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_output_path=preflight_path,
                supervisor_runtime_dir=runtime,
                operation="preflight",
            )
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(json.loads(preflight_path.read_text()), receipt)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["environment_preflight"]["status"], "passed")
        self.assertEqual(
            private["environment_preflight"]["public_release"]["status"],
            "released",
        )

    def test_supervised_preflight_retries_transient_snapshot_at_all_boundaries(
        self,
    ):
        from epiagentbench.launchd_agent import (
            LiveAttestationError,
            LiveAttestationFailureCode,
        )

        public = self._prepare()
        runtime = self.root / "preflight-supervisor-runtime"
        preflight_path = self.root / "results" / "preflight-pending.json"
        live = self._supervisor_attestation(
            "preflight", public["precommitment_sha256"]
        )
        attestation_calls = 0

        def attest(*_args, **_kwargs):
            nonlocal attestation_calls
            attestation_calls += 1
            # Initial binding, before/after the first provider, and final
            # completion each fail once with the sole retryable read error.
            if attestation_calls in {1, 3, 5, 17}:
                raise LiveAttestationError(
                    LiveAttestationFailureCode.STATUS_SNAPSHOT_UNSTABLE
                )
            return live

        def evaluate(system: str, **kwargs):
            return self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                0.0,
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=attest,
            ) as attestation,
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
        ):
            pending = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(pending["status"], matched._PENDING_PREFLIGHT_STATUS)
        self.assertEqual(invoked.call_count, len(PROFILES))
        self.assertEqual(attestation.call_count, 18)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [0.05, 0.05, 0.05, 0.05],
        )
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            len(private["environment_preflight"]["attempts"]),
            len(PROFILES),
        )

    def test_supervised_preflight_snapshot_exhaustion_never_retries_provider(
        self,
    ):
        from epiagentbench.launchd_agent import (
            LiveAttestationError,
            LiveAttestationFailureCode,
        )

        public = self._prepare()
        runtime = self.root / "preflight-supervisor-runtime"
        preflight_path = self.root / "results" / "preflight-failed.json"
        live = self._supervisor_attestation(
            "preflight", public["precommitment_sha256"]
        )
        attestation_calls = 0

        def attest(*_args, **_kwargs):
            nonlocal attestation_calls
            attestation_calls += 1
            # Exhaust the post-provider read retries for the first profile.
            if attestation_calls in {3, 4, 5}:
                raise LiveAttestationError(
                    LiveAttestationFailureCode.STATUS_SNAPSHOT_UNSTABLE
                )
            return live

        def evaluate(system: str, **kwargs):
            return self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                0.0,
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=attest,
            ) as attestation,
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
        ):
            failed = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(attestation.call_count, 5)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [0.05, 0.10],
        )
        self.assertEqual(
            failed["failure_stage"],
            "supervisor_attestation_after_harness",
        )
        self.assertEqual(
            failed["attestation_failure_code"],
            "status_snapshot_unstable",
        )
        self.assertEqual(
            failed["profiles"][0]["attestation_failure_code"],
            "status_snapshot_unstable",
        )
        self.assertTrue(
            all(
                profile["invocation_state"] == "not_started"
                for profile in failed["profiles"][1:]
            )
        )
        self.assertEqual(
            failed["provider_calls_conservatively_chargeable"],
            1,
        )
        self.assertNotIn("raw_result", json.dumps(failed))

    def test_supervised_preflight_nontransient_attestation_never_retries(
        self,
    ):
        from epiagentbench.launchd_agent import (
            LiveAttestationError,
            LiveAttestationFailureCode,
        )

        public = self._prepare()
        runtime = self.root / "preflight-supervisor-runtime"
        preflight_path = self.root / "results" / "preflight-failed.json"
        live = self._supervisor_attestation(
            "preflight", public["precommitment_sha256"]
        )
        attestation_calls = 0

        def attest(*_args, **_kwargs):
            nonlocal attestation_calls
            attestation_calls += 1
            if attestation_calls == 3:
                raise LiveAttestationError(
                    LiveAttestationFailureCode.HEARTBEAT_STALE
                )
            return live

        def evaluate(system: str, **kwargs):
            return self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                0.0,
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=attest,
            ) as attestation,
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
        ):
            failed = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(attestation.call_count, 3)
        sleep.assert_not_called()
        self.assertEqual(
            failed["failure_stage"],
            "supervisor_attestation_after_harness",
        )
        self.assertEqual(
            failed["attestation_failure_code"],
            "heartbeat_stale",
        )

    def test_supervised_preflight_final_snapshot_exhaustion_never_replays(
        self,
    ):
        from epiagentbench.launchd_agent import (
            LiveAttestationError,
            LiveAttestationFailureCode,
        )

        public = self._prepare()
        runtime = self.root / "preflight-supervisor-runtime"
        preflight_path = self.root / "results" / "preflight-stopped.json"
        live = self._supervisor_attestation(
            "preflight", public["precommitment_sha256"]
        )
        attestation_calls = 0

        def attest(*_args, **_kwargs):
            nonlocal attestation_calls
            attestation_calls += 1
            if attestation_calls in {14, 15, 16}:
                raise LiveAttestationError(
                    LiveAttestationFailureCode.STATUS_SNAPSHOT_UNSTABLE
                )
            return live

        def evaluate(system: str, **kwargs):
            return self._result(
                system,
                kwargs["model"],
                kwargs["executable"],
                0.0,
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=attest,
            ) as attestation,
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
            patch("epiagentbench.development_matched_panel.time.sleep") as sleep,
        ):
            stopped = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                supervisor_runtime_dir=runtime,
                require_persistent_supervisor=True,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(stopped["status"], "stopped_supervisor_incident")
        self.assertEqual(invoked.call_count, len(PROFILES))
        self.assertEqual(attestation.call_count, 16)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [0.05, 0.10],
        )
        self.assertEqual(stopped["profiles_terminal"], len(PROFILES))
        self.assertEqual(
            stopped["provider_calls_conservatively_chargeable"],
            len(PROFILES),
        )
        self.assertEqual(
            stopped["failure_stage"],
            "supervisor_attestation_final_completion",
        )
        self.assertEqual(
            stopped["attestation_failure_code"],
            "status_snapshot_unstable",
        )
        self.assertNotIn("profiles", stopped)
        self.assertNotIn("raw_result", json.dumps(stopped))

    def test_finalizer_requires_completed_supervisor(self):
        _, runtime, pending, live = self._stage_pending_production()
        with (
            self._contracts(),
            patch(
                "epiagentbench.launchd_agent.attest_completed_launch_agent",
                return_value=live,
            ),
            self.assertRaisesRegex(
                RuntimeError, "requires authenticated supervisor completion"
            ),
        ):
            matched.finalize_supervised_release(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_output_path=self.results_path,
                supervisor_runtime_dir=runtime,
                operation="production",
            )
        self.assertEqual(json.loads(self.results_path.read_text()), pending)
        self.assertFalse(
            matched._cohort_retirement_path(
                Path(
                    matched._load_private_state(
                        self.private_path, AUTHENTICATION_KEY
                    )["cohort_manifest_path"]
                )
            ).exists()
        )

    def test_finalizer_public_last_write_is_crash_idempotent(self):
        _, runtime, pending, live = self._stage_pending_production()
        completed = {**live, "lifecycle": "completed"}
        original_atomic_json = matched._atomic_json
        injected = False

        def fail_public_final(path, value, **kwargs):
            nonlocal injected
            if (
                not injected
                and Path(path) == self.results_path
                and isinstance(value, dict)
                and str(value.get("status", "")).startswith("complete")
            ):
                injected = True
                raise OSError("injected final publication crash")
            return original_atomic_json(path, value, **kwargs)

        arguments = {
            "root": self.root,
            "authentication_key_file": self.key_path,
            "claude_secure_storage_dir": self.claude_secure_storage_dir,
            "codex_secure_storage_dir": self.codex_secure_storage_dir,
            "private_state_path": self.private_path,
            "public_manifest_path": self.public_path,
            "public_output_path": self.results_path,
            "supervisor_runtime_dir": runtime,
            "operation": "production",
        }
        with (
            self._contracts(),
            patch(
                "epiagentbench.launchd_agent.attest_completed_launch_agent",
                return_value=completed,
            ),
            patch(
                "epiagentbench.development_matched_panel._atomic_json",
                side_effect=fail_public_final,
            ),
            self.assertRaisesRegex(OSError, "injected final publication crash"),
        ):
            matched.finalize_supervised_release(**arguments)
        self.assertTrue(injected)
        self.assertEqual(json.loads(self.results_path.read_text()), pending)
        private_after_crash = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private_after_crash["status"], "complete")
        self.assertEqual(
            private_after_crash["public_release"]["status"], "released"
        )
        with self._contracts(), patch(
            "epiagentbench.launchd_agent.attest_completed_launch_agent",
            return_value=completed,
        ):
            artifact = matched.finalize_supervised_release(**arguments)
        self.assertEqual(json.loads(self.results_path.read_text()), artifact)
        with self._contracts(), patch(
            "epiagentbench.launchd_agent.attest_completed_launch_agent",
            return_value=completed,
        ):
            repeated = matched.finalize_supervised_release(**arguments)
        self.assertEqual(repeated, artifact)

    def test_final_boundary_supervisor_loss_blocks_trace_release(self):
        public, _, stopped, _ = self._stage_pending_production(
            lose_final_attestation=True
        )
        self.assertEqual(stopped["status"], "stopped_supervisor_incident")
        self.assertEqual(stopped["results"], [])
        self.assertEqual(
            stopped["failure_stage"],
            "supervisor_attestation_final_completion",
        )
        self.assertEqual(
            stopped["attestation_failure_code"],
            "attestation_internal",
        )
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            private["execution_incident"]["boundary"], "final_completion"
        )
        self.assertNotEqual(private["status"], "complete")
        self.assertFalse(
            matched._cohort_retirement_path(
                Path(private["cohort_manifest_path"])
            ).exists()
        )
        running = matched._public_running(public, private)
        matched._atomic_json(self.results_path, running)
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
            ) as evaluator,
        ):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "non-resumable"):
                    # A terminal incident is reconciled before any requirement
                    # for a new/live runtime.  It can never resume providers.
                    matched.run_panel(
                        root=self.root,
                        authentication_key_file=self.key_path,
                        claude_secure_storage_dir=self.claude_secure_storage_dir,
                        codex_secure_storage_dir=self.codex_secure_storage_dir,
                        private_state_path=self.private_path,
                        public_manifest_path=self.public_path,
                        public_results_path=self.results_path,
                        acknowledge_unbounded_provider_spend=True,
                    )
                reconciled = json.loads(self.results_path.read_text())
                self.assertEqual(
                    reconciled["status"], "stopped_supervisor_incident"
                )
                self.assertEqual(reconciled["results"], [])
                self.assertEqual(
                    reconciled["summary"], {"primary_estimand": "pending"}
                )
        evaluator.assert_not_called()

    @staticmethod
    def _timeout_result(
        system: str, model: str, executable: str
    ) -> PilotRunResult:
        return replace(
            MatchedPanelTests._result(system, model, executable, 0.0),
            returncode=124,
            submission=None,
            scorecard={
                "valid": False,
                "total": 0.0,
                "dimensions": {
                    name: 0.0 for name in matched.DIMENSION_MAXIMA
                },
                "metrics": {"tool_calls": 2},
                "violations": ["timeout"],
            },
            audit_events=("agent_failure:timeout",),
            diagnostic="redacted provider timeout",
            timed_out=True,
            progress_telemetry={
                "schema_version": "epiagentbench.provider_progress.v1",
                "observed_elapsed_bucket": "ge_1800s",
                "output_seen": True,
                "first_output_elapsed_bucket": "lt_30s",
                "last_output_elapsed_bucket": "900_1799s",
                "combined_output_bytes_bucket": "1_4095",
            },
        )

    def _assert_harness_startup_failure_terminal_aborts(
        self,
        *,
        audit_events: tuple[str, ...],
        diagnostic: str,
        returncode: int,
    ) -> None:
        self._prepare()
        preflight_path = self.root / "results" / "preflight-startup-failure.json"
        invoked_models: list[str] = []

        def evaluate(system: str, **kwargs):
            model = kwargs["model"]
            invoked_models.append(model)
            if system == "claude":
                self.keychain_present = True
            return replace(
                self._result(system, model, kwargs["executable"], 0.0),
                returncode=returncode,
                audit_events=audit_events,
                diagnostic=diagnostic,
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
        ):
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(invoked_models, ["claude-opus-4-8"])
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failure_reason"], "terminal_abort")
        self.assertEqual(receipt["failure_stage"], "harness_startup_contract")
        self.assertEqual(
            [item["profile_id"] for item in receipt["profiles"]],
            [profile["profile_id"] for profile in PROFILES],
        )
        self.assertEqual(
            [item["outcome"] for item in receipt["profiles"]],
            ["terminal_abort"]
            + ["not_started_terminal_abort"] * (len(PROFILES) - 1),
        )
        self.assertEqual(
            [item["invocation_state"] for item in receipt["profiles"]],
            ["finished"] + ["not_started"] * (len(PROFILES) - 1),
        )
        self.assertEqual(
            [item["conservative_chargeable"] for item in receipt["profiles"]],
            [True] + [False] * (len(PROFILES) - 1),
        )
        self.assertEqual(receipt["provider_calls_conservatively_chargeable"], 1)
        self.assertFalse(receipt["scores_reported"])

    def _assert_non_codex_timeout_is_fixed_zero(self, system: str) -> None:
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        keys = matched._assignment_keys(private["schedule"])
        target_index = next(
            index
            for index, (_ref, profile_id) in enumerate(keys)
            if matched._PROFILE_BY_ID[profile_id]["system"] == system
        )
        self._set_terminal_assignment_prefix(target_index)
        calls = 0

        def evaluate(observed_system: str, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                self.assertEqual(observed_system, system)
                return self._timeout_result(
                    observed_system,
                    kwargs["model"],
                    kwargs["executable"],
                )
            raise RuntimeError("stop after classified timeout")

        result, invoked = self._run_with(evaluate)
        self.assertEqual(invoked.call_count, 2)
        self.assertEqual(result["status"], "stopped_transport_void")
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        assignment = private["assignments"][target_index]
        self.assertEqual(assignment["status"], "complete")
        self.assertEqual(assignment["public_result"]["returncode"], 124)
        self.assertFalse(assignment["public_result"]["valid"])
        self.assertEqual(assignment["public_result"]["total"], 0.0)
        self.assertIn(
            "agent_failure:timeout",
            assignment["public_result"]["audit_events"],
        )
        self.assertIsNone(private.get("execution_incident"))
        self.assertIsNone(private.get("codex_auth_incident"))

    def test_budget_contract_precommits_cumulative_authorization_ceilings(self):
        contract = matched._budget_contract(5.0)
        self.assertEqual(
            contract["claude_current_v14_authorization_breakdown"],
            {
                "preflight_calls": 2,
                "production_calls": 100,
                "per_call_ceiling_usd": 5.0,
                "preflight_ceiling_usd": 10.0,
                "production_ceiling_usd": 500.0,
            },
        )
        self.assertEqual(
            contract["claude_current_v14_authorization_ceiling_usd"], 510.0
        )
        self.assertEqual(
            contract["claude_prior_failed_panel_breakdown"],
            {
                "v2_usd": 10.0,
                "v3_usd": 0.0,
                "v4_usd": 0.0,
                "v5_usd": 5.0,
                "v6_usd": 0.0,
                "v7_usd": 10.0,
                "v8_usd": 15.0,
                "v9_usd": 20.0,
                "v10_usd": 0.0,
                "v11_usd": 0.0,
                "v12_usd": 0.0,
                "v13_usd": 0.0,
            },
        )
        self.assertEqual(
            contract["claude_prior_failed_panel_conservative_ceiling_usd"],
            60.0,
        )
        self.assertEqual(
            contract["claude_cumulative_authorization_ceiling_usd"], 570.0
        )
        self.assertEqual(
            set(contract["prior_public_audit_references"]),
            {
                "v2_preflight_receipt",
                "v2_supersession",
                "v5_preflight_receipt",
                "v5_supersession",
                "v6_preflight_receipt",
                "v6_supersession",
                "v7_preflight_receipt",
                "v7_supersession",
                "v8_preflight_receipt",
                "v8_stopped_watermark",
                "v8_supersession",
                "v9_preflight_receipt",
                "v9_stopped_watermark",
                "v10_manifest",
                "v10_supersession",
                "v11_manifest",
                "v11_supersession",
                "v12_supersession",
                "v13_manifest",
                "v13_supersession",
            },
        )
        for reference in contract["prior_public_audit_references"].values():
            self.assertTrue((Path(__file__).parents[1] / reference).is_file())
        self.assertIn("not measured", contract["ceiling_interpretation"])
        self.assertEqual(contract["other_provider_spend"], "unbounded")

    def test_live_cli_execution_requires_manifest_bound_supervisor(self):
        public = {
            "panel_id": matched.PANEL_ID,
            "precommitment_sha256": "sha256:" + "9" * 64,
            "persistent_supervisor_contract": (
                matched._persistent_supervisor_contract()
            ),
        }
        with self.assertRaisesRegex(RuntimeError, "live persistent supervisor"):
            matched._attest_required_persistent_execution(
                required=True,
                supervisor_runtime_dir=None,
                authentication_key_file=self.key_path,
                operation="production",
                public_manifest=public,
            )
        runtime = self.root / "supervisor-runtime"
        live_attestation = self._supervisor_attestation(
            "production", public["precommitment_sha256"]
        )
        with patch(
            "epiagentbench.launchd_agent.attest_live_launch_agent",
            return_value=live_attestation,
        ) as attest:
            observed = matched._attest_required_persistent_execution(
                required=True,
                supervisor_runtime_dir=runtime,
                authentication_key_file=self.key_path,
                operation="production",
                public_manifest=public,
            )
        self.assertEqual(observed["label"], live_attestation["label"])
        attest.assert_called_once_with(
            runtime,
            authentication_key_file=self.key_path,
            expected_operation="production",
            expected_panel_id=matched.PANEL_ID,
            expected_precommitment_sha256=public["precommitment_sha256"],
        )
        with (
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=ValueError("private path must not escape"),
            ),
            self.assertRaisesRegex(
                RuntimeError, "Live persistent-supervisor attestation failed"
            ) as raised,
        ):
            matched._attest_required_persistent_execution(
                required=True,
                supervisor_runtime_dir=runtime,
                authentication_key_file=self.key_path,
                operation="production",
                public_manifest=public,
            )
        self.assertNotIn("private path", str(raised.exception))
        self.assertEqual(
            raised.exception.attestation_failure_code,
            "attestation_internal",
        )
        from epiagentbench.launchd_agent import (
            LiveAttestationError,
            LiveAttestationFailureCode,
        )

        with (
            patch(
                "epiagentbench.launchd_agent.attest_live_launch_agent",
                side_effect=LiveAttestationError(
                    LiveAttestationFailureCode.HEARTBEAT_STALE
                ),
            ),
            self.assertRaises(ProviderExecutionIsolationError) as finite,
        ):
            matched._attest_required_persistent_execution(
                required=True,
                supervisor_runtime_dir=runtime,
                authentication_key_file=self.key_path,
                operation="production",
                public_manifest=public,
            )
        self.assertEqual(
            finite.exception.attestation_failure_code,
            "heartbeat_stale",
        )

    def test_v14_preserves_profile_order_with_sol_medium_and_luna_max(self):
        self.assertEqual(
            [profile["profile_id"] for profile in PROFILES],
            [
                "claude-opus-high",
                "claude-sonnet-high",
                "codex-sol",
                "codex-luna-max",
                "cursor-grok-high",
                "cursor-kimi-k27-code",
            ],
        )
        sol = matched._PROFILE_BY_ID["codex-sol"]
        luna = matched._PROFILE_BY_ID["codex-luna-max"]
        self.assertEqual(sol["requested_model"], "gpt-5.6-sol")
        self.assertEqual(sol["requested_reasoning"], "medium")
        self.assertEqual(luna["requested_model"], "gpt-5.6-luna")
        self.assertEqual(luna["requested_reasoning"], "max")

    def test_prepare_defaults_to_and_freezes_1800_second_timeout(self):
        manifest_path = self._cohort()
        with self._contracts(), patch(
            "epiagentbench.development_matched_panel.secrets.token_bytes",
            return_value=b"s" * 32,
        ):
            public = prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                claude_max_budget_usd=5.0,
            )

        self.assertEqual(
            public["timeout_contract"]["seconds_per_assignment"], 1800
        )
        self.assertEqual(matched._load_json(self.public_path), public)
        self.assertEqual(
            public["contract_hashes"]["timeouts_sha256"],
            matched._component_hash(public["timeout_contract"]),
        )

    def test_prepare_publishes_create_once_without_provider_or_replace_calls(self):
        manifest_path = self._cohort()
        forbidden = AssertionError("prepare crossed a forbidden live boundary")
        executable = self.root / "identity-cli"
        executable.write_bytes(b"provider-controlled-version-sentinel")
        executable.chmod(0o755)
        real_cli_contract = matched._cli_contract
        with (
            self._contracts(),
            patch.dict(os.environ, {}, clear=True),
            patch(
                "epiagentbench.development_matched_panel._cli_contract",
                side_effect=real_cli_contract,
            ),
            patch(
                "epiagentbench.development_matched_panel.shutil.which",
                return_value=str(executable),
            ),
            patch(
                "epiagentbench.development_matched_panel._GLEAN_HELPER_PATH",
                executable,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_deferred_root_owned_executable_contract",
                side_effect=lambda path, **_kwargs: {
                    "path": str(path),
                    "entrypoint_kind": (
                        "root_owned_single_link_regular_executable"
                    ),
                    "group_or_world_writable": False,
                    "trusted_root_owned_nonwritable_ancestry": True,
                    "exact_content_freeze_stage": (
                        "manifest_bound_spend_authorization_before_"
                        "authentication"
                    ),
                    "freeze_once": True,
                    "required_live_attestation_boundaries": [
                        "before_and_after_foreground_authentication",
                        "before_and_after_each_preflight_provider_call",
                        "before_and_after_each_production_provider_call",
                    ],
                },
            ),
            patch(
                "epiagentbench.development_matched_panel._safe_glean_config",
                return_value=(
                    self._glean_config_fixture(),
                    {
                        "path": str(matched._GLEAN_CONFIG_PATH),
                        "sha256": "sha256:" + "4" * 64,
                    },
                ),
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_managed_settings_identity",
                return_value=(
                    {"sha256": "sha256:" + "5" * 64},
                    False,
                ),
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_safe_entrypoint_identity",
                return_value={
                    "path": str(matched._GLEAN_GATEWAY_TOKEN_WRAPPER_PATH),
                    "entrypoint_kind": "regular_file",
                    "link_text": None,
                    "resolved_path": str(
                        matched._GLEAN_GATEWAY_TOKEN_WRAPPER_PATH
                    ),
                    "target_sha256": "sha256:" + "6" * 64,
                },
            ),
            patch(
                "epiagentbench.development_matched_panel.secrets.token_bytes",
                return_value=b"s" * 32,
            ),
            patch(
                "epiagentbench.development_matched_panel._atomic_json",
                side_effect=forbidden,
            ) as atomic_json,
            patch(
                "epiagentbench.development_matched_panel."
                "_run_provider_process_group",
                side_effect=forbidden,
            ) as provider_process,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=forbidden,
            ) as evaluator,
        ):
            public = prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )

        self.assertEqual(matched._load_json(self.public_path), public)
        self.assertNotIn(
            "provider-controlled-version-sentinel",
            json.dumps(public, sort_keys=True),
        )
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            private["public_precommitment_sha256"],
            public["precommitment_sha256"],
        )
        marker = matched._load_cohort_preparation_marker(
            matched._cohort_preparation_path(manifest_path),
            AUTHENTICATION_KEY,
        )
        self.assertEqual(private["cohort_preparation_claim"], marker)
        atomic_json.assert_not_called()
        provider_process.assert_not_called()
        evaluator.assert_not_called()

    def test_prepare_refuses_a_concurrent_host_global_panel_lease(self):
        manifest_path = self._cohort()
        with (
            matched._exclusive_run_lock(self.private_path),
            self._contracts(),
            self.assertRaisesRegex(RuntimeError, "already holds the lock"),
        ):
            prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())
        self.assertFalse(
            matched._cohort_preparation_path(manifest_path).exists()
        )

    def test_prepare_private_publication_race_never_creates_public_manifest(self):
        manifest_path = self._cohort()
        competitor = b"competitor-owned-private-publication\n"
        original_create = matched._create_private_json_once

        def lose_private_race(path, value):
            if Path(path) == self.private_path:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_bytes(competitor)
                Path(path).chmod(0o600)
            return original_create(path, value)

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel.secrets.token_bytes",
                return_value=b"s" * 32,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_create_private_json_once",
                side_effect=lose_private_race,
            ),
            self.assertRaisesRegex(FileExistsError, "private state"),
        ):
            prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )

        self.assertEqual(self.private_path.read_bytes(), competitor)
        self.assertFalse(self.public_path.exists())
        self.assertTrue(
            matched._cohort_preparation_path(manifest_path).is_file()
        )

    def test_prepare_cohort_claim_race_never_clobbers_competitor(self):
        manifest_path = self._cohort()
        claim_path = matched._cohort_preparation_path(manifest_path)
        competitor = b"competitor-owned-cohort-claim\n"
        original_create = matched._create_private_json_once

        def lose_claim_race(path, value):
            if Path(path).name == matched._COHORT_PREPARATION_FILE:
                Path(path).write_bytes(competitor)
                Path(path).chmod(0o600)
            return original_create(path, value)

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel.secrets.token_bytes",
                return_value=b"s" * 32,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_create_private_json_once",
                side_effect=lose_claim_race,
            ),
            self.assertRaisesRegex(FileExistsError, "preparation claim"),
        ):
            prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )

        self.assertEqual(claim_path.read_bytes(), competitor)
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())

    def test_prepare_publication_race_never_clobbers_competitor(self):
        manifest_path = self._cohort()
        competitor = b"competitor-owned-publication\n"
        original_create = matched._create_public_json_once

        def lose_public_race(path, value):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(competitor)
            return original_create(path, value)

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel.secrets.token_bytes",
                return_value=b"s" * 32,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_create_public_json_once",
                side_effect=lose_public_race,
            ),
            self.assertRaises(FileExistsError),
        ):
            prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )

        self.assertEqual(self.public_path.read_bytes(), competitor)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["status"], "prepared")
        self.assertTrue(
            matched._cohort_preparation_path(manifest_path).is_file()
        )

    def test_prepare_rejects_dangling_artifact_symlinks_without_replacement(self):
        manifest_path = self._cohort()
        for destination_name in ("private", "public"):
            with self.subTest(destination=destination_name):
                private_path = (
                    self.root
                    / "run_artifacts"
                    / f"{destination_name}-private.json"
                )
                public_path = (
                    self.root
                    / "results"
                    / f"{destination_name}-manifest.json"
                )
                destination = (
                    private_path
                    if destination_name == "private"
                    else public_path
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(
                    destination.with_name(destination.name + ".missing")
                )
                with self._contracts(), self.assertRaises(FileExistsError):
                    prepare_panel(
                        root=self.root,
                        cohort_manifest_path=manifest_path,
                        authentication_key_file=self.key_path,
                        claude_secure_storage_dir=(
                            self.claude_secure_storage_dir
                        ),
                        codex_secure_storage_dir=(
                            self.codex_secure_storage_dir
                        ),
                        private_state_path=private_path,
                        public_manifest_path=public_path,
                    )
                self.assertTrue(destination.is_symlink())
                self.assertFalse(
                    matched._cohort_preparation_path(manifest_path).exists()
                )

    def test_prepare_rejects_any_non_1800_second_timeout(self):
        manifest_path = self._cohort()
        for timeout in (1, 900, 1799, 1801, 3600):
            with (
                self.subTest(timeout=timeout),
                self._contracts(),
                self.assertRaisesRegex(ValueError, "exact 1800"),
            ):
                prepare_panel(
                    root=self.root,
                    cohort_manifest_path=manifest_path,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=self.claude_secure_storage_dir,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    timeout_seconds=timeout,
                    claude_max_budget_usd=5.0,
                )
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())

    def test_prepare_cli_defaults_to_1800_second_timeout(self):
        arguments = [
            "run_development_matched_panel.py",
            "prepare",
            "--cohort-manifest",
            "/private/cohort.manifest",
            "--authentication-key",
            "/private/authentication.key",
            "--claude-secure-storage-dir",
            "/private/claude-auth",
            "--codex-secure-storage-dir",
            "/private/codex-auth",
            "--private-state",
            "/private/state.json",
            "--public-manifest",
            "/public/manifest.json",
        ]
        with (
            patch.object(sys, "argv", arguments),
            patch.object(
                matched_cli,
                "prepare_panel",
                return_value={"panel_id": "test", "status": "precommitted"},
            ) as prepare,
            patch.object(
                matched_cli, "assert_durable_live_execution_paths"
            ),
            patch("builtins.print"),
        ):
            matched_cli.main()

        self.assertEqual(prepare.call_args.kwargs["timeout_seconds"], 1800)

    def test_prepare_rejects_any_non_five_dollar_claude_ceiling(self):
        manifest_path = self._cohort()
        for ceiling in (4.99, 5.01):
            with self.subTest(ceiling=ceiling), self._contracts(), self.assertRaisesRegex(
                ValueError, "exact \\$5"
            ):
                prepare_panel(
                    root=self.root,
                    cohort_manifest_path=manifest_path,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=self.claude_secure_storage_dir,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    claude_max_budget_usd=ceiling,
                )
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())

    def test_prepare_hides_private_fields_and_commits_balanced_schedule(self):
        public = self._prepare()
        private = json.loads(self.private_path.read_text())
        self.assertEqual(public["planned_assignments"], ASSIGNMENT_COUNT)
        self.assertEqual(len(public["episodes"]), EPISODE_COUNT)
        self.assertEqual(len(public["profiles"]), 6)
        self.assertEqual(public["panel_id"], "development-matched-50x6-v14")
        self.assertEqual(public["cohort"]["cohort_id"], COHORT_ID)
        self.assertEqual(
            public["run_contract"]["spend_authorization"],
            matched._spend_authorization_contract(),
        )
        self.assertEqual(
            private["spend_authorization"],
            matched._expected_spend_authorization(
                public,
                frozen_glean_auth_dependency_identity_sha256=private[
                    "authentication_dependency_freeze"
                ]["identity_sha256"],
            ),
        )
        self.assertEqual(
            private["spend_authorization"][
                "final_public_precommitment_sha256"
            ],
            public["precommitment_sha256"],
        )
        self.assertEqual(
            private["spend_authorization"]["budget_contract_sha256"],
            public["contract_hashes"]["budgets_sha256"],
        )
        self.assertEqual(
            private["spend_authorization"][
                "claude_cumulative_authorization_ceiling_usd"
            ],
            570.0,
        )
        self.assertEqual(
            private["spend_authorization"]["unbounded_provider_spend"],
            {"codex": "unbounded", "cursor": "unbounded"},
        )
        self.assertEqual(
            private["spend_authorization"]["acknowledgement_text"],
            REQUIRED_SPEND_ACKNOWLEDGEMENT,
        )
        self.assertEqual(
            public["run_contract"]["transport_void_policy"],
            (
                "ordinary cleanly quiesced void ends only that provider "
                "assignment and the same still-running supervised evaluator "
                "continues with the next assignment without a second outer "
                "launch; crash-orphan, provider process or state isolation, "
                "episode-service cleanup, and Codex authentication incidents "
                "are terminal and non-resumable"
            ),
        )
        self.assertEqual(
            public["run_contract"]["terminal_incident_policy"],
            {
                "crash_after_durable_start": {
                    "non_codex": ["execution_incident"],
                    "codex": [
                        "execution_incident",
                        "codex_auth_incident",
                    ],
                },
                "provider_process_or_output_pipe_isolation_failure": {
                    "non_codex": ["execution_incident"],
                    "codex": [
                        "execution_incident",
                        "codex_auth_incident",
                    ],
                },
                "provider_state_persistence_guard_failure": {
                    "non_codex": ["execution_incident"],
                    "codex": [
                        "execution_incident",
                        "codex_auth_incident",
                    ],
                },
                "episode_service_cleanup_failure": {
                    "non_codex": ["execution_incident"],
                    "codex": [
                        "execution_incident",
                        "codex_auth_incident",
                    ],
                },
                "codex_timeout_or_post_launch_credential_link_drift": [
                    "codex_auth_incident"
                ],
                "effects": (
                    "seal the current assignment as transport_void; never "
                    "retry; call no later provider; block cohort retirement, "
                    "terminal completion, and private trace release"
                ),
            },
        )
        self.assertIn(
            (
                "provider output capture is bounded, but this macOS development "
                "runner enforces no aggregate provider RSS, filesystem-byte or "
                "file-count, process-count, or OS-job ceiling; original-process-"
                "group containment is not full job containment"
            ),
            public["limitations"],
        )
        self.assertIn(
            "block cohort completion",
            public["run_contract"]["orphan_policy"],
        )
        self.assertIn(
            "detached processes",
            public["run_contract"]["provider_process_policy"],
        )
        self.assertEqual(
            public["run_contract"]["replay_trace_release"]["release"],
            "terminal_retired_panel_only",
        )
        self.assertEqual(
            public["run_contract"]["authentication_setup"],
            matched._authentication_setup_contract(self.public_path),
        )
        self.assertEqual(
            public["run_contract"]["authentication_prerequisite"],
            "committed_sanitized_receipt_before_supervisor_creation",
        )
        self.assertEqual(
            public["run_contract"]["per_provider_call_execution_attestation"],
            {
                "surfaces": [
                    "source_contract",
                    "cli_contract",
                    "runtime_contract",
                    "replay_trace_contract",
                    "profiles",
                ],
                "preflight": {
                    "before": "before_top_level_provider_harness_invocation",
                    "after": "after_top_level_provider_harness_return",
                    "drift_policy": "fail_preflight_closed",
                },
                "production": {
                    "before": "before_durable_assignment_start",
                    "after": (
                        "after_top_level_provider_harness_return_inside_transport_guard"
                    ),
                    "preexisting_drift_consumes_assignment": False,
                    "mid_call_drift": "transport_void",
                },
                "private_secrets_or_episode_packs_read_per_check": False,
            },
        )
        self.assertIn("replay_sha256", public["contract_hashes"])
        self.assertIn("supervisor_sha256", public["contract_hashes"])
        self.assertIn("claude_auth_sha256", public["contract_hashes"])
        self.assertIn("codex_auth_sha256", public["contract_hashes"])
        self.assertEqual(
            public["claude_auth_contract"]["schema_version"],
            "epiagentbench.claude_auth.v3",
        )
        self.assertEqual(
            public["claude_auth_contract"]["secure_storage_role"],
            "stable_managed_glean_auth_only",
        )
        self.assertEqual(
            public["claude_auth_contract"]["credential_backend"],
            {
                "managed_glean_api_key_helper": "required",
                "persistent_allowlist": ["credentials.json"],
                "credential_contents": "never_read_or_hashed",
                "credential_file_metadata": {
                    "type": "regular_nonsymlink",
                    "owner": "current_uid",
                    "mode": "0600",
                    "hard_links": 1,
                    "size_bytes_min": 1,
                    "size_bytes_max": 1024 * 1024,
                },
                "initial_state": "absent_at_prepare",
                "authentication_stage": (
                    "foreground_interactive_zero_model_before_preflight"
                ),
                "claude_calls": "credentials_required_before_and_after",
                "macos_keychain": "required_absent_throughout",
                "claude_plaintext_fallback": "forbidden",
            },
        )
        self.assertEqual(
            private["claude_secure_storage_dir"],
            str(self.claude_secure_storage_dir.resolve()),
        )
        self.assertEqual(
            private["claude_secure_storage_identity"],
            {
                "device": self.claude_secure_storage_dir.stat().st_dev,
                "inode": self.claude_secure_storage_dir.stat().st_ino,
            },
        )
        self.assertEqual(
            len(bytes.fromhex(private["claude_auth_commitment_key_hex"])),
            32,
        )
        self.assertTrue(
            public["claude_auth_contract"][
                "secure_storage_namespace_commitment"
            ].startswith("hmac-sha256:")
        )
        self.assertEqual(
            public["codex_auth_contract"]["schema_version"],
            "epiagentbench.codex_auth.v1",
        )
        self.assertEqual(
            public["codex_auth_contract"]["secure_storage_role"],
            "stable_codex_auth_only",
        )
        self.assertEqual(
            private["codex_secure_storage_dir"],
            str(self.codex_secure_storage_dir.resolve()),
        )
        self.assertEqual(
            private["codex_secure_storage_identity"],
            {
                "device": self.codex_secure_storage_dir.stat().st_dev,
                "inode": self.codex_secure_storage_dir.stat().st_ino,
            },
        )
        self.assertEqual(
            len(bytes.fromhex(private["codex_auth_commitment_key_hex"])),
            32,
        )
        self.assertTrue(
            public["codex_auth_contract"][
                "secure_storage_namespace_commitment"
            ].startswith("hmac-sha256:")
        )
        self.assertEqual(
            public["schedule_design"],
            {
                "name": "private_family_stratified_near_balanced_williams",
                "profile_position_count_min": 8,
                "profile_position_count_max": 9,
                "within_family_profile_position_count_min": 1,
                "within_family_profile_position_count_max": 2,
                "ordered_carryover_count_min": 8,
                "ordered_carryover_count_max": 9,
                "within_family_ordered_carryover_count_min": 1,
                "within_family_ordered_carryover_count_max": 2,
                "order_released_only_after_terminal_panel": True,
            },
        )
        self.assertEqual(
            public["run_contract"]["bootstrap"]["pairwise_multiplicity"],
            "bonferroni_fifteen_pairs",
        )
        self.assertEqual(os.stat(self.private_path).st_mode & 0o777, 0o600)
        cohort_manifest_path = Path(private["cohort_manifest_path"])
        self.assertFalse(
            matched._cohort_retirement_path(cohort_manifest_path).exists()
        )
        encoded = json.dumps(public)
        hidden_assignment_surface = json.dumps(
            {
                "episodes": public["episodes"],
                "schedule_design": public["schedule_design"],
                "results": public["results"],
            }
        )
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn(str(self.claude_secure_storage_dir), encoded)
        self.assertNotIn(str(self.codex_secure_storage_dir), encoded)
        self.assertNotIn(private["claude_auth_commitment_key_hex"], encoded)
        self.assertNotIn(private["codex_auth_commitment_key_hex"], encoded)
        for family in FAMILIES:
            self.assertNotIn(family, hidden_assignment_surface)
        for forbidden in ("pack_path", "seed", "episode_secret", "profile_order"):
            self.assertNotIn(forbidden, encoded)

        keys = matched._assignment_keys(private["schedule"])
        self.assertEqual(len(keys), ASSIGNMENT_COUNT)
        self.assertEqual(len(set(keys)), ASSIGNMENT_COUNT)
        self.assertEqual(
            Counter(item["family"] for item in private["episodes"]),
            Counter({family: 10 for family in FAMILIES}),
        )
        profile_ids = {profile["profile_id"] for profile in PROFILES}
        self.assertTrue(
            all(
                len(item["profile_order"]) == len(PROFILES)
                and set(item["profile_order"]) == profile_ids
                for item in private["schedule"]
            )
        )
        for position in range(len(PROFILES)):
            counts = Counter(
                item["profile_order"][position] for item in private["schedule"]
            )
            self.assertEqual(set(counts), profile_ids)
            self.assertTrue(set(counts.values()).issubset({8, 9}))

        family_by_ref = {
            item["episode_ref"]: item["family"] for item in private["episodes"]
        }
        expected_carryovers = {
            (first, second)
            for first in profile_ids
            for second in profile_ids
            if first != second
        }
        overall_carryovers: Counter[tuple[str, str]] = Counter()
        for family in FAMILIES:
            family_schedule = [
                item
                for item in private["schedule"]
                if family_by_ref[item["episode_ref"]] == family
            ]
            self.assertEqual(len(family_schedule), 10)
            for position in range(len(PROFILES)):
                counts = Counter(
                    item["profile_order"][position] for item in family_schedule
                )
                self.assertEqual(set(counts), profile_ids)
                self.assertTrue(set(counts.values()).issubset({1, 2}))
            family_carryovers = Counter(
                pair
                for item in family_schedule
                for pair in zip(
                    item["profile_order"], item["profile_order"][1:]
                )
            )
            self.assertEqual(set(family_carryovers), expected_carryovers)
            self.assertTrue(
                set(family_carryovers.values()).issubset({1, 2})
            )
            overall_carryovers.update(family_carryovers)
        self.assertEqual(set(overall_carryovers), expected_carryovers)
        self.assertTrue(set(overall_carryovers.values()).issubset({8, 9}))

    def test_prepare_rejects_wrong_cardinality_and_public_tamper(self):
        with self.assertRaisesRegex(ValueError, "exactly 50"):
            self._prepare(self._cohort(49))

        self.private_path.unlink(missing_ok=True)
        self.public_path.unlink(missing_ok=True)
        self._prepare()
        public = json.loads(self.public_path.read_text())
        public["episodes"][0]["pack_commitment"] = "sha256:" + "f" * 64
        with self._contracts(), self.assertRaisesRegex(ValueError, "precommitment"):
            matched._validate_contracts(
                root=self.root,
                private=matched._load_private_state(
                    self.private_path, AUTHENTICATION_KEY
                ),
                public=public,
                authentication_key=AUTHENTICATION_KEY,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
            )

    def test_claude_secure_storage_validation_rejects_unsafe_paths(self):
        self.assertEqual(
            matched._validate_claude_secure_storage_dir(
                self.claude_secure_storage_dir, root=self.root
            ),
            self.claude_secure_storage_dir.resolve(),
        )

        invalid_file = self.claude_secure_storage_dir / "not-a-directory"
        invalid_file.write_text("not credentials\n")
        missing = self.claude_secure_storage_dir / "missing"
        repository_storage = self.root / "claude-auth"
        repository_storage.mkdir(mode=0o700)
        with TemporaryDirectory(dir="/tmp") as temporary_storage:
            os.chmod(temporary_storage, 0o700)
            unsafe = (
                Path("relative-auth"),
                invalid_file,
                missing,
                repository_storage,
                Path(temporary_storage),
            )
            for path in unsafe:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    matched._validate_claude_secure_storage_dir(
                        path, root=self.root
                    )

        os.chmod(self.claude_secure_storage_dir, 0o755)
        try:
            with self.assertRaisesRegex(ValueError, "exact 0700"):
                matched._validate_claude_secure_storage_dir(
                    self.claude_secure_storage_dir, root=self.root
                )
        finally:
            os.chmod(self.claude_secure_storage_dir, 0o700)

        target = self.claude_secure_storage_dir / "real"
        target.mkdir(mode=0o700)
        alias = self.claude_secure_storage_dir / "alias"
        alias.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            matched._validate_claude_secure_storage_dir(alias, root=self.root)

    def test_live_execution_requires_external_durable_private_state(self):
        self.assertTrue(
            matched._is_temporary_storage_path(
                Path("/var/tmp/epiagentbench-disposable")
            )
        )
        with (
            TemporaryDirectory(
                prefix="epiagentbench-live-root-", dir=Path.home()
            ) as durable_root_text,
            TemporaryDirectory(
                prefix="epiagentbench-private-state-", dir=Path.home()
            ) as state_root_text,
        ):
            durable_root = Path(durable_root_text)
            state_root = Path(state_root_text)
            os.chmod(durable_root, 0o700)
            os.chmod(state_root, 0o700)
            state_path = state_root / "private.json"
            matched.assert_durable_live_execution_paths(
                root=durable_root,
                private_state_path=state_path,
            )
            binding = matched._private_state_storage_binding(
                state_path,
                root=durable_root,
            )
            self.assertEqual(binding["storage_class"], "durable_external")

            repository_state = durable_root / "private.json"
            with self.assertRaisesRegex(ValueError, "outside the repository"):
                matched.assert_durable_live_execution_paths(
                    root=durable_root,
                    private_state_path=repository_state,
                )

            os.chmod(state_root, 0o755)
            try:
                with self.assertRaisesRegex(ValueError, "current-user 0700"):
                    matched.assert_durable_live_execution_paths(
                        root=durable_root,
                        private_state_path=state_path,
                    )
            finally:
                os.chmod(state_root, 0o700)

        with self.assertRaisesRegex(RuntimeError, "outside OS temporary"):
            matched.assert_durable_live_execution_paths(
                root=self.root,
                private_state_path=self.private_path,
            )

    def test_private_state_storage_binding_rejects_relocation_and_hard_links(self):
        with (
            TemporaryDirectory(
                prefix="epiagentbench-live-root-", dir=Path.home()
            ) as durable_root_text,
            TemporaryDirectory(
                prefix="epiagentbench-private-state-", dir=Path.home()
            ) as first_state_root_text,
            TemporaryDirectory(
                prefix="epiagentbench-private-state-copy-", dir=Path.home()
            ) as second_state_root_text,
        ):
            durable_root = Path(durable_root_text)
            first_state_root = Path(first_state_root_text)
            second_state_root = Path(second_state_root_text)
            for directory in (
                durable_root,
                first_state_root,
                second_state_root,
            ):
                os.chmod(directory, 0o700)
            state_path = first_state_root / "private.json"
            private = {
                "private_state_storage": matched._private_state_storage_binding(
                    state_path,
                    root=durable_root,
                ),
                "status": "test",
            }
            matched._write_private_state(
                state_path, private, AUTHENTICATION_KEY
            )
            self.assertEqual(
                matched._load_private_state(state_path, AUTHENTICATION_KEY),
                private,
            )

            relocated = second_state_root / "private.json"
            relocated.write_bytes(state_path.read_bytes())
            os.chmod(relocated, 0o600)
            with self.assertRaisesRegex(ValueError, "storage binding"):
                matched._load_private_state(relocated, AUTHENTICATION_KEY)

            hard_link = first_state_root / "private-hard-link.json"
            os.link(state_path, hard_link)
            try:
                with self.assertRaisesRegex(ValueError, "Unsafe matched-panel"):
                    matched._load_private_state(
                        state_path, AUTHENTICATION_KEY
                    )
            finally:
                hard_link.unlink()

    def test_managed_glean_credential_attestation_is_metadata_only(self):
        self.assertFalse(
            matched._attest_managed_glean_credentials(
                self.claude_secure_storage_dir
            )
        )
        credential = self.claude_secure_storage_dir / "credentials.json"
        credential.write_bytes(b"opaque-test-credential")
        credential.chmod(0o600)
        with patch.object(
            Path,
            "read_bytes",
            side_effect=AssertionError("credential contents must not be read"),
        ), patch.object(
            Path,
            "open",
            side_effect=AssertionError("credential contents must not be opened"),
        ):
            self.assertTrue(
                matched._attest_managed_glean_credentials(
                    self.claude_secure_storage_dir
                )
            )

        replacement = self.claude_secure_storage_dir / "replacement"
        replacement.write_bytes(b"rotated-opaque-test-credential")
        replacement.chmod(0o600)
        os.replace(replacement, credential)
        self.assertTrue(
            matched._attest_managed_glean_credentials(
                self.claude_secure_storage_dir
            )
        )

    def test_managed_glean_credential_attestation_rejects_unsafe_tree(self):
        def assert_rejected(setup) -> None:
            with TemporaryDirectory(
                prefix="epiagentbench-glean-tree-", dir=Path.home()
            ) as container:
                root = Path(container) / "auth"
                root.mkdir(mode=0o700)
                setup(root)
                with self.assertRaises(RuntimeError):
                    matched._attest_managed_glean_credentials(root)

        def wrong_mode(root: Path) -> None:
            credential = root / "credentials.json"
            credential.write_bytes(b"opaque")
            credential.chmod(0o644)

        def empty(root: Path) -> None:
            credential = root / "credentials.json"
            credential.touch(mode=0o600)

        def oversized(root: Path) -> None:
            credential = root / "credentials.json"
            credential.touch(mode=0o600)
            os.truncate(
                credential,
                matched._MAX_MANAGED_GLEAN_CREDENTIAL_BYTES + 1
            )

        def symlink(root: Path) -> None:
            target = root.parent / (root.name + "-target")
            target.write_bytes(b"opaque")
            target.chmod(0o600)
            (root / "credentials.json").symlink_to(target)

        def hardlink(root: Path) -> None:
            target = root.parent / (root.name + "-target")
            target.write_bytes(b"opaque")
            target.chmod(0o600)
            os.link(target, root / "credentials.json")

        def extra(root: Path) -> None:
            credential = root / "credentials.json"
            credential.write_bytes(b"opaque")
            credential.chmod(0o600)
            (root / "unexpected").write_text("metadata leak")

        def directory(root: Path) -> None:
            (root / "credentials.json").mkdir(mode=0o700)

        def wrong_parent_mode(root: Path) -> None:
            root.chmod(0o755)

        for name, setup in (
            ("wrong_mode", wrong_mode),
            ("empty", empty),
            ("oversized", oversized),
            ("symlink", symlink),
            ("hardlink", hardlink),
            ("extra", extra),
            ("directory", directory),
            ("wrong_parent_mode", wrong_parent_mode),
        ):
            with self.subTest(name=name):
                assert_rejected(setup)

    def test_no_capture_group_helper_quiesces_success_without_pipes(self):
        command = ["/trusted/login", "--authenticate"]
        events: list[str] = []
        with (
            patch(
                "epiagentbench.development_matched_panel.subprocess.Popen"
            ) as start,
            patch(
                "epiagentbench.development_matched_panel."
                "_quiesce_provider_process_group"
            ) as quiesce,
        ):
            process = start.return_value
            process.wait.return_value = 0
            quiesce.side_effect = lambda *_args, **_kwargs: events.append(
                "quiesced"
            )
            result = matched._run_no_capture_process_group(
                command,
                cwd=self.root,
                environment={"PATH": "/bin"},
                timeout_seconds=30,
                stdout_target=subprocess.DEVNULL,
                stderr_target=None,
                umask=0o077,
                invocation_launch_pending=lambda: events.append(
                    "launch_pending"
                ),
                invocation_started=lambda: events.append("started"),
                invocation_start_failed=lambda: events.append(
                    "start_failed"
                ),
                invocation_returned=lambda returncode: events.append(
                    f"returned:{returncode}"
                ),
            )

        self.assertEqual(result.returncode, 0)
        invocation = start.call_args.kwargs
        self.assertIs(invocation["stdin"], subprocess.DEVNULL)
        self.assertIs(invocation["stdout"], subprocess.DEVNULL)
        self.assertIsNone(invocation["stderr"])
        self.assertNotIn(subprocess.PIPE, (invocation["stdout"], invocation["stderr"]))
        self.assertTrue(invocation["start_new_session"])
        self.assertEqual(process.wait.call_count, 2)
        quiesce.assert_called_once_with(process, force=False)
        self.assertEqual(
            events,
            ["launch_pending", "started", "quiesced", "returned:0"],
        )

    def test_no_capture_group_helper_forces_timeout_group_cleanup(self):
        command = ["/trusted/login", "--authenticate"]
        timeout = subprocess.TimeoutExpired(command, 2)
        events: list[str] = []
        with (
            patch(
                "epiagentbench.development_matched_panel.subprocess.Popen"
            ) as start,
            patch(
                "epiagentbench.development_matched_panel."
                "_quiesce_provider_process_group"
            ) as quiesce,
        ):
            process = start.return_value
            process.wait.side_effect = [timeout, 0]
            with self.assertRaises(subprocess.TimeoutExpired):
                matched._run_no_capture_process_group(
                    command,
                    cwd=self.root,
                    environment={"PATH": "/bin"},
                    timeout_seconds=2,
                    stdout_target=subprocess.DEVNULL,
                    stderr_target=subprocess.DEVNULL,
                    umask=0o077,
                    invocation_launch_pending=lambda: events.append(
                        "launch_pending"
                    ),
                    invocation_started=lambda: events.append("started"),
                    invocation_start_failed=lambda: events.append(
                        "start_failed"
                    ),
                    invocation_returned=lambda returncode: events.append(
                        f"returned:{returncode}"
                    ),
                )

        quiesce.assert_called_once_with(process, force=True)
        self.assertEqual(process.wait.call_count, 2)
        self.assertEqual(events, ["launch_pending", "started"])

    def test_no_capture_group_helper_has_typed_start_and_wait_failures(self):
        events: list[str] = []
        kwargs = {
            "cwd": self.root,
            "environment": {"PATH": "/bin"},
            "timeout_seconds": 2,
            "stdout_target": subprocess.DEVNULL,
            "stderr_target": subprocess.DEVNULL,
            "umask": 0o077,
            "invocation_launch_pending": lambda: events.append(
                "launch_pending"
            ),
            "invocation_started": lambda: events.append("started"),
            "invocation_start_failed": lambda: events.append(
                "start_failed"
            ),
            "invocation_returned": lambda returncode: events.append(
                f"returned:{returncode}"
            ),
        }
        with (
            patch(
                "epiagentbench.development_matched_panel.subprocess.Popen",
                side_effect=OSError("start fault"),
            ),
            self.assertRaises(ProviderProcessIsolationError),
        ):
            matched._run_no_capture_process_group(["/trusted/login"], **kwargs)
        self.assertEqual(events, ["launch_pending", "start_failed"])
        events.clear()

        with (
            patch(
                "epiagentbench.development_matched_panel.subprocess.Popen"
            ) as start,
            patch(
                "epiagentbench.development_matched_panel."
                "_quiesce_provider_process_group"
            ) as quiesce,
            self.assertRaises(ProviderProcessIsolationError),
        ):
            process = start.return_value
            process.wait.side_effect = [OSError("wait fault"), 0]
            matched._run_no_capture_process_group(["/trusted/login"], **kwargs)
        quiesce.assert_called_once_with(process, force=True)
        self.assertEqual(events, ["launch_pending", "started"])

    def test_no_capture_cleanup_failure_dominates_active_state_error(self):
        active = ProviderStateIsolationError("test durable-marker failure")
        cleanup = ProviderProcessIsolationError("test process cleanup failure")
        events: list[str] = []

        def fail_started_marker() -> None:
            raise active

        with (
            patch(
                "epiagentbench.development_matched_panel.subprocess.Popen"
            ) as start,
            patch(
                "epiagentbench.development_matched_panel."
                "_quiesce_provider_process_group",
                side_effect=cleanup,
            ),
            self.assertRaises(ProviderProcessIsolationError) as raised,
        ):
            matched._run_no_capture_process_group(
                ["/trusted/login"],
                cwd=self.root,
                environment={"PATH": "/bin"},
                timeout_seconds=2,
                stdout_target=subprocess.DEVNULL,
                stderr_target=subprocess.DEVNULL,
                umask=0o077,
                invocation_launch_pending=lambda: events.append(
                    "launch_pending"
                ),
                invocation_started=fail_started_marker,
            )
        self.assertIs(raised.exception, cleanup)
        self.assertIs(raised.exception.__cause__, active)
        self.assertEqual(events, ["launch_pending"])
        self.assertEqual(start.call_count, 1)

    def test_identity_contract_hashes_files_without_running_provider_processes(self):
        executable = self.root / "identity-cli"
        executable.write_bytes(b"fixed executable bytes")
        executable.chmod(0o755)
        expected = "sha256:" + hashlib.sha256(
            b"fixed executable bytes"
        ).hexdigest()

        with (
            patch(
                "epiagentbench.development_matched_panel.shutil.which",
                return_value=str(executable),
            ),
            patch(
                "epiagentbench.development_matched_panel._GLEAN_HELPER_PATH",
                executable,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_root_owned_regular_executable_sha256",
                return_value=expected,
            ) as root_owned_hash,
            patch(
                "epiagentbench.development_matched_panel."
                "_run_provider_process_group",
                side_effect=AssertionError("identity hashing must not execute"),
            ) as run_group,
        ):
            cli_identity = matched._read_cli_identity("identity-cli")
            glean_identity = matched._glean_helper_identity()

        self.assertEqual(
            cli_identity,
            {"name": "identity-cli", "executable_sha256": expected},
        )
        self.assertEqual(
            glean_identity,
            {
                "path": str(executable),
                "sha256": expected,
                "policy": (
                    "root_owned_root_group_single_link_regular_"
                    "nonwritable_executable"
                ),
            },
        )
        self.assertEqual(root_owned_hash.call_count, 2)
        run_group.assert_not_called()

    def test_glean_dependency_bundle_freeze_rejects_mixed_snapshot(self):
        wrapper = copy.deepcopy(
            AUTHENTICATION_DEPENDENCY_IDENTITY[
                "glean_llm_gateway_token_wrapper"
            ]
        )
        with (
            patch(
                "epiagentbench.development_matched_panel."
                "_glean_helper_identity",
                side_effect=[
                    {
                        "path": str(matched._GLEAN_HELPER_PATH),
                        "sha256": "sha256:" + "1" * 64,
                        "policy": (
                            "root_owned_root_group_single_link_regular_"
                            "nonwritable_executable"
                        ),
                    },
                    {
                        "path": str(matched._GLEAN_HELPER_PATH),
                        "sha256": "sha256:" + "2" * 64,
                        "policy": (
                            "root_owned_root_group_single_link_regular_"
                            "nonwritable_executable"
                        ),
                    },
                ],
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_root_owned_regular_executable_identity",
                return_value={
                    name: value
                    for name, value in wrapper.items()
                    if name != "dispatch_contract"
                },
            ),
            patch(
                "epiagentbench.development_matched_panel.subprocess.Popen",
                side_effect=AssertionError("identity freeze must not execute"),
            ) as popen,
            self.assertRaisesRegex(
                ProviderStateIsolationError,
                "changed during identity freeze",
            ),
        ):
            matched._current_glean_auth_dependency_identity()
        popen.assert_not_called()

    def test_authorization_identity_rejects_non_root_or_symlink_entrypoint(self):
        regular = self.root / "gateway-token"
        regular.write_bytes(b"gateway-token\n")
        regular.chmod(0o755)
        symlink = self.root / "gateway-token-link"
        symlink.symlink_to(regular)

        for path in (regular, symlink):
            with (
                self.subTest(path=path),
                patch(
                    "epiagentbench.development_matched_panel."
                    "_require_root_owned_nonwritable_ancestry"
                ),
                self.assertRaisesRegex(RuntimeError, "ownership policy drifted"),
            ):
                matched._root_owned_regular_executable_identity(
                    path, label="gateway"
                )

    def test_root_managed_executable_policy_rejects_every_metadata_downgrade(self):
        def metadata(
            *,
            mode: int = stat.S_IFREG | 0o755,
            links: int = 1,
            uid: int = 0,
            gid: int = 0,
        ) -> os.stat_result:
            return os.stat_result(
                (mode, 1, 1, links, uid, gid, 10, 0, 0, 0)
            )

        matched._require_root_owned_regular_executable_metadata(
            metadata(), label="gateway"
        )
        downgraded = (
            metadata(mode=stat.S_IFLNK | 0o755),
            metadata(mode=stat.S_IFREG | 0o775),
            metadata(mode=stat.S_IFREG | 0o644),
            metadata(links=2),
            metadata(uid=max(os.getuid(), 1)),
            metadata(gid=max(os.getgid(), 1)),
        )
        for observed in downgraded:
            with self.subTest(observed=observed), self.assertRaisesRegex(
                RuntimeError, "ownership policy drifted"
            ):
                matched._require_root_owned_regular_executable_metadata(
                    observed, label="gateway"
                )

        untrusted = self.root / "gateway-token"
        untrusted.write_bytes(b"gateway-token\n")
        with self.assertRaisesRegex(
            RuntimeError, "ancestor ownership policy drifted"
        ):
            matched._require_root_owned_nonwritable_ancestry(
                untrusted, label="gateway"
            )

    def test_cli_contract_is_provider_process_free(self):
        forbidden = AssertionError("CLI contract attempted to execute a process")

        def identity(executable: str) -> dict[str, str]:
            return {
                "name": executable,
                "executable_sha256": "sha256:" + "1" * 64,
            }

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "epiagentbench.development_matched_panel._read_cli_identity",
                side_effect=identity,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_glean_helper_identity",
                side_effect=forbidden,
            ) as glean_identity,
            patch(
                "epiagentbench.development_matched_panel._safe_glean_config",
                return_value=(
                    self._glean_config_fixture(),
                    {
                        "path": str(matched._GLEAN_CONFIG_PATH),
                        "sha256": "sha256:" + "3" * 64,
                    },
                ),
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_managed_settings_identity",
                return_value=(
                    {"sha256": "sha256:" + "4" * 64},
                    False,
                ),
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_safe_entrypoint_identity",
                side_effect=forbidden,
            ) as entrypoint_identity,
            patch(
                "epiagentbench.development_matched_panel."
                "_deferred_root_owned_executable_contract",
                side_effect=lambda path, **_kwargs: {
                    "path": str(path),
                    "entrypoint_kind": (
                        "root_owned_single_link_regular_executable"
                    ),
                    "group_or_world_writable": False,
                    "trusted_root_owned_nonwritable_ancestry": True,
                    "exact_content_freeze_stage": (
                        "manifest_bound_spend_authorization_before_"
                        "authentication"
                    ),
                    "freeze_once": True,
                    "required_live_attestation_boundaries": [],
                },
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_fixed_file_sha256",
                return_value="sha256:" + "6" * 64,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_run_provider_process_group",
                side_effect=forbidden,
            ) as provider_process,
            patch(
                "epiagentbench.development_matched_panel.subprocess.run",
                side_effect=forbidden,
            ) as subprocess_run,
            patch(
                "epiagentbench.development_matched_panel.subprocess.Popen",
                side_effect=forbidden,
            ) as subprocess_popen,
        ):
            contract = matched._cli_contract()

        self.assertEqual(
            {item["name"] for item in contract["executables"]},
            {"claude", "codex", "cursor-agent"},
        )
        glean_identity.assert_not_called()
        entrypoint_identity.assert_not_called()
        provider_process.assert_not_called()
        subprocess_run.assert_not_called()
        subprocess_popen.assert_not_called()

    def test_managed_glean_bootstrap_discards_token_and_cleans_home(self):
        captured_home: Path | None = None

        def bootstrap(command, **kwargs):
            nonlocal captured_home
            self.assertEqual(
                command, [str(matched._GLEAN_GATEWAY_TOKEN_WRAPPER_PATH)]
            )
            self.assertIsNone(kwargs["stdin_target"])
            self.assertIs(kwargs["stdout_target"], subprocess.DEVNULL)
            self.assertIsNone(kwargs["stderr_target"])
            self.assertEqual(kwargs["umask"], 0o077)
            self.assertEqual(kwargs["timeout_seconds"], 30)
            environment = kwargs["environment"]
            self.assertEqual(
                environment["GLEAN_HELPER_OAUTH_CLIENT_ID"],
                "test-client-id",
            )
            captured_home = Path(environment["HOME"])
            link = captured_home / ".glean-llm-gateway"
            self.assertTrue(link.is_symlink())
            self.assertNotEqual(
                link.resolve(), self.claude_secure_storage_dir.resolve()
            )
            self.assertEqual(
                link.resolve().parent, captured_home.parent.parent
            )
            credential = link / "credentials.json"
            credential.write_bytes(b"opaque-bootstrap-credential")
            credential.chmod(0o600)
            return subprocess.CompletedProcess(command, 0)

        with patch(
            "epiagentbench.development_matched_panel."
            "_run_no_capture_process_group",
            side_effect=bootstrap,
        ):
            matched._bootstrap_managed_glean_credentials(
                self.claude_secure_storage_dir,
                oauth_client_id="test-client-id",
                timeout_seconds=30,
            )
        assert captured_home is not None
        self.assertFalse(captured_home.exists())
        self.assertTrue(
            matched._attest_managed_glean_credentials(
                self.claude_secure_storage_dir
            )
        )

    def test_glean_bootstrap_preserves_process_incident_over_final_guard(self):
        incident = ProviderProcessIsolationError(
            "Authentication process group remained alive"
        )
        with (
            patch(
                "epiagentbench.development_matched_panel."
                "_run_no_capture_process_group",
                side_effect=incident,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_attest_managed_glean_home_link",
                side_effect=[None, RuntimeError("final guard fault")],
            ),
            self.assertRaises(ProviderProcessIsolationError) as raised,
        ):
            matched._bootstrap_managed_glean_credentials(
                self.claude_secure_storage_dir,
                oauth_client_id="test-client-id",
                timeout_seconds=30,
            )
        self.assertIs(raised.exception, incident)

    def test_codex_bootstrap_relocates_independent_disposable_file_store(self):
        captured_codex_home: Path | None = None

        def login(command, **kwargs):
            nonlocal captured_codex_home
            self.assertEqual(
                command,
                [
                    "/trusted/codex",
                    "login",
                    "--device-auth",
                    "-c",
                    'cli_auth_credentials_store="file"',
                ],
            )
            self.assertIsNone(kwargs["stdin_target"])
            self.assertIsNone(kwargs["stdout_target"])
            self.assertIsNone(kwargs["stderr_target"])
            self.assertEqual(kwargs["umask"], 0o077)
            self.assertEqual(kwargs["timeout_seconds"], 30)
            environment = kwargs["environment"]
            self.assertEqual(set(environment) & {"OPENAI_API_KEY", "CURSOR_API_KEY"}, set())
            captured_codex_home = Path(environment["CODEX_HOME"])
            staged_auth = captured_codex_home / "auth.json"
            self.assertFalse(staged_auth.exists())
            self.assertFalse(staged_auth.is_symlink())
            self.assertEqual(
                captured_codex_home.parent.parent.parent,
                self.codex_secure_storage_dir.parent,
            )
            self.assertFalse((self.codex_secure_storage_dir / "auth.json").exists())
            # Codex 0.144.3 logs out before OAuth: it removes this path even
            # when absent, then writes a new regular file after the callback.
            staged_auth.unlink(missing_ok=True)
            staged_auth.write_bytes(b"independent-panel-oauth")
            staged_auth.chmod(0o600)
            side_state = captured_codex_home / "tmp" / "arg0"
            side_state.mkdir(parents=True)
            (side_state / "lock").write_text("disposable", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)

        with (
            patch.dict(
                os.environ,
                {
                    "PATH": "/bin",
                    "OPENAI_API_KEY": "must-not-pass",
                    "CURSOR_API_KEY": "must-not-pass",
                    "NODE_OPTIONS": "--require=/tmp/inject.js",
                },
                clear=True,
            ),
            patch(
                "epiagentbench.development_matched_panel.shutil.which",
                return_value="/trusted/codex",
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_run_no_capture_process_group",
                side_effect=login,
            ) as invoked,
        ):
            matched._bootstrap_codex_credentials(
                self.codex_secure_storage_dir,
                executable="codex",
                timeout_seconds=30,
            )

        self.assertEqual(invoked.call_count, 1)
        assert captured_codex_home is not None
        self.assertFalse(captured_codex_home.exists())
        self.assertTrue(
            matched._attest_codex_auth_storage(
                self.codex_secure_storage_dir
            )
        )
        self.assertEqual(
            {entry.name for entry in os.scandir(self.codex_secure_storage_dir)},
            {"auth.json"},
        )

    def test_codex_bootstrap_nonzero_or_missing_auth_never_publishes(self):
        captured_homes: list[Path] = []

        for returncode in (1, 0):
            def login(command, **kwargs):
                home = Path(kwargs["environment"]["CODEX_HOME"])
                captured_homes.append(home)
                (home / "auth.json").unlink(missing_ok=True)
                return subprocess.CompletedProcess(command, returncode)

            with (
                self.subTest(returncode=returncode),
                patch(
                    "epiagentbench.development_matched_panel.shutil.which",
                    return_value="/trusted/codex",
                ),
                patch(
                    "epiagentbench.development_matched_panel."
                    "_run_no_capture_process_group",
                    side_effect=login,
                ),
                self.assertRaisesRegex(
                    RuntimeError, "Codex authentication bootstrap failed"
                ),
            ):
                matched._bootstrap_codex_credentials(
                    self.codex_secure_storage_dir,
                    executable="codex",
                    timeout_seconds=30,
                )
            self.assertEqual(
                list(os.scandir(self.codex_secure_storage_dir)), []
            )

        self.assertTrue(all(not path.exists() for path in captured_homes))

    def test_codex_bootstrap_rejects_unsafe_staged_auth_metadata(self):
        def symlink(path: Path) -> None:
            target = path.with_name("staged-target")
            target.write_bytes(b"credential")
            target.chmod(0o600)
            path.symlink_to(target.name)

        def hardlink(path: Path) -> None:
            path.write_bytes(b"credential")
            path.chmod(0o600)
            os.link(path, path.with_name("second-link"))

        def fifo(path: Path) -> None:
            os.mkfifo(path, mode=0o600)

        def directory(path: Path) -> None:
            path.mkdir(mode=0o700)

        def wrong_mode(path: Path) -> None:
            path.write_bytes(b"credential")
            path.chmod(0o644)

        def empty(path: Path) -> None:
            path.write_bytes(b"")
            path.chmod(0o600)

        def oversized(path: Path) -> None:
            path.touch(mode=0o600)
            path.chmod(0o600)
            with path.open("r+b") as stream:
                stream.truncate(
                    matched._CODEX_BOOTSTRAP_AUTH_BYTES_MAX + 1
                )

        for label, create in (
            ("symlink", symlink),
            ("hardlink", hardlink),
            ("fifo", fifo),
            ("directory", directory),
            ("wrong_mode", wrong_mode),
            ("empty", empty),
            ("oversized", oversized),
        ):
            captured_home: Path | None = None

            def login(command, **kwargs):
                nonlocal captured_home
                captured_home = Path(kwargs["environment"]["CODEX_HOME"])
                staged_auth = captured_home / "auth.json"
                staged_auth.unlink(missing_ok=True)
                create(staged_auth)
                return subprocess.CompletedProcess(command, 0)

            with (
                self.subTest(label=label),
                patch(
                    "epiagentbench.development_matched_panel.shutil.which",
                    return_value="/trusted/codex",
                ),
                patch(
                    "epiagentbench.development_matched_panel."
                    "_run_no_capture_process_group",
                    side_effect=login,
                ),
                self.assertRaises(ProviderStateIsolationError),
            ):
                matched._bootstrap_codex_credentials(
                    self.codex_secure_storage_dir,
                    executable="codex",
                    timeout_seconds=30,
                )
            assert captured_home is not None
            self.assertFalse(captured_home.exists())
            self.assertEqual(
                list(os.scandir(self.codex_secure_storage_dir)), []
            )

    def test_codex_bootstrap_target_race_is_no_clobber(self):
        stable_auth = self.codex_secure_storage_dir / "auth.json"
        original_link = os.link

        def login(command, **kwargs):
            staged_auth = Path(kwargs["environment"]["CODEX_HOME"]) / "auth.json"
            staged_auth.unlink(missing_ok=True)
            staged_auth.write_bytes(b"new-credential")
            staged_auth.chmod(0o600)
            return subprocess.CompletedProcess(command, 0)

        def race_link(*args, **kwargs):
            stable_auth.write_bytes(b"racing-credential")
            stable_auth.chmod(0o600)
            return original_link(*args, **kwargs)

        with (
            patch(
                "epiagentbench.development_matched_panel.shutil.which",
                return_value="/trusted/codex",
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_run_no_capture_process_group",
                side_effect=login,
            ),
            patch(
                "epiagentbench.development_matched_panel.os.link",
                side_effect=race_link,
            ),
            self.assertRaises(ProviderStateIsolationError),
        ):
            matched._bootstrap_codex_credentials(
                self.codex_secure_storage_dir,
                executable="codex",
                timeout_seconds=30,
            )
        self.assertEqual(stable_auth.read_bytes(), b"racing-credential")

    def test_codex_bootstrap_promotion_failure_leaves_target_empty(self):
        def login(command, **kwargs):
            staged_auth = Path(kwargs["environment"]["CODEX_HOME"]) / "auth.json"
            staged_auth.unlink(missing_ok=True)
            staged_auth.write_bytes(b"credential")
            staged_auth.chmod(0o600)
            return subprocess.CompletedProcess(command, 0)

        with (
            patch(
                "epiagentbench.development_matched_panel.shutil.which",
                return_value="/trusted/codex",
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_run_no_capture_process_group",
                side_effect=login,
            ),
            patch(
                "epiagentbench.development_matched_panel.os.link",
                side_effect=OSError("test relocation failure"),
            ),
            self.assertRaisesRegex(
                ProviderStateIsolationError, "promotion failed"
            ),
        ):
            matched._bootstrap_codex_credentials(
                self.codex_secure_storage_dir,
                executable="codex",
                timeout_seconds=30,
            )
        self.assertEqual(list(os.scandir(self.codex_secure_storage_dir)), [])

    def test_codex_promotion_fsyncs_target_before_source_unlink(self):
        events: list[str] = []
        target_metadata = self.codex_secure_storage_dir.stat()
        real_link = os.link
        real_fsync = os.fsync
        real_unlink = os.unlink

        with TemporaryDirectory(
            prefix="eabp-staging-",
            dir=self.codex_secure_storage_dir.parent,
        ) as temporary:
            staging = Path(temporary)
            staging.chmod(0o700)
            staged_auth = staging / "auth.json"
            staged_auth.write_bytes(b"opaque-credential")
            staged_auth.chmod(0o600)
            staging_metadata = staging.stat()

            def tracked_link(*args, **kwargs):
                events.append("link")
                return real_link(*args, **kwargs)

            def tracked_fsync(descriptor: int):
                metadata = os.fstat(descriptor)
                if (
                    metadata.st_dev == target_metadata.st_dev
                    and metadata.st_ino == target_metadata.st_ino
                ):
                    events.append("target_fsync")
                return real_fsync(descriptor)

            def tracked_unlink(*args, **kwargs):
                directory_descriptor = kwargs.get("dir_fd")
                if directory_descriptor is not None:
                    metadata = os.fstat(directory_descriptor)
                    if (
                        metadata.st_dev == staging_metadata.st_dev
                        and metadata.st_ino == staging_metadata.st_ino
                    ):
                        events.append("source_unlink")
                return real_unlink(*args, **kwargs)

            with (
                patch(
                    "epiagentbench.development_matched_panel.os.link",
                    side_effect=tracked_link,
                ),
                patch(
                    "epiagentbench.development_matched_panel.os.fsync",
                    side_effect=tracked_fsync,
                ),
                patch(
                    "epiagentbench.development_matched_panel.os.unlink",
                    side_effect=tracked_unlink,
                ),
            ):
                matched._promote_staged_codex_auth(
                    staging,
                    self.codex_secure_storage_dir,
                    expected_target_identity=(
                        matched._codex_secure_storage_identity(
                            self.codex_secure_storage_dir
                        )
                    ),
                )

        self.assertLess(events.index("link"), events.index("target_fsync"))
        self.assertLess(
            events.index("target_fsync"), events.index("source_unlink")
        )
        self.assertTrue(
            matched._attest_codex_auth_storage(
                self.codex_secure_storage_dir
            )
        )

    def test_codex_bootstrap_cleanup_failure_remains_terminal(self):
        temporaries: list[TemporaryDirectory] = []

        class FailingCleanupTemporaryDirectory:
            def __init__(self, *, directory: Path):
                self.temporary = TemporaryDirectory(
                    prefix="eabp-test-", dir=directory
                )
                temporaries.append(self.temporary)

            def __enter__(self) -> str:
                return self.temporary.name

            def __exit__(self, *_args) -> bool:
                raise ProviderStateIsolationError(
                    "Disposable provider state could not be removed"
                )

        def login(command, **kwargs):
            staged_auth = Path(kwargs["environment"]["CODEX_HOME"]) / "auth.json"
            staged_auth.unlink(missing_ok=True)
            staged_auth.write_bytes(b"credential")
            staged_auth.chmod(0o600)
            return subprocess.CompletedProcess(command, 0)

        try:
            with (
                patch(
                    "epiagentbench.development_matched_panel.shutil.which",
                    return_value="/trusted/codex",
                ),
                patch(
                    "epiagentbench.development_matched_panel."
                    "_run_no_capture_process_group",
                    side_effect=login,
                ),
                patch(
                    "epiagentbench.development_matched_panel."
                    "_ProviderTemporaryDirectory",
                    FailingCleanupTemporaryDirectory,
                ),
                self.assertRaisesRegex(
                    ProviderStateIsolationError,
                    "Disposable provider state could not be removed",
                ),
            ):
                matched._bootstrap_codex_credentials(
                    self.codex_secure_storage_dir,
                    executable="codex",
                    timeout_seconds=30,
                )
            self.assertTrue(
                matched._attest_codex_auth_storage(
                    self.codex_secure_storage_dir
                )
            )
        finally:
            for temporary in temporaries:
                temporary.cleanup()

    def test_cli_contract_defers_mutable_glean_dependency_bytes(self):
        def identity(executable: str) -> dict[str, str]:
            return {
                "name": executable,
                "executable_sha256": "sha256:" + "1" * 64,
            }

        def deferred(path: Path, **_kwargs) -> dict[str, object]:
            return {
                "path": str(path),
                "entrypoint_kind": (
                    "root_owned_single_link_regular_executable"
                ),
                "group_or_world_writable": False,
                "trusted_root_owned_nonwritable_ancestry": True,
                "exact_content_freeze_stage": (
                    "manifest_bound_spend_authorization_before_authentication"
                ),
                "freeze_once": True,
                "required_live_attestation_boundaries": [
                    "before_and_after_foreground_authentication",
                    "before_and_after_each_preflight_provider_call",
                    "before_and_after_each_production_provider_call",
                ],
            }

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "epiagentbench.development_matched_panel._read_cli_identity",
                side_effect=identity,
            ),
            patch(
                "epiagentbench.development_matched_panel._glean_helper_identity",
                side_effect=AssertionError(
                    "prepare must not hash the mutable Glean helper"
                ),
            ) as glean_identity,
            patch(
                "epiagentbench.development_matched_panel._fixed_file_sha256",
                return_value="sha256:" + "3" * 64,
            ) as fixed_hash,
            patch(
                "epiagentbench.development_matched_panel._safe_entrypoint_identity",
                side_effect=AssertionError(
                    "prepare must not hash the mutable Glean wrapper"
                ),
            ) as entrypoint_identity,
            patch(
                "epiagentbench.development_matched_panel."
                "_deferred_root_owned_executable_contract",
                side_effect=deferred,
            ),
            patch(
                "epiagentbench.development_matched_panel._safe_glean_config",
                return_value=(
                    {
                        "gateway_url": "https://gateway.test",
                        "oauth": {
                            "claude": {"client_id": "claude-test"},
                            "codex": {"client_id": "codex-test"},
                        },
                    },
                    {
                        "path": str(matched._GLEAN_CONFIG_PATH),
                        "sha256": "sha256:" + "5" * 64,
                        "semantic_projection": {"safe": True},
                    },
                ),
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_managed_settings_identity",
                return_value=(
                    {
                        "path": str(matched._CLAUDE_MANAGED_SETTINGS_PATH),
                        "sha256": "sha256:" + "6" * 64,
                        "semantic_projection": {"safe": True},
                    },
                    True,
                ),
            ),
        ):
            contract = matched._cli_contract()

        dependencies = contract["claude_auth_dependencies"]
        self.assertEqual(
            dependencies["macos_security_metadata_tool"]["path"],
            "/usr/bin/security",
        )
        self.assertEqual(
            dependencies["glean_llm_gateway_token_wrapper"]["path"],
            "/usr/local/bin/glean-llm-gateway-token",
        )
        self.assertEqual(
            dependencies["glean_llm_gateway_token_wrapper"],
            {
                "path": "/usr/local/bin/glean-llm-gateway-token",
                "entrypoint_kind": (
                    "root_owned_single_link_regular_executable"
                ),
                "group_or_world_writable": False,
                "trusted_root_owned_nonwritable_ancestry": True,
                "exact_content_freeze_stage": (
                    "manifest_bound_spend_authorization_before_authentication"
                ),
                "freeze_once": True,
                "required_live_attestation_boundaries": [
                    "before_and_after_foreground_authentication",
                    "before_and_after_each_preflight_provider_call",
                    "before_and_after_each_production_provider_call",
                ],
                "dispatch_contract": {
                    "argv0_basename": "glean-llm-gateway-token",
                    "arguments": [],
                    "option_source": "glean.DefaultOptions",
                    "oauth_client_id_source": (
                        "explicit_GLEAN_HELPER_OAUTH_CLIENT_ID"
                    ),
                    "credential_path": (
                        "$HOME/.glean-llm-gateway/credentials.json"
                    ),
                },
            },
        )
        self.assertEqual(
            dependencies["glean_helper"],
            {
                "path": "/usr/local/bin/glean-helper",
                "entrypoint_kind": (
                    "root_owned_single_link_regular_executable"
                ),
                "group_or_world_writable": False,
                "trusted_root_owned_nonwritable_ancestry": True,
                "exact_content_freeze_stage": (
                    "manifest_bound_spend_authorization_before_authentication"
                ),
                "freeze_once": True,
                "required_live_attestation_boundaries": [
                    "before_and_after_foreground_authentication",
                    "before_and_after_each_preflight_provider_call",
                    "before_and_after_each_production_provider_call",
                ],
            },
        )
        self.assertEqual(
            dependencies["managed_settings"]["path"],
            "/Library/Application Support/ClaudeCode/managed-settings.json",
        )
        self.assertEqual(
            dependencies["glean_config"]["path"],
            "/usr/local/etc/glean/config.json",
        )
        self.assertEqual(
            dependencies["claude_otel_headers_helper"]["path"],
            "/usr/local/bin/claude-otel-helper",
        )
        hashed_paths = {call.args[0] for call in fixed_hash.call_args_list}
        self.assertEqual(
            hashed_paths,
            {
                matched._MACOS_SECURITY_PATH,
                matched._CLAUDE_OTEL_HELPER_PATH,
            },
        )
        glean_identity.assert_not_called()
        entrypoint_identity.assert_not_called()

    @unittest.skipUnless(
        sys.platform == "darwin"
        and matched._GLEAN_CONFIG_PATH.is_file()
        and matched._CLAUDE_MANAGED_SETTINGS_PATH.is_file(),
        "requires the local managed macOS Glean installation",
    )
    def test_installed_glean_and_managed_settings_semantics_are_safe(self):
        config, config_identity = matched._safe_glean_config()
        settings_identity, telemetry_enabled = matched._managed_settings_identity(
            config
        )
        self.assertTrue(config_identity["sha256"].startswith("sha256:"))
        self.assertTrue(
            settings_identity["redacted_projection_sha256"].startswith(
                "sha256:"
            )
        )
        self.assertEqual(
            config_identity["semantic_projection"][
                "contains_secret_bearing_fields"
            ],
            False,
        )
        self.assertTrue(
            settings_identity["semantic_projection"][
                "anthropic_base_url_matches_glean_gateway"
            ]
        )
        self.assertTrue(telemetry_enabled)
        encoded_identity = json.dumps(
            {"config": config_identity, "settings": settings_identity}
        )
        self.assertNotIn(
            config["oauth"]["claude"]["client_id"], encoded_identity
        )
        self.assertNotIn(
            config["oauth"]["codex"]["client_id"], encoded_identity
        )
        raw_settings = matched._CLAUDE_MANAGED_SETTINGS_PATH.read_bytes()
        decoded_settings = matched._decode_unique_json(
            raw_settings, label="Claude managed settings"
        )
        personal_attribute = decoded_settings["env"][
            "OTEL_RESOURCE_ATTRIBUTES"
        ]
        self.assertNotIn(personal_attribute, encoded_identity)
        self.assertNotIn(matched._sha256(raw_settings), encoded_identity)
        self.assertNotIn(
            matched._sha256(personal_attribute.encode("utf-8")),
            encoded_identity,
        )

    def test_glean_and_managed_settings_fixture_semantics_are_safe(self):
        config = self._glean_config_fixture()
        settings = self._managed_settings_fixture()
        gateway_digest = matched._sha256(
            config["gateway_url"].encode("utf-8")
        )
        otel_endpoint = settings["env"]["OTEL_EXPORTER_OTLP_ENDPOINT"]
        with (
            patch(
                "epiagentbench.development_matched_panel."
                "_read_root_owned_json",
                side_effect=(
                    (b"config-fixture", config),
                    (b"settings-fixture", settings),
                ),
            ),
            patch.object(
                matched,
                "_APPROVED_GLEAN_GATEWAY_SHA256",
                gateway_digest,
            ),
            patch.object(
                matched,
                "_APPROVED_CLAUDE_OTEL_ENDPOINT_SHA256",
                matched._sha256(otel_endpoint.encode("utf-8")),
            ),
        ):
            parsed_config, config_identity = matched._safe_glean_config()
            settings_identity, telemetry_enabled = (
                matched._managed_settings_identity(parsed_config)
            )

        self.assertTrue(telemetry_enabled)
        semantics = settings_identity["semantic_projection"]
        self.assertTrue(semantics["top_level_key_allowlist_exact"])
        self.assertTrue(semantics["managed_environment_key_allowlist_exact"])
        self.assertEqual(semantics["managed_environment_key_count"], 17)
        self.assertTrue(
            semantics[
                "managed_environment_value_types_and_policies_validated"
            ]
        )
        encoded_identity = json.dumps(
            {"config": config_identity, "settings": settings_identity}
        )
        for raw_value in (
            config["gateway_url"],
            otel_endpoint,
            settings["env"]["OTEL_RESOURCE_ATTRIBUTES"],
        ):
            self.assertNotIn(raw_value, encoded_identity)
        self.assertIn(gateway_digest, encoded_identity)
        for raw_value in (
            otel_endpoint,
            settings["env"]["OTEL_RESOURCE_ATTRIBUTES"],
        ):
            self.assertNotIn(
                matched._sha256(raw_value.encode("utf-8")),
                encoded_identity,
            )

    def test_glean_gateway_allowlist_rejects_host_port_and_path_drift(self):
        for name, gateway_url in (
            ("host", "https://evil.test/api/v1"),
            ("port", "https://gateway.test:8443/api/v1"),
            ("path", "https://gateway.test/api/v2"),
        ):
            config = self._glean_config_fixture(gateway_url)
            approved_digest = (
                matched._APPROVED_GLEAN_GATEWAY_SHA256
                if name == "host"
                else matched._sha256(gateway_url.encode("utf-8"))
            )
            with self.subTest(name=name), patch(
                "epiagentbench.development_matched_panel."
                "_read_root_owned_json",
                return_value=(b"config-fixture", config),
            ), patch.object(
                matched,
                "_APPROVED_GLEAN_GATEWAY_SHA256",
                approved_digest,
            ), self.assertRaisesRegex(RuntimeError, "gateway URL"):
                matched._safe_glean_config()

    def test_managed_settings_fixture_rejects_schema_and_sensitive_fields(self):
        for name, mutate, message in (
            (
                "unknown_top_level",
                lambda value: value.update({"unexpected": "value"}),
                "top-level schema",
            ),
            (
                "unknown_environment",
                lambda value: value["env"].update({"UNEXPECTED": "value"}),
                "environment schema",
            ),
            (
                "nested_sensitive",
                lambda value: value.update(
                    {"authorization": {"access_token": "forbidden"}}
                ),
                "forbidden sensitive field",
            ),
        ):
            settings = copy.deepcopy(self._managed_settings_fixture())
            mutate(settings)
            with self.subTest(name=name), patch(
                "epiagentbench.development_matched_panel."
                "_read_root_owned_json",
                return_value=(b"settings-fixture", settings),
            ), self.assertRaisesRegex(RuntimeError, message):
                matched._managed_settings_identity(
                    self._glean_config_fixture()
                )

    def test_managed_settings_fixture_rejects_every_env_policy_drift(self):
        invalid_values = {
            "ANTHROPIC_BASE_URL": "https://other.test/anthropic",
            "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": 1800000,
            "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "0",
            "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "0",
            "CLAUDE_CODE_ENABLE_TELEMETRY": 0,
            "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "0",
            "CLAUDE_CODE_USE_VERTEX": 1,
            "ENABLE_TOOL_SEARCH": 0,
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel.test",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
            "OTEL_LOGS_EXPORTER": "console",
            "OTEL_LOGS_EXPORT_INTERVAL": 5000,
            "OTEL_METRICS_EXPORTER": "console",
            "OTEL_METRICS_INCLUDE_ACCOUNT_UUID": "false",
            "OTEL_METRIC_EXPORT_INTERVAL": 60000,
            "OTEL_RESOURCE_ATTRIBUTES": "authorization=forbidden",
            "USE_CLAUDE_PROJECT_DIR": "0",
        }
        approved_otel_digest = matched._sha256(
            self._managed_settings_fixture()["env"][
                "OTEL_EXPORTER_OTLP_ENDPOINT"
            ].encode("utf-8")
        )
        for key, invalid_value in invalid_values.items():
            settings = copy.deepcopy(self._managed_settings_fixture())
            settings["env"][key] = invalid_value
            with (
                self.subTest(key=key),
                patch(
                    "epiagentbench.development_matched_panel."
                    "_read_root_owned_json",
                    return_value=(b"settings-fixture", settings),
                ),
                patch.object(
                    matched,
                    "_APPROVED_CLAUDE_OTEL_ENDPOINT_SHA256",
                    approved_otel_digest,
                ),
                self.assertRaises(RuntimeError),
            ):
                matched._managed_settings_identity(
                    self._glean_config_fixture()
                )

    def test_glean_config_rejects_unknown_or_secret_fields(self):
        unsafe = {
            "gateway_url": "https://gateway.test",
            "oauth": {
                "claude": {"client_id": "claude-test"},
                "codex": {"client_id": "codex-test"},
            },
            "api_key": "must-not-be-accepted",
        }
        with patch(
            "epiagentbench.development_matched_panel._read_root_owned_json",
            return_value=(b"opaque", unsafe),
        ), self.assertRaisesRegex(RuntimeError, "forbidden field"):
            matched._safe_glean_config()

    def test_glean_config_json_rejects_duplicate_keys(self):
        with self.assertRaisesRegex(RuntimeError, "JSON is invalid"):
            matched._decode_unique_json(
                b'{"gateway_url":"https://one","gateway_url":"https://two"}',
                label="Glean configuration",
            )

    def test_safe_entrypoint_identity_pins_regular_file(self):
        target = self.root / "gateway-token"
        target.write_bytes(b"gateway-token\n")

        identity = matched._safe_entrypoint_identity(target, label="gateway")

        self.assertEqual(
            identity,
            {
                "path": str(target),
                "entrypoint_kind": "regular_file",
                "link_text": None,
                "resolved_path": str(target.resolve()),
                "target_sha256": "sha256:"
                + hashlib.sha256(b"gateway-token\n").hexdigest(),
            },
        )

    def test_safe_entrypoint_identity_pins_direct_symlink(self):
        target = self.root / "gateway-target"
        target.write_bytes(b"gateway-target\n")
        entrypoint = self.root / "gateway-token"
        link_text = "gateway-target"
        entrypoint.symlink_to(link_text)

        identity = matched._safe_entrypoint_identity(
            entrypoint, label="gateway"
        )

        self.assertEqual(
            identity,
            {
                "path": str(entrypoint),
                "entrypoint_kind": "symlink",
                "link_text": link_text,
                "resolved_path": str(target.resolve()),
                "target_sha256": "sha256:"
                + hashlib.sha256(b"gateway-target\n").hexdigest(),
            },
        )

    def test_safe_entrypoint_identity_rejects_unsafe_entrypoints(self):
        directory = self.root / "directory"
        directory.mkdir()
        directory_link = self.root / "directory-link"
        directory_link.symlink_to(directory)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        dangling = self.root / "dangling"
        dangling.symlink_to("missing")
        target = self.root / "target"
        target.write_bytes(b"target\n")
        intermediate = self.root / "intermediate"
        intermediate.symlink_to(target)
        multihop = self.root / "multihop"
        multihop.symlink_to(intermediate)

        unsafe = (
            (directory, "regular file or direct symlink"),
            (directory_link, "point directly to a regular file"),
            (fifo, "regular file or direct symlink"),
            (dangling, "target is unavailable"),
            (multihop, "point directly to a regular file"),
            (Path("relative-entrypoint"), "path must be absolute"),
        )
        for path, message in unsafe:
            with self.subTest(path=path), self.assertRaisesRegex(
                RuntimeError, message
            ):
                matched._safe_entrypoint_identity(path, label="gateway")

    def test_safe_entrypoint_identity_rejects_target_replacement(self):
        target = self.root / "gateway-target"
        target.write_bytes(b"original target\n")
        replacement = self.root / "replacement"
        replacement.write_bytes(b"replacement target\n")
        entrypoint = self.root / "gateway-token"
        entrypoint.symlink_to(target)
        real_read = os.read
        replaced = False

        def replace_after_read(descriptor: int, size: int) -> bytes:
            nonlocal replaced
            chunk = real_read(descriptor, size)
            if chunk and not replaced:
                replaced = True
                os.replace(replacement, target)
            return chunk

        with patch(
            "epiagentbench.development_matched_panel.os.read",
            side_effect=replace_after_read,
        ), self.assertRaisesRegex(RuntimeError, "changed while hashing"):
            matched._safe_entrypoint_identity(entrypoint, label="gateway")

    def test_execution_contract_attestation_checks_public_surfaces_only(self):
        public = self._prepare()
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._read_authentication_key"
            ) as read_key,
            patch.object(PrivateEpisodePack, "read") as read_pack,
        ):
            matched._attest_execution_contracts(root=self.root, public=public)
        read_key.assert_not_called()
        read_pack.assert_not_called()

        drift_cases = (
            (
                "source_contract",
                "epiagentbench.development_matched_panel._source_contract",
            ),
            (
                "cli_contract",
                "epiagentbench.development_matched_panel._cli_contract",
            ),
            (
                "runtime_contract",
                "epiagentbench.development_matched_panel._runtime_contract",
            ),
            (
                "replay_trace_contract",
                "epiagentbench.development_matched_panel.replay_trace_contract",
            ),
            (
                "profiles",
                "epiagentbench.development_matched_panel._profile_contract",
            ),
        )
        for surface, target in drift_cases:
            with self.subTest(surface=surface), self._contracts(), patch(
                target, return_value={"drifted": surface}
            ), self.assertRaisesRegex(RuntimeError, surface):
                matched._attest_execution_contracts(
                    root=self.root, public=public
                )

    def test_frozen_glean_dependency_attestation_checks_full_topology(self):
        public = self._prepare(authenticate=False)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        drifted = copy.deepcopy(AUTHENTICATION_DEPENDENCY_IDENTITY)
        wrapper = drifted["glean_llm_gateway_token_wrapper"]
        wrapper["entrypoint_kind"] = "symlink"
        wrapper["link_text"] = "glean-helper"
        with patch(
            "epiagentbench.development_matched_panel."
            "_current_glean_auth_dependency_identity",
            return_value=drifted,
        ), self.assertRaisesRegex(
            ProviderStateIsolationError,
            "Frozen Glean authentication dependencies drifted",
        ):
            matched._attest_frozen_glean_auth_dependencies(private, public)

    def test_prepare_rejects_secure_storage_nested_in_frozen_cohort(self):
        with TemporaryDirectory(
            prefix="epiagentbench-cohort-separation-", dir=Path.home()
        ) as container:
            container_path = Path(container)
            os.chmod(container_path, 0o700)
            cohort = container_path / "cohort"
            cohort.mkdir(mode=0o700)
            manifest_path = cohort / "cohort.manifest"
            manifest_path.write_bytes(b"placeholder")
            os.chmod(manifest_path, 0o600)
            nested_storage = cohort / "claude-auth"
            nested_storage.mkdir(mode=0o700)
            with self._contracts(), self.assertRaisesRegex(
                ValueError, "must not overlap"
            ):
                prepare_panel(
                    root=self.root,
                    cohort_manifest_path=manifest_path,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=nested_storage,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                )

    def test_prepare_rejects_frozen_cohort_nested_in_secure_storage(self):
        with TemporaryDirectory(
            prefix="epiagentbench-reverse-separation-", dir=Path.home()
        ) as container:
            secure_storage = Path(container)
            os.chmod(secure_storage, 0o700)
            cohort = secure_storage / "cohort"
            cohort.mkdir(mode=0o700)
            manifest_path = cohort / "cohort.manifest"
            manifest_path.write_bytes(b"placeholder")
            os.chmod(manifest_path, 0o600)
            with self._contracts(), self.assertRaisesRegex(
                ValueError, "must not overlap"
            ):
                prepare_panel(
                    root=self.root,
                    cohort_manifest_path=manifest_path,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=secure_storage,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                )

    def test_prepare_requires_fresh_managed_glean_directory_before_writing(self):
        manifest_path = self._cohort()
        self.keychain_present = True
        with self._contracts(), self.assertRaisesRegex(
            RuntimeError, "Managed Glean credential file must be absent"
        ):
            prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())

    def test_prepare_requires_claude_keychain_record_absent(self):
        manifest_path = self._cohort()
        with self._contracts(), patch(
            "epiagentbench.development_matched_panel."
            "_attest_claude_secure_storage_keychain",
            return_value=True,
        ), self.assertRaisesRegex(RuntimeError, "Keychain record must remain absent"):
            prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())

    def test_prepare_rejects_plaintext_fallback_before_writing(self):
        manifest_path = self._cohort()
        fallback = self.claude_secure_storage_dir / ".credentials.json"
        fallback.write_text('{"token":"test-only"}', encoding="utf-8")
        with self._contracts(), self.assertRaisesRegex(
            RuntimeError, "plaintext credential fallback"
        ):
            prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())

    def test_auth_path_mismatch_stops_preflight_and_run_before_provider(self):
        self._prepare()
        with TemporaryDirectory(
            prefix="epiagentbench-other-claude-auth-", dir=Path.home()
        ) as other:
            other_path = Path(other)
            os.chmod(other_path, 0o700)
            with patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
            ) as evaluate, self.assertRaisesRegex(ValueError, "does not match"):
                run_panel(
                    root=self.root,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=other_path,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    public_results_path=self.results_path,
                    acknowledge_unbounded_provider_spend=True,
                )
            evaluate.assert_not_called()

            with patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}), patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
            ) as evaluate, self.assertRaisesRegex(ValueError, "does not match"):
                run_environment_preflight(
                    root=self.root,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=other_path,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    public_preflight_path=self.root / "results" / "preflight.json",
                    acknowledge_unbounded_provider_spend=True,
                )
            evaluate.assert_not_called()

    def test_replaced_secure_storage_directory_stops_before_provider(self):
        self._prepare()
        original = self.claude_secure_storage_dir
        moved = original.with_name(original.name + "-original")
        original.rename(moved)
        original.mkdir(mode=0o700)
        try:
            with (
                patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
                self._contracts(),
                patch(
                    "epiagentbench.development_matched_panel."
                    "evaluate_local_cli_agent"
                ) as evaluate,
                self.assertRaisesRegex(ValueError, "filesystem identity changed"),
            ):
                run_environment_preflight(
                    root=self.root,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=original,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    public_preflight_path=self.root / "results" / "preflight.json",
                    acknowledge_unbounded_provider_spend=True,
                )
            evaluate.assert_not_called()
        finally:
            original.rmdir()
            moved.rename(original)

    def test_six_treatment_williams_rows_and_family_extras_are_exact(self):
        rows = matched._WILLIAMS
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0], (0, 1, 5, 2, 4, 3))
        self.assertTrue(all(set(row) == set(range(6)) for row in rows))
        predecessor_counts = Counter(
            (first, second)
            for row in rows
            for first, second in zip(row, row[1:])
        )
        self.assertEqual(
            predecessor_counts,
            Counter(
                {
                    (first, second): 1
                    for first in range(6)
                    for second in range(6)
                    if first != second
                }
            ),
        )

        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        nonce = bytes.fromhex(private["schedule_nonce_hex"])
        profile_permutation = tuple(
            sorted(
                (profile["profile_id"] for profile in PROFILES),
                key=lambda value: matched._keyed(nonce, "profile", value),
            )
        )
        treatment_by_profile = {
            profile_id: index
            for index, profile_id in enumerate(profile_permutation)
        }
        row_id_by_order = {row: row_id for row_id, row in enumerate(rows)}
        family_by_ref = {
            item["episode_ref"]: item["family"] for item in private["episodes"]
        }
        rows_by_family = {family: Counter() for family in FAMILIES}
        for item in private["schedule"]:
            treatment_order = tuple(
                treatment_by_profile[profile_id]
                for profile_id in item["profile_order"]
            )
            rows_by_family[family_by_ref[item["episode_ref"]]][
                row_id_by_order[treatment_order]
            ] += 1

        for family_index, family in enumerate(FAMILIES):
            expected = Counter(range(6))
            expected.update(matched._EXTRA_SEQUENCES[family_index])
            self.assertEqual(rows_by_family[family], expected)
        overall = sum(rows_by_family.values(), Counter())
        self.assertEqual(overall, Counter({0: 9, 1: 9, 2: 8, 3: 8, 4: 8, 5: 8}))

    def test_prepare_rejects_incomplete_or_wrong_cohort_identity(self):
        incomplete = self._cohort()
        (incomplete.parent / ".freeze-incomplete").write_text("incomplete\n")
        with self.assertRaisesRegex(ValueError, "incomplete marker"):
            self._prepare(incomplete)
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())

        wrong = self._cohort(cohort_id="development-matched-50x4-v1")
        with self.assertRaisesRegex(ValueError, "identifier"):
            self._prepare(wrong)
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())

    def test_spend_gate_prevents_every_provider_call(self):
        self._prepare()
        with patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
        ) as evaluate, self.assertRaisesRegex(RuntimeError, "unbounded provider spend"):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
            )
        evaluate.assert_not_called()

    def test_preflight_spend_gate_prevents_bootstrap_and_provider_calls(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight-no-ack.json"
        with (
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
            self.assertRaisesRegex(RuntimeError, "unbounded preflight provider spend"),
        ):
            run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
            )
        bootstrap.assert_not_called()
        codex_bootstrap.assert_not_called()
        evaluate.assert_not_called()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["environment_preflight"]["status"], "required")
        self.assertFalse(preflight_path.exists())

    def test_authorize_spend_requires_the_exact_v14_acknowledgement(self):
        public = self._prepare(authorize=False)
        public_before = self.public_path.read_bytes()
        stale_v10_text = REQUIRED_SPEND_ACKNOWLEDGEMENT.replace(
            "six-call v14", "six-call v10"
        )
        with (
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as glean_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
            patch(
                "epiagentbench.development_matched_panel."
                "_current_glean_auth_dependency_identity"
            ) as dependency_identity,
            patch(
                "epiagentbench.development_matched_panel."
                "_read_authentication_key"
            ) as read_authentication_key,
            patch(
                "epiagentbench.development_matched_panel._cli_contract"
            ) as cli_contract,
            patch(
                "epiagentbench.development_matched_panel."
                "_glean_helper_identity"
            ) as glean_helper_identity,
            patch(
                "epiagentbench.development_matched_panel."
                "_root_owned_regular_executable_identity"
            ) as wrapper_identity,
            self.assertRaisesRegex(RuntimeError, "exact v14 \\$570"),
        ):
            authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=stale_v10_text,
            )
        glean_bootstrap.assert_not_called()
        codex_bootstrap.assert_not_called()
        evaluate.assert_not_called()
        dependency_identity.assert_not_called()
        read_authentication_key.assert_not_called()
        cli_contract.assert_not_called()
        glean_helper_identity.assert_not_called()
        wrapper_identity.assert_not_called()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertNotIn("spend_authorization", private)
        self.assertEqual(self.public_path.read_bytes(), public_before)

        with self._contracts():
            receipt = authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            receipt,
            matched._expected_spend_authorization(
                public,
                frozen_glean_auth_dependency_identity_sha256=private[
                    "authentication_dependency_freeze"
                ]["identity_sha256"],
            ),
        )
        self.assertEqual(private["spend_authorization"], receipt)
        self.assertEqual(self.public_path.read_bytes(), public_before)

    def test_authorization_freezes_post_prepare_glean_identity_once(self):
        public = self._prepare(authorize=False)
        public_before = self.public_path.read_bytes()
        drifted = copy.deepcopy(AUTHENTICATION_DEPENDENCY_IDENTITY)
        drifted["glean_helper"]["sha256"] = "sha256:" + "6" * 64
        drifted["glean_llm_gateway_token_wrapper"]["target_sha256"] = (
            "sha256:" + "7" * 64
        )
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_current_glean_auth_dependency_identity",
                return_value=drifted,
            ) as identity,
        ):
            receipt = authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        freeze = private["authentication_dependency_freeze"]
        self.assertEqual(identity.call_count, 2)
        self.assertEqual(freeze["identity"], drifted)
        self.assertEqual(
            freeze["identity_sha256"], matched._component_hash(drifted)
        )
        self.assertEqual(
            receipt["frozen_glean_auth_dependency_identity_sha256"],
            freeze["identity_sha256"],
        )
        self.assertEqual(self.public_path.read_bytes(), public_before)

        changed_again = copy.deepcopy(drifted)
        changed_again["glean_helper"]["sha256"] = "sha256:" + "8" * 64
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_current_glean_auth_dependency_identity",
                return_value=changed_again,
            ),
            self.assertRaisesRegex(
                ProviderStateIsolationError,
                "Frozen Glean authentication dependencies drifted",
            ),
        ):
            authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        unchanged = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            unchanged["authentication_dependency_freeze"], freeze
        )

    def test_repeated_authorization_returns_without_refreeze_or_rewrite(self):
        self._prepare(authorize=False)
        with self._contracts():
            first = authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        before = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_write_private_state"
            ) as write_private,
            patch(
                "epiagentbench.development_matched_panel._utc_now",
                side_effect=AssertionError("authorization must not refreeze"),
            ),
        ):
            second = authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        after = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(second, first)
        self.assertEqual(after, before)
        write_private.assert_not_called()

    def test_authorization_dependency_drift_before_write_leaves_no_receipt(self):
        self._prepare(authorize=False)
        first = copy.deepcopy(AUTHENTICATION_DEPENDENCY_IDENTITY)
        second = copy.deepcopy(first)
        second["glean_helper"]["sha256"] = "sha256:" + "8" * 64
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_current_glean_auth_dependency_identity",
                side_effect=[first, second],
            ),
            self.assertRaisesRegex(
                ProviderStateIsolationError,
                "changed during authorization",
            ),
        ):
            authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            private["authentication_dependency_freeze"],
            {
                "schema_version": (
                    "epiagentbench.authentication_dependency_freeze.v1"
                ),
                "status": "required",
            },
        )
        self.assertNotIn("spend_authorization", private)

    def test_authorization_atomic_write_failure_is_fail_closed_or_idempotent(self):
        self._prepare(authorize=False)
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel.os.replace",
                side_effect=OSError("pre-replace failure"),
            ),
            self.assertRaises(OSError),
        ):
            authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        unchanged = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            unchanged["authentication_dependency_freeze"]["status"],
            "required",
        )
        self.assertNotIn("spend_authorization", unchanged)

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._fsync_directory",
                side_effect=OSError("ambiguous post-replace failure"),
            ),
            self.assertRaises(OSError),
        ):
            authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        durable = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        frozen_at = durable["authentication_dependency_freeze"][
            "frozen_at_utc"
        ]
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_write_private_state"
            ) as write_private,
        ):
            recovered = authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        final = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(recovered, durable["spend_authorization"])
        self.assertEqual(
            final["authentication_dependency_freeze"]["frozen_at_utc"],
            frozen_at,
        )
        self.assertEqual(final, durable)
        write_private.assert_not_called()

    def test_concurrent_authorization_is_rejected_before_private_reads(self):
        self._prepare(authorize=False)
        with (
            matched._exclusive_run_lock(self.private_path),
            patch(
                "epiagentbench.development_matched_panel."
                "_read_authentication_key"
            ) as read_key,
            patch(
                "epiagentbench.development_matched_panel."
                "_current_glean_auth_dependency_identity"
            ) as identity,
            patch(
                "epiagentbench.development_matched_panel."
                "assert_durable_live_execution_paths"
            ),
            self.assertRaisesRegex(RuntimeError, "already holds the lock"),
        ):
            authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        read_key.assert_not_called()
        identity.assert_not_called()

    def test_authorization_half_states_block_authentication_zero_call(self):
        public = self._prepare(authorize=False)
        baseline = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        frozen = copy.deepcopy(AUTHENTICATION_DEPENDENCY_IDENTITY)
        frozen_record = {
            "schema_version": (
                "epiagentbench.authentication_dependency_freeze.v1"
            ),
            "status": "frozen",
            "panel_id": "development-matched-50x6-v14",
            "public_precommitment_sha256": public["precommitment_sha256"],
            "static_cli_contract_sha256": public["contract_hashes"][
                "cli_sha256"
            ],
            "identity": frozen,
            "identity_sha256": matched._component_hash(frozen),
            "frozen_at_utc": "2026-07-25T00:00:00Z",
        }
        authorized = matched._expected_spend_authorization(
            public,
            frozen_glean_auth_dependency_identity_sha256=frozen_record[
                "identity_sha256"
            ],
        )
        cases = {
            "frozen_without_receipt": (
                frozen_record,
                None,
            ),
            "receipt_without_freeze": (
                baseline["authentication_dependency_freeze"],
                authorized,
            ),
        }
        for name, (freeze, receipt) in cases.items():
            candidate = copy.deepcopy(baseline)
            candidate["authentication_dependency_freeze"] = copy.deepcopy(
                freeze
            )
            if receipt is None:
                candidate.pop("spend_authorization", None)
            else:
                candidate["spend_authorization"] = copy.deepcopy(receipt)
            matched._write_private_state(
                self.private_path, candidate, AUTHENTICATION_KEY
            )
            with (
                self.subTest(name=name),
                self._contracts(),
                patch(
                    "epiagentbench.development_matched_panel."
                    "_require_operator_authentication_tty"
                ) as tty,
                patch(
                    "epiagentbench.development_matched_panel."
                    "_bootstrap_codex_credentials"
                ) as codex_bootstrap,
                patch(
                    "epiagentbench.development_matched_panel."
                    "_bootstrap_managed_glean_credentials"
                ) as glean_bootstrap,
                self.assertRaises(RuntimeError),
            ):
                matched.authenticate_panel(
                    root=self.root,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=self.claude_secure_storage_dir,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    acknowledge_interactive_authentication=True,
                )
            tty.assert_not_called()
            codex_bootstrap.assert_not_called()
            glean_bootstrap.assert_not_called()
        matched._write_private_state(
            self.private_path, baseline, AUTHENTICATION_KEY
        )

    def test_authorize_requires_committed_clean_manifest_zero_call(self):
        self._prepare(authorize=False)
        public_relative = matched._relative_to_root(self.public_path, self.root)
        private_relative = matched._relative_to_root(self.private_path, self.root)

        for scenario in ("uncommitted", "dirty"):
            def git_output(_: Path, *arguments: str) -> str:
                if arguments == ("rev-parse", "HEAD"):
                    return "d" * 40
                if arguments == (
                    "ls-files",
                    "--error-unmatch",
                    public_relative,
                ):
                    return "" if scenario == "uncommitted" else public_relative
                if arguments == ("ls-files", private_relative):
                    return ""
                if arguments == (
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                ):
                    return f" M {public_relative}" if scenario == "dirty" else ""
                self.fail(f"unexpected git probe: {arguments!r}")

            expected_error = "committed" if scenario == "uncommitted" else "clean"
            with (
                self.subTest(scenario=scenario),
                patch(
                    "epiagentbench.development_matched_panel._git_output",
                    side_effect=git_output,
                ),
                patch(
                    "epiagentbench.development_matched_panel."
                    "_bootstrap_managed_glean_credentials"
                ) as glean_bootstrap,
                patch(
                    "epiagentbench.development_matched_panel."
                    "_bootstrap_codex_credentials"
                ) as codex_bootstrap,
                patch(
                    "epiagentbench.development_matched_panel."
                    "evaluate_local_cli_agent"
                ) as evaluate,
                patch(
                    "epiagentbench.development_matched_panel."
                    "assert_durable_live_execution_paths"
                ),
                self.assertRaisesRegex(RuntimeError, expected_error),
            ):
                authorize_panel_spend(
                    root=self.root,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=self.claude_secure_storage_dir,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
                )
            glean_bootstrap.assert_not_called()
            codex_bootstrap.assert_not_called()
            evaluate.assert_not_called()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertNotIn("spend_authorization", private)

    def test_authorize_rechecks_head_and_manifest_before_receipt_write(self):
        self._prepare(authorize=False)
        public_relative = matched._relative_to_root(self.public_path, self.root)
        private_relative = matched._relative_to_root(self.private_path, self.root)
        head_calls = 0

        def git_output(_: Path, *arguments: str) -> str:
            nonlocal head_calls
            if arguments == ("rev-parse", "HEAD"):
                head_calls += 1
                return ("d" if head_calls <= 2 else "e") * 40
            if arguments == (
                "ls-files",
                "--error-unmatch",
                public_relative,
            ):
                return public_relative
            if arguments == ("ls-files", private_relative):
                return ""
            if arguments == (
                "status",
                "--porcelain",
                "--untracked-files=all",
            ):
                return ""
            self.fail(f"unexpected git probe: {arguments!r}")

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._git_output",
                side_effect=git_output,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as glean_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
            self.assertRaisesRegex(RuntimeError, "HEAD changed"),
        ):
            authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        glean_bootstrap.assert_not_called()
        codex_bootstrap.assert_not_called()
        evaluate.assert_not_called()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertNotIn("spend_authorization", private)

    def test_authorize_reloads_manifest_before_receipt_write(self):
        self._prepare(authorize=False)
        public_relative = matched._relative_to_root(self.public_path, self.root)
        private_relative = matched._relative_to_root(self.private_path, self.root)
        status_calls = 0

        def git_output(_: Path, *arguments: str) -> str:
            nonlocal status_calls
            if arguments == ("rev-parse", "HEAD"):
                return "d" * 40
            if arguments == (
                "ls-files",
                "--error-unmatch",
                public_relative,
            ):
                return public_relative
            if arguments == ("ls-files", private_relative):
                return ""
            if arguments == (
                "status",
                "--porcelain",
                "--untracked-files=all",
            ):
                status_calls += 1
                if status_calls == 2:
                    changed = json.loads(self.public_path.read_text())
                    changed["prepared_at_utc"] = "changed-during-authorization"
                    matched._atomic_json(self.public_path, changed)
                return ""
            self.fail(f"unexpected git probe: {arguments!r}")

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._git_output",
                side_effect=git_output,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as glean_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
            self.assertRaisesRegex(RuntimeError, "precommitment changed"),
        ):
            authorize_panel_spend(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledgement_text=REQUIRED_SPEND_ACKNOWLEDGEMENT,
            )
        glean_bootstrap.assert_not_called()
        codex_bootstrap.assert_not_called()
        evaluate.assert_not_called()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertNotIn("spend_authorization", private)

    def test_stale_or_wrong_private_spend_receipt_blocks_preflight_zero_call(self):
        self._prepare()
        baseline = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        mutations = {
            "missing": lambda receipt: None,
            "stale_precommitment": lambda receipt: receipt.__setitem__(
                "final_public_precommitment_sha256", "sha256:" + "5" * 64
            ),
            "wrong_budget_hash": lambda receipt: receipt.__setitem__(
                "budget_contract_sha256", "sha256:" + "6" * 64
            ),
            "wrong_ceiling": lambda receipt: receipt.__setitem__(
                "claude_cumulative_authorization_ceiling_usd", 520.0
            ),
            "cursor_capped": lambda receipt: receipt[
                "unbounded_provider_spend"
            ].__setitem__("cursor", "capped"),
            "wrong_text": lambda receipt: receipt.__setitem__(
                "acknowledgement_text", "stale acknowledgement"
            ),
            "wrong_frozen_dependency_hash": lambda receipt: receipt.__setitem__(
                "frozen_glean_auth_dependency_identity_sha256",
                "sha256:" + "8" * 64,
            ),
        }
        for name, mutate in mutations.items():
            candidate = copy.deepcopy(baseline)
            if name == "missing":
                candidate.pop("spend_authorization")
            else:
                receipt = candidate["spend_authorization"]
                mutate(receipt)
                unsigned_receipt = dict(receipt)
                unsigned_receipt.pop("receipt_sha256")
                receipt["receipt_sha256"] = matched._component_hash(
                    unsigned_receipt
                )
            matched._write_private_state(
                self.private_path, candidate, AUTHENTICATION_KEY
            )
            preflight_path = self.root / "results" / f"preflight-{name}.json"
            with (
                self.subTest(name=name),
                patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
                self._contracts(),
                patch(
                    "epiagentbench.development_matched_panel."
                    "_preflight_execution"
                ),
                patch(
                    "epiagentbench.development_matched_panel._cli_contract"
                ) as cli_contract,
                patch(
                    "epiagentbench.development_matched_panel."
                    "_bootstrap_managed_glean_credentials"
                ) as glean_bootstrap,
                patch(
                    "epiagentbench.development_matched_panel."
                    "_bootstrap_codex_credentials"
                ) as codex_bootstrap,
                patch(
                    "epiagentbench.development_matched_panel."
                    "evaluate_local_cli_agent"
                ) as evaluate,
                self.assertRaisesRegex(RuntimeError, "manifest-bound exact v14"),
            ):
                run_environment_preflight(
                    root=self.root,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=self.claude_secure_storage_dir,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    public_preflight_path=preflight_path,
                    acknowledge_unbounded_provider_spend=True,
                )
            glean_bootstrap.assert_not_called()
            codex_bootstrap.assert_not_called()
            cli_contract.assert_not_called()
            evaluate.assert_not_called()
            self.assertFalse(preflight_path.exists())
        matched._write_private_state(
            self.private_path, baseline, AUTHENTICATION_KEY
        )

    def test_wrong_private_spend_receipt_blocks_production_zero_call(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        private["spend_authorization"]["budget_contract_sha256"] = (
            "sha256:" + "7" * 64
        )
        unsigned_receipt = dict(private["spend_authorization"])
        unsigned_receipt.pop("receipt_sha256")
        private["spend_authorization"]["receipt_sha256"] = (
            matched._component_hash(unsigned_receipt)
        )
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._cli_contract"
            ) as cli_contract,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
            self.assertRaisesRegex(RuntimeError, "manifest-bound exact v14"),
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        cli_contract.assert_not_called()
        evaluate.assert_not_called()
        self.assertFalse(self.results_path.exists())

    def test_clean_worktree_gate_allows_only_the_private_retirement_marker(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        retirement_path = matched._cohort_retirement_path(
            Path(private["cohort_manifest_path"])
        )
        matched._atomic_json(retirement_path, {"test": True}, private=True)
        matched._atomic_json(self.results_path, {"status": "complete"})
        public_relative = matched._relative_to_root(self.public_path, self.root)
        private_relative = matched._relative_to_root(self.private_path, self.root)
        results_relative = matched._relative_to_root(self.results_path, self.root)
        retirement_relative = matched._relative_to_root(retirement_path, self.root)

        def git_output(_: Path, *arguments: str) -> str:
            if arguments == (
                "ls-files",
                "--error-unmatch",
                public_relative,
            ):
                return public_relative
            if arguments in {
                ("ls-files", private_relative),
                ("ls-files", retirement_relative),
            }:
                return ""
            if arguments == (
                "status",
                "--porcelain",
                "--untracked-files=all",
            ):
                return "\n".join(
                    (
                        f"?? {retirement_relative}",
                        f"?? {results_relative}",
                    )
                )
            self.fail(f"unexpected git probe: {arguments!r}")

        with patch(
            "epiagentbench.development_matched_panel._git_output",
            side_effect=git_output,
        ):
            matched._preflight_execution(
                root=self.root,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                allowed_private_artifact_paths=(retirement_path,),
            )

        def dirty_git_output(root: Path, *arguments: str) -> str:
            observed = git_output(root, *arguments)
            if arguments == (
                "status",
                "--porcelain",
                "--untracked-files=all",
            ):
                return observed + "\n?? unexpected-private-file"
            return observed

        with patch(
            "epiagentbench.development_matched_panel._git_output",
            side_effect=dirty_git_output,
        ), self.assertRaisesRegex(RuntimeError, "worktree is not clean"):
            matched._preflight_execution(
                root=self.root,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                allowed_private_artifact_paths=(retirement_path,),
            )

    def test_six_profiles_complete_300_without_partial_public_scores(self):
        self._prepare()
        private_before_run = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        cohort_manifest_path = Path(private_before_run["cohort_manifest_path"])
        retirement_path = matched._cohort_retirement_path(cohort_manifest_path)
        calls: list[tuple[str, str, str | None, str | None]] = []
        auth_kwargs_seen: list[
            tuple[str, bool, Path | None, bool, Path | None]
        ] = []
        terminal_write_saw_retirement = False
        captured_progress_artifacts = 0

        def evaluate(system: str, **kwargs):
            running = json.loads(self.results_path.read_text())
            self.assertEqual(running["results"], [])
            self.assertEqual(running["summary"], {"primary_estimand": "pending"})
            self.assertNotIn("replay_trace", json.dumps(running))
            self.assertNotIn("family", json.dumps(running))
            self.assertNotIn("profile_order", json.dumps(running))
            calls.append(
                (
                    system,
                    kwargs["model"],
                    kwargs["claude_effort"],
                    kwargs["codex_reasoning_effort"],
                )
            )
            auth_kwargs_seen.append(
                (
                    system,
                    "claude_secure_storage_dir" in kwargs,
                    kwargs.get("claude_secure_storage_dir"),
                    "codex_auth_storage_dir" in kwargs,
                    kwargs.get("codex_auth_storage_dir"),
                )
            )
            if system == "claude":
                self.assertEqual(
                    kwargs["claude_glean_oauth_client_id"],
                    "test-glean-client-id",
                )
            else:
                self.assertNotIn("claude_glean_oauth_client_id", kwargs)
            totals = {"claude": 10.0, "codex": 20.0}
            total = totals.get(system, 30.0 if "grok" in kwargs["model"] else 40.0)
            return self._result(system, kwargs["model"], kwargs["executable"], total)

        original_atomic_json = matched._atomic_json

        def guarded_atomic_json(path, value, **kwargs):
            nonlocal terminal_write_saw_retirement, captured_progress_artifacts
            if (
                Path(path) == self.results_path
                and isinstance(value, dict)
                and value.get("status")
                in {"running", "stopped_transport_void"}
            ):
                captured_progress_artifacts += 1
                self.assertEqual(value.get("results"), [])
                self.assertNotIn("replay_trace", json.dumps(value))
            if (
                Path(path) == self.results_path
                and isinstance(value, dict)
                and str(value.get("status", "")).startswith("complete")
            ):
                terminal_write_saw_retirement = True
                self.assertTrue(retirement_path.exists())
                matched._load_cohort_retirement_marker(
                    retirement_path, AUTHENTICATION_KEY
                )
            return original_atomic_json(path, value, **kwargs)

        with patch(
            "epiagentbench.development_matched_panel._atomic_json",
            side_effect=guarded_atomic_json,
        ):
            payload, invoked = self._run_with(evaluate)
        self.assertEqual(payload["status"], "complete")
        self.assertEqual(invoked.call_count, ASSIGNMENT_COUNT)
        self.assertTrue(terminal_write_saw_retirement)
        self.assertGreater(captured_progress_artifacts, ASSIGNMENT_COUNT)
        self.assertTrue(payload["cohort_retired_before_trace_publication"])
        self.assertTrue(
            all(result["trace_status"] == "recorded" for result in payload["results"])
        )
        self.assertTrue(
            all("cli_version" not in result for result in payload["results"])
        )
        self.assertTrue(
            all(
                result["replay_trace_sha256"].startswith("sha256:")
                for result in payload["results"]
            )
        )
        for result in payload["results"]:
            with self.subTest(
                episode_ref=result["episode_ref"],
                profile_id=result["profile_id"],
            ):
                self.assertEqual(
                    result["replay_trace_sha256"],
                    replay_trace_sha256(
                        result["replay_trace"],
                        episode_ref=result["episode_ref"],
                        profile_id=result["profile_id"],
                        pack_commitment=result["pack_commitment"],
                    ),
                )
        self.assertEqual(os.stat(retirement_path).st_mode & 0o777, 0o600)
        retirement = matched._load_cohort_retirement_marker(
            retirement_path, AUTHENTICATION_KEY
        )
        self.assertEqual(retirement["cohort_id"], COHORT_ID)
        self.assertEqual(retirement["panel_id"], matched.PANEL_ID)
        self.assertEqual(
            retirement["public_precommitment_sha256"],
            payload["precommitment_sha256"],
        )
        self.assertEqual(
            retirement["terminal_results_sha256"], payload["results_sha256"]
        )
        self.assertEqual(
            retirement["terminal_trace_results_sha256"],
            matched._terminal_trace_results_hash(payload),
        )
        self.assertEqual(retirement["terminal_assignments"], ASSIGNMENT_COUNT)

        resumed, resumed_invoked = self._run_with(
            lambda *_args, **_kwargs: self.fail(
                "a terminal retry must not invoke a provider"
            )
        )
        self.assertEqual(resumed, payload)
        resumed_invoked.assert_not_called()

        self.keychain_present = False
        with TemporaryDirectory(
            prefix="epiagentbench-fresh-codex-auth-", dir=Path.home()
        ) as fresh_codex:
            fresh_codex_path = Path(fresh_codex)
            fresh_codex_path.chmod(0o700)
            with self._contracts(), self.assertRaisesRegex(ValueError, "retired"):
                prepare_panel(
                    root=self.root,
                    cohort_manifest_path=cohort_manifest_path,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=self.claude_secure_storage_dir,
                    codex_secure_storage_dir=fresh_codex_path,
                    private_state_path=self.root
                    / "run_artifacts"
                    / "reused-private.json",
                    public_manifest_path=self.root
                    / "reused-results"
                    / "reused-manifest.json",
                )

        tampered = json.loads(retirement_path.read_text())
        tampered["terminal_results_sha256"] = "sha256:" + "f" * 64
        matched._atomic_json(retirement_path, tampered, private=True)
        with self.assertRaisesRegex(ValueError, "authentication"):
            self._run_with(
                lambda *_args, **_kwargs: self.fail(
                    "tampered retirement must fail before a provider call"
                )
            )
        cursor_models = {
            model for system, model, _, _ in calls if system == "cursor"
        }
        self.assertEqual(cursor_models, {"cursor-grok-4.5-high", "kimi-k2.7-code"})
        self.assertEqual(
            sum(system == "cursor" for system, _, _, _ in calls), 100
        )
        self.assertTrue(
            all(
                (
                    present and value == self.claude_secure_storage_dir.resolve()
                    if system == "claude"
                    else (not present and value is None)
                )
                and (
                    codex_present
                    and codex_value == self.codex_secure_storage_dir.resolve()
                    if system == "codex"
                    else (not codex_present and codex_value is None)
                )
                for (
                    system,
                    present,
                    value,
                    codex_present,
                    codex_value,
                ) in auth_kwargs_seen
            )
        )
        self.assertTrue(
            all(
                effort == "high"
                for system, _, effort, _ in calls
                if system == "claude"
            )
        )
        self.assertEqual(
            {
                model: reasoning
                for system, model, _, reasoning in calls
                if system == "codex"
            },
            {"gpt-5.6-sol": "medium", "gpt-5.6-luna": "max"},
        )
        means = {
            key: value["mean_total"]
            for key, value in payload["summary"]["profiles"].items()
        }
        self.assertEqual(
            means,
            {
                "claude-opus-high": 10.0,
                "claude-sonnet-high": 10.0,
                "codex-sol": 20.0,
                "codex-luna-max": 20.0,
                "cursor-grok-high": 30.0,
                "cursor-kimi-k27-code": 40.0,
            },
        )

    def test_terminalization_rejects_cross_profile_no_action_mismatch(self):
        first = asdict(
            self._result("codex", "gpt-5.6-sol", "codex", 50.0)
        )
        second = asdict(
            self._result("codex", "gpt-5.6-luna", "codex", 50.0)
        )
        second["replay_trace"]["frames"][1][
            "no_action_currently_infected"
        ] = 1
        # Both traces remain individually valid; only their shared no-action
        # counterfactual has been made inconsistent.
        matched.validate_replay_trace(first["replay_trace"])
        matched.validate_replay_trace(second["replay_trace"])

        private = {
            "episodes": [
                {
                    "episode_ref": "episode_0001",
                    "family": FAMILIES[0],
                    "pack_commitment": "sha256:" + "1" * 64,
                }
            ],
            "assignments": [
                {
                    "episode_ref": "episode_0001",
                    "profile_id": "codex-sol",
                    "status": "complete",
                    "public_result": {
                        "episode_ref": "episode_0001",
                        "profile_id": "codex-sol",
                    },
                    "raw_result": first,
                },
                {
                    "episode_ref": "episode_0001",
                    "profile_id": "codex-luna-max",
                    "status": "complete",
                    "public_result": {
                        "episode_ref": "episode_0001",
                        "profile_id": "codex-luna-max",
                    },
                    "raw_result": second,
                },
            ],
        }
        with self.assertRaisesRegex(
            ValueError, "profiles disagree on the no-action replay twin"
        ):
            matched._complete_artifact({}, private)

    def test_crash_interrupted_codex_assignment_is_non_resumable(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        keys = matched._assignment_keys(private["schedule"])
        orphan_index = next(
            index
            for index, (_ref, profile_id) in enumerate(keys)
            if matched._PROFILE_BY_ID[profile_id]["system"] == "codex"
        )
        self._set_terminal_assignment_prefix(orphan_index)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        orphan_ref, orphan_profile = keys[orphan_index]
        private["assignments"].append(
            {
                "episode_ref": orphan_ref,
                "profile_id": orphan_profile,
                "status": "started",
                "started_at_utc": "before-crash",
            }
        )
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )

        stopped, first_run = self._run_with(
            lambda *_args, **_kwargs: self.fail("orphan must not be retried")
        )
        self.assertEqual(stopped["status"], "stopped_transport_void")
        first_run.assert_not_called()

        private_after = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            private_after["codex_auth_incident"],
            {
                "status": "terminal",
                "assignment_index": orphan_index,
                "failure_class": "interrupted_after_durable_start",
            },
        )
        with self.assertRaisesRegex(RuntimeError, "non-resumable"):
            self._run_with(
                lambda *_args, **_kwargs: self.fail(
                    "Codex orphan must make the remaining panel non-resumable"
                )
            )

    def test_crash_interrupted_non_codex_assignment_is_non_resumable(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        keys = matched._assignment_keys(private["schedule"])
        orphan_index = next(
            index
            for index, (_ref, profile_id) in enumerate(keys)
            if matched._PROFILE_BY_ID[profile_id]["system"] != "codex"
        )
        private["assignments"] = [
            {
                "episode_ref": ref,
                "profile_id": profile_id,
                "status": "transport_void",
                "started_at_utc": "earlier-start",
                "finished_at_utc": "earlier-finish",
                "void_reason": "test-prefix",
            }
            for ref, profile_id in keys[:orphan_index]
        ]
        orphan_ref, orphan_profile = keys[orphan_index]
        private["assignments"].append(
            {
                "episode_ref": orphan_ref,
                "profile_id": orphan_profile,
                "status": "started",
                "started_at_utc": "before-crash",
            }
        )
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )

        stopped, first_run = self._run_with(
            lambda *_args, **_kwargs: self.fail("orphan must not be retried")
        )
        self.assertEqual(stopped["status"], "stopped_transport_void")
        first_run.assert_not_called()
        private_after = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            private_after["execution_incident"],
            {
                "status": "terminal",
                "assignment_index": orphan_index,
                "failure_class": "interrupted_after_durable_start",
            },
        )
        with self.assertRaisesRegex(RuntimeError, "execution incident"):
            self._run_with(
                lambda *_args, **_kwargs: self.fail(
                    "crash-recovered assignment must not resume providers"
                )
            )

    def test_last_assignment_crash_blocks_completion_and_trace_release(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        keys = matched._assignment_keys(private["schedule"])
        private["assignments"] = [
            {
                "episode_ref": ref,
                "profile_id": profile_id,
                "status": "transport_void",
                "started_at_utc": "earlier-start",
                "finished_at_utc": "earlier-finish",
                "void_reason": "test-prefix",
            }
            for ref, profile_id in keys[:-1]
        ]
        final_ref, final_profile = keys[-1]
        private["assignments"].append(
            {
                "episode_ref": final_ref,
                "profile_id": final_profile,
                "status": "started",
                "started_at_utc": "before-crash",
            }
        )
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )

        stopped, invoked = self._run_with(
            lambda *_args, **_kwargs: self.fail("orphan must not be retried")
        )
        invoked.assert_not_called()
        self.assertEqual(stopped["status"], "stopped_transport_void")
        self.assertEqual(stopped["terminal_assignments"], ASSIGNMENT_COUNT)

        private_after = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        public = json.loads(self.public_path.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(RuntimeError, "blocks cohort completion"):
            matched._complete_artifact(public, private_after)
        with self.assertRaisesRegex(RuntimeError, "execution incident"):
            self._run_with(
                lambda *_args, **_kwargs: self.fail(
                    "terminal incident must block completion"
                )
            )
        cohort_manifest = Path(str(private_after["cohort_manifest_path"]))
        self.assertFalse(
            matched._cohort_retirement_path(cohort_manifest).exists()
        )

    def test_aggregate_arithmetic_and_bootstrap_are_deterministic(self):
        totals = {
            "claude-opus-high": 10.0,
            "claude-sonnet-high": 15.0,
            "codex-sol": 20.0,
            "codex-luna-max": 25.0,
            "cursor-grok-high": 30.0,
            "cursor-kimi-k27-code": 40.0,
        }
        results = []
        for index in range(EPISODE_COUNT):
            family = FAMILIES[index % len(FAMILIES)]
            for profile_id, total in totals.items():
                results.append(
                    {
                        "episode_ref": f"episode_{index + 1:04d}",
                        "profile_id": profile_id,
                        "family": family,
                        "valid": True,
                        "total": total,
                    }
                )
        first = aggregate_complete_results(results)
        second = aggregate_complete_results(results)
        self.assertEqual(first, second)
        for profile_id, total in totals.items():
            profile = first["profiles"][profile_id]
            self.assertEqual(profile["mean_total"], total)
            self.assertEqual(profile["valid_rate"], 1.0)
            self.assertEqual(profile["family_stratified_bootstrap_95_ci"], [total, total])
            self.assertEqual(set(profile["by_family"]), set(FAMILIES))
            self.assertTrue(
                all(
                    family["fixed_denominator"] == 10
                    and family["valid"] == 10
                    and family["mean_total"] == total
                    for family in profile["by_family"].values()
                )
            )
        self.assertEqual(len(first["exploratory_pairwise_deltas"]), 15)
        self.assertEqual(
            first["exploratory_pairwise_deltas"][
                "claude-opus-high_minus_codex-sol"
            ]["mean_delta"],
            -10.0,
        )
        pair = first["exploratory_pairwise_deltas"][
            "claude-opus-high_minus_codex-sol"
        ]
        self.assertEqual(pair["simultaneous_familywise_confidence_target"], 0.95)
        self.assertEqual(set(pair["by_family_mean_delta"].values()), {-10.0})

    def test_aggregate_rejects_family_disagreement_and_invalid_totals(self):
        results = []
        for index in range(EPISODE_COUNT):
            family = FAMILIES[index % len(FAMILIES)]
            for profile in PROFILES:
                results.append(
                    {
                        "episode_ref": f"episode_{index + 1:04d}",
                        "profile_id": profile["profile_id"],
                        "family": family,
                        "valid": True,
                        "total": 50.0,
                    }
                )
        results[0]["family"] = FAMILIES[1]
        with self.assertRaisesRegex(ValueError, "disagree"):
            aggregate_complete_results(results)
        results[0]["family"] = FAMILIES[0]
        results[0]["total"] = float("nan")
        with self.assertRaisesRegex(ValueError, "Invalid complete"):
            aggregate_complete_results(results)

    def test_private_checkpoint_tamper_is_rejected(self):
        self._prepare()
        payload = json.loads(self.private_path.read_text())
        payload["status"] = "complete"
        matched._atomic_json(self.private_path, payload, private=True)
        with self.assertRaisesRegex(ValueError, "authentication failed"):
            matched._load_private_state(self.private_path, AUTHENTICATION_KEY)

    def test_exact_kimi_code_receipt_rejects_model_alias_downgrade(self):
        profile = next(
            profile
            for profile in PROFILES
            if profile["profile_id"] == "cursor-kimi-k27-code"
        )
        result = self._result("cursor", "kimi-k2.7-code", "cursor-agent", 50.0)
        downgraded = replace(result, observed_models=("Kimi K2.7",))
        sanitized = matched._sanitize_result(
            episode={
                "episode_ref": "episode_0001",
                "family": FAMILIES[0],
                "pack_commitment": "sha256:" + "1" * 64,
            },
            profile=profile,
            result=downgraded,
            started_at="start",
            finished_at="finish",
        )
        self.assertFalse(sanitized["valid"])
        self.assertEqual(sanitized["total"], 0.0)
        self.assertIn("agent_failure:model_receipt_missing", sanitized["audit_events"])

    def test_terminal_trace_survives_an_invalid_model_scorecard(self):
        result = self._result("codex", "gpt-5.6-sol", "codex", 0.0)
        invalid = replace(
            result,
            scorecard={
                "valid": False,
                "total": 0.0,
                "dimensions": {},
                "metrics": {"integrity_pass": False, "tool_calls": 1},
                "violations": ["invalid_submission"],
            },
        )
        payload = matched._terminal_replay_payload(
            {
                "episode_ref": "episode_0001",
                "profile_id": "codex-sol",
                "raw_result": asdict(invalid),
            },
            {"pack_commitment": "sha256:" + "1" * 64},
        )
        self.assertEqual(payload["trace_status"], "recorded")
        self.assertTrue(payload["replay_trace_sha256"].startswith("sha256:"))

    def test_sonnet_five_receipt_identity_is_exact(self):
        profile = next(
            profile
            for profile in PROFILES
            if profile["profile_id"] == "claude-sonnet-high"
        )
        self.assertTrue(
            matched._exact_model_receipt_satisfied(
                profile, ("Claude Sonnet 5",)
            )
        )
        self.assertFalse(
            matched._exact_model_receipt_satisfied(
                profile, ("Claude Sonnet 5 High",)
            )
        )

    def test_environment_preflight_gate_prevents_production_call(self):
        self._prepare()
        with self._contracts(), patch(
            "epiagentbench.development_matched_panel._preflight_execution"
        ), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
        ) as evaluate, self.assertRaisesRegex(RuntimeError, "environment preflight"):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()

    def test_missing_cursor_key_stops_production_before_durable_start(self):
        self._prepare()
        self.keychain_present = True
        with (
            patch.dict(os.environ, {}, clear=True),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
            ) as evaluate,
            self.assertRaisesRegex(RuntimeError, "requires CURSOR_API_KEY"),
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["status"], "prepared")
        self.assertEqual(private["assignments"], [])
        self.assertFalse(self.results_path.exists())

    def test_production_before_call_drift_does_not_consume_assignment(self):
        self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_attest_execution_contracts",
                side_effect=RuntimeError("preexisting execution drift"),
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
        ):
            result = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["assignments"], [])
        self.assertEqual(result["status"], "stopped_supervisor_incident")
        self.assertEqual(
            private["execution_incident"]["failure_class"],
            "ProviderStateIsolationError",
        )
        self.assertEqual(
            private["execution_incident"]["boundary"],
            "clean_before_assignment",
        )

    def test_production_before_call_helper_drift_is_terminal_zero_call(self):
        self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_attest_frozen_glean_auth_dependencies",
                side_effect=ProviderStateIsolationError(
                    "frozen helper drift"
                ),
            ) as helper_attestation,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
        ):
            result = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()
        self.assertEqual(helper_attestation.call_count, 1)
        self.assertEqual(result["status"], "stopped_supervisor_incident")
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["assignments"], [])
        self.assertEqual(
            private["execution_incident"]["boundary"],
            "clean_before_assignment",
        )

    def test_production_after_call_drift_becomes_transport_void(self):
        self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True
        events: list[str] = []

        def attest(**_kwargs):
            events.append("attest")
            if events.count("attest") == 2:
                raise RuntimeError("mid-call execution drift")

        def evaluate(system: str, **kwargs):
            events.append("provider")
            return self._result(
                system, kwargs["model"], kwargs["executable"], 50.0
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_attest_execution_contracts",
                side_effect=attest,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
        ):
            result = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(events, ["attest", "provider", "attest"])
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(result["status"], "stopped_supervisor_incident")
        self.assertEqual(
            result["failure_stage"],
            "provider_isolation_after_provider",
        )
        self.assertNotIn("attestation_failure_code", result)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(len(private["assignments"]), 1)
        self.assertEqual(private["assignments"][0]["status"], "transport_void")
        self.assertEqual(
            private["assignments"][0]["void_reason"],
            "ProviderStateIsolationError",
        )
        self.assertEqual(
            private["execution_incident"]["failure_class"],
            "ProviderStateIsolationError",
        )

    def test_production_after_call_helper_drift_is_terminal_void(self):
        self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True

        def evaluate(system: str, **kwargs):
            return self._result(
                system, kwargs["model"], kwargs["executable"], 50.0
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_attest_frozen_glean_auth_dependencies",
                side_effect=[
                    None,
                    ProviderStateIsolationError("frozen helper drift"),
                ],
            ) as helper_attestation,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
        ):
            result = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
        )
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(helper_attestation.call_count, 2)
        self.assertEqual(result["status"], "stopped_supervisor_incident")
        self.assertEqual(
            result["failure_stage"],
            "provider_isolation_after_provider",
        )
        self.assertNotIn("attestation_failure_code", result)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(len(private["assignments"]), 1)
        self.assertEqual(
            private["assignments"][0]["void_reason"],
            "ProviderStateIsolationError",
        )
        self.assertEqual(
            private["execution_incident"]["failure_class"],
            "ProviderStateIsolationError",
        )

    def test_final_helper_drift_blocks_terminal_release(self):
        self._prepare()
        self._prime_codex_auth()
        self.keychain_present = True
        self._set_terminal_assignment_prefix(ASSIGNMENT_COUNT - 1)

        def evaluate(system: str, **kwargs):
            return self._result(
                system, kwargs["model"], kwargs["executable"], 50.0
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_attest_frozen_glean_auth_dependencies",
                side_effect=[
                    None,
                    None,
                    ProviderStateIsolationError("frozen helper drift"),
                ],
            ) as helper_attestation,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
        ):
            result = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                require_persistent_supervisor=False,
                offline_test_evaluator=invoked,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(helper_attestation.call_count, 3)
        self.assertEqual(result["status"], "stopped_supervisor_incident")
        self.assertEqual(result["results"], [])
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(len(private["assignments"]), ASSIGNMENT_COUNT)
        self.assertEqual(
            private["execution_incident"]["boundary"], "final_completion"
        )
        self.assertNotEqual(private["status"], "complete")
        self.assertFalse(
            matched._cohort_retirement_path(
                Path(private["cohort_manifest_path"])
            ).exists()
        )

    def test_production_nonzero_provider_exit_becomes_transport_void(self):
        self._prepare()

        def evaluate(system: str, **kwargs):
            return replace(
                self._result(
                    system, kwargs["model"], kwargs["executable"], 0.0
                ),
                returncode=7,
                submission=None,
                diagnostic="redacted provider transport failure",
            )

        result, invoked = self._run_with(evaluate)
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(result["status"], "stopped_transport_void")
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["assignments"][0]["status"], "transport_void")
        self.assertNotIn("public_result", private["assignments"][0])
        self.assertNotIn("codex_auth_incident", private)
        self.assertNotIn("execution_incident", private)

        resumed, resumed_call = self._run_with(
            RuntimeError("stop after proving ordinary void can resume")
        )
        self.assertEqual(resumed_call.call_count, 1)
        self.assertEqual(resumed["status"], "stopped_transport_void")
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(len(private["assignments"]), 2)

    def test_codex_auth_attestation_error_is_terminal_but_not_generic_error(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        keys = matched._assignment_keys(private["schedule"])
        codex_index = next(
            index
            for index, (_ref, profile_id) in enumerate(keys)
            if matched._PROFILE_BY_ID[profile_id]["system"] == "codex"
        )
        self._set_terminal_assignment_prefix(codex_index)

        result, invoked = self._run_with(
            CodexAuthenticationIncidentError(
                "Isolated Codex authentication state became ambiguous"
            )
        )
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(result["status"], "stopped_transport_void")
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            private["codex_auth_incident"]["failure_class"],
            "CodexAuthenticationIncidentError",
        )
        self.assertNotIn("execution_incident", private)

    def test_provider_process_isolation_error_is_terminal(self):
        self._prepare()

        result, invoked = self._run_with(
            ProviderProcessIsolationError(
                "Provider process group remained alive after termination"
            )
        )
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(result["status"], "stopped_supervisor_incident")
        self.assertEqual(
            result["failure_stage"],
            "provider_isolation_after_provider",
        )
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            private["execution_incident"]["failure_class"],
            "ProviderProcessIsolationError",
        )
        with self.assertRaisesRegex(RuntimeError, "execution incident"):
            self._run_with(
                lambda *_args, **_kwargs: self.fail(
                    "isolation incident must block later providers"
                )
            )

    def test_post_return_claude_credential_drift_is_terminal(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        keys = matched._assignment_keys(private["schedule"])
        claude_index = next(
            index
            for index, (_ref, profile_id) in enumerate(keys)
            if matched._PROFILE_BY_ID[profile_id]["system"] == "claude"
        )
        self._set_terminal_assignment_prefix(claude_index)
        credential_checks = 0

        def require_credential_state(*_args, **_kwargs):
            nonlocal credential_checks
            credential_checks += 1
            if credential_checks == 4:
                raise RuntimeError("sensitive post-return credential detail")

        def evaluate(system: str, **kwargs):
            self.assertEqual(system, "claude")
            return self._result(
                system, kwargs["model"], kwargs["executable"], 50.0
            )

        with patch(
            "epiagentbench.development_matched_panel."
            "_require_claude_credential_state",
            side_effect=require_credential_state,
        ):
            stopped, invoked = self._run_with(evaluate)

        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(credential_checks, 4)
        self.assertEqual(stopped["status"], "stopped_supervisor_incident")
        self.assertEqual(
            stopped["failure_stage"],
            "provider_isolation_after_provider",
        )
        self.assertEqual(stopped["terminal_assignments"], claude_index + 1)
        self.assertEqual(stopped["results"], [])
        self.assertNotIn(
            "sensitive post-return credential detail",
            json.dumps(stopped, sort_keys=True),
        )
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        assignment = private["assignments"][claude_index]
        self.assertEqual(assignment["status"], "transport_void")
        self.assertNotIn("raw_result", assignment)
        self.assertEqual(
            assignment["void_reason"], "ProviderStateIsolationError"
        )
        self.assertEqual(
            private["execution_incident"],
            {
                "status": "terminal",
                "assignment_index": claude_index,
                "failure_class": "ProviderStateIsolationError",
            },
        )
        retirement_path = matched._cohort_retirement_path(
            Path(private["cohort_manifest_path"])
        )
        self.assertFalse(retirement_path.exists())

        with (
            patch.dict(os.environ, {}, clear=True),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate_again,
            self.assertRaisesRegex(RuntimeError, "execution incident"),
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate_again.assert_not_called()
        self.assertFalse(retirement_path.exists())

    def test_claude_timeout_is_a_fixed_denominator_zero(self):
        self._assert_non_codex_timeout_is_fixed_zero("claude")

    def test_cursor_timeout_is_a_fixed_denominator_zero(self):
        self._assert_non_codex_timeout_is_fixed_zero("cursor")

    def test_provider_callback_observes_durable_start_and_trace_free_public_state(
        self,
    ):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        expected_key = matched._assignment_keys(private["schedule"])[0]

        def evaluate(_system: str, **_kwargs):
            durable = matched._load_private_state(
                self.private_path, AUTHENTICATION_KEY
            )
            self.assertEqual(len(durable["assignments"]), 1)
            marker = durable["assignments"][0]
            self.assertEqual(
                set(marker),
                {
                    "episode_ref",
                    "profile_id",
                    "status",
                    "started_at_utc",
                },
            )
            self.assertEqual(
                (marker["episode_ref"], marker["profile_id"]), expected_key
            )
            self.assertEqual(marker["status"], "started")

            public = matched._load_json(self.results_path)
            self.assertEqual(public["status"], "running")
            self.assertEqual(public["terminal_assignments"], 0)
            self.assertEqual(public["results"], [])
            self.assertEqual(public["summary"], {"primary_estimand": "pending"})
            serialized = json.dumps(public, sort_keys=True)
            for private_name in (
                "replay_trace",
                "agent_events",
                "raw_result",
                "episode_secret",
                "schedule_nonce_hex",
            ):
                self.assertNotIn(private_name, serialized)
            raise RuntimeError("stop after observing durable launch boundary")

        result, invoked = self._run_with(evaluate)
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(result["status"], "stopped_transport_void")

    def test_assignment_300_process_isolation_incident_blocks_retirement(self):
        self._prepare()
        self._set_terminal_assignment_prefix(ASSIGNMENT_COUNT - 1)

        result, invoked = self._run_with(
            ProviderProcessIsolationError(
                "Provider process group remained alive after termination"
            )
        )
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(result["status"], "stopped_supervisor_incident")
        self.assertEqual(
            result["failure_stage"],
            "provider_isolation_after_provider",
        )
        self.assertEqual(result["terminal_assignments"], ASSIGNMENT_COUNT)
        self.assertEqual(result["results"], [])
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(len(private["assignments"]), ASSIGNMENT_COUNT)
        self.assertEqual(
            private["execution_incident"]["assignment_index"],
            ASSIGNMENT_COUNT - 1,
        )
        self.assertEqual(
            private["execution_incident"]["failure_class"],
            "ProviderProcessIsolationError",
        )
        retirement_path = matched._cohort_retirement_path(
            Path(private["cohort_manifest_path"])
        )
        self.assertFalse(retirement_path.exists())
        self.assertNotIn("replay_trace", json.dumps(result, sort_keys=True))

        with (
            patch.dict(os.environ, {}, clear=True),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate_again,
            self.assertRaisesRegex(RuntimeError, "execution incident"),
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate_again.assert_not_called()
        self.assertFalse(retirement_path.exists())

    def test_terminal_incident_restart_repairs_only_trace_free_public_progress(
        self,
    ):
        self._prepare()
        real_atomic_json = matched._atomic_json
        failed_public_stop = False

        def crash_before_public_stop(path, value, *, private=False):
            nonlocal failed_public_stop
            if (
                Path(path) == self.results_path
                and isinstance(value, dict)
                and value.get("status") == "stopped_supervisor_incident"
                and not failed_public_stop
            ):
                failed_public_stop = True
                raise OSError("simulated public progress crash")
            return real_atomic_json(path, value, private=private)

        with (
            patch(
                "epiagentbench.development_matched_panel._atomic_json",
                side_effect=crash_before_public_stop,
            ),
            self.assertRaisesRegex(OSError, "simulated public progress crash"),
        ):
            self._run_with(
                ProviderProcessIsolationError(
                    "Provider process group remained alive after termination"
                )
            )

        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["assignments"][0]["status"], "transport_void")
        self.assertEqual(private["execution_incident"]["status"], "terminal")
        stale_public = matched._load_json(self.results_path)
        self.assertEqual(stale_public["status"], "running")
        self.assertEqual(stale_public["terminal_assignments"], 0)
        self.assertEqual(stale_public["results"], [])
        self.assertNotIn(
            "replay_trace", json.dumps(stale_public, sort_keys=True)
        )

        with (
            patch.dict(os.environ, {}, clear=True),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate_again,
            self.assertRaisesRegex(RuntimeError, "execution incident"),
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
        )
        evaluate_again.assert_not_called()
        repaired = matched._load_json(self.results_path)
        self.assertEqual(repaired["status"], "stopped_supervisor_incident")
        self.assertEqual(
            repaired["failure_stage"],
            "provider_isolation_after_provider",
        )
        self.assertEqual(repaired["terminal_assignments"], 1)
        self.assertEqual(repaired["completed_assignments"], 0)
        self.assertEqual(repaired["transport_voids"], 1)
        self.assertEqual(repaired["results"], [])
        serialized = json.dumps(repaired, sort_keys=True)
        for private_name in ("replay_trace", "agent_events", "raw_result"):
            self.assertNotIn(private_name, serialized)
        self.assertFalse(
            matched._cohort_retirement_path(
                Path(private["cohort_manifest_path"])
            ).exists()
        )

    def test_terminal_incident_restart_rejects_unknown_boundary(self):
        self._assert_signed_isolation_incident_refused(
            {
                "status": "terminal",
                "assignment_index": 0,
                "failure_class": "ProviderExecutionIsolationError",
                "boundary": "provider-output-DO-NOT-LEAK",
                "attestation_failure_code": "status_snapshot_unstable",
            },
            "boundary is invalid",
        )

    def test_terminal_incident_restart_rejects_unknown_boundary_without_code(
        self,
    ):
        self._assert_signed_isolation_incident_refused(
            {
                "status": "terminal",
                "assignment_index": 0,
                "failure_class": "interrupted_after_durable_start",
                "boundary": "provider-output-DO-NOT-LEAK",
            },
            "boundary is invalid",
        )

    def test_terminal_incident_restart_rejects_unsafe_failure_code(self):
        self._assert_signed_isolation_incident_refused(
            {
                "status": "terminal",
                "assignment_index": 0,
                "failure_class": "interrupted_after_durable_start",
                "attestation_failure_code": "provider-output-DO-NOT-LEAK",
            },
            "failure code",
        )

    def test_terminal_incident_restart_rejects_untrusted_failure_class(self):
        self._assert_signed_isolation_incident_refused(
            {
                "status": "terminal",
                "assignment_index": 1,
                "failure_class": "provider-output-DO-NOT-LEAK",
                "boundary": "clean_before_assignment",
                "profile_id": PROFILES[0]["profile_id"],
            },
            "class is invalid",
        )

    def test_terminal_incident_restart_rejects_malformed_clean_boundary(self):
        self._assert_signed_isolation_incident_refused(
            {
                "status": "terminal",
                "assignment_index": 0,
                "failure_class": "ProviderExecutionIsolationError",
                "boundary": "clean_before_assignment",
                "profile_id": PROFILES[0]["profile_id"],
            },
            "boundary is invalid",
        )

    def test_terminal_incident_restart_rejects_malformed_final_boundary(self):
        self._assert_signed_isolation_incident_refused(
            {
                "status": "terminal",
                "assignment_index": 0,
                "failure_class": "ProviderExecutionIsolationError",
                "boundary": "final_completion",
            },
            "boundary is invalid",
        )

    def test_terminal_incident_restart_rejects_nonmapping_execution_incident(
        self,
    ):
        self._assert_signed_raw_incident_refused(
            "execution_incident",
            "provider-output-DO-NOT-LEAK",
            "execution incident state is invalid",
        )

    def test_terminal_incident_restart_rejects_nonmapping_codex_incident(
        self,
    ):
        self._assert_signed_raw_incident_refused(
            "codex_auth_incident",
            "provider-output-DO-NOT-LEAK",
            "Codex authentication incident is invalid",
        )

    def test_terminal_incident_restart_refuses_unsafe_public_payload(self):
        public_manifest = self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        episode_ref, profile_id = matched._assignment_keys(
            private["schedule"]
        )[0]
        private["status"] = "running"
        private["panel_started_at_utc"] = "test-panel-start"
        private["assignments"] = [
            {
                "episode_ref": episode_ref,
                "profile_id": profile_id,
                "status": "transport_void",
                "started_at_utc": "test-assignment-start",
                "finished_at_utc": "test-assignment-finish",
                "void_reason": "ProviderProcessIsolationError",
            }
        ]
        private["execution_incident"] = {
            "status": "terminal",
            "assignment_index": 0,
            "failure_class": "ProviderProcessIsolationError",
        }
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        unsafe = matched._public_running(public_manifest, private)
        unsafe["raw_result"] = {"must_not_be_overwritten": True}
        matched._atomic_json(self.results_path, unsafe)

        with (
            patch.dict(os.environ, {}, clear=True),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
            self.assertRaisesRegex(ValueError, "unsafe schema"),
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()
        self.assertEqual(matched._load_json(self.results_path), unsafe)

    def test_late_codex_auth_incident_never_launches_assignment_300(
        self,
    ):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        keys = matched._assignment_keys(private["schedule"])
        codex_index = max(
            index
            for index, (_ref, profile_id) in enumerate(keys)
            if matched._PROFILE_BY_ID[profile_id]["system"] == "codex"
            and index < ASSIGNMENT_COUNT - 1
        )
        self._set_terminal_assignment_prefix(codex_index)

        result, invoked = self._run_with(
            CodexAuthenticationIncidentError(
                "Isolated Codex authentication state became ambiguous"
            )
        )
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(result["status"], "stopped_transport_void")
        self.assertEqual(result["terminal_assignments"], codex_index + 1)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(len(private["assignments"]), codex_index + 1)
        self.assertEqual(
            private["codex_auth_incident"]["assignment_index"], codex_index
        )
        retirement_path = matched._cohort_retirement_path(
            Path(private["cohort_manifest_path"])
        )
        self.assertFalse(retirement_path.exists())

        with (
            patch.dict(os.environ, {}, clear=True),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate_again,
            self.assertRaisesRegex(RuntimeError, "authentication incident"),
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate_again.assert_not_called()
        self.assertEqual(
            len(
                matched._load_private_state(
                    self.private_path, AUTHENTICATION_KEY
                )["assignments"]
            ),
            codex_index + 1,
        )
        self.assertFalse(retirement_path.exists())

    def test_final_ordinary_void_resumes_without_provider_call_and_retires(self):
        self._prepare()
        self._set_terminal_assignment_prefix(ASSIGNMENT_COUNT - 1)
        stopped, invoked = self._run_with(
            RuntimeError("ordinary final-assignment transport failure")
        )
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(stopped["status"], "stopped_transport_void")
        self.assertEqual(stopped["terminal_assignments"], ASSIGNMENT_COUNT)

        self.keychain_present = False
        with (
            patch.dict(os.environ, {}, clear=True),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate_again,
        ):
            completed = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate_again.assert_not_called()
        self.assertEqual(completed["status"], "complete_with_transport_voids")
        self.assertEqual(completed["terminal_assignments"], ASSIGNMENT_COUNT)
        self.assertEqual(len(completed["results"]), ASSIGNMENT_COUNT)
        self.assertTrue(
            all(item["status"] == "transport_void" for item in completed["results"])
        )
        self.assertNotIn("replay_trace", json.dumps(completed, sort_keys=True))
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertTrue(
            matched._cohort_retirement_path(
                Path(private["cohort_manifest_path"])
            ).exists()
        )

    def test_production_codex_timeout_is_terminal_auth_incident(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        keys = matched._assignment_keys(private["schedule"])
        codex_index = next(
            index
            for index, (_ref, profile_id) in enumerate(keys)
            if matched._PROFILE_BY_ID[profile_id]["system"] == "codex"
        )
        self._set_terminal_assignment_prefix(codex_index)
        calls = 0

        def evaluate(system: str, **kwargs):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("stop after timeout classification")
            return replace(
                self._result(
                    system, kwargs["model"], kwargs["executable"], 0.0
                ),
                returncode=124,
                submission=None,
                scorecard={
                    "valid": False,
                    "total": 0.0,
                    "dimensions": {
                        name: 0.0 for name in matched.DIMENSION_MAXIMA
                    },
                    "metrics": {},
                    "violations": ["timeout"],
                },
                audit_events=("agent_failure:timeout",),
                diagnostic="authentication required after model hung",
            )

        result, invoked = self._run_with(evaluate)
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(result["status"], "stopped_transport_void")
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        timeout_assignment = private["assignments"][codex_index]
        self.assertEqual(timeout_assignment["status"], "transport_void")
        self.assertNotIn("public_result", timeout_assignment)
        self.assertEqual(private["codex_auth_incident"]["status"], "terminal")

        with self._contracts(), patch(
            "epiagentbench.development_matched_panel._preflight_execution"
        ), patch(
            "epiagentbench.development_matched_panel._assert_environment_preflight"
        ), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
        ) as evaluate_again, self.assertRaisesRegex(RuntimeError, "non-resumable"):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate_again.assert_not_called()

    def test_production_zero_exit_malformed_submission_is_invalid_zero(self):
        self._prepare()
        calls = 0

        def evaluate(system: str, **kwargs):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("stop after malformed classification")
            return replace(
                self._result(
                    system, kwargs["model"], kwargs["executable"], 0.0
                ),
                submission=None,
                scorecard={
                    "valid": False,
                    "total": 0.0,
                    "dimensions": {
                        name: 0.0 for name in matched.DIMENSION_MAXIMA
                    },
                    "metrics": {"tool_calls": 2},
                    "violations": ["invalid_submission"],
                },
                audit_events=("agent_failure:invalid_submission",),
            )

        _result, invoked = self._run_with(evaluate)
        self.assertEqual(invoked.call_count, 2)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        malformed_assignment = private["assignments"][0]
        self.assertEqual(malformed_assignment["status"], "complete")
        self.assertFalse(malformed_assignment["public_result"]["valid"])
        self.assertEqual(malformed_assignment["public_result"]["total"], 0.0)

    def test_terminal_crash_recovery_finalizes_without_provider_credentials(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        private["status"] = "running"
        private["panel_started_at_utc"] = "start"
        private["assignments"] = [
            {
                "episode_ref": episode_ref,
                "profile_id": profile_id,
                "status": "transport_void",
                "started_at_utc": "start",
                "finished_at_utc": "finish",
                "void_reason": "test_terminal_checkpoint",
            }
            for episode_ref, profile_id in matched._assignment_keys(
                private["schedule"]
            )
        ]
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        self.keychain_present = False

        with (
            patch.dict(os.environ, {}, clear=True),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_assert_environment_preflight"
            ),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
            ) as evaluate,
        ):
            result = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()
        self.assertEqual(result["status"], "complete_with_transport_voids")
        self.assertEqual(result["terminal_assignments"], ASSIGNMENT_COUNT)

    def test_disposable_preflight_checks_all_profiles_without_scores(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight.json"
        claude_efforts: list[str | None] = []
        codex_reasoning_efforts: list[str | None] = []
        auth_kwargs_seen: list[
            tuple[str, bool, Path | None, bool, Path | None]
        ] = []
        episode_inputs: list[tuple[int, bytes, str]] = []

        def evaluate(system: str, **kwargs):
            episode_inputs.append(
                (kwargs["seed"], kwargs["episode_secret"], kwargs["family"])
            )
            auth_kwargs_seen.append(
                (
                    system,
                    "claude_secure_storage_dir" in kwargs,
                    kwargs.get("claude_secure_storage_dir"),
                    "codex_auth_storage_dir" in kwargs,
                    kwargs.get("codex_auth_storage_dir"),
                )
            )
            if system == "claude":
                self.assertEqual(
                    kwargs["claude_glean_oauth_client_id"],
                    "test-glean-client-id",
                )
            else:
                self.assertNotIn("claude_glean_oauth_client_id", kwargs)
            if system == "claude":
                claude_efforts.append(kwargs["claude_effort"])
                self.keychain_present = True
            if system == "codex":
                codex_reasoning_efforts.append(
                    kwargs["codex_reasoning_effort"]
                )
            return self._result(system, kwargs["model"], kwargs["executable"], 50.0)

        with patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}), self._contracts(), patch(
            "epiagentbench.development_matched_panel._preflight_execution"
        ), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
            side_effect=evaluate,
        ) as invoked:
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(invoked.call_count, len(PROFILES))
        self.assertEqual(len(set(episode_inputs)), 1)
        self.assertEqual(claude_efforts, ["high", "high"])
        self.assertEqual(codex_reasoning_efforts, ["medium", "max"])
        public = matched._load_json(self.public_path)
        self.assertEqual(
            receipt["precommitment_sha256"],
            public["precommitment_sha256"],
        )
        self.assertEqual(receipt["contract_hashes"], public["contract_hashes"])
        self.assertEqual(
            set(receipt["contract_hashes"]),
            {
                "source_sha256",
                "cli_sha256",
                "claude_auth_sha256",
                "codex_auth_sha256",
                "profiles_sha256",
                "budgets_sha256",
                "timeouts_sha256",
                "runtime_sha256",
                "replay_sha256",
                "supervisor_sha256",
            },
        )
        self.assertTrue(
            all(
                (
                    present and value == self.claude_secure_storage_dir.resolve()
                    if system == "claude"
                    else (not present and value is None)
                )
                and (
                    codex_present
                    and codex_value == self.codex_secure_storage_dir.resolve()
                    if system == "codex"
                    else (not codex_present and codex_value is None)
                )
                for (
                    system,
                    present,
                    value,
                    codex_present,
                    codex_value,
                ) in auth_kwargs_seen
            )
        )
        self.assertEqual(receipt["production_episodes_consumed"], 0)
        authentication = receipt["authentication_prerequisite"]
        self.assertEqual(authentication["codex"], "passed_before_preflight")
        self.assertEqual(
            authentication["managed_glean"], "passed_before_preflight"
        )
        self.assertEqual(authentication["model_calls"], 0)
        self.assertEqual(
            receipt["preflight_purpose"],
            "unscored_infrastructure_routing_handshake",
        )
        self.assertIsNone(receipt["failed_provider_invocation_state"])
        self.assertEqual(
            receipt["provider_calls_conservatively_chargeable"], 6
        )
        self.assertEqual(len(receipt["profiles"]), len(PROFILES))
        self.assertTrue(
            all("cli_version" not in item for item in receipt["profiles"])
        )
        self.assertEqual(
            [
                (
                    item["profile_id"],
                    item["requested_reasoning"],
                    item["invocation_state"],
                    item["outcome"],
                    item["timed_out"],
                    item["conservative_chargeable"],
                )
                for item in receipt["profiles"]
            ],
            [
                (
                    profile["profile_id"],
                    profile["requested_reasoning"],
                    "finished",
                    "passed",
                    False,
                    True,
                )
                for profile in PROFILES
            ],
        )
        self.assertTrue(all(not item["scored"] for item in receipt["profiles"]))
        self.assertTrue(
            all(
                item["infrastructure_handshake_passed"]
                for item in receipt["profiles"]
            )
        )
        claude_receipts = [
            item for item in receipt["profiles"] if item["system"] == "claude"
        ]
        self.assertEqual(
            [
                item["managed_glean_credentials_state_before"]
                for item in claude_receipts
            ],
            ["present", "present"],
        )
        self.assertTrue(
            all(
                item["managed_glean_credentials_state_after"] == "present"
                for item in claude_receipts
            )
        )
        self.assertTrue(
            all(item["replay_trace_validated"] for item in receipt["profiles"])
        )
        codex_receipts = [
            item for item in receipt["profiles"] if item["system"] == "codex"
        ]
        self.assertTrue(
            all(
                item["codex_credentials_state_before"] == "present"
                and item["codex_credentials_state_after"] == "present"
                and item["codex_auth_link_before"] == "bound"
                and item["codex_auth_link_after"] == "bound"
                and item["refresh_persistence_attested"] is True
                for item in codex_receipts
            )
        )
        self.assertNotIn("agent_events", json.dumps(receipt))
        self.assertNotIn("total", json.dumps(receipt))
        self.assertNotIn(
            str(self.claude_secure_storage_dir), json.dumps(receipt)
        )
        self.assertNotIn(
            str(self.codex_secure_storage_dir), json.dumps(receipt)
        )
        self.assertNotIn("test-glean-client-id", json.dumps(receipt))
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["environment_preflight"]["status"], "passed")
        prerequisite = private["environment_preflight"][
            "authentication_prerequisite"
        ]
        self.assertEqual(prerequisite["codex"], "passed_before_preflight")
        self.assertEqual(
            prerequisite["managed_glean"], "passed_before_preflight"
        )
        self.assertEqual(prerequisite["model_calls"], 0)
        self.assertEqual(
            private["codex_auth_file_identity"],
            matched._codex_auth_file_identity(self.codex_secure_storage_dir),
        )
        self.assertTrue(
            all(
                attempt["provider_invocation"]["status"] == "finished"
                and "started_at_utc" in attempt["provider_invocation"]
                and "finished_at_utc" in attempt["provider_invocation"]
                for attempt in private["environment_preflight"]["attempts"]
            )
        )
        self.assertIn(
            "claude_auth_sha256",
            private["environment_preflight"]["passed_contract_hashes"],
        )
        self.assertIn(
            "codex_auth_sha256",
            private["environment_preflight"]["passed_contract_hashes"],
        )
        self.assertEqual(private["assignments"], [])

    def test_disposable_preflight_is_not_a_capability_screen(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight-capability.json"

        def evaluate(system: str, **kwargs):
            if system == "claude":
                self.keychain_present = True
            return replace(
                self._result(
                    system, kwargs["model"], kwargs["executable"], 0.0
                ),
                submission=None,
                scorecard={
                    "valid": False,
                    "total": 0.0,
                    "dimensions": {
                        name: 0.0 for name in matched.DIMENSION_MAXIMA
                    },
                    "metrics": {"tool_calls": 2},
                    "violations": ["invalid_submission"],
                },
                audit_events=("agent_failure:invalid_submission",),
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate,
            ),
        ):
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(len(receipt["profiles"]), len(PROFILES))
        self.assertTrue(
            all(
                item["infrastructure_handshake_passed"]
                for item in receipt["profiles"]
            )
        )

    def test_contained_codex_timeout_quarantines_codex_and_continues_cursor(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight-timeout.json"
        invoked_models: list[str] = []

        def evaluate(system: str, **kwargs):
            model = kwargs["model"]
            invoked_models.append(model)
            if system == "claude":
                self.keychain_present = True
            if model == "gpt-5.6-sol":
                return self._timeout_result(
                    system, model, kwargs["executable"]
                )
            return self._result(system, model, kwargs["executable"], 0.0)

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
        ):
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(
            invoked.call_count,
            5,
            json.dumps(receipt, sort_keys=True),
        )
        self.assertEqual(
            invoked_models,
            [
                "claude-opus-4-8",
                "claude-sonnet-5",
                "gpt-5.6-sol",
                "cursor-grok-4.5-high",
                "kimi-k2.7-code",
            ],
        )
        self.assertEqual(receipt["status"], "failed")
        self.assertTrue(
            all("cli_version" not in item for item in receipt["profiles"])
        )
        self.assertEqual(
            [item["profile_id"] for item in receipt["profiles"]],
            [profile["profile_id"] for profile in PROFILES],
        )
        outcomes = {
            item["profile_id"]: item for item in receipt["profiles"]
        }
        self.assertEqual(
            {
                key: outcomes["codex-sol"][key]
                for key in (
                    "invocation_state",
                    "outcome",
                    "timed_out",
                    "conservative_chargeable",
                    "failure_reason",
                )
            },
            {
                "invocation_state": "finished",
                "outcome": "failed_timeout",
                "timed_out": True,
                "conservative_chargeable": True,
                "failure_reason": "timeout",
            },
        )
        self.assertEqual(
            {
                key: outcomes["codex-luna-max"][key]
                for key in (
                    "invocation_state",
                    "outcome",
                    "timed_out",
                    "conservative_chargeable",
                )
            },
            {
                "invocation_state": "not_started",
                "outcome": "skipped_dependency",
                "timed_out": False,
                "conservative_chargeable": False,
            },
        )
        self.assertEqual(
            outcomes["cursor-grok-high"]["outcome"], "passed"
        )
        self.assertEqual(
            outcomes["cursor-kimi-k27-code"]["outcome"], "passed"
        )
        self.assertEqual(
            receipt["provider_calls_conservatively_chargeable"], 5
        )
        self.assertFalse(receipt["scores_reported"])

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as production,
            self.assertRaisesRegex(RuntimeError, "must pass"),
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        production.assert_not_called()

    def test_contained_non_codex_failure_continues_all_later_profiles(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight-nonzero.json"
        invoked_models: list[str] = []

        def evaluate(system: str, **kwargs):
            model = kwargs["model"]
            invoked_models.append(model)
            if system == "claude":
                self.keychain_present = True
            result = self._result(system, model, kwargs["executable"], 0.0)
            if model == "claude-opus-4-8":
                return replace(
                    result,
                    returncode=7,
                    audit_events=("agent_failure:nonzero_exit",),
                    diagnostic="redacted provider nonzero exit",
                )
            return result

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
        ):
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(invoked.call_count, len(PROFILES))
        self.assertEqual(
            invoked_models,
            [profile["requested_model"] for profile in PROFILES],
        )
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(
            [item["outcome"] for item in receipt["profiles"]],
            [
                "failed_provider",
                "passed",
                "passed",
                "passed",
                "passed",
                "passed",
            ],
        )
        failure = receipt["profiles"][0]
        self.assertEqual(failure["failure_reason"], "nonzero_exit")
        self.assertEqual(failure["invocation_state"], "finished")
        self.assertFalse(failure["timed_out"])
        self.assertTrue(failure["conservative_chargeable"])
        self.assertEqual(
            receipt["provider_calls_conservatively_chargeable"], len(PROFILES)
        )
        self.assertEqual(receipt["failed_profile_ids"], ["claude-opus-high"])

    def test_cli_startup_failure_aborts_all_remaining_preflight_profiles(self):
        self._assert_harness_startup_failure_terminal_aborts(
            audit_events=("agent_failure:nonzero_exit",),
            diagnostic="stderr: unknown option --unsupported-harness-flag",
            returncode=2,
        )

    def test_auth_failure_aborts_all_remaining_preflight_profiles(self):
        self._assert_harness_startup_failure_terminal_aborts(
            audit_events=("agent_failure:nonzero_exit",),
            diagnostic="stderr: authentication required",
            returncode=1,
        )

    def test_mcp_failure_aborts_all_remaining_preflight_profiles(self):
        self._assert_harness_startup_failure_terminal_aborts(
            audit_events=("agent_failure:mcp_unavailable",),
            diagnostic="",
            returncode=0,
        )

    def test_structured_output_failure_aborts_remaining_preflight_profiles(self):
        self._assert_harness_startup_failure_terminal_aborts(
            audit_events=("agent_failure:structured_output_unavailable",),
            diagnostic="",
            returncode=0,
        )

    def test_preflight_isolation_failure_aborts_all_remaining_profiles(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight-isolation.json"
        invoked_models: list[str] = []

        def evaluate(system: str, **kwargs):
            model = kwargs["model"]
            invoked_models.append(model)
            if system == "claude":
                self.keychain_present = True
            if model == "gpt-5.6-sol":
                raise ProviderStateIsolationError(
                    "provider-secret-must-not-leak"
                )
            return self._result(system, model, kwargs["executable"], 0.0)

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate,
            ) as invoked,
        ):
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )

        self.assertEqual(invoked.call_count, 3)
        self.assertEqual(
            invoked_models,
            ["claude-opus-4-8", "claude-sonnet-5", "gpt-5.6-sol"],
        )
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(
            [item["profile_id"] for item in receipt["profiles"]],
            [profile["profile_id"] for profile in PROFILES],
        )
        outcomes = receipt["profiles"]
        self.assertEqual(
            [item["outcome"] for item in outcomes],
            [
                "passed",
                "passed",
                "terminal_abort",
                "not_started_terminal_abort",
                "not_started_terminal_abort",
                "not_started_terminal_abort",
            ],
        )
        self.assertEqual(
            [item["invocation_state"] for item in outcomes],
            [
                "finished",
                "finished",
                "started_not_finished",
                "not_started",
                "not_started",
                "not_started",
            ],
        )
        self.assertEqual(
            [item["conservative_chargeable"] for item in outcomes],
            [True, True, True, False, False, False],
        )
        self.assertEqual(
            receipt["provider_calls_conservatively_chargeable"], 3
        )
        self.assertNotIn(
            "provider-secret-must-not-leak",
            json.dumps(receipt, sort_keys=True),
        )

    def test_environment_preflight_gate_validates_full_v14_receipt(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight-gate.json"

        def evaluate(system: str, **kwargs):
            if system == "claude":
                self.keychain_present = True
            return self._result(
                system, kwargs["model"], kwargs["executable"], 0.0
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate,
            ),
        ):
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )

        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        public = matched._load_json(self.public_path)
        relative = matched._relative_to_root(preflight_path, self.root)
        with patch(
            "epiagentbench.development_matched_panel._git_output",
            return_value=relative,
        ):
            matched._assert_environment_preflight(self.root, private, public)

        candidates: list[dict] = []
        for key, value in (
            ("schema_version", "older-schema"),
            ("panel_id", "older-panel"),
            ("development_only", False),
            ("production_episodes_consumed", 1),
            ("scores_reported", True),
        ):
            candidate = copy.deepcopy(receipt)
            candidate[key] = value
            candidates.append(candidate)
        wrong_authentication = copy.deepcopy(receipt)
        wrong_authentication["authentication_prerequisite"][
            "managed_glean"
        ] = "failed"
        candidates.append(wrong_authentication)
        missing_profile = copy.deepcopy(receipt)
        missing_profile["profiles"].pop()
        candidates.append(missing_profile)
        duplicate_profile = copy.deepcopy(receipt)
        duplicate_profile["profiles"][1]["profile_id"] = duplicate_profile[
            "profiles"
        ][0]["profile_id"]
        candidates.append(duplicate_profile)
        failed_handshake = copy.deepcopy(receipt)
        failed_handshake["profiles"][0][
            "infrastructure_handshake_passed"
        ] = False
        candidates.append(failed_handshake)
        wrong_model_receipt = copy.deepcopy(receipt)
        wrong_model_receipt["profiles"][0]["observed_models"] = [
            "unexpected-model"
        ]
        candidates.append(wrong_model_receipt)
        wrong_precommitment = copy.deepcopy(receipt)
        wrong_precommitment["precommitment_sha256"] = "sha256:" + "f" * 64
        candidates.append(wrong_precommitment)
        missing_budget_binding = copy.deepcopy(receipt)
        missing_budget_binding["contract_hashes"].pop("budgets_sha256")
        candidates.append(missing_budget_binding)
        wrong_timeout_binding = copy.deepcopy(receipt)
        wrong_timeout_binding["contract_hashes"]["timeouts_sha256"] = (
            "sha256:" + "e" * 64
        )
        candidates.append(wrong_timeout_binding)

        for index, candidate in enumerate(candidates):
            matched._atomic_json(preflight_path, candidate)
            candidate_private = copy.deepcopy(private)
            candidate_private["environment_preflight"][
                "public_receipt_sha256"
            ] = matched._component_hash(candidate)
            with self.subTest(index=index), patch(
                "epiagentbench.development_matched_panel._git_output",
                return_value=relative,
            ), self.assertRaisesRegex(RuntimeError, "receipt is invalid"):
                matched._assert_environment_preflight(
                    self.root, candidate_private, public
                )

    def test_disposable_preflight_attests_immediately_around_each_call(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight.json"
        events: list[str] = []

        def attest(**_kwargs):
            events.append("attest")

        def bootstrap(*_args, **kwargs):
            events.append("glean_bootstrap")
            kwargs["invocation_launch_pending"]()
            kwargs["invocation_started"]()
            self.keychain_present = True
            kwargs["invocation_returned"](0)

        def codex_bootstrap(path: Path, **kwargs):
            events.append("codex_bootstrap")
            self._bootstrap_codex_fixture(path, **kwargs)

        def evaluate(system: str, **kwargs):
            events.append(f"provider:{kwargs['model']}")
            if system == "claude":
                self.keychain_present = True
            return self._result(
                system, kwargs["model"], kwargs["executable"], 50.0
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_attest_execution_contracts",
                side_effect=attest,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials",
                side_effect=bootstrap,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials",
                side_effect=codex_bootstrap,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate,
            ),
        ):
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )

        expected_events = [
            event
            for profile in PROFILES
            for event in (
                "attest",
                f"provider:{profile['requested_model']}",
                "attest",
            )
        ]
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(events, expected_events)

    def test_disposable_preflight_before_call_drift_fails_closed(self):
        self._prepare()
        before_path = self.root / "results" / "preflight-before.json"
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_attest_execution_contracts",
                side_effect=RuntimeError("before-call drift"),
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
        ):
            before_receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=before_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()
        self.assertEqual(before_receipt["status"], "failed")
        self.assertEqual(
            before_receipt["failure_stage"],
            "execution_contract_before_harness",
        )
        self.assertEqual(
            before_receipt["failed_provider_invocation_state"],
            "not_started",
        )
        self.assertEqual(
            before_receipt["provider_calls_conservatively_chargeable"], 0
        )

    def test_provider_invocation_accounting_uses_only_durable_markers(self):
        attempts = [
            {"profile_id": "not-started"},
            {
                "profile_id": "started",
                "provider_invocation": {"status": "started"},
            },
            {
                "profile_id": "finished",
                "provider_invocation": {"status": "finished"},
            },
        ]
        self.assertEqual(
            [
                matched._durable_provider_invocation_state(attempt)
                for attempt in attempts
            ],
            ["not_started", "started_not_finished", "finished"],
        )
        self.assertEqual(
            matched._conservatively_chargeable_provider_calls(attempts), 2
        )

    def test_glean_authentication_clean_failure_is_retryable_zero_model_call(self):
        self._prepare(authenticate=False)

        def fail_after_start(*_args, **kwargs):
            kwargs["invocation_launch_pending"]()
            kwargs["invocation_started"]()
            raise RuntimeError("redacted bootstrap failure")

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials",
                side_effect=fail_after_start,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
        ):
            status = matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        evaluate.assert_not_called()
        self.assertEqual(status["status"], "retryable_failed")
        self.assertEqual(
            status["providers"]["codex"]["status"], "passed"
        )
        self.assertEqual(
            status["providers"]["managed_glean"]["status"],
            "retryable_failed",
        )
        self.assertFalse(
            matched._authentication_receipt_path(self.public_path).exists()
        )
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
        ):
            resumed = matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        codex_bootstrap.assert_not_called()
        self.assertEqual(resumed["status"], "passed")

    def test_codex_clean_failure_leaves_glean_unstarted_and_is_retryable(self):
        self._prepare(authenticate=False)

        def fail_codex(*_args, **_kwargs):
            raise RuntimeError("redacted Codex bootstrap failure")

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials",
                side_effect=fail_codex,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as glean_bootstrap,
        ):
            status = matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        glean_bootstrap.assert_not_called()
        self.assertEqual(status["status"], "retryable_failed")
        self.assertEqual(
            status["providers"]["codex"]["status"], "retryable_failed"
        )
        self.assertEqual(
            status["providers"]["managed_glean"]["status"], "required"
        )
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
        ):
            resumed = matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
        )
        self.assertEqual(resumed["status"], "passed")

    def test_codex_launch_pending_is_terminal_on_isolation_failure(self):
        self._prepare(authenticate=False)

        def fail_after_spawn(*_args, **kwargs):
            kwargs["invocation_launch_pending"]()
            raise ProviderStateIsolationError(
                "redacted pre-start marker failure"
            )

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials",
                side_effect=fail_after_spawn,
            ),
            self.assertRaisesRegex(RuntimeError, "terminal ambiguous"),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        setup = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )["authentication_setup"]
        self.assertEqual(setup["status"], "terminal_failed")
        marker = setup["codex"]["attempts"][-1]
        self.assertEqual(marker["status"], "terminal_failed")
        self.assertIn("launch_pending_at_utc", marker)

    def test_codex_popen_failure_is_terminal_and_records_start_failure(self):
        self._prepare(authenticate=False)

        def fail_to_start(*_args, **kwargs):
            kwargs["invocation_launch_pending"]()
            kwargs["invocation_start_failed"]()
            raise ProviderProcessIsolationError(
                "redacted process start failure"
            )

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials",
                side_effect=fail_to_start,
            ),
            self.assertRaisesRegex(RuntimeError, "terminal ambiguous"),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        marker = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )["authentication_setup"]["codex"]["attempts"][-1]
        self.assertEqual(marker["status"], "terminal_failed")
        self.assertIn("start_failed_at_utc", marker)

    def test_codex_post_return_isolation_failure_is_terminal(self):
        self._prepare(authenticate=False)

        def fail_after_return(*_args, **kwargs):
            kwargs["invocation_launch_pending"]()
            kwargs["invocation_started"]()
            kwargs["invocation_returned"](0)
            raise ProviderStateIsolationError(
                "redacted post-return promotion failure"
            )

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials",
                side_effect=fail_after_return,
            ),
            self.assertRaisesRegex(RuntimeError, "terminal ambiguous"),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        marker = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )["authentication_setup"]["codex"]["attempts"][-1]
        self.assertEqual(marker["status"], "terminal_failed")
        self.assertEqual(marker["returncode"], 0)
        self.assertIn("returned_at_utc", marker)

    def test_successful_authentication_is_durable_and_preflight_never_logs_in(self):
        self._prepare(authenticate=False)
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
        ):
            status = matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        self.assertEqual(status["status"], "passed")
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        for name in ("codex", "managed_glean"):
            marker = private["authentication_setup"][name]["attempts"][-1]
            self.assertEqual(marker["status"], "passed")
            self.assertEqual(marker["returncode"], 0)
            self.assertIn("started_at_utc", marker)
            self.assertIn("returned_at_utc", marker)
        authentication_receipt = matched._load_json(
            matched._authentication_receipt_path(self.public_path)
        )
        public = matched._load_json(self.public_path)
        self.assertEqual(
            set(authentication_receipt),
            {
                "schema_version",
                "panel_id",
                "status",
                "development_only",
                "precommitment_sha256",
                "authentication_contract_hashes",
                "spend_authorization_receipt_sha256",
                "authentication_dependency_identity",
                "authentication_prerequisite",
                "model_calls_started",
                "production_episodes_consumed",
                "scores_reported",
                "receipt_sha256",
            },
        )
        self.assertEqual(
            authentication_receipt["schema_version"],
            "epiagentbench.authentication_receipt.v2",
        )
        self.assertEqual(
            authentication_receipt["panel_id"],
            "development-matched-50x6-v14",
        )
        self.assertEqual(authentication_receipt["status"], "passed")
        self.assertIs(authentication_receipt["development_only"], True)
        self.assertEqual(
            authentication_receipt["precommitment_sha256"],
            public["precommitment_sha256"],
        )
        self.assertEqual(
            authentication_receipt["authentication_contract_hashes"],
            matched._authentication_contract_hashes(public),
        )
        self.assertEqual(
            authentication_receipt["spend_authorization_receipt_sha256"],
            private["spend_authorization"]["receipt_sha256"],
        )
        self.assertEqual(
            authentication_receipt["authentication_prerequisite"],
            {
                "codex": "passed_before_preflight",
                "managed_glean": "passed_before_preflight",
                "codex_method": "pinned_cli_device_auth",
                "managed_glean_method": "pinned_managed_oauth_helper",
                "model_calls": 0,
            },
        )
        self.assertEqual(authentication_receipt["model_calls_started"], 0)
        self.assertEqual(
            authentication_receipt["production_episodes_consumed"], 0
        )
        self.assertIs(authentication_receipt["scores_reported"], False)
        unsigned_receipt = dict(authentication_receipt)
        unsigned_receipt.pop("receipt_sha256")
        self.assertEqual(
            authentication_receipt["receipt_sha256"],
            matched._component_hash(unsigned_receipt),
        )
        dependency = authentication_receipt[
            "authentication_dependency_identity"
        ]
        self.assertEqual(
            dependency["identity_sha256"],
            matched._component_hash(AUTHENTICATION_DEPENDENCY_IDENTITY),
        )
        self.assertEqual(
            set(dependency),
            {
                "schema_version",
                "identity_sha256",
                "root_owned_single_link_regular_executable_policy_attested",
                "exact_bundle_identity_withheld",
                "raw_provider_output_published",
                "raw_machine_paths_published",
            },
        )
        self.assertIs(
            dependency[
                "root_owned_single_link_regular_executable_policy_attested"
            ],
            True,
        )
        self.assertIs(dependency["exact_bundle_identity_withheld"], True)
        self.assertIs(dependency["raw_provider_output_published"], False)
        self.assertIs(dependency["raw_machine_paths_published"], False)
        encoded_dependency = json.dumps(dependency, sort_keys=True).lower()
        self.assertNotIn("/usr/local/", encoded_dependency)
        self.assertNotIn(
            AUTHENTICATION_DEPENDENCY_IDENTITY["glean_helper"]["sha256"],
            encoded_dependency,
        )
        self.assertNotIn(
            AUTHENTICATION_DEPENDENCY_IDENTITY[
                "glean_llm_gateway_token_wrapper"
            ]["target_sha256"],
            encoded_dependency,
        )
        self.assertNotIn("stdout", encoded_dependency)
        self.assertNotIn("stderr", encoded_dependency)
        self.assertNotIn("credential", encoded_dependency)
        encoded_receipt = json.dumps(
            authentication_receipt, sort_keys=True
        ).lower()
        for forbidden in (
            "/usr/local/",
            "/users/",
            "/private/",
            "credentials.json",
            "auth.json",
            "access_token",
            "refresh_token",
            "oauth_state",
            "\"provider_output\":",
            "episode_ref",
            "episode_id",
            "schedule_nonce",
            "trace_steps",
        ):
            self.assertNotIn(forbidden, encoded_receipt)

        preflight_path = self.root / "results" / "preflight-markers.json"
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as glean_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=lambda system, **kwargs: self._result(
                    system,
                    kwargs["model"],
                    kwargs["executable"],
                    0.0,
                ),
            ),
        ):
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )
        codex_bootstrap.assert_not_called()
        glean_bootstrap.assert_not_called()
        self.assertEqual(receipt["status"], "passed")

    def test_tampered_public_dependency_commitment_blocks_preflight(self):
        self._prepare()
        receipt_path = matched._authentication_receipt_path(
            self.public_path
        )
        baseline = matched._load_json(receipt_path)
        mutations = {
            "identity": lambda dependency: dependency.__setitem__(
                "identity_sha256", "sha256:" + "9" * 64
            ),
            "policy": lambda dependency: dependency.__setitem__(
                "root_owned_single_link_regular_executable_policy_attested",
                False,
            ),
        }
        for name, mutate in mutations.items():
            candidate = copy.deepcopy(baseline)
            mutate(candidate["authentication_dependency_identity"])
            unsigned = dict(candidate)
            unsigned.pop("receipt_sha256")
            candidate["receipt_sha256"] = matched._component_hash(unsigned)
            matched._atomic_json(receipt_path, candidate)
            with (
                self.subTest(name=name),
                self._contracts(),
                patch(
                    "epiagentbench.development_matched_panel."
                    "evaluate_local_cli_agent"
                ) as evaluate,
                self.assertRaisesRegex(
                    ValueError, "Public authentication receipt is invalid"
                ),
            ):
                matched.assert_panel_authentication_ready(
                    root=self.root,
                    authentication_key_file=self.key_path,
                    claude_secure_storage_dir=self.claude_secure_storage_dir,
                    codex_secure_storage_dir=self.codex_secure_storage_dir,
                    private_state_path=self.private_path,
                    public_manifest_path=self.public_path,
                    require_clean_checkout=False,
                    revalidate_live_identity_contracts=False,
                )
            evaluate.assert_not_called()
        matched._atomic_json(receipt_path, baseline)

    def test_invalid_authentication_cross_states_cannot_publish(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        public = matched._load_json(self.public_path)
        passed = copy.deepcopy(private["authentication_setup"]["codex"])
        required = {"status": "required", "attempts": []}
        invalid = (
            ("pending_publication", required, required),
            ("pending_publication", passed, required),
            ("passed", passed, required),
            ("required", passed, passed),
            ("running", passed, passed),
            ("retryable_failed", passed, passed),
        )
        for overall, codex, glean in invalid:
            with self.subTest(
                overall=overall,
                codex=codex["status"],
                glean=glean["status"],
            ):
                candidate = copy.deepcopy(private)
                candidate["authentication_setup"]["status"] = overall
                candidate["authentication_setup"]["codex"] = copy.deepcopy(
                    codex
                )
                candidate["authentication_setup"]["managed_glean"] = (
                    copy.deepcopy(glean)
                )
                with self.assertRaises(ValueError):
                    matched._validate_authentication_setup_state(
                        candidate, public
                    )

        receipt_path = matched._authentication_receipt_path(
            self.public_path
        )
        receipt_path.unlink()
        private["authentication_setup"]["status"] = "pending_publication"
        private["authentication_setup"]["codex"] = copy.deepcopy(required)
        private["authentication_setup"]["managed_glean"] = copy.deepcopy(
            required
        )
        with self.assertRaises(ValueError):
            matched._publish_authentication_receipt(
                private=private,
                public=public,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                authentication_key=AUTHENTICATION_KEY,
            )
        self.assertFalse(receipt_path.exists())

    def test_interrupted_authentication_is_terminal_and_idempotent(self):
        public = self._prepare(authenticate=False)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        setup = private["authentication_setup"]
        setup["status"] = "running"
        setup["codex"] = {
            "status": "running",
            "attempts": [
                {
                    "status": "started",
                    "launch_pending_at_utc": "test",
                    "started_at_utc": "test",
                }
            ],
        }
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ) as tty,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            self.assertRaisesRegex(RuntimeError, "ambiguous"),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        tty.assert_not_called()
        codex_bootstrap.assert_not_called()
        terminal = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        matched._validate_authentication_setup_state(terminal, public)
        self.assertEqual(
            terminal["authentication_setup"]["status"],
            "terminal_failed",
        )
        for provider in ("codex", "managed_glean"):
            self.assertEqual(
                terminal["authentication_setup"][provider]["status"],
                "terminal_failed",
            )
            self.assertEqual(
                terminal["authentication_setup"][provider]["attempts"][-1][
                    "status"
                ],
                "terminal_failed",
            )

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            self.assertRaisesRegex(RuntimeError, "terminal"),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        codex_bootstrap.assert_not_called()

    def test_replaced_empty_auth_directory_is_terminal_not_retryable(self):
        self._prepare(authenticate=False)

        def replace_then_fail(path: Path, **_kwargs):
            path.rmdir()
            path.mkdir(mode=0o700)
            raise RuntimeError("redacted authentication failure")

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials",
                side_effect=replace_then_fail,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as glean_bootstrap,
            self.assertRaisesRegex(RuntimeError, "terminal ambiguous"),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        glean_bootstrap.assert_not_called()
        setup = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )["authentication_setup"]
        self.assertEqual(setup["status"], "terminal_failed")
        self.assertEqual(setup["codex"]["status"], "terminal_failed")

    def test_partial_pass_credential_drift_reports_and_persists_terminal(self):
        self._prepare(authenticate=False)
        self._bootstrap_codex_fixture(self.codex_secure_storage_dir)
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        private["codex_auth_file_identity"] = (
            matched._codex_auth_file_identity(
                self.codex_secure_storage_dir
            )
        )
        private["authentication_setup"]["status"] = "required"
        private["authentication_setup"]["codex"] = {
            "status": "passed",
            "attempts": [
                {
                    "status": "passed",
                    "launch_pending_at_utc": "test",
                    "started_at_utc": "test",
                    "returned_at_utc": "test",
                    "returncode": 0,
                    "finished_at_utc": "test",
                }
            ],
        }
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        credential = self.codex_secure_storage_dir / "auth.json"
        credential.unlink()
        credential.write_text('{"test":"replacement"}', encoding="utf-8")
        credential.chmod(0o600)

        with self._contracts():
            status = matched.panel_authentication_status(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )
        self.assertEqual(status["status"], "terminal_failed")
        self.assertEqual(
            status["providers"]["codex"]["status"], "terminal_failed"
        )
        unchanged = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            unchanged["authentication_setup"]["status"], "required"
        )

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ) as tty,
            self.assertRaisesRegex(
                RuntimeError, "terminal credential-integrity"
            ),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        tty.assert_not_called()
        terminal = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            terminal["authentication_setup"]["status"], "terminal_failed"
        )

    def test_keyboard_interrupt_is_always_terminal(self):
        self._prepare(authenticate=False)
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials",
                side_effect=KeyboardInterrupt,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        setup = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )["authentication_setup"]
        self.assertEqual(setup["status"], "terminal_failed")
        self.assertEqual(setup["codex"]["status"], "terminal_failed")

    def test_authentication_receipt_recovers_from_private_pending_crash(self):
        self._prepare(authenticate=False)
        private, public = self._stage_authentication_pending_publication()
        expected = matched._expected_authentication_receipt(private, public)
        setup = private["authentication_setup"]
        setup["pending_public_receipt"] = expected
        setup["public_receipt_path"] = str(
            matched._authentication_receipt_path(
                self.public_path
            ).resolve()
        )
        setup["public_receipt_sha256"] = expected["receipt_sha256"]
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ) as tty,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
        ):
            status = matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        tty.assert_not_called()
        codex_bootstrap.assert_not_called()
        self.assertEqual(status["status"], "passed")
        self.assertEqual(
            matched._load_json(
                matched._authentication_receipt_path(self.public_path)
            ),
            expected,
        )

    def test_authentication_receipt_recovers_after_public_write_crash(self):
        self._prepare(authenticate=False)
        private, public = self._stage_authentication_pending_publication()
        expected = matched._expected_authentication_receipt(private, public)
        setup = private["authentication_setup"]
        setup["pending_public_receipt"] = expected
        setup["public_receipt_path"] = str(
            matched._authentication_receipt_path(
                self.public_path
            ).resolve()
        )
        setup["public_receipt_sha256"] = expected["receipt_sha256"]
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        matched._create_public_json_once(
            matched._authentication_receipt_path(self.public_path),
            expected,
        )

        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ) as tty,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
        ):
            status = matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        tty.assert_not_called()
        codex_bootstrap.assert_not_called()
        self.assertEqual(status["status"], "passed")
        final = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(
            final["authentication_setup"]["status"], "passed"
        )

    def test_authentication_receipt_publication_never_clobbers(self):
        self._prepare(authenticate=False)
        private, public = self._stage_authentication_pending_publication()
        receipt_path = matched._authentication_receipt_path(self.public_path)
        original = b'{"schema_version":"foreign"}\n'

        def race_create(
            _source: Path,
            destination: Path,
            *,
            follow_symlinks: bool,
        ) -> None:
            self.assertFalse(follow_symlinks)
            Path(destination).write_bytes(original)
            raise FileExistsError

        with (
            patch(
                "epiagentbench.development_matched_panel.os.link",
                side_effect=race_create,
            ),
            self.assertRaises(ValueError),
        ):
            matched._publish_authentication_receipt(
                private=private,
                public=public,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                authentication_key=AUTHENTICATION_KEY,
            )
        self.assertEqual(receipt_path.read_bytes(), original)

    def test_authentication_requires_tty_without_state_or_provider_call(self):
        self._prepare(authenticate=False)
        before = self.private_path.read_bytes()
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty",
                side_effect=RuntimeError("foreground operator TTY"),
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as glean_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
            self.assertRaisesRegex(RuntimeError, "operator TTY"),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        codex_bootstrap.assert_not_called()
        glean_bootstrap.assert_not_called()
        evaluate.assert_not_called()
        self.assertEqual(self.private_path.read_bytes(), before)
        self.assertFalse(
            matched._authentication_receipt_path(self.public_path).exists()
        )

    def test_authentication_requires_spend_before_tty_or_provider_call(self):
        self._prepare(authorize=False, authenticate=False)
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ) as tty,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as glean_bootstrap,
            self.assertRaisesRegex(RuntimeError, "manifest-bound exact v14"),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        tty.assert_not_called()
        codex_bootstrap.assert_not_called()
        glean_bootstrap.assert_not_called()

    def test_glean_dependency_drift_blocks_authentication_before_tty(self):
        self._prepare(authenticate=False)
        drifted = copy.deepcopy(AUTHENTICATION_DEPENDENCY_IDENTITY)
        drifted["glean_helper"]["sha256"] = "sha256:" + "9" * 64
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_current_glean_auth_dependency_identity",
                return_value=drifted,
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ) as tty,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as glean_bootstrap,
            self.assertRaisesRegex(
                ProviderStateIsolationError,
                "Frozen Glean authentication dependencies drifted",
            ),
        ):
            matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        tty.assert_not_called()
        codex_bootstrap.assert_not_called()
        glean_bootstrap.assert_not_called()
        self.assertFalse(
            matched._authentication_receipt_path(self.public_path).exists()
        )

    def test_authentication_does_not_read_hidden_packs_or_leak_metadata(self):
        self._prepare(authenticate=False)
        with (
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel."
                "_require_operator_authentication_tty"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "PrivateEpisodePack.read",
                side_effect=AssertionError(
                    "authentication must not open hidden packs"
                ),
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
        ):
            status = matched.authenticate_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                acknowledge_interactive_authentication=True,
            )
        evaluate.assert_not_called()
        self.assertEqual(status["status"], "passed")
        receipt = matched._load_json(
            matched._authentication_receipt_path(self.public_path)
        )
        serialized = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(str(self.private_path), serialized)
        self.assertNotIn(str(self.claude_secure_storage_dir), serialized)
        self.assertNotIn(str(self.codex_secure_storage_dir), serialized)
        self.assertNotIn("episode_", serialized)
        self.assertNotIn("schedule", serialized)
        self.assertEqual(receipt["model_calls_started"], 0)
        self.assertEqual(receipt["production_episodes_consumed"], 0)
        self.assertFalse(receipt["scores_reported"])

    def test_disposable_preflight_after_call_drift_fails_closed(self):
        self._prepare()
        after_path = self.root / "results" / "preflight-after.json"

        def evaluate_once(system: str, **kwargs):
            if system == "claude":
                self.keychain_present = True
            return self._result(
                system, kwargs["model"], kwargs["executable"], 50.0
            )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "_attest_execution_contracts",
                side_effect=(
                    None,
                    RuntimeError("mid-call drift"),
                ),
            ),
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent",
                side_effect=evaluate_once,
            ) as evaluate,
        ):
            after_receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=after_path,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(after_receipt["status"], "failed")
        self.assertEqual(
            after_receipt["failure_stage"],
            "execution_contract_after_harness",
        )
        self.assertEqual(
            after_receipt["failed_provider_invocation_state"], "finished"
        )
        self.assertEqual(
            after_receipt["provider_calls_conservatively_chargeable"], 1
        )

    def test_disposable_preflight_requires_cursor_key_before_any_call(self):
        self._prepare()
        with patch.dict(os.environ, {}, clear=True), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
        ) as evaluate, self.assertRaisesRegex(RuntimeError, "requires CURSOR_API_KEY"):
            run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=self.root / "results" / "preflight.json",
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()

    def test_plaintext_fallback_stops_preflight_before_one_shot_state(self):
        self._prepare()
        fallback = self.claude_secure_storage_dir / ".credentials.json"
        fallback.write_text('{"token":"test-only"}', encoding="utf-8")
        preflight_path = self.root / "results" / "preflight.json"
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
            ) as evaluate,
            self.assertRaisesRegex(RuntimeError, "plaintext credential fallback"),
        ):
            run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["environment_preflight"]["status"], "required")
        self.assertFalse(preflight_path.exists())

    def test_failed_disposable_preflight_is_one_shot(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight.json"
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=RuntimeError("credential exchange failed"),
            ),
        ):
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failure_stage"], "provider_launch")
        self.assertEqual(
            receipt["failed_provider_invocation_state"],
            "started_not_finished",
        )
        self.assertEqual(
            receipt["provider_calls_conservatively_chargeable"], 1
        )

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
            ) as evaluate,
            self.assertRaisesRegex(RuntimeError, "one-shot required state"),
        ):
            run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()

    def test_running_preflight_with_started_provider_invocation_is_one_shot(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight-running.json"
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        required_hashes = private["environment_preflight"][
            "required_contract_hashes"
        ]
        private["environment_preflight"] = {
            "status": "running",
            "started_at_utc": "test-preflight-start",
            "required_contract_hashes": required_hashes,
            "managed_glean_auth_bootstrap": {"status": "passed"},
            "codex_auth_bootstrap": {"status": "passed"},
            "attempts": [
                {
                    "profile_id": PROFILES[0]["profile_id"],
                    "status": "started",
                    "started_at_utc": "test-attempt-start",
                    "provider_invocation": {
                        "status": "started",
                        "started_at_utc": "test-provider-start",
                    },
                }
            ],
        }
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        checkpoint = self.private_path.read_bytes()

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch(
                "epiagentbench.development_matched_panel._preflight_execution"
            ) as preflight_execution,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_managed_glean_credentials"
            ) as glean_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "_bootstrap_codex_credentials"
            ) as codex_bootstrap,
            patch(
                "epiagentbench.development_matched_panel."
                "evaluate_local_cli_agent"
            ) as evaluate,
        ):
            for _attempt in range(2):
                with self.assertRaisesRegex(
                    RuntimeError, "one-shot required state"
                ):
                    run_environment_preflight(
                        root=self.root,
                        authentication_key_file=self.key_path,
                        claude_secure_storage_dir=self.claude_secure_storage_dir,
                        codex_secure_storage_dir=self.codex_secure_storage_dir,
                        private_state_path=self.private_path,
                        public_manifest_path=self.public_path,
                        public_preflight_path=preflight_path,
                        acknowledge_unbounded_provider_spend=True,
                    )
        preflight_execution.assert_not_called()
        glean_bootstrap.assert_not_called()
        codex_bootstrap.assert_not_called()
        evaluate.assert_not_called()
        self.assertEqual(self.private_path.read_bytes(), checkpoint)
        self.assertFalse(preflight_path.exists())

    def test_exclusive_runner_lock_rejects_concurrent_invocation(self):
        copied_state_path = self.root / "run_artifacts" / "copied-private.json"
        with matched._exclusive_run_lock(self.private_path), self.assertRaisesRegex(
            RuntimeError, "already holds the lock"
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=copied_state_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )

    def test_prepare_rejects_aliased_private_and_public_paths(self):
        manifest = self._cohort()
        with self._contracts(), self.assertRaisesRegex(ValueError, "must be distinct"):
            prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.private_path,
            )

    def test_partial_state_cannot_claim_completion(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        private["status"] = "complete"
        private["assignments"] = [
            {
                "episode_ref": private["schedule"][0]["episode_ref"],
                "profile_id": private["schedule"][0]["profile_order"][0],
                "status": "transport_void",
                "started_at_utc": "start",
                "finished_at_utc": "finish",
            }
        ]
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        with self._contracts(), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
        ) as evaluate, self.assertRaisesRegex(ValueError, "not fully terminal"):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_secure_storage_dir,
                codex_secure_storage_dir=self.codex_secure_storage_dir,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()

    def test_terminal_artifact_reveals_verifiable_schedule_and_family_map(self):
        self._prepare()

        def evaluate(system: str, **kwargs):
            return self._result(system, kwargs["model"], kwargs["executable"], 50.0)

        payload, _ = self._run_with(evaluate)
        public = matched._load_json(self.public_path)
        matched.verify_revealed_commitments(public, payload)
        payload["schedule"][0]["profile_order"] = list(
            reversed(payload["schedule"][0]["profile_order"])
        )
        with self.assertRaisesRegex(ValueError, "schedule"):
            matched.verify_revealed_commitments(public, payload)


if __name__ == "__main__":
    unittest.main()
