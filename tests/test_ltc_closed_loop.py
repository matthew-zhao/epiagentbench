from __future__ import annotations

import importlib.util
import json
import unittest

from epiagentbench.cli import build_parser
from epiagentbench.trusted.backend import build_backend
from epiagentbench.trusted.controller import TrustedEpisodeController
from epiagentbench.trusted.ltc_closed_loop import LtcStarsimV3Backend
from epiagentbench.trusted.service import launch_secure_episode


HAS_STARSIM = importlib.util.find_spec("starsim") is not None
TEST_EPISODE_KEY = b"\x5a" * 32


@unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
class LtcClosedLoopTests(unittest.TestCase):
    def runtime(self, family: str = "institution_person_to_person"):
        runtime = LtcStarsimV3Backend().create_runtime(
            seed=7,
            family=family,
            presentation_key=b"x" * 32,
        )
        self.addCleanup(runtime.close)
        return runtime

    def test_backend_and_cli_expose_only_the_secure_backend_name(self):
        self.assertIsInstance(build_backend("starsim-ltc-v3"), LtcStarsimV3Backend)
        parsed = build_parser().parse_args(
            ["secure-demo", "--backend", "starsim-ltc-v3"]
        )
        self.assertEqual(parsed.backend, "starsim-ltc-v3")

    def test_backend_runs_through_the_separate_secure_broker(self):
        session, client = launch_secure_episode(
            seed=7,
            family="institution_person_to_person",
            backend="starsim-ltc-v3",
            episode_secret=TEST_EPISODE_KEY,
        )
        try:
            started = {
                "manifest": client.manifest,
                "observations": client.initial_observations(),
            }
            self.assertEqual(len(started["manifest"]["hypothesis_catalog"]), 6)
            serialized = json.dumps(started, sort_keys=True)
            self.assertNotIn("private_metadata", serialized)
            self.assertNotIn("opening_snapshot", serialized)
        finally:
            session.close()

    def test_start_is_role_aware_but_contains_no_private_facility_state(self):
        runtime = self.runtime()
        controller = TrustedEpisodeController(runtime)
        started = controller.public_call("start", {})
        self.assertEqual(len(started["manifest"]["hypothesis_catalog"]), 6)
        searchable = controller.public_call(
            "search_observations", {"kind": None, "filters": {}}
        )
        contextual = [
            observation
            for observation in searchable
            if observation["kind"] == "encounter"
            and "facility_role" in observation["payload"]
        ]
        self.assertTrue(contextual)
        self.assertTrue(
            all(
                observation["payload"]["facility_role"]
                in {"resident", "staff", "visitor"}
                and observation["payload"]["ward_id"].startswith("ward_")
                for observation in contextual
            )
        )
        serialized = json.dumps(
            {"start": started, "searchable": searchable}, sort_keys=True
        )
        for private_fragment in (
            "resident-",
            "staff-",
            "visitor-",
            "ward-",
            "room-",
            "contact-",
            "shift-",
            "meal-",
            "entry-",
            "private_metadata",
            "scheduled_exposures",
            "scenario_commitment",
            "manifest_sha256",
            "opening_snapshot",
            "authentication_tag",
        ):
            self.assertNotIn(private_fragment, serialized)

    def test_active_and_shadow_have_identical_full_opening_snapshots(self):
        runtime = self.runtime("restaurant_point_source")
        self.assertEqual(
            runtime._active.private_snapshot(),  # evaluator-only assertion
            runtime._shadow.private_snapshot(),
        )

    def test_source_control_is_routed_to_the_source_hook(self):
        runtime = self.runtime("restaurant_point_source")
        target = runtime._stream.food_service_id
        receipt = runtime.apply_response_control(
            "source_control", "standard", target, 0
        )
        self.assertEqual(receipt.status, "scheduled")
        self.assertEqual(receipt.effective_at_minute, 360)
        runtime.advance_to(360)
        oracle = runtime.finalize()
        self.assertEqual(
            oracle.counterfactual_metrics["source_control_state_changes"], 1
        )
        self.assertLessEqual(
            oracle.counterfactual_metrics["realized_active_infections"],
            oracle.counterfactual_metrics["counterfactual_no_action_infections"],
        )

    def test_each_supported_family_is_scored_from_realized_trace_facts(self):
        expected = {
            "institution_person_to_person": "propagated",
            "restaurant_point_source": "common_source",
            "repeated_introduction": "repeated_introduction",
            "coincidental_venue": "sporadic_background",
            "reporting_artifact": "reporting_artifact",
        }
        for family, explanation in expected.items():
            with self.subTest(family=family):
                runtime = LtcStarsimV3Backend().create_runtime(
                    seed=7,
                    family=family,
                    presentation_key=b"ltc-v3-family-test-key-00000001",
                )
                try:
                    self.assertEqual(runtime.finalize().explanation_type, explanation)
                finally:
                    runtime.close()

    def test_background_nuisance_count_is_independent_of_family(self):
        counts = set()
        for family in (
            "institution_person_to_person",
            "restaurant_point_source",
            "repeated_introduction",
            "coincidental_venue",
            "reporting_artifact",
        ):
            runtime = LtcStarsimV3Backend().create_runtime(
                seed=11,
                family=family,
                presentation_key=b"ltc-v3-nuisance-test-key-0000001",
            )
            try:
                counts.add(runtime._stream._background_episode_count)
            finally:
                runtime.close()
        self.assertEqual(len(counts), 1)


if __name__ == "__main__":
    unittest.main()
