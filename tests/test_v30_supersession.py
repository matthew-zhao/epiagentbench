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


class V30SupersessionTests(unittest.TestCase):
    CONTROL_COMMIT = "c8d2ee2cff076e3311898073ceec6ee73f527a9b"
    RUNTIME_COMMIT = "7cbce20bef4d349678cc3cd592a1d98ff152f11a"
    MANIFEST_COMMIT = "ea959876868f51ae979287a77d93d57a6cc5b79e"
    AUTHENTICATION_COMMIT = (
        "ba25bab441f7cc28f56e4668006f12821949a0e4"
    )
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v30.superseded.json"
    )
    COMMIT_BINDINGS = {
        "control": (
            CONTROL_COMMIT,
            "4491e38afe05cfd0bdb4b7c030633ee4be8121e7",
            "286f7f914caabfd7af301ce160aa7569e6394e01",
        ),
        "runtime_receipt": (
            RUNTIME_COMMIT,
            CONTROL_COMMIT,
            "ce3b4ead732b832e8e66f1528a066b95e36212f0",
        ),
        "manifest": (
            MANIFEST_COMMIT,
            RUNTIME_COMMIT,
            "3a7f264f21ef3960822fe2678ecc9e1182685a6f",
        ),
        "authentication_receipt": (
            AUTHENTICATION_COMMIT,
            MANIFEST_COMMIT,
            "f773e5aad3d02cf24752c77381c2d55b45aa4f89",
        ),
    }
    PUBLIC_FILE_HASHES = {
        "results/development-matched-50x6-v30.runtime.json": (
            "sha256:2ff4d2bf4893f1a9c927553130a771868e4386a333f4e751ec04975636703e4d"
        ),
        "results/development-matched-50x6-v30.manifest.json": (
            "sha256:53fb0f3b3915bfa08ceb893915d50f1f305399e20b2cfcec30a1ec0c962d9f44"
        ),
        "results/development-matched-50x6-v30.authentication.json": (
            "sha256:078d3fa2a2c59837806c0e6e3c4aa2a9762795a47833df03fc3a096d1f289f6d"
        ),
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.raw = (cls.root / cls.SUPERSESSION_PATH).read_bytes()
        payload = json.loads(
            cls.raw,
            object_pairs_hook=_object_without_duplicate_keys,
        )
        if not isinstance(payload, dict):
            raise TypeError("V30 supersession must be a JSON object")
        cls.superseded = payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V30SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V30SupersessionTests._keys(value))
        return observed

    @staticmethod
    def _strings(payload: object) -> list[str]:
        observed: list[str] = []
        if isinstance(payload, str):
            observed.append(payload)
        elif isinstance(payload, Mapping):
            for value in payload.values():
                observed.extend(V30SupersessionTests._strings(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.extend(V30SupersessionTests._strings(value))
        return observed

    def test_canonical_duplicate_free_closed_record(self) -> None:
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v23",
        )
        expected = (
            json.dumps(self.superseded, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        self.assertEqual(self.raw, expected)

    def test_exact_v30_public_commit_chain_and_files_are_bound(self) -> None:
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
            self.assertEqual(self.superseded[f"{prefix}_commit"], commit)
            self.assertEqual(
                self.superseded[f"{prefix}_parent_commit"], parent
            )
            self.assertEqual(self.superseded[f"{prefix}_tree"], tree)
        for relative, expected in self.PUBLIC_FILE_HASHES.items():
            observed = "sha256:" + hashlib.sha256(
                (self.root / relative).read_bytes()
            ).hexdigest()
            self.assertEqual(observed, expected)

    def test_generation_refusal_preceded_every_irreversible_boundary(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_preflight_supervisor_generation_refusal",
        )
        self.assertEqual(self.superseded["generate_cli_invocations"], 1)
        self.assertEqual(self.superseded["install_cli_invocations"], 0)
        self.assertEqual(self.superseded["start_cli_invocations"], 0)
        self.assertIs(self.superseded["failure_before_first_runtime_write"], True)
        self.assertIs(self.superseded["runtime_directory_created"], False)
        self.assertIs(self.superseded["launch_agent_config_created"], False)
        self.assertIs(self.superseded["launch_agent_plist_created"], False)
        self.assertIs(self.superseded["launchctl_bootstrap_invoked"], False)
        self.assertIs(self.superseded["launchctl_kickstart_invoked"], False)
        self.assertEqual(self.superseded["preflight_profiles_attempted"], 0)
        self.assertEqual(self.superseded["preflight_profiles_passed"], 0)
        self.assertEqual(self.superseded["production_assignments_started"], 0)
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 0, "codex": 0, "cursor": 0, "total": 0},
        )
        self.assertEqual(
            self.superseded[
                "model_bearing_provider_calls_conservatively_chargeable"
            ],
            0,
        )

    def test_root_cause_is_finite_and_path_free(self) -> None:
        self.assertEqual(
            self.superseded["audited_root_cause_code"],
            "owner_scoped_temporary_directory_contract_failed",
        )
        self.assertEqual(
            self.superseded["failure_stage"],
            "launch_agent_safe_environment_before_runtime_write",
        )
        self.assertEqual(
            self.superseded["temporary_directory_required_owner"],
            "effective_user",
        )
        self.assertEqual(
            self.superseded["temporary_directory_required_mode"], "0700"
        )
        self.assertIs(
            self.superseded[
                "observed_temporary_directory_owner_matched_effective_user"
            ],
            False,
        )
        self.assertEqual(
            self.superseded["observed_temporary_directory_mode"], "0777"
        )
        self.assertIs(
            self.superseded["temporary_directory_absolute_path_released"],
            False,
        )
        source = (
            self.root / "src/epiagentbench/launchd_agent.py"
        ).read_text(encoding="utf-8")
        late_environment_call = "base_environment\": _safe_environment("
        if late_environment_call in source:
            self.assertLess(
                source.index(late_environment_call),
                source.index("os.mkdir(runtime, 0o700)"),
            )
        else:
            self.assertLess(
                source.index(
                    "base_environment = _safe_environment(root, path_environment)"
                ),
                source.index(
                    '_require_directory(root, label="repository root")'
                ),
            )

    def test_no_runner_receipt_was_fabricated(self) -> None:
        self.assertIs(self.superseded["terminal_runner_receipt_created"], False)
        self.assertFalse(
            (
                self.root
                / "results/development-matched-50x6-v30.preflight.json"
            ).exists()
        )
        self.assertFalse(
            (
                self.root / "results/development-matched-50x6-v30.json"
            ).exists()
        )
        self.assertIs(
            self.superseded["public_preflight_artifact_created"], False
        )
        self.assertIs(self.superseded["public_results_artifact_created"], False)

    def test_v30_is_nonresumable_and_v31_is_unset(self) -> None:
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(self.superseded["v30_cohort_reuse_permitted"], False)
        self.assertIs(
            self.superseded["v30_key_or_namespace_reuse_permitted"], False
        )
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v31",
        )
        self.assertEqual(
            self.superseded["replacement_values_status"],
            "not_yet_created_or_authorized",
        )
        self.assertIs(
            self.superseded["v31_acknowledgement_receipt_recorded"], False
        )
        self.assertIs(
            self.superseded["v31_commit_or_hash_values_recorded"], False
        )

    def test_record_is_trace_free_and_contains_no_protected_payload(self) -> None:
        forbidden_keys = {
            "access_token",
            "api_key",
            "argv",
            "credential",
            "episode_id",
            "episode_ref",
            "exception",
            "family",
            "hidden_episode_identifier",
            "observation",
            "oauth_state",
            "private_path",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_output",
            "schedule",
            "score",
            "stderr",
            "stdout",
            "trace",
        }
        self.assertTrue(forbidden_keys.isdisjoint(self._keys(self.superseded)))
        for value in self._strings(self.superseded):
            lowered = value.lower()
            self.assertFalse(lowered.startswith(("/", "~", "file://")))
            self.assertNotIn("\n", value)
            for fragment in (
                "/private/",
                "/users/",
                "access_token",
                "api_key",
                "episode_",
                "family",
                "oauth_state",
                "observation",
                "private_seed",
                "prompt",
                "provider_output",
                "score",
                "trace_steps",
            ):
                self.assertNotIn(fragment, lowered)

    def test_supersession_timestamp_is_current_utc(self) -> None:
        superseded_at = datetime.fromisoformat(
            str(self.superseded["superseded_at_utc"]).replace("Z", "+00:00")
        )
        self.assertEqual(superseded_at.tzinfo, timezone.utc)
        self.assertLessEqual(superseded_at, datetime.now(timezone.utc))


if __name__ == "__main__":
    unittest.main()
