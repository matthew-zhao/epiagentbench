from __future__ import annotations

import unittest

from epiagentbench.models import EpisodeBundle, Oracle
from epiagentbench.trusted.controller import TrustedEpisodeController
from epiagentbench.trusted.live_surveillance import IncrementalSurveillanceStream
from epiagentbench.trusted.surveillance import (
    LIVE_PROFILE_RESOURCE,
    load_gi_surveillance_profile,
)


class InspectionApiTests(unittest.TestCase):
    def make_controller(self) -> TrustedEpisodeController:
        profile = load_gi_surveillance_profile(LIVE_PROFILE_RESOURCE)
        stream = IncrementalSurveillanceStream(
            seed=3,
            presentation_key=b"inspection-api-presentation-key-01",
            profile=profile,
            population_size=1000,
            decision_minute=8 * 24 * 60,
            deadline_minutes=5 * 24 * 60,
            review_interval_minutes=360,
            causal_mode="common_source",
        )
        public = stream.bootstrap()
        bundle = EpisodeBundle(
            public=public,
            oracle=Oracle(
                family="test",
                is_outbreak=False,
                true_case_ids=frozenset(),
                explanation_type="sporadic_background",
                source_id=None,
                decisive_evidence_ids=frozenset(),
                action_utilities={("monitor", None): 0.0},
            ),
        )
        controller = TrustedEpisodeController(bundle)
        self.addCleanup(controller.close)
        return controller

    def test_request_inspection_is_targeted_delayed_and_single_release(self):
        controller = self.make_controller()
        started = controller.public_call("start", {})
        policy = next(
            record
            for record in started["observations"]
            if record["kind"] == "policy"
        )
        target = policy["payload"]["response_control_catalog"][
            "source_control"
        ]["target_id"]

        receipt = controller.public_call(
            "request_inspection", {"target_id": target}
        )
        self.assertEqual(receipt["status"], "scheduled")
        self.assertEqual(receipt["available_at_minute"], 180)
        self.assertEqual(
            controller.public_call(
                "search_observations", {"kind": "inspection", "filters": {}}
            ),
            [],
        )

        released = controller.public_call("advance_time", {"minutes": 180})
        inspections = [
            record for record in released if record["kind"] == "inspection"
        ]
        self.assertEqual(len(inspections), 1)
        self.assertEqual(inspections[0]["payload"]["target_id"], target)
        self.assertEqual(
            controller.public_call(
                "request_inspection", {"target_id": target}
            )["status"],
            "duplicate_request",
        )


if __name__ == "__main__":
    unittest.main()
