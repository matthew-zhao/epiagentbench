from __future__ import annotations

import unittest

from epiagentbench.trusted.backend import ReferenceEpisodeBackend
from epiagentbench.trusted.runtime import (
    RuntimeInterventionReceipt,
    StaticEpisodeRuntime,
)


class StaticEpisodeRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        backend = ReferenceEpisodeBackend()
        self.bundle = backend.create_episode(
            seed=7,
            family="institution_person_to_person",
        )
        self.runtime = StaticEpisodeRuntime(self.bundle)

    def test_exposes_public_episode_and_private_final_oracle(self):
        self.assertIs(self.runtime.public_episode, self.bundle.public)
        self.assertEqual(
            self.runtime.canary_tokens,
            self.bundle.oracle.canary_tokens,
        )
        self.assertIs(self.runtime.finalize(), self.bundle.oracle)

    def test_advance_and_unsupported_intervention_do_not_mutate_episode(self):
        before = self.runtime.finalize()

        self.assertEqual(self.runtime.advance_to(600), ())
        receipt = self.runtime.apply_institution_control(
            "standard",
            "facility-1",
            600,
        )

        self.assertEqual(
            receipt,
            RuntimeInterventionReceipt(
                status="unsupported",
                intervention_id=None,
                effective_at_minute=None,
                level="standard",
            ),
        )
        self.assertIs(self.runtime.finalize(), before)

    def test_reference_backend_preserves_both_creation_paths(self):
        backend = ReferenceEpisodeBackend()
        runtime = backend.create_runtime(
            seed=11,
            family="restaurant_point_source",
        )
        bundle = backend.create_episode(
            seed=11,
            family="restaurant_point_source",
        )

        self.assertEqual(runtime.public_episode, bundle.public)
        self.assertEqual(runtime.finalize(), bundle.oracle)
        self.assertIsNone(runtime.close())


if __name__ == "__main__":
    unittest.main()
