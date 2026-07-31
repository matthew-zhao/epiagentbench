from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import unittest


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _load_json_without_duplicate_keys(raw: bytes) -> object:
    return json.loads(raw, object_pairs_hook=_object_without_duplicate_keys)


class V26SupersessionTests(unittest.TestCase):
    CONTROL_COMMIT = "8c0aa9e29d57b3085604edcbaf08d52a50e2d490"
    RUNTIME_COMMIT = "fd9404abf7580398cc0328797c2a56f641890449"
    MANIFEST_COMMIT = "187973ba14f97568d709658ef96a4ae1237534f1"
    AUTHENTICATION_COMMIT = "e8f0b606af9f821e7da090083b3e772ad832dc79"
    PUBLIC_ARTIFACTS = {
        "results/development-matched-50x6-v26.runtime.json": (
            "runtime_receipt_file_sha256",
            "sha256:da05a9a4b5858aa7b1f404eb43a8ed49c2312822b499239fa61b36a316ab2866",
        ),
        "results/development-matched-50x6-v26.manifest.json": (
            "manifest_file_sha256",
            "sha256:3bb9bdcf2a6da679f1d1ba9c36c1bd33cbe01f70ca74e6a223c00e845df0da7a",
        ),
        "results/development-matched-50x6-v26.authentication.json": (
            "authentication_receipt_file_sha256",
            "sha256:605ba3c670fefd1d3dd075b80808a84373e28ab3aa512492fa3604000a4e4510",
        ),
    }
    PINNED_FILES = {
        "docs/V26_RUNBOOK.md": (
            "published_runbook_sha256",
            "sha256:43f2e4ad10bed9a8dfc5aae74c697b0e2768d26112dc4c6247abee56e785cf0f",
        ),
        "docs/PERSISTENT_RUNNER_PROTOCOL.md": (
            "published_protocol_sha256",
            "sha256:6196f1cb772beff40743d8a6d2cf9e6e7a50f3556228ee82d58606c9d90779a1",
        ),
        "src/epiagentbench/development_matched_panel.py": (
            "published_matched_panel_source_sha256",
            "sha256:6fd78b13daac9330a32ccaa25716329cc38b1525905cdf00ca8c7251b4ffb811",
        ),
        "src/epiagentbench/launchd_agent.py": (
            "published_launchd_source_sha256",
            "sha256:ba3fc3fd7e24b23f8510a46be96cccbd0a389a7eeabba17948243b0cc77c58c5",
        ),
        "src/epiagentbench/persistent_supervisor.py": (
            "published_persistent_supervisor_source_sha256",
            "sha256:54bc1d740889ea43b4a4d1a74dd0cc51cd4baddf7b8cb3c74a9e710c10aea1b0",
        ),
        "src/epiagentbench/provider_cli_environment.py": (
            "published_provider_cli_environment_source_sha256",
            "sha256:e0b8adaa6a44ef6c763ace75fa0e17b2d3b7c9636c63cdac4d67b0058cb8281c",
        ),
        "examples/run_development_matched_panel.py": (
            "published_entrypoint_sha256",
            "sha256:48f29a081d5f1b8e4feef9394a8aeb03c730472f3344e6e6ab40979c2396ca09",
        ),
        "examples/run_persistent_panel_supervisor.py": (
            "published_launchd_entrypoint_sha256",
            "sha256:4b55a63936bb914cbc692ab7840367a750a2161d5de9c7e9e639c8b9f6979270",
        ),
        "pyproject.toml": (
            "published_pyproject_sha256",
            "sha256:a5f691b5e92e285dff9429773133c619425cdfa73f741414a05d3b96fb227014",
        ),
    }
    COMMIT_BINDINGS = {
        "control": (
            CONTROL_COMMIT,
            "5ba7585cbc6568eeaaa5a2c9126b6879428e0478",
            "a702c5f428997d6e9ea6f4c97bb1d3dadd244aee",
        ),
        "runtime_receipt": (
            RUNTIME_COMMIT,
            CONTROL_COMMIT,
            "5ae171eb14eced90babe0566deaeb9aa1cd6cd71",
        ),
        "manifest": (
            MANIFEST_COMMIT,
            RUNTIME_COMMIT,
            "ee845d4a13721f7da9865404af96cd1bc339790a",
        ),
        "authentication_receipt": (
            AUTHENTICATION_COMMIT,
            MANIFEST_COMMIT,
            "cc2187a0a54b5dbb7827b8b30143825359aff2d4",
        ),
    }
    V27_ACKNOWLEDGEMENT = (
        "I acknowledge the replacement six-call v27 preflight and "
        "300-assignment production run, including unbounded Codex/Cursor "
        "provider spend and up to $610 total Claude spend across the failed "
        "v2 preflight, failed v5 preflight, failed v6 authentication "
        "bootstrap, failed v7 preflight, failed v8 production run, v9 "
        "preflight and failed production run, the abandoned zero-model-call "
        "v10 precommitment, the failed zero-model-call v11 authentication "
        "bootstrap, the abandoned zero-model-call v12 precommitment, the "
        "abandoned zero-model-call v13 precommitment, the failed v14 "
        "preflight, the failed zero-model-call v15 pre-claim preparation, "
        "the failed v16 preflight, the failed zero-model-call v17 pre-start "
        "runtime-cache-environment refusal, the failed v18 preflight, the "
        "failed zero-model-call v19 authentication setup, the failed "
        "zero-model-call v20 preflight, the failed zero-model-call v21 "
        "preflight, the failed zero-model-call v22 interrupted "
        "authentication ceremony, the failed v23 six-call preflight release "
        "validation, the abandoned zero-model-call v24 control-plane "
        "precommitment, the failed zero-model-call v25 provider-free "
        "preparation-runtime CLI discovery, the failed v26 preflight with "
        "indeterminate provider-call count and a conservative $10 Claude "
        "allowance, and the v27 preflight and production run."
    )
    V27_ACKNOWLEDGEMENT_SHA256 = (
        "sha256:47c3e8d7eb79a574acffaf6f480b84fe8f44494775af994d4b1d40b3752f59f4"
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.supersession = cls._read(
            "results/development-matched-50x6-v26.superseded.json"
        )
        cls.runtime = cls._read(
            "results/development-matched-50x6-v26.runtime.json"
        )
        cls.manifest = cls._read(
            "results/development-matched-50x6-v26.manifest.json"
        )
        cls.authentication = cls._read(
            "results/development-matched-50x6-v26.authentication.json"
        )

    @classmethod
    def _read(cls, relative: str) -> dict[str, object]:
        payload = _load_json_without_duplicate_keys(
            (cls.root / relative).read_bytes()
        )
        if not isinstance(payload, dict):
            raise TypeError(f"{relative} must contain a JSON object")
        return payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V26SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V26SupersessionTests._keys(value))
        return observed

    def _git_show_bytes(self, relative: str) -> bytes:
        return subprocess.run(
            ["git", "show", f"{self.CONTROL_COMMIT}:{relative}"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout

    def test_duplicate_json_object_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError, r"duplicate JSON object key: status"
        ):
            _load_json_without_duplicate_keys(
                b'{"status":"first","status":"second"}'
            )

    def test_exact_v26_commit_chain_and_public_bytes_are_bound(self) -> None:
        for prefix, (commit, parent, tree) in self.COMMIT_BINDINGS.items():
            observed = subprocess.run(
                ["git", "show", "-s", "--format=%H %P %T", commit],
                cwd=self.root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            self.assertEqual(observed, f"{commit} {parent} {tree}")
            self.assertEqual(self.supersession[f"{prefix}_commit"], commit)
            self.assertEqual(
                self.supersession[f"{prefix}_parent_commit"], parent
            )
            self.assertEqual(self.supersession[f"{prefix}_tree"], tree)
        for relative, (field, expected) in self.PUBLIC_ARTIFACTS.items():
            observed = "sha256:" + hashlib.sha256(
                (self.root / relative).read_bytes()
            ).hexdigest()
            self.assertEqual(observed, expected)
            self.assertEqual(self.supersession[field], expected)

    def test_exact_published_v26_source_surface_is_bound(self) -> None:
        for relative, (field, expected) in self.PINNED_FILES.items():
            observed = "sha256:" + hashlib.sha256(
                self._git_show_bytes(relative)
            ).hexdigest()
            self.assertEqual(observed, expected)
            self.assertEqual(self.supersession[field], expected)

    def test_public_receipt_internal_bindings_are_exact(self) -> None:
        self.assertEqual(
            self.runtime["schema_version"],
            "epiagentbench.preparation_runtime_preflight.v4",
        )
        self.assertEqual(self.runtime["status"], "passed")
        self.assertEqual(
            self.runtime["runtime_identity_sha256"],
            self.supersession["runtime_receipt_identity_sha256"],
        )
        self.assertEqual(
            self.manifest["schema_version"], "development_matched_panel_v26"
        )
        self.assertEqual(self.manifest["status"], "precommitted")
        self.assertEqual(
            self.manifest["precommitment_sha256"],
            self.supersession["manifest_precommitment_sha256"],
        )
        self.assertEqual(
            self.authentication["schema_version"],
            "epiagentbench.authentication_receipt.v2",
        )
        self.assertEqual(self.authentication["status"], "passed")
        self.assertEqual(
            self.authentication["receipt_sha256"],
            self.supersession["authentication_receipt_self_sha256"],
        )
        self.assertEqual(self.authentication["model_calls_started"], 0)
        self.assertEqual(
            self.authentication["production_episodes_consumed"], 0
        )
        self.assertIs(self.authentication["scores_reported"], False)

    def test_terminal_accounting_is_bounded_but_never_falsely_exact(
        self,
    ) -> None:
        self.assertEqual(
            self.supersession["schema_version"],
            "epiagentbench.panel_supersession.v18",
        )
        self.assertEqual(
            self.supersession["status"],
            "failed_preflight_terminal_candidate_missing_or_invalid",
        )
        self.assertIs(
            self.supersession["exact_provider_or_model_call_count_known"],
            False,
        )
        self.assertEqual(
            self.supersession[
                "model_bearing_provider_call_exposure_upper_bound"
            ],
            {"claude": 2, "codex": 2, "cursor": 2, "total": 6},
        )
        self.assertEqual(
            self.supersession[
                "model_bearing_provider_calls_"
                "conservatively_chargeable_upper_bound"
            ],
            6,
        )
        self.assertEqual(
            self.supersession["v26_conservative_claude_ceiling_added_usd"],
            10.0,
        )
        self.assertIs(
            self.supersession["supervisor_started_exactly_once"], True
        )
        self.assertEqual(
            self.supersession["supervised_child_exit_class"], "nonzero"
        )
        self.assertIs(
            self.supersession["terminal_preflight_candidate_valid"], False
        )
        for field in (
            "production_assignments_started",
            "production_episodes_consumed",
            "provider_free_reconciliation_authentication_processes_started",
            "provider_free_reconciliation_model_calls_started",
            "provider_free_reconciliation_provider_processes_started",
        ):
            self.assertEqual(self.supersession[field], 0)
        for field in (
            "public_preflight_receipt_created",
            "public_results_artifact_created",
            "resumption_permitted",
            "results_released",
            "scores_released",
            "traces_released",
            "v26_identifier_or_namespace_reuse_permitted",
        ):
            self.assertIs(self.supersession[field], False)
        self.assertEqual(
            self.supersession["provider_free_reconciliation_result"],
            "refused_invalid_terminal_candidate",
        )
        self.assertFalse(
            (
                self.root
                / "results/development-matched-50x6-v26.preflight.json"
            ).exists()
        )
        self.assertFalse(
            (self.root / "results/development-matched-50x6-v26.json").exists()
        )

    def test_v27_runbook_has_exact_replacement_contract(self) -> None:
        runbook = (self.root / "docs/V27_RUNBOOK.md").read_text()
        for required in (
            "development-matched-50x6-v27",
            "development_matched_panel_v27",
            "epiagentbench.persistent_supervisor.v3",
            "epiagentbench.persistent_supervisor_contract.v12",
            "epiagentbench.launchd_worker_status.v6",
            "persistent-supervisor-v8",
            "epiagentbench.launchd_agent.v14",
            "epiagentbench.preflight_incident_envelope.v1",
            "epiagentbench.terminal_audit.v1",
            "exit `65`",
            "$610 ($510 + $100)",
            self.V27_ACKNOWLEDGEMENT,
            self.V27_ACKNOWLEDGEMENT_SHA256,
        ):
            self.assertIn(required, runbook)
        observed = "sha256:" + hashlib.sha256(
            self.V27_ACKNOWLEDGEMENT.encode("utf-8")
        ).hexdigest()
        self.assertEqual(observed, self.V27_ACKNOWLEDGEMENT_SHA256)
        self.assertEqual(
            self.supersession[
                "required_v27_spend_acknowledgement_text_sha256"
            ],
            self.V27_ACKNOWLEDGEMENT_SHA256,
        )

    def test_v26_runbook_is_terminal_and_points_to_v27(self) -> None:
        runbook = (self.root / "docs/V26_RUNBOOK.md").read_text()
        warning = runbook.split("> [!CAUTION]", 1)[0]
        for required in (
            "TERMINAL, NON-RESUMABLE PREFLIGHT FAILURE",
            "DO NOT EXECUTE THIS RUNBOOK",
            "indeterminate",
            "$10 Claude allowance",
            "development-matched-50x6-v26.superseded.json",
            "V27_RUNBOOK.md",
        ):
            self.assertIn(required, warning)

    def test_supersession_is_utc_and_contains_no_sensitive_payload(self) -> None:
        superseded_at = datetime.fromisoformat(
            str(self.supersession["superseded_at_utc"]).replace(
                "Z", "+00:00"
            )
        )
        prepared_at = datetime.fromisoformat(
            str(self.manifest["prepared_at_utc"]).replace("Z", "+00:00")
        )
        self.assertEqual(superseded_at.tzinfo, timezone.utc)
        self.assertGreater(superseded_at, prepared_at)
        serialized = json.dumps(
            self.supersession, sort_keys=True, separators=(",", ":")
        ).lower()
        for forbidden in (
            "/users/",
            "access_token",
            "api_key",
            "device_code",
            "episode_id",
            "episode_ref",
            "oauth_state",
            "private_seed",
            '"prompt"',
            '"observation"',
            '"trace"',
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertNotIn("exception_text", self._keys(self.supersession))


if __name__ == "__main__":
    unittest.main()
