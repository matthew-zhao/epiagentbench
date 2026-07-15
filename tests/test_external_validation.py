from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from epiagentbench.external_validation import (
    ADAMS_HEADERS,
    ADAMS_S1_SHA256,
    REFERENCE_VERSION,
    CurveShapeCase,
    compare_simulated_curve_shapes,
    parse_adams_line_list,
    parse_adams_line_list_bytes,
    parse_simulated_reported_line_list,
    summarize_curve_shapes,
)


def _csv_bytes(rows: list[dict[str, str]], headers=ADAMS_HEADERS) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def _source_row(
    outbreak: int,
    onset: int | None,
    *,
    index: int,
    resident: str = "1",
    vomit: str = "1",
    diarrhea: str = "1",
) -> dict[str, str]:
    row = {header: "" for header in ADAMS_HEADERS}
    row.update(
        {
            "Outbreak_Number": str(outbreak),
            "Onset_Day": "" if onset is None else str(onset),
            "Index": str(index),
            "Diarrhea": diarrhea,
            "Vomit": vomit,
            "Resident": resident,
            "log_R_1.5": "#NUM!",
        }
    )
    return row


def _reference(cases: tuple[CurveShapeCase, ...]) -> dict:
    report = {
        "reference_version": REFERENCE_VERSION,
        "evidence_role": "visible_narrow_external_reference",
        "blind_holdout": False,
        "summary": summarize_curve_shapes(cases),
    }
    report["report_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    return report


class AdamsExternalValidationTests(unittest.TestCase):
    def test_strict_parser_accepts_missing_values_and_published_num_marker(self):
        data = _csv_bytes(
            [
                _source_row(1, 1, index=1),
                _source_row(
                    1, 2, index=0, resident="", vomit="0", diarrhea=""
                ),
            ]
        )

        rows = parse_adams_line_list_bytes(data)

        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].is_index)
        self.assertIsNone(rows[1].is_resident)
        self.assertFalse(rows[1].vomited)
        self.assertIsNone(rows[1].diarrhea)

    def test_parser_rejects_schema_type_and_index_inconsistency(self):
        wrong_headers = ADAMS_HEADERS[:-1]
        with self.assertRaisesRegex(ValueError, "schema"):
            parse_adams_line_list_bytes(_csv_bytes([], wrong_headers))

        bad_binary = _source_row(1, 1, index=1, vomit="2")
        with self.assertRaisesRegex(ValueError, "Vomit"):
            parse_adams_line_list_bytes(_csv_bytes([bad_binary]))

        inconsistent = [
            _source_row(1, 1, index=0),
            _source_row(1, 2, index=1),
        ]
        with self.assertRaisesRegex(ValueError, "Index field"):
            parse_adams_line_list_bytes(_csv_bytes(inconsistent))

    def test_nonofficial_fixture_cannot_be_mislabeled_as_pinned_snapshot(self):
        data = _csv_bytes([_source_row(1, 1, index=1)])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "not-the-published-file.csv"
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "pinned snapshot"):
                parse_adams_line_list(path)
        self.assertEqual(len(ADAMS_S1_SHA256), 64)

    def test_metric_contract_uses_earliest_peak_and_explicit_denominators(self):
        cases = (
            CurveShapeCase("a", "1", 1, True, True, True),
            CurveShapeCase("a", "2", 2, False, True, False),
            CurveShapeCase("a", "3", 2, None, None, True),
            CurveShapeCase("a", "4", 3, True, False, None),
            CurveShapeCase("b", "1", 5, None, None, None),
        )

        summary = summarize_curve_shapes(cases)
        outbreak = summary["outbreak_rows"][0]

        self.assertEqual(outbreak["duration_days"], 3)
        self.assertEqual(outbreak["peak_timing_fraction"], 0.5)
        self.assertEqual(outbreak["peak_case_fraction"], 0.5)
        self.assertAlmostEqual(outbreak["resident_fraction"], 2 / 3, places=6)
        self.assertEqual(outbreak["resident_status_missing"], 1)
        self.assertEqual(outbreak["vomiting_known"], 3)
        self.assertEqual(outbreak["joint_symptoms_known"], 2)
        self.assertEqual(
            summary["metrics"]["duration_days"]["values"], [3, 1]
        )

    def test_comparison_is_descriptive_and_surfaces_unsupported_features(self):
        target_cases = (
            CurveShapeCase("t", "1", 1, True, True, True),
            CurveShapeCase("t", "2", 2, False, False, True),
        )
        simulated = parse_simulated_reported_line_list(
            [
                {
                    "outbreak_id": "s",
                    "case_id": "1",
                    "onset_day": 1,
                    "is_resident": None,
                    "vomited": None,
                    "diarrhea": None,
                },
                {
                    "outbreak_id": "s",
                    "case_id": "2",
                    "onset_day": 3,
                    "is_resident": None,
                    "vomited": None,
                    "diarrhea": None,
                },
            ]
        )

        result = compare_simulated_curve_shapes(
            simulated, _reference(target_cases), candidate_label="fixture"
        )

        self.assertIsNone(result["composite_score"])
        self.assertIsNone(result["pass_fail_gate"])
        self.assertEqual(
            result["metric_comparisons"]["duration_days"]["status"],
            "descriptive_only",
        )
        self.assertEqual(
            result["metric_comparisons"]["resident_fraction"]["status"],
            "not_comparable",
        )
        self.assertFalse(result["blind_holdout"])

    def test_simulated_parser_rejects_extra_fields_and_duplicate_cases(self):
        valid = {
            "outbreak_id": "s",
            "case_id": "1",
            "onset_day": 1,
            "is_resident": None,
            "vomited": None,
            "diarrhea": None,
        }
        with self.assertRaisesRegex(ValueError, "wrong schema"):
            parse_simulated_reported_line_list([{**valid, "oracle": "leak"}])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_simulated_reported_line_list([valid, valid])


if __name__ == "__main__":
    unittest.main()
