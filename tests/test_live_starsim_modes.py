from __future__ import annotations

import importlib.util
import unittest

from epiagentbench.trusted.starsim_episode import StarsimSurveillanceBackend


HAS_STARSIM = importlib.util.find_spec("starsim") is not None
PRESENTATION_KEY = b"runtime-modes-control-test-key-00001"


@unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
class LiveStarsimModeControlTests(unittest.TestCase):
    def make_runtime(self, family: str):
        runtime = StarsimSurveillanceBackend().create_runtime(
            seed=7,
            family=family,
            presentation_key=PRESENTATION_KEY,
        )
        self.addCleanup(runtime.close)
        return runtime

    @staticmethod
    def apply(runtime, action_type: str) -> None:
        runtime.apply_response_control(
            action_type,
            "intensive",
            runtime._stream.response_control_targets[action_type],
            0,
        )

    @staticmethod
    def finish(runtime):
        runtime.advance_to(runtime._deadline_minutes)
        return runtime._active.oracle_snapshot().transmission_events

    def test_common_source_control_is_route_specific(self):
        uncontrolled = self.make_runtime("restaurant_point_source")
        controlled = self.make_runtime("restaurant_point_source")
        irrelevant = self.make_runtime("restaurant_point_source")
        self.apply(controlled, "source_control")
        self.apply(irrelevant, "entry_control")

        baseline = self.finish(uncontrolled)
        controlled_events = self.finish(controlled)
        irrelevant_events = self.finish(irrelevant)

        self.assertLess(len(controlled_events), len(baseline))
        self.assertEqual(irrelevant_events, baseline)
        self.assertEqual(
            uncontrolled._active.oracle_snapshot().transmission_events,
            uncontrolled._shadow.oracle_snapshot().transmission_events,
        )

    def test_entry_control_is_route_specific(self):
        uncontrolled = self.make_runtime("repeated_introduction")
        controlled = self.make_runtime("repeated_introduction")
        irrelevant = self.make_runtime("repeated_introduction")
        self.apply(controlled, "entry_control")
        self.apply(irrelevant, "source_control")

        baseline = self.finish(uncontrolled)
        controlled_events = self.finish(controlled)
        irrelevant_events = self.finish(irrelevant)

        self.assertLess(len(controlled_events), len(baseline))
        self.assertEqual(irrelevant_events, baseline)
        self.assertEqual(
            uncontrolled._active.oracle_snapshot().transmission_events,
            uncontrolled._shadow.oracle_snapshot().transmission_events,
        )

    def test_audit_changes_only_future_artifact_emissions(self):
        uncontrolled = self.make_runtime("reporting_artifact")
        audited = self.make_runtime("reporting_artifact")
        biological_control = self.make_runtime("reporting_artifact")
        self.apply(audited, "audit_reporting")
        self.apply(biological_control, "infection_control")

        baseline_events = self.finish(uncontrolled)
        audited_events = self.finish(audited)
        irrelevant_events = self.finish(biological_control)

        self.assertEqual(audited_events, baseline_events)
        self.assertEqual(irrelevant_events, baseline_events)
        self.assertLess(
            audited._stream.total_emitted_reporting_artifacts,
            uncontrolled._stream.total_emitted_reporting_artifacts,
        )
        self.assertEqual(
            biological_control._stream.total_emitted_reporting_artifacts,
            uncontrolled._stream.total_emitted_reporting_artifacts,
        )
        self.assertEqual(
            uncontrolled._active.oracle_snapshot().transmission_events,
            uncontrolled._shadow.oracle_snapshot().transmission_events,
        )


if __name__ == "__main__":
    unittest.main()
