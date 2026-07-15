from __future__ import annotations

from contextlib import redirect_stderr
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epiagentbench.calibration import (
    build_nors_calibration_plan,
    compare_reported_outbreak_sizes,
    fetch_nors_snapshot,
    freeze_calibration_candidate,
    release_nors_partition,
)
from epiagentbench.cli import build_parser


_HEADERS = [
    "Year",
    "Month",
    "State",
    "Primary Mode",
    "Etiology",
    "Serotype or Genotype",
    "Etiology Status",
    "Setting",
    "Illnesses",
    "Hospitalizations",
    "Info On Hospitalizations",
    "Deaths",
    "Info On Deaths",
    "Food Vehicle",
    "Food Contaminated Ingredient",
    "IFSAC Category",
    "Water Exposure",
    "Water Type",
    "Animal Type",
]


def _row(
    year: int,
    illnesses: int,
    *,
    primary_mode: str = "Person-to-person",
    setting: str = "Hospital",
) -> list[object]:
    return [
        year,
        1,
        "Test State",
        primary_mode,
        "Norovirus",
        "GII",
        "Confirmed",
        setting,
        illnesses,
        1,
        illnesses,
        0,
        illnesses,
        "",
        "",
        "",
        "",
        "",
        "",
    ]


class NorsCalibrationTests(unittest.TestCase):
    def _snapshot(self, root: Path) -> tuple[Path, Path]:
        csv_path = root / "nors.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(_HEADERS)
            year_values = {year: 10 for year in range(2009, 2019)}
            year_values.update(
                {2018: 18, 2019: 20, 2020: 30, 2021: 31, 2022: 90, 2023: 99}
            )
            for year, illnesses in year_values.items():
                writer.writerow(_row(year, illnesses))
                writer.writerow(
                    _row(
                        year,
                        illnesses + 2,
                        primary_mode="Food",
                        setting="Restaurant: Sit-down dining",
                    )
                )
        metadata_path = root / "nors.metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "id": "5xkq-dg7x",
                    "rowsUpdatedAt": 1734724660,
                }
            ),
            encoding="utf-8",
        )
        return csv_path, metadata_path

    def test_plan_releases_fit_targets_and_seals_later_outcomes(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path, metadata_path = self._snapshot(Path(temp))
            plan = build_nors_calibration_plan(
                csv_path,
                metadata_path,
                created_at="2026-07-14T00:00:00+00:00",
            )

        institutional = plan["cohorts"]["institution_person_to_person"]
        self.assertEqual(
            institutional["released_targets"]["calibration"][
                "reported_outbreak_size"
            ]["median"],
            10.0,
        )
        self.assertNotIn("targets", institutional["sealed_partitions"])
        self.assertNotIn("99.0", json.dumps(plan))
        self.assertFalse(plan["holdout_policy"]["released"])

    def test_temporal_validation_requires_and_verifies_a_pre_release_freeze(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path, metadata_path = self._snapshot(Path(temp))
            plan = build_nors_calibration_plan(csv_path, metadata_path)
            freeze = freeze_calibration_candidate(
                plan,
                b'{"profile":"fitted-without-temporal-validation"}',
                frozen_at="2026-07-14T01:00:00+00:00",
            )
            report = release_nors_partition(
                csv_path,
                plan,
                freeze,
                acknowledge_sealed_release=True,
            )

        self.assertTrue(report["post_freeze_only"])
        self.assertEqual(report["partition"], "temporal_generalization")
        self.assertRegex(
            freeze["candidate_implementation_fingerprint"],
            r"^sha256:[0-9a-f]{64}$",
        )
        target = report["targets"]["institution_person_to_person"]
        self.assertEqual(target["reported_outbreak_size"]["median"], 94.5)

    def test_tampered_plan_or_snapshot_cannot_release_temporal_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path, metadata_path = self._snapshot(Path(temp))
            plan = build_nors_calibration_plan(csv_path, metadata_path)
            freeze = freeze_calibration_candidate(plan, b"profile")
            tampered = json.loads(json.dumps(plan))
            tampered["temporal_split"]["temporal_generalization"] = [2023]
            with self.assertRaisesRegex(ValueError, "commitment"):
                release_nors_partition(
                    csv_path,
                    tampered,
                    freeze,
                    acknowledge_sealed_release=True,
                )

            with csv_path.open("a", encoding="utf-8") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(ValueError, "snapshot differs"):
                release_nors_partition(
                    csv_path,
                    plan,
                    freeze,
                    acknowledge_sealed_release=True,
                )

    def test_every_sealed_partition_requires_explicit_acknowledgement(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path, metadata_path = self._snapshot(Path(temp))
            plan = build_nors_calibration_plan(csv_path, metadata_path)
            freeze = freeze_calibration_candidate(plan, b"profile")
            for partition in ("disruption_stress", "temporal_generalization"):
                with self.subTest(partition=partition), self.assertRaisesRegex(
                    ValueError, "Explicit acknowledgement"
                ):
                    release_nors_partition(
                        csv_path, plan, freeze, partition=partition
                    )

    def test_freeze_cli_has_no_caller_selected_calibration_file(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "freeze-calibration-candidate",
                "--plan",
                "plan.json",
                "--profile",
                "profile.json",
                "--output",
                "freeze.json",
            ]
        )
        self.assertFalse(hasattr(args, "calibration_code"))
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            parser.parse_args(
                [
                    "freeze-calibration-candidate",
                    "--plan",
                    "plan.json",
                    "--profile",
                    "profile.json",
                    "--calibration-code",
                    "one-file.py",
                    "--output",
                    "freeze.json",
                ]
            )

    def test_snapshot_fetch_rejects_revision_change_during_csv_download(self):
        before = {
            "id": "5xkq-dg7x",
            "rowsUpdatedAt": 1_734_724_660,
            "viewLastModified": 1_735_000_000,
            "columns": [{"id": 1, "fieldName": "year", "position": 1}],
        }
        after = dict(before, rowsUpdatedAt=1_734_724_661)
        csv_bytes = b"Year,Illnesses\n2023,4\n"
        with tempfile.TemporaryDirectory() as temp, patch(
            "epiagentbench.calibration._download",
            side_effect=(json.dumps(before).encode(), csv_bytes, json.dumps(after).encode()),
        ):
            with self.assertRaisesRegex(ValueError, "changed during CSV"):
                fetch_nors_snapshot(temp)
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_snapshot_fetch_accepts_stable_revision_despite_view_counter(self):
        before = {
            "id": "5xkq-dg7x",
            "rowsUpdatedAt": 1_734_724_660,
            "viewLastModified": 1_735_000_000,
            "viewCount": 10,
            "columns": [{"id": 1, "fieldName": "year", "position": 1}],
        }
        after = dict(before, viewCount=11)
        csv_bytes = b"Year,Illnesses\n2023,4\n"
        with tempfile.TemporaryDirectory() as temp, patch(
            "epiagentbench.calibration._download",
            side_effect=(json.dumps(before).encode(), csv_bytes, json.dumps(after).encode()),
        ):
            snapshot = fetch_nors_snapshot(temp)
        self.assertEqual(snapshot.rows, 1)

    def test_like_for_like_posterior_predictive_comparison(self):
        result = compare_reported_outbreak_sizes(
            [8, 10, 12, 16],
            {
                "reported_outbreak_size": {
                    "q25": 9.0,
                    "median": 11.0,
                    "q75": 15.0,
                }
            },
        )

        self.assertEqual(result["estimand"], "reported_illnesses_per_outbreak")
        self.assertEqual(result["simulated"]["median"], 11.0)
        self.assertEqual(result["absolute_log_quantile_errors"]["median"], 0.0)
        self.assertEqual(result["target_iqr_coverage"], 0.5)


if __name__ == "__main__":
    unittest.main()
