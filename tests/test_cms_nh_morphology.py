from __future__ import annotations

from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from epiagentbench.cms_nh_morphology import (
    CMS_NH_MORPHOLOGY_CONTRACT_VERSION,
    CMS_PROVIDER_INFORMATION_DATASET_ID,
    build_cms_nh_morphology_report,
    main,
)


_FIXTURES = Path(__file__).parent / "fixtures"
_CSV = _FIXTURES / "cms_provider_information_development.csv"
_METADATA = _FIXTURES / "cms_provider_information_development.metadata.json"


def _pinned_copy(
    directory: str,
    *,
    csv_transform=None,
    metadata_transform=None,
) -> tuple[Path, Path]:
    csv_text = _CSV.read_text(encoding="utf-8")
    if csv_transform is not None:
        csv_text = csv_transform(csv_text)
    csv_path = Path(directory) / _CSV.name
    csv_path.write_text(csv_text, encoding="utf-8")

    metadata = json.loads(_METADATA.read_text(encoding="utf-8"))
    payload = csv_path.read_bytes()
    metadata["artifact"]["bytes"] = len(payload)
    metadata["artifact"]["filename"] = csv_path.name
    metadata["artifact"]["sha256"] = (
        "sha256:" + hashlib.sha256(payload).hexdigest()
    )
    if metadata_transform is not None:
        metadata_transform(metadata)
    metadata_path = Path(directory) / _METADATA.name
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return csv_path, metadata_path


def _add_ambiguous_ccn_alias(csv_text: str) -> str:
    rows = list(csv.reader(io.StringIO(csv_text)))
    rows[0].insert(1, "Federal Provider Number")
    for row in rows[1:]:
        row.insert(1, row[0])
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue()


class CmsNursingHomeMorphologyTests(unittest.TestCase):
    def test_scientific_v3_margins_and_missingness_are_reported(self):
        report = build_cms_nh_morphology_report(_CSV, _METADATA)
        morphology = report["scientific_v3_morphology"]
        margins = morphology["observed_facility_margins"]

        self.assertEqual(
            report["contract_version"], CMS_NH_MORPHOLOGY_CONTRACT_VERSION
        )
        self.assertEqual(report["source_commitments"]["dataset_id"], "4pq5-n9py")
        self.assertEqual(morphology["facility_count"], 3)
        self.assertEqual(
            margins["certified_beds"]["summary"],
            {
                "n": 3,
                "missing": 0,
                "min": 50.0,
                "q25": 53.5,
                "median": 57.0,
                "mean": 64.0,
                "q75": 71.0,
                "max": 85.0,
            },
        )
        self.assertEqual(
            margins["total_nurse_hprd"]["summary"]["median"], 4.40675
        )
        turnover = margins["total_nursing_staff_turnover_pct"]
        self.assertEqual(turnover["summary"]["n"], 2)
        self.assertEqual(turnover["missingness"]["missing"], 1)
        self.assertEqual(
            turnover["missingness"]["footnote_counts_on_missing"], {"26": 1}
        )

        occupancy = morphology["derived_margins"]["occupancy_ratio"]
        self.assertEqual(occupancy["summary"]["median"], 0.919298)
        self.assertEqual(
            occupancy["evidence_class"],
            "derived_from_two_values_in_pinned_cms_source",
        )

    def test_contact_structure_is_explicitly_unidentifiable(self):
        report = build_cms_nh_morphology_report(_CSV, _METADATA)
        boundary = report["scientific_v3_morphology"][
            "unidentifiable_ward_and_contact_structure"
        ]

        self.assertEqual(boundary["status"], "not_identified_by_provider_information")
        self.assertIn("number of wards or units", boundary["items"])
        self.assertIn("staff-to-resident contact edges", boundary["items"])
        self.assertIn("must not be reported as CMS-observed", boundary["simulation_guardrail"])

        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn("facility_records", report["scientific_v3_morphology"])
        self.assertNotIn("BURNS NURSING HOME", serialized)
        self.assertNotIn("015068", serialized)
        self.assertFalse(
            report["scientific_v3_morphology"]["identity_guardrail"]
            ["ccn_or_provider_name_emitted"]
        )
        self.assertEqual(
            report["admissibility"]["agent_visibility"],
            "trusted_offline_only",
        )
        self.assertFalse(
            report["admissibility"]["simulation_conditioning_admissible"]
        )

    def test_monthly_vintage_does_not_relabel_turnover_as_monthly(self):
        report = build_cms_nh_morphology_report(_CSV, _METADATA)
        temporal = report["temporal_semantics"]

        self.assertEqual(
            temporal["file_vintage"]["publication_frequency"], "monthly_refresh"
        )
        self.assertTrue(
            temporal["by_measure_group"]["turnover"]["is_annual"]
        )
        self.assertFalse(
            temporal["by_measure_group"]["turnover"]["exact_interval_known"]
        )
        self.assertIn(
            "must not be substituted", temporal["guardrail"]
        )

    def test_source_and_report_hashes_are_recomputable(self):
        report = build_cms_nh_morphology_report(_CSV, _METADATA)

        self.assertEqual(
            report["source_commitments"]["csv_sha256"],
            "sha256:" + hashlib.sha256(_CSV.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["source_commitments"]["metadata_sha256"],
            "sha256:" + hashlib.sha256(_METADATA.read_bytes()).hexdigest(),
        )
        supplied = report.pop("report_sha256")
        expected = hashlib.sha256(
            json.dumps(
                report,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(supplied, f"sha256:{expected}")

    def test_declared_legacy_ccn_alias_is_accepted_but_ambiguity_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            aliased_csv, aliased_metadata = _pinned_copy(
                temp,
                csv_transform=lambda text: text.replace(
                    "CMS Certification Number (CCN)",
                    "Federal Provider Number",
                    1,
                ),
            )
            report = build_cms_nh_morphology_report(
                aliased_csv, aliased_metadata
            )
            self.assertEqual(
                report["parser_commitments"]["resolved_source_columns"]["ccn"],
                "Federal Provider Number",
            )

        with tempfile.TemporaryDirectory() as temp:
            ambiguous_csv, ambiguous_metadata = _pinned_copy(
                temp, csv_transform=_add_ambiguous_ccn_alias
            )
            with self.assertRaisesRegex(ValueError, "ambiguously maps logical field 'ccn'"):
                build_cms_nh_morphology_report(
                    ambiguous_csv, ambiguous_metadata
                )

    def test_hash_pin_schema_drift_and_processing_date_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path = Path(temp) / _CSV.name
            metadata_path = Path(temp) / _METADATA.name
            csv_path.write_bytes(
                _CSV.read_bytes().replace(b"BURNS", b"TURNS", 1)
            )
            metadata_path.write_bytes(_METADATA.read_bytes())
            with self.assertRaisesRegex(ValueError, "sha256"):
                build_cms_nh_morphology_report(csv_path, metadata_path)

        with tempfile.TemporaryDirectory() as temp:
            drift_csv, drift_metadata = _pinned_copy(
                temp,
                csv_transform=lambda text: text.replace(
                    "Total nursing staff turnover,",
                    "Unrecognized turnover field,",
                    1,
                ),
            )
            with self.assertRaisesRegex(
                ValueError,
                "missing expected logical fields: total_nursing_staff_turnover_pct",
            ):
                build_cms_nh_morphology_report(drift_csv, drift_metadata)

        with tempfile.TemporaryDirectory() as temp:
            dated_csv, dated_metadata = _pinned_copy(
                temp,
                csv_transform=lambda text: text.replace(
                    "2026-06-01\n", "2026-05-01\n", 1
                ),
            )
            with self.assertRaisesRegex(ValueError, "Processing Date"):
                build_cms_nh_morphology_report(dated_csv, dated_metadata)

    def test_public_vintage_cannot_be_labeled_holdout_or_non_cms(self):
        def make_public_holdout(metadata):
            metadata["benchmark_use"]["holdout"] = True
            metadata["benchmark_use"]["role"] = "private_holdout"

        with tempfile.TemporaryDirectory() as temp:
            csv_path, metadata_path = _pinned_copy(
                temp, metadata_transform=make_public_holdout
            )
            with self.assertRaisesRegex(ValueError, "public development evidence"):
                build_cms_nh_morphology_report(csv_path, metadata_path)

        def make_fake_private_holdout(metadata):
            metadata["benchmark_use"] = {
                "visibility": "private",
                "role": "private_holdout",
                "holdout": True,
            }

        with tempfile.TemporaryDirectory() as temp:
            csv_path, metadata_path = _pinned_copy(
                temp, metadata_transform=make_fake_private_holdout
            )
            with self.assertRaisesRegex(ValueError, "public development evidence"):
                build_cms_nh_morphology_report(csv_path, metadata_path)

        def change_source(metadata):
            metadata["source"]["dataset_id"] = "not-cms-provider-info"

        with tempfile.TemporaryDirectory() as temp:
            csv_path, metadata_path = _pinned_copy(
                temp, metadata_transform=change_source
            )
            with self.assertRaisesRegex(ValueError, "official Provider Data Catalog"):
                build_cms_nh_morphology_report(csv_path, metadata_path)

    def test_vintage_ordering_is_fail_closed(self):
        def time_travel(metadata):
            metadata["vintage"]["release_date"] = "2026-06-25"
            metadata["artifact"]["retrieved_at"] = "2026-06-24T00:00:00Z"

        with tempfile.TemporaryDirectory() as temp:
            csv_path, metadata_path = _pinned_copy(
                temp, metadata_transform=time_travel
            )
            with self.assertRaisesRegex(ValueError, "processing_date <="):
                build_cms_nh_morphology_report(csv_path, metadata_path)

    def test_dependency_free_cli_writes_report_from_explicit_paths(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            output = Path(temp) / "cms-morphology.json"
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
            saved["source_commitments"]["dataset_id"],
            CMS_PROVIDER_INFORMATION_DATASET_ID,
        )
        self.assertEqual(
            saved["parser_commitments"]["input_access"],
            "two caller-supplied local paths only; no network access, latest-release discovery, archive lookup, or holdout lookup",
        )

    def test_cli_cannot_overwrite_an_input_or_follow_alias_to_one(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path, metadata_path = _pinned_copy(temp)
            original = csv_path.read_bytes()
            with redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "must not overwrite"):
                    main(
                        [
                            "--csv",
                            str(csv_path),
                            "--metadata",
                            str(metadata_path),
                            "--output",
                            str(csv_path),
                        ]
                    )
            self.assertEqual(csv_path.read_bytes(), original)

            alias = Path(temp) / "report-alias.json"
            alias.symlink_to(metadata_path)
            with redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "must not overwrite"):
                    main(
                        [
                            "--csv",
                            str(csv_path),
                            "--metadata",
                            str(metadata_path),
                            "--output",
                            str(alias),
                        ]
                    )


if __name__ == "__main__":
    unittest.main()
