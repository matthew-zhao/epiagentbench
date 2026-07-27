from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import unittest


class V14SupersessionTests(unittest.TestCase):
    MANIFEST_FILE_SHA256 = (
        "sha256:e9617f782b16ee814b65523729b7b17ad237ac71ab37bcb44fe9f913227895ae"
    )
    MANIFEST_GIT_COMMIT = "a5ea99f14bf51f80bb2c3633a8eb8bcf77b908c0"
    SOURCE_COMMIT = "fa08d6f9ef67dc04cf80ef5f315812777208e651"
    PRECOMMITMENT_SHA256 = (
        "sha256:c1e9aae32fd3193a773f93a99852f4f79f099e34efe17cccd405bf71c1c277b5"
    )
    AUTHENTICATION_FILE_SHA256 = (
        "sha256:23d5a3eea46ea8fa837a2b439557e9110997e7bcaebda026445c264777c2b4b6"
    )
    AUTHENTICATION_GIT_COMMIT = "ed3b62875ae263f0169395c5d02c9b11892df413"
    AUTHENTICATION_RECEIPT_SHA256 = (
        "sha256:ec77e0071f695ea1018f1f0dbbf177006f054d4ffadc6cee79ab941eb08b3c90"
    )
    SPEND_AUTHORIZATION_RECEIPT_SHA256 = (
        "sha256:b2afff85c743786490ce00d177fe88f100a53916b336b14950441bf8ab5e50d3"
    )
    SPEND_ACKNOWLEDGEMENT_SHA256 = (
        "sha256:683f601da2ab4da4039f448e0755cdc405fc6929492ee62c184c1c19ee89ecbf"
    )
    PREFLIGHT_FILE_SHA256 = (
        "sha256:43453c89623b6c6a41e8629deca062653c77acb3ec282797270d9c0b12e8bef3"
    )
    PREFLIGHT_CANONICAL_SHA256 = (
        "sha256:f7a64034fe62fe40c80b81ec3ecf06bcc91e4424ed95816a5474ee849a93a772"
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.results = cls.root / "results"
        cls.manifest_path = (
            cls.results / "development-matched-50x6-v14.manifest.json"
        )
        cls.authentication_path = (
            cls.results / "development-matched-50x6-v14.authentication.json"
        )
        cls.preflight_path = (
            cls.results / "development-matched-50x6-v14.preflight.json"
        )
        cls.superseded_path = (
            cls.results / "development-matched-50x6-v14.superseded.json"
        )
        cls.manifest = json.loads(cls.manifest_path.read_bytes())
        cls.authentication = json.loads(cls.authentication_path.read_bytes())
        cls.preflight = json.loads(cls.preflight_path.read_bytes())
        cls.superseded = json.loads(cls.superseded_path.read_bytes())

    @staticmethod
    def _file_sha256(path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _canonical_sha256(payload: Mapping[str, object]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V14SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V14SupersessionTests._keys(value))
        return observed

    def test_supersession_has_a_closed_public_schema(self) -> None:
        self.assertEqual(
            set(self.superseded),
            {
                "audited_root_cause_code",
                "authentication_receipt_file_sha256",
                "authentication_receipt_git_commit",
                "authentication_receipt_sha256",
                "cohort_retired",
                "development_only",
                "failure_stage",
                "model_bearing_provider_call_exposure",
                "model_bearing_provider_calls_conservatively_chargeable",
                "original_manifest_file_sha256",
                "original_manifest_git_commit",
                "original_panel_id",
                "original_precommitment_sha256",
                "original_source_commit",
                "preflight_profile_states",
                "preflight_profiles_attempted",
                "preflight_profiles_passed",
                "production_assignments_started",
                "public_authentication_receipt_created",
                "public_results_artifact_created",
                "public_stopped_preflight_artifact_canonical_sha256",
                "public_stopped_preflight_artifact_created",
                "public_stopped_preflight_artifact_file_sha256",
                "replacement_panel_id",
                "replacement_requirements",
                "results_released",
                "resumption_permitted",
                "required_spend_acknowledgement_text_sha256",
                "schema_version",
                "scores_released",
                "spend_acknowledgement_supplied",
                "spend_authorization_recorded",
                "spend_authorization_receipt_sha256",
                "status",
                "superseded_at_utc",
                "supervisor_terminal_failure_code",
                "traces_released",
                "v14_cohort_reuse_permitted",
            },
        )
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v6",
        )
        self.assertRegex(
            self.superseded["superseded_at_utc"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )

    def test_supersession_binds_every_frozen_public_v14_artifact(self) -> None:
        self.assertEqual(
            self._file_sha256(self.manifest_path),
            self.MANIFEST_FILE_SHA256,
        )
        self.assertEqual(
            self.superseded["original_manifest_file_sha256"],
            self.MANIFEST_FILE_SHA256,
        )
        self.assertEqual(
            self.superseded["original_manifest_git_commit"],
            self.MANIFEST_GIT_COMMIT,
        )
        self.assertEqual(
            self.manifest["benchmark_base_commit"], self.SOURCE_COMMIT
        )
        self.assertEqual(
            self.superseded["original_source_commit"], self.SOURCE_COMMIT
        )
        self.assertEqual(
            self.manifest["precommitment_sha256"], self.PRECOMMITMENT_SHA256
        )
        self.assertEqual(
            self.superseded["original_precommitment_sha256"],
            self.PRECOMMITMENT_SHA256,
        )
        self.assertEqual(
            self._file_sha256(self.authentication_path),
            self.AUTHENTICATION_FILE_SHA256,
        )
        self.assertEqual(
            self.superseded["authentication_receipt_file_sha256"],
            self.AUTHENTICATION_FILE_SHA256,
        )
        self.assertEqual(
            self.superseded["authentication_receipt_git_commit"],
            self.AUTHENTICATION_GIT_COMMIT,
        )
        self.assertEqual(
            self.authentication["receipt_sha256"],
            self.AUTHENTICATION_RECEIPT_SHA256,
        )
        self.assertEqual(
            self.superseded["authentication_receipt_sha256"],
            self.AUTHENTICATION_RECEIPT_SHA256,
        )
        self.assertEqual(
            self.authentication["spend_authorization_receipt_sha256"],
            self.SPEND_AUTHORIZATION_RECEIPT_SHA256,
        )
        self.assertEqual(
            self.superseded["spend_authorization_receipt_sha256"],
            self.SPEND_AUTHORIZATION_RECEIPT_SHA256,
        )
        self.assertEqual(
            self.manifest["run_contract"]["spend_authorization"][
                "required_acknowledgement_text_sha256"
            ],
            self.SPEND_ACKNOWLEDGEMENT_SHA256,
        )
        self.assertEqual(
            self.superseded["required_spend_acknowledgement_text_sha256"],
            self.SPEND_ACKNOWLEDGEMENT_SHA256,
        )
        self.assertEqual(
            self._file_sha256(self.preflight_path),
            self.PREFLIGHT_FILE_SHA256,
        )
        self.assertEqual(
            self.superseded["public_stopped_preflight_artifact_file_sha256"],
            self.PREFLIGHT_FILE_SHA256,
        )
        self.assertEqual(
            self._canonical_sha256(self.preflight),
            self.PREFLIGHT_CANONICAL_SHA256,
        )
        self.assertEqual(
            self.superseded[
                "public_stopped_preflight_artifact_canonical_sha256"
            ],
            self.PREFLIGHT_CANONICAL_SHA256,
        )
        for payload in (
            self.manifest,
            self.authentication,
            self.preflight,
        ):
            self.assertEqual(
                payload["panel_id"], "development-matched-50x6-v14"
            )
            self.assertEqual(
                payload["precommitment_sha256"],
                self.PRECOMMITMENT_SHA256,
            )
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v15",
        )

    def test_stopped_preflight_projection_matches_the_supersession(self) -> None:
        profiles = self.preflight["profiles"]
        attempted = [
            profile
            for profile in profiles
            if profile["invocation_state"] == "finished"
        ]
        passed = [
            profile for profile in profiles if profile["outcome"] == "passed"
        ]
        exposure = {"claude": 0, "codex": 0, "cursor": 0, "total": 0}
        for profile in attempted:
            exposure[profile["system"]] += 1
            exposure["total"] += 1

        self.assertEqual(self.preflight["status"], "failed")
        self.assertEqual(self.preflight["failure_reason"], "terminal_abort")
        self.assertEqual(
            self.preflight["failure_stage"],
            "execution_contract_after_harness",
        )
        self.assertEqual(
            self.preflight["provider_calls_conservatively_chargeable"], 3
        )
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"], exposure
        )
        self.assertEqual(
            self.superseded[
                "model_bearing_provider_calls_conservatively_chargeable"
            ],
            3,
        )
        self.assertEqual(
            self.superseded["preflight_profiles_attempted"], len(attempted)
        )
        self.assertEqual(
            self.superseded["preflight_profiles_passed"], len(passed)
        )
        self.assertEqual(
            self.superseded["preflight_profile_states"],
            {"finished": 3, "not_started": 3},
        )
        self.assertEqual(
            self.superseded["audited_root_cause_code"],
            "status_snapshot_unstable",
        )
        self.assertEqual(
            self.superseded["supervisor_terminal_failure_code"],
            "runner_nonzero_exit",
        )

    def test_v14_cannot_resume_reuse_release_or_leak(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_preflight_terminal_attestation",
        )
        self.assertIs(self.superseded["development_only"], True)
        self.assertIs(self.superseded["spend_acknowledgement_supplied"], True)
        self.assertIs(self.superseded["spend_authorization_recorded"], True)
        self.assertIs(
            self.superseded["public_authentication_receipt_created"], True
        )
        self.assertIs(
            self.superseded["public_stopped_preflight_artifact_created"], True
        )
        self.assertEqual(self.superseded["production_assignments_started"], 0)
        self.assertIs(self.superseded["cohort_retired"], False)
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(self.superseded["v14_cohort_reuse_permitted"], False)
        self.assertIs(self.superseded["results_released"], False)
        self.assertIs(self.superseded["scores_released"], False)
        self.assertIs(self.superseded["traces_released"], False)
        self.assertIs(self.superseded["public_results_artifact_created"], False)

        forbidden_keys = {
            "access_token",
            "api_key",
            "credential",
            "credential_contents",
            "episode_id",
            "family",
            "oauth_state",
            "observation",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_stderr",
            "raw_stdout",
            "refresh_token",
            "schedule_nonce",
            "score",
            "stderr",
            "stdout",
            "trace",
            "trace_steps",
        }
        self.assertTrue(forbidden_keys.isdisjoint(self._keys(self.superseded)))
        self.assertTrue(forbidden_keys.isdisjoint(self._keys(self.preflight)))
        for payload in (self.superseded, self.preflight):
            encoded = json.dumps(payload, sort_keys=True).lower()
            for forbidden in (
                "/users/",
                "/private/",
                "credentials.json",
                "auth.json",
                "access_token",
                "refresh_token",
                "oauth_state",
                "provider_output",
                "raw_stdout",
                "raw_stderr",
                "trace_steps",
            ):
                self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
