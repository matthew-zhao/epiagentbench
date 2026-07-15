from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

from epiagentbench.models import Observation, PublicEpisode
from epiagentbench.validation import (
    _candidate_match_diagnostics,
    _fixed_response_policy_diagnostics,
    _live_fixed_response_utilities,
    _minute_zero_public_features,
    run_adaptive_live_mode_audit,
    run_live_mode_panel,
)
from epiagentbench.trusted.starsim_episode import (
    StarsimSurveillanceBackend,
    _public_opening_admissible,
)


class LiveModeValidationTests(unittest.TestCase):
    def test_panel_uses_distinct_private_keys_and_emits_only_root_commitment(self):
        panel_secret = b"p" * 32
        with patch(
            "epiagentbench.validation.secrets.token_bytes",
            return_value=panel_secret,
        ), patch.object(
            StarsimSurveillanceBackend,
            "create_runtime",
            side_effect=RuntimeError("stop before simulation"),
        ) as create_runtime:
            report = run_live_mode_panel(start_seed=4, seeds_per_mode=1)

        keys = [
            call.kwargs["presentation_key"]
            for call in create_runtime.call_args_list
        ]
        self.assertEqual(len(keys), 5)
        self.assertEqual(len(set(keys)), 5)
        self.assertEqual(
            report["presentation_secret_commitment"],
            "sha256:" + hashlib.sha256(panel_secret).hexdigest(),
        )
        self.assertFalse(report["presentation_secret_persisted"])
        self.assertFalse(report["panel_exactly_replayable"])
        self.assertNotIn(panel_secret.hex(), str(report))

    def test_opening_admission_uses_only_current_public_patient_counts(self):
        alert = Observation(
            observation_id="obs_alert",
            kind="alert",
            subject_id=None,
            available_minute=0,
            release_key="initial",
            payload={"observed_count": 8},
        )
        encounters = tuple(
            Observation(
                observation_id=f"obs_patient_{index}",
                kind="encounter",
                subject_id=f"patient_{index}",
                available_minute=0,
                release_key="stream",
                payload={"patient_id": f"patient_{index}"},
            )
            for index in range(6)
        )
        future = Observation(
            observation_id="obs_future",
            kind="encounter",
            subject_id="patient_future",
            available_minute=360,
            release_key="stream",
            payload={"patient_id": "patient_future"},
        )
        request_only = Observation(
            observation_id="obs_inspection",
            kind="inspection",
            subject_id="site_1",
            available_minute=0,
            release_key="inspection:site_1",
            payload={"target_id": "site_1", "patient_id": "patient_hidden"},
        )
        episode = PublicEpisode(
            manifest={"initial_alert_ids": [alert.observation_id]},
            observations=(alert, *encounters, future, request_only),
        )

        self.assertTrue(_public_opening_admissible(episode, "low"))
        too_few = PublicEpisode(
            manifest=episode.manifest,
            observations=(alert, *encounters[:5], future, request_only),
        )
        self.assertFalse(_public_opening_admissible(too_few, "low"))

    def test_future_exposure_pressure_is_not_redrawn_by_admission_retry(self):
        backend = StarsimSurveillanceBackend()
        key = b"future-pressure-independence-key-01"
        decision_minute = 8 * 24 * 60

        for mode in ("common_source", "repeated_introduction"):
            with self.subTest(mode=mode):
                first = backend._scheduled_exposures(
                    seed=11,
                    attempt=0,
                    presentation_key=key,
                    causal_mode=mode,
                )
                retried = backend._scheduled_exposures(
                    seed=11,
                    attempt=9,
                    presentation_key=key,
                    causal_mode=mode,
                )
                first_future = tuple(
                    item
                    for item in first
                    if item.exposure_minute > decision_minute
                )
                retried_future = tuple(
                    item
                    for item in retried
                    if item.exposure_minute > decision_minute
                )
                self.assertEqual(first_future, retried_future)

    def test_fixed_response_metrics_include_generic_and_legacy_keys(self):
        utilities = _live_fixed_response_utilities(
            {
                "closed_loop_fixed_off_utility": 0.0,
                "closed_loop_fixed_standard_utility": 3.0,
                "closed_loop_fixed_source_control_standard_utility": 8.0,
                "closed_loop_fixed_audit_reporting_intensive_utility": -2.0,
            }
        )

        self.assertEqual(utilities["off"], 0.0)
        self.assertEqual(utilities["infection_control_standard"], 3.0)
        self.assertEqual(utilities["source_control_standard"], 8.0)
        self.assertEqual(utilities["audit_reporting_intensive"], -2.0)

    def test_universal_constant_policy_uses_best_bundle_denominator(self):
        rows = [
            {
                "fixed_response_utilities": {
                    "off": 0.0,
                    "source_control_standard": 5.0,
                },
                "best_fixed_utility": 10.0,
            },
            {
                "fixed_response_utilities": {
                    "off": 0.0,
                    "source_control_standard": -2.0,
                },
                "best_fixed_utility": 10.0,
            },
        ]

        diagnostics = _fixed_response_policy_diagnostics(rows)

        self.assertEqual(
            diagnostics["source_control_standard"][
                "mean_normalized_response_score"
            ],
            0.25,
        )
        self.assertEqual(
            diagnostics["source_control_standard"][
                "harm_rate_below_no_action"
            ],
            0.5,
        )

    def test_minute_zero_features_ignore_unreleased_inspection(self):
        episode = PublicEpisode(
            manifest={
                "initial_alert_ids": ["obs_alert"],
                "enabled_tools": ["search_observations"],
            },
            observations=(
                Observation(
                    observation_id="obs_alert",
                    kind="alert",
                    subject_id=None,
                    available_minute=0,
                    release_key="initial",
                    payload={"observed_count": 9},
                ),
                Observation(
                    observation_id="obs_policy",
                    kind="policy",
                    subject_id=None,
                    available_minute=0,
                    release_key="initial",
                    payload={
                        "permitted": ["monitor"],
                        "response_control_catalog": {},
                    },
                ),
                Observation(
                    observation_id="obs_encounter",
                    kind="encounter",
                    subject_id="patient_1",
                    available_minute=0,
                    release_key="stream",
                    payload={"patient_id": "patient_1"},
                ),
                Observation(
                    observation_id="obs_inspection",
                    kind="inspection",
                    subject_id="site_1",
                    available_minute=0,
                    release_key="inspection:site_1",
                    payload={"target_id": "site_1"},
                ),
            ),
        )

        features = _minute_zero_public_features(episode)

        self.assertEqual(features["initial_alert_count"], 9)
        self.assertEqual(features["initial_public_patient_count"], 1)
        self.assertEqual(features["episode_id_bucket"], -1)
        self.assertEqual(features["policy_pack_id_bucket"], -1)

    def test_candidate_count_caliper_is_not_called_causal_matching(self):
        rows = [
            {
                "seed": 1,
                "initial_alert_count": 10 + index,
                "initial_public_patient_count": 8 + index,
            }
            for index in range(5)
        ]

        diagnostics = _candidate_match_diagnostics(rows, seeds_per_mode=1)

        self.assertEqual(diagnostics["groups_within_count_caliper"], 1)
        self.assertFalse(diagnostics["causal_match_claim"])

    def test_adaptive_audit_requires_disjoint_complete_panels(self):
        training_panel = {
            "successful_episodes": 10,
            "failures": [],
            "episodes": [{"placeholder": index} for index in range(10)],
            "presentation_secret_commitment": "sha256:" + "1" * 64,
            "panel_exactly_replayable": False,
        }
        heldout_panel = {
            **training_panel,
            "presentation_secret_commitment": "sha256:" + "2" * 64,
        }
        with (
            patch(
                "epiagentbench.validation.run_live_mode_panel",
                side_effect=(training_panel, heldout_panel),
            ),
            patch(
                "epiagentbench.adversarial.run_adaptive_reward_hacking_audit",
                return_value={"guardrail_pass": True},
            ) as shortcut,
            patch(
                "epiagentbench.adversarial.run_reference_integrity_attack_matrix",
                return_value={"guardrail_pass": True},
            ),
            patch(
                "epiagentbench.adversarial.run_secure_public_capability_probe_matrix",
                return_value={"guardrail_pass": True},
            ),
        ):
            report = run_adaptive_live_mode_audit(
                training_start_seed=0,
                training_seeds_per_mode=2,
                heldout_start_seed=100,
                heldout_seeds_per_mode=2,
            )

        self.assertEqual(report["adversarial_guardrail_gate"], "pass")
        self.assertTrue(report["guardrail_pass"])
        self.assertNotEqual(
            report["training_split"]["presentation_secret_commitment"],
            report["heldout_split"]["presentation_secret_commitment"],
        )
        self.assertEqual(
            report["heldout_split"]["role"],
            "disjoint_development_check_panel",
        )
        self.assertIn("not_authenticated_private_holdout", report["split_status"])
        self.assertEqual(
            shortcut.call_args.kwargs["metadata_features"],
            ("schema_version", "episode_id_bucket", "policy_pack_id_bucket"),
        )

        with self.assertRaisesRegex(ValueError, "overlap"):
            run_adaptive_live_mode_audit(
                training_start_seed=0,
                training_seeds_per_mode=2,
                heldout_start_seed=1,
                heldout_seeds_per_mode=2,
            )


if __name__ == "__main__":
    unittest.main()
