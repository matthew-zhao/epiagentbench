from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from epiagentbench.nors_ltc_observation import (
    build_ltc_nors_observation_diagnostics,
    main,
)


_FIXTURES = Path(__file__).parent / "fixtures"
_CSV = _FIXTURES / "nors_ltc_observation.csv"
_METADATA = _FIXTURES / "nors_ltc_observation.metadata.json"


class LtcNorsObservationTests(unittest.TestCase):
    def test_contract_selects_only_ltc_person_to_person_norovirus_reports(self):
        report = build_ltc_nors_observation_diagnostics(_CSV, _METADATA)

        self.assertEqual(
            report["scope_label"],
            "reported-outbreak observation diagnostics; not latent transmission",
        )
        self.assertFalse(
            report["scientific_scope"]["latent_transmission_estimand"]
        )
        self.assertFalse(report["admissibility"]["scientific_use_authorized"])
        self.assertEqual(
            report["admissibility"]["source_authenticity"],
            "caller_supplied_unverified",
        )
        self.assertTrue(
            report["admissibility"]["declared_fixture_or_synthetic"]
        )
        self.assertEqual(
            report["source_commitments"]["authenticity_claim"],
            "not established by this adapter",
        )
        self.assertEqual(
            report["estimand_contract"]["reporting_margin_definitions"][
                "season_from_earliest_onset_month"
            ]["winter"],
            [12, 1, 2],
        )
        self.assertEqual(report["cohort_flow"]["source_rows"], 16)
        self.assertEqual(
            report["cohort_flow"]["eligible_rows_before_year_restriction"], 12
        )
        self.assertEqual(report["cohort_flow"]["eligible_rows_2009_2019"], 11)
        self.assertEqual(
            report["cohort_flow"][
                "otherwise_eligible_rows_outside_2009_2019"
            ],
            1,
        )

        diagnostics = report["reporting_regime_diagnostics"]
        self.assertEqual(
            diagnostics["annual"]["2012"]["exposure_state_category_count"],
            1,
        )
        self.assertEqual(
            diagnostics["annual"]["2015"]["reported_outbreak_size"],
            {"n": 1, "q25": 14.0, "median": 14.0, "q75": 14.0},
        )
        self.assertEqual(
            diagnostics["eras"]["2009-2012"]["reported_outbreak_size"],
            {"n": 4, "q25": 3.5, "median": 5.0, "q75": 6.5},
        )
        self.assertEqual(
            diagnostics["eras"]["2013-2016"]["reported_outbreak_size"],
            {"n": 4, "q25": 11.5, "median": 13.0, "q75": 14.5},
        )
        self.assertEqual(
            diagnostics["eras"]["2017-2019"]["reported_outbreak_size"],
            {"n": 3, "q25": 19.0, "median": 20.0, "q75": 21.0},
        )

        overall = diagnostics["overall_2009_2019"]
        self.assertEqual(
            overall["confirmed_vs_suspected_mix"]["counts"],
            {
                "confirmed_only": 5,
                "suspected_only": 5,
                "mixed_confirmed_and_suspected": 1,
                "unresolved_or_other": 0,
            },
        )
        self.assertEqual(
            overall["state_reporting_margin"]["categories"]["California"]["n"],
            4,
        )
        self.assertEqual(
            overall["state_reporting_margin"]["categories"]["missing"]["n"],
            1,
        )
        self.assertEqual(
            {
                season: value["n"]
                for season, value in overall[
                    "season_of_earliest_illness_onset_margin"
                ]["categories"].items()
            },
            {"winter": 3, "spring": 3, "summer": 3, "autumn": 2},
        )

    def test_source_and_report_commitments_are_recomputable(self):
        report = build_ltc_nors_observation_diagnostics(_CSV, _METADATA)

        expected_csv = hashlib.sha256(_CSV.read_bytes()).hexdigest()
        expected_metadata = hashlib.sha256(_METADATA.read_bytes()).hexdigest()
        self.assertEqual(
            report["source_commitments"]["csv_sha256"],
            f"sha256:{expected_csv}",
        )
        self.assertEqual(
            report["source_commitments"]["metadata_sha256"],
            f"sha256:{expected_metadata}",
        )
        supplied = report.pop("diagnostic_sha256")
        expected_report = hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(supplied, f"sha256:{expected_report}")

        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / "changed.csv"
            shutil.copyfile(_CSV, changed)
            with changed.open("a", encoding="utf-8") as handle:
                handle.write("\n")
            changed_report = build_ltc_nors_observation_diagnostics(
                changed, _METADATA
            )
        self.assertNotEqual(
            changed_report["source_commitments"]["csv_sha256"],
            f"sha256:{expected_csv}",
        )
        self.assertEqual(
            changed_report["source_commitments"][
                "eligible_normalized_rows_sha256"
            ],
            report["source_commitments"]["eligible_normalized_rows_sha256"],
        )

    def test_dependency_free_module_cli_can_write_the_report(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            output = Path(temp) / "diagnostics.json"
            result = main(
                [
                    "--csv",
                    str(_CSV),
                    "--metadata",
                    str(_METADATA),
                    "--output",
                    str(output),
                ]
            )
            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(
            saved["contract_version"],
            "ltc_nors_reported_outbreak_observation_v1",
        )
        self.assertEqual(
            saved["reporting_regime_diagnostics"]["overall_2009_2019"][
                "reported_outbreak_size"
            ]["n"],
            11,
        )

    def test_schema_drift_is_rejected_instead_of_silently_dropping_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            malformed = Path(temp) / "missing_month.csv"
            malformed.write_text(
                _CSV.read_text(encoding="utf-8").replace(
                    "Year,Month,State", "Year,Onset,State", 1
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing required fields: month"):
                build_ltc_nors_observation_diagnostics(malformed, _METADATA)


if __name__ == "__main__":
    unittest.main()
