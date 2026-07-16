from __future__ import annotations

import importlib.util
import unittest
from copy import deepcopy
from dataclasses import replace

from epiagentbench.baseline import run_scripted_baseline
from epiagentbench.environment import InvestigationEnvironment
from epiagentbench.hypotheses import normalize_hypothesis_catalog
from epiagentbench.ltc_scenario import ltc_norovirus_hypothesis_catalog
from epiagentbench.scenario import generate_episode
from epiagentbench.scoring import score_episode
from epiagentbench.trusted.controller import TrustedEpisodeController
from epiagentbench.trusted.starsim_episode import StarsimSurveillanceBackend


HAS_STARSIM = importlib.util.find_spec("starsim") is not None


class HypothesisCatalogScoringTests(unittest.TestCase):
    def setUp(self):
        self.bundle = generate_episode(
            seed=13, family="restaurant_point_source"
        )
        self.environment = InvestigationEnvironment(self.bundle.public)
        self.submission = run_scripted_baseline(self.environment)
        self.legacy_submission = deepcopy(self.submission)
        self.catalog = ltc_norovirus_hypothesis_catalog()
        self.manifest = deepcopy(dict(self.bundle.public.manifest))
        self.manifest["hypothesis_catalog"] = deepcopy(self.catalog)
        targets = {
            "propagated": "site_institution001",
            "common_source": self.bundle.oracle.source_id,
            "repeated_introduction": "program_entry001",
            "reporting_artifact": "system_reporting001",
            "sporadic_background": None,
            "other_or_insufficient": None,
        }
        self.submission["hypotheses"] = [
            {
                "type": option["id"],
                "target_id": targets[option["id"]],
                "probability": (
                    0.7 if option["id"] == "common_source" else 0.06
                ),
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
            }
            for option in self.catalog
        ]

    def score(self, submission=None, *, manifest=None, oracle=None):
        return score_episode(
            oracle=oracle or self.bundle.oracle,
            manifest=manifest or self.manifest,
            ledger=self.environment.ledger,
            seen_ids=self.environment.seen_ids,
            submission=submission or self.submission,
        )

    def test_ltc_catalog_is_stable_public_data(self):
        first = ltc_norovirus_hypothesis_catalog()
        second = ltc_norovirus_hypothesis_catalog()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertEqual(
            [option["id"] for option in normalize_hypothesis_catalog(first)],
            [
                "propagated",
                "common_source",
                "repeated_introduction",
                "reporting_artifact",
                "sporadic_background",
                "other_or_insufficient",
            ],
        )

    def test_complete_distribution_is_scored_with_multiclass_brier(self):
        scorecard = self.score()
        self.assertTrue(scorecard.valid)
        expected = (1.0 - 0.7) ** 2 + 5 * 0.06**2
        self.assertAlmostEqual(
            scorecard.metrics["hypothesis_multiclass_brier"], expected, 6
        )
        self.assertAlmostEqual(
            scorecard.dimensions["hypothesis"], 15.0 * (1 - expected / 2)
        )

    def test_unknown_duplicate_and_missing_options_fail_closed(self):
        unknown = deepcopy(self.submission)
        unknown["hypotheses"][-1]["type"] = "unpublished_answer"
        unknown_score = self.score(unknown)
        self.assertFalse(unknown_score.valid)
        self.assertIn(
            "unknown:hypothesis_catalog_option:5",
            unknown_score.violations,
        )

        duplicate = deepcopy(self.submission)
        duplicate["hypotheses"][-1]["type"] = "sporadic_background"
        duplicate_score = self.score(duplicate)
        self.assertFalse(duplicate_score.valid)
        self.assertIn(
            "duplicate:hypothesis_catalog_option",
            duplicate_score.violations,
        )
        self.assertIn(
            "missing:hypothesis_catalog_options",
            duplicate_score.violations,
        )

        missing = deepcopy(self.submission)
        missing["hypotheses"].pop()
        missing_score = self.score(missing)
        self.assertFalse(missing_score.valid)
        self.assertIn(
            "missing:hypothesis_catalog_options", missing_score.violations
        )

    def test_distribution_mass_and_target_rules_fail_closed(self):
        underweight = deepcopy(self.submission)
        underweight["hypotheses"][1]["probability"] = 0.6
        underweight_score = self.score(underweight)
        self.assertFalse(underweight_score.valid)
        self.assertIn(
            "invalid:hypothesis_probability_mass",
            underweight_score.violations,
        )

        missing_target = deepcopy(self.submission)
        missing_target["hypotheses"][0]["target_id"] = None
        missing_target_score = self.score(missing_target)
        self.assertFalse(missing_target_score.valid)
        self.assertIn(
            "missing:hypothesis_target:0", missing_target_score.violations
        )

        forbidden_target = deepcopy(self.submission)
        forbidden_target["hypotheses"][-1]["target_id"] = "site_guess001"
        forbidden_target_score = self.score(forbidden_target)
        self.assertFalse(forbidden_target_score.valid)
        self.assertIn(
            "invalid:hypothesis_target:5", forbidden_target_score.violations
        )

    def test_catalog_must_cover_trace_derived_oracle_explanation(self):
        oracle = replace(self.bundle.oracle, explanation_type="not_in_catalog")
        scorecard = self.score(oracle=oracle)
        self.assertFalse(scorecard.valid)
        self.assertIn(
            "invalid:hypothesis_catalog_oracle", scorecard.violations
        )

    def test_legacy_episode_retains_legacy_single_hypothesis_contract(self):
        legacy_score = self.score(
            self.legacy_submission, manifest=self.bundle.public.manifest
        )
        self.assertTrue(legacy_score.valid)
        self.assertEqual(len(self.legacy_submission["hypotheses"]), 1)
        self.assertNotIn(
            "hypothesis_multiclass_brier", legacy_score.metrics
        )


@unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
class LiveHypothesisCatalogTests(unittest.TestCase):
    def test_pack_publishes_catalog_and_baseline_submits_every_option(self):
        runtime = StarsimSurveillanceBackend().create_runtime(
            seed=7,
            family="institution_person_to_person",
            presentation_key=b"hypothesis-catalog-live-test-key01",
        )
        self.addCleanup(runtime.close)
        controller = TrustedEpisodeController(runtime)
        started = controller.public_call("start", {})
        catalog = started["manifest"]["hypothesis_catalog"]
        self.assertEqual(catalog, ltc_norovirus_hypothesis_catalog())

        environment = InvestigationEnvironment(runtime.public_episode)
        submission = run_scripted_baseline(environment)
        self.assertEqual(
            {item["type"] for item in submission["hypotheses"]},
            {option["id"] for option in catalog},
        )
        self.assertAlmostEqual(
            sum(item["probability"] for item in submission["hypotheses"]),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
