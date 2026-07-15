"""Pinned CMS nursing-home facility-morphology data contract.

The contract consumes exactly two caller-supplied local files: a CMS Provider
Information CSV and matching JSON source metadata.  It never discovers,
downloads, or selects a newer release.  Public releases are development
evidence and cannot be labeled as a private holdout.

The output deliberately separates margins present in Provider Information
(beds, average census, reported staffing, and turnover) from ward layouts and
contact structure, which this source cannot identify.

Run the dependency-free CLI with::

    python -m epiagentbench.cms_nh_morphology \
        --csv NH_ProviderInfo_MonYYYY.csv \
        --metadata NH_ProviderInfo_MonYYYY.metadata.json
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import unicodedata


CMS_NH_MORPHOLOGY_CONTRACT_VERSION = (
    "cms_nh_provider_information_morphology_v1"
)
CMS_SOURCE_METADATA_CONTRACT_VERSION = (
    "cms_nh_provider_information_source_v1"
)
CMS_PROVIDER_INFORMATION_DATASET_ID = "4pq5-n9py"
CMS_PROVIDER_INFORMATION_TITLE = "Provider Information"
CMS_AUTHORITY = "Centers for Medicare & Medicaid Services (CMS)"
CMS_CATALOG = "Provider Data Catalog"
CMS_PROVIDER_INFORMATION_PAGE = (
    "https://data.cms.gov/provider-data/dataset/4pq5-n9py"
)
CMS_NURSING_HOME_DATA_DICTIONARY = (
    "https://data.cms.gov/provider-data/sites/default/files/"
    "data_dictionaries/nursing_home/NH_Data_Dictionary.pdf"
)
CMS_ALIAS_PROFILE = "cms_nh_provider_information_aliases_v1"


@dataclass(frozen=True, slots=True)
class _FieldSpec:
    key: str
    aliases: tuple[str, ...]
    kind: str


@dataclass(frozen=True, slots=True)
class _MetricSpec:
    key: str
    label: str
    unit: str
    temporal_group: str
    source_definition: str
    footnote_field: str | None = None


# These aliases are declarations, not fuzzy guesses.  The human-readable CSV
# headers and PDC API-style snake-case forms normalize to the same keys.  The
# one legacy CCN label is retained because it appeared in official CMS nursing
# home files; arbitrary user aliases are never accepted from metadata.
_FIELD_SPECS: tuple[_FieldSpec, ...] = (
    _FieldSpec(
        "ccn",
        (
            "CMS Certification Number (CCN)",
            "cms_certification_number_ccn",
            "Federal Provider Number",
        ),
        "ccn",
    ),
    _FieldSpec("provider_name", ("Provider Name", "provider_name"), "text"),
    _FieldSpec(
        "certified_beds",
        ("Number of Certified Beds", "number_of_certified_beds"),
        "nonnegative_integer",
    ),
    _FieldSpec(
        "average_residents_per_day",
        (
            "Average Number of Residents per Day",
            "average_number_of_residents_per_day",
        ),
        "nonnegative_number",
    ),
    _FieldSpec(
        "average_residents_per_day_footnote",
        (
            "Average Number of Residents per Day Footnote",
            "average_number_of_residents_per_day_footnote",
        ),
        "footnote",
    ),
    _FieldSpec(
        "reported_staffing_footnote",
        ("Reported Staffing Footnote", "reported_staffing_footnote"),
        "footnote",
    ),
    _FieldSpec(
        "nurse_aide_hprd",
        (
            "Reported Nurse Aide Staffing Hours per Resident per Day",
            "reported_nurse_aide_staffing_hours_per_resident_per_day",
        ),
        "nonnegative_number",
    ),
    _FieldSpec(
        "lpn_hprd",
        (
            "Reported LPN Staffing Hours per Resident per Day",
            "reported_lpn_staffing_hours_per_resident_per_day",
        ),
        "nonnegative_number",
    ),
    _FieldSpec(
        "rn_hprd",
        (
            "Reported RN Staffing Hours per Resident per Day",
            "reported_rn_staffing_hours_per_resident_per_day",
        ),
        "nonnegative_number",
    ),
    _FieldSpec(
        "licensed_nurse_hprd",
        (
            "Reported Licensed Staffing Hours per Resident per Day",
            "reported_licensed_staffing_hours_per_resident_per_day",
        ),
        "nonnegative_number",
    ),
    _FieldSpec(
        "total_nurse_hprd",
        (
            "Reported Total Nurse Staffing Hours per Resident per Day",
            "reported_total_nurse_staffing_hours_per_resident_per_day",
        ),
        "nonnegative_number",
    ),
    _FieldSpec(
        "weekend_total_nurse_hprd",
        (
            "Total number of nurse staff hours per resident per day on the weekend",
            "total_number_of_nurse_staff_hours_per_resident_per_day_on_the_weekend",
        ),
        "nonnegative_number",
    ),
    _FieldSpec(
        "weekend_rn_hprd",
        (
            "Registered Nurse hours per resident per day on the weekend",
            "registered_nurse_hours_per_resident_per_day_on_the_weekend",
        ),
        "nonnegative_number",
    ),
    _FieldSpec(
        "physical_therapist_hprd",
        (
            "Reported Physical Therapist Staffing Hours per Resident Per Day",
            "reported_physical_therapist_staffing_hours_per_resident_per_day",
        ),
        "nonnegative_number",
    ),
    _FieldSpec(
        "total_nursing_staff_turnover_pct",
        ("Total nursing staff turnover", "total_nursing_staff_turnover"),
        "percentage",
    ),
    _FieldSpec(
        "total_nursing_staff_turnover_footnote",
        (
            "Total nursing staff turnover footnote",
            "total_nursing_staff_turnover_footnote",
        ),
        "footnote",
    ),
    _FieldSpec(
        "rn_turnover_pct",
        ("Registered Nurse turnover", "registered_nurse_turnover"),
        "percentage",
    ),
    _FieldSpec(
        "rn_turnover_footnote",
        (
            "Registered Nurse turnover footnote",
            "registered_nurse_turnover_footnote",
        ),
        "footnote",
    ),
    _FieldSpec(
        "administrator_departures",
        (
            "Number of administrators who have left the nursing home",
            "number_of_administrators_who_have_left_the_nursing_home",
        ),
        "nonnegative_integer",
    ),
    _FieldSpec(
        "administrator_turnover_footnote",
        (
            "Administrator turnover footnote",
            "administrator_turnover_footnote",
        ),
        "footnote",
    ),
    _FieldSpec(
        "processing_date", ("Processing Date", "processing_date"), "date"
    ),
)
_FIELD_BY_KEY = {spec.key: spec for spec in _FIELD_SPECS}

# Scientific-v3 requires these columns to be explicitly committed by source
# metadata.  Cells may be missing and are counted; a missing/renamed column is
# schema drift and is rejected instead of being mistaken for ordinary
# facility-level missingness.
_SCIENTIFIC_V3_FIELDS = frozenset(spec.key for spec in _FIELD_SPECS)

_METRIC_SPECS: tuple[_MetricSpec, ...] = (
    _MetricSpec(
        "certified_beds",
        "federally certified beds",
        "beds",
        "certified_beds",
        "CMS Provider Information: Number of Federally Certified Beds.",
    ),
    _MetricSpec(
        "average_residents_per_day",
        "average resident census",
        "residents_per_day",
        "average_resident_census",
        "CMS Provider Information: average residents based on MDS daily census.",
        "average_residents_per_day_footnote",
    ),
    _MetricSpec(
        "nurse_aide_hprd",
        "reported nurse aide staffing",
        "hours_per_resident_day",
        "staffing_hprd",
        "Reported nurse aide staffing hours per resident per day.",
        "reported_staffing_footnote",
    ),
    _MetricSpec(
        "lpn_hprd",
        "reported LPN staffing",
        "hours_per_resident_day",
        "staffing_hprd",
        "Reported LPN staffing hours per resident per day.",
        "reported_staffing_footnote",
    ),
    _MetricSpec(
        "rn_hprd",
        "reported RN staffing",
        "hours_per_resident_day",
        "staffing_hprd",
        "Reported RN staffing hours per resident per day.",
        "reported_staffing_footnote",
    ),
    _MetricSpec(
        "licensed_nurse_hprd",
        "reported licensed nurse staffing",
        "hours_per_resident_day",
        "staffing_hprd",
        "Reported licensed staffing hours per resident per day (RN plus LPN).",
        "reported_staffing_footnote",
    ),
    _MetricSpec(
        "total_nurse_hprd",
        "reported total nurse staffing",
        "hours_per_resident_day",
        "staffing_hprd",
        "Reported total nurse staffing hours per resident per day (aide, LPN, and RN).",
        "reported_staffing_footnote",
    ),
    _MetricSpec(
        "weekend_total_nurse_hprd",
        "reported weekend total nurse staffing",
        "hours_per_resident_day",
        "staffing_hprd",
        "Reported total nurse staff hours per resident per weekend day.",
        "reported_staffing_footnote",
    ),
    _MetricSpec(
        "weekend_rn_hprd",
        "reported weekend RN staffing",
        "hours_per_resident_day",
        "staffing_hprd",
        "Reported RN hours per resident per weekend day.",
        "reported_staffing_footnote",
    ),
    _MetricSpec(
        "physical_therapist_hprd",
        "reported physical therapist staffing",
        "hours_per_resident_day",
        "staffing_hprd",
        "Reported physical therapist staffing hours per resident per day.",
    ),
    _MetricSpec(
        "total_nursing_staff_turnover_pct",
        "total nursing staff turnover",
        "percent",
        "turnover",
        "CMS annual turnover measure for total nursing staff.",
        "total_nursing_staff_turnover_footnote",
    ),
    _MetricSpec(
        "rn_turnover_pct",
        "registered nurse turnover",
        "percent",
        "turnover",
        "CMS annual turnover measure for registered nurses.",
        "rn_turnover_footnote",
    ),
    _MetricSpec(
        "administrator_departures",
        "administrator departures",
        "administrators",
        "turnover",
        "Number of administrators who left the nursing home.",
        "administrator_turnover_footnote",
    ),
)

_MISSING_NUMERIC_TOKENS = frozenset(
    {"", "na", "n/a", "not available", "null", "--", "---"}
)

# Relevant definitions are copied as compact parser/report commitments from
# Table 15 of the official CMS Nursing Home data dictionary.  Unknown numeric
# footnotes are retained, never guessed.
_CMS_FOOTNOTE_DEFINITIONS: Mapping[str, str] = {
    "1": "newly certified facility or insufficient history",
    "2": "not enough data to calculate a star rating",
    "6": "submitted data did not meet staffing-measure criteria",
    "7": "CMS found a percentage inaccurate or suppressed one or more quarters",
    "9": "resident or stay count too small to report",
    "10": "measure data missing or not submitted",
    "13": "results use a shorter period than required",
    "20": "rating data accuracy could not be validated by CMS",
    "21": "measure data accuracy could not be validated by CMS",
    "23": "facility did not submit staffing data",
    "24": "facility reported many days without an RN onsite",
    "25": "staffing-measure accuracy could not be validated by CMS",
    "26": "staffing data absent or invalid for turnover calculation",
    "27": "staffing data did not meet turnover calculation criteria",
    "28": "annual measure; individual-quarter data unavailable",
}

_UNIDENTIFIABLE_STRUCTURE = (
    "number of wards or units",
    "beds and residents assigned to each ward",
    "room assignments or roommates",
    "resident-to-resident contact edges",
    "staff-to-resident contact edges",
    "staff shift rosters and temporal contact schedules",
    "staff sharing between wards",
    "visitor contact networks",
    "spatial proximity, ventilation, and airflow",
    "infection states, transmission rates, and intervention effects",
)


def build_cms_nh_morphology_report(
    csv_path: str | Path,
    metadata_path: str | Path,
) -> dict[str, Any]:
    """Validate pinned inputs and build a deterministic morphology report."""

    # There is intentionally no URL, discovery, archive, or "latest" branch in
    # this function.  Only these two explicit local paths are resolved/opened.
    csv_file = Path(csv_path).resolve(strict=True)
    metadata_file = Path(metadata_path).resolve(strict=True)
    metadata = _load_and_validate_metadata(metadata_file)
    _verify_pinned_artifact(csv_file, metadata)

    expected_fields = frozenset(metadata["schema"]["expected_logical_fields"])
    facilities, resolved_columns, extra_columns = _read_facilities(
        csv_file,
        expected_fields=expected_fields,
        expected_processing_date=metadata["vintage"]["processing_date"],
    )
    if len(facilities) != metadata["artifact"]["rows"]:
        raise ValueError(
            "CMS CSV row count does not match pinned source metadata"
        )

    temporal = {
        key: dict(value)
        for key, value in metadata["temporal_semantics"].items()
    }
    observed_margins = {
        spec.key: _metric_report(
            facilities,
            spec,
            source_column=resolved_columns[spec.key],
            temporal_status=temporal[spec.temporal_group],
        )
        for spec in _METRIC_SPECS
    }
    occupancy = _occupancy_report(facilities, temporal)
    # These normalized rows remain inside this trusted/offline adapter.  The
    # report exposes aggregate margins and a commitment, never CCNs or provider
    # names that a benchmark episode could accidentally reveal to an agent.
    trusted_facility_rows = [_trusted_facility_row(row) for row in facilities]

    report: dict[str, Any] = {
        "contract_version": CMS_NH_MORPHOLOGY_CONTRACT_VERSION,
        "scope_label": (
            "development-only CMS facility-margin diagnostic; not a "
            "simulation calibration or episode-generation input"
        ),
        "admissibility": {
            "agent_visibility": "trusted_offline_only",
            "scientific_use_authorized": False,
            "simulation_conditioning_admissible": False,
            "episode_generation_admissible": False,
            "requires_integration_as_of_cutoff_check": True,
            "reason": (
                "The adapter validates a caller-supplied public artifact, "
                "but it does not authenticate acquisition, define a sampling "
                "estimand, recover missing collection intervals, or prove "
                "that its release predates a candidate episode."
            ),
        },
        "source_commitments": {
            "authority": CMS_AUTHORITY,
            "catalog": CMS_CATALOG,
            "dataset_id": CMS_PROVIDER_INFORMATION_DATASET_ID,
            "dataset_title": CMS_PROVIDER_INFORMATION_TITLE,
            "landing_page_url": CMS_PROVIDER_INFORMATION_PAGE,
            "data_dictionary_url": CMS_NURSING_HOME_DATA_DICTIONARY,
            "csv_filename": csv_file.name,
            "csv_bytes": csv_file.stat().st_size,
            "csv_sha256": f"sha256:{_file_sha256(csv_file)}",
            "metadata_filename": metadata_file.name,
            "metadata_sha256": f"sha256:{_file_sha256(metadata_file)}",
            "artifact_kind": metadata["artifact"]["kind"],
            "retrieved_at": metadata["artifact"]["retrieved_at"],
            "vintage": dict(metadata["vintage"]),
            "benchmark_use": dict(metadata["benchmark_use"]),
            "source_row_count": len(facilities),
            "source_scope_note": metadata["source"].get(
                "projection_note",
                "Pinned CMS Provider Information artifact.",
            ),
            "integrity_claim": (
                "The local CSV matches the size and SHA-256 value in the "
                "caller-supplied metadata."
            ),
            "authenticity_claim": (
                "not established; caller-supplied hashes do not prove that "
                "the artifact was acquired from CMS"
            ),
        },
        "parser_commitments": {
            "input_access": (
                "two caller-supplied local paths only; no network access, "
                "latest-release discovery, archive lookup, or holdout lookup"
            ),
            "text_encoding": "UTF-8 with optional BOM (utf-8-sig)",
            "csv_parser": "Python standard-library csv.DictReader",
            "schema_profile": CMS_ALIAS_PROFILE,
            "field_aliases": {
                spec.key: list(spec.aliases) for spec in _FIELD_SPECS
            },
            "header_matching": (
                "Unicode NFKC, case-insensitive alphanumeric token matching "
                "against only the declared aliases; ambiguous matches fail"
            ),
            "expected_logical_fields": sorted(expected_fields),
            "resolved_source_columns": dict(sorted(resolved_columns.items())),
            "ignored_extra_columns": extra_columns,
            "missing_numeric_tokens": sorted(_MISSING_NUMERIC_TOKENS),
            "missingness_policy": (
                "missing cells remain null and are counted; no imputation, "
                "zero fill, row deletion, or footnote reinterpretation"
            ),
            "numeric_policy": (
                "finite base-10 values only; counts must be nonnegative "
                "integers, other margins nonnegative, and percentages 0-100"
            ),
            "ccn_policy": (
                "six alphanumeric characters preserved as text, including "
                "leading zeroes; duplicate CCNs fail"
            ),
            "occupancy_formula": (
                "average_residents_per_day / certified_beds when census is "
                "present and certified beds are positive; no clipping"
            ),
            "summary_policy": (
                "all pinned rows are denominators; quantiles use linear "
                "interpolation at (n-1)*p (Hyndman-Fan type 7); outputs "
                "round to six decimal places"
            ),
        },
        "temporal_semantics": {
            "file_vintage": dict(metadata["vintage"]),
            "by_measure_group": temporal,
            "guardrail": (
                "A monthly file refresh is not a monthly measurement window. "
                "Turnover is annual. Where exact intervals are unknown, the "
                "release or processing date must not be substituted for them."
            ),
            "episode_cutoff_guardrail": (
                "A downstream trusted builder must prove that this source's "
                "release date is no later than the episode's as-of cutoff. "
                "This standalone report intentionally cannot make that proof."
            ),
        },
        "sampling_scope": {
            "status": "not_defined_by_this_adapter",
            "estimand": None,
            "national_representativeness_claim": False,
            "guardrail": (
                "Rows are exactly the pinned caller-supplied artifact. A "
                "sampling frame, inclusion rule, and target estimand must be "
                "frozen separately before these margins support calibration."
            ),
        },
        "scientific_v3_morphology": {
            "unit": "one active CMS-certified nursing home row",
            "facility_count": len(facilities),
            "observed_facility_margins": observed_margins,
            "derived_margins": {"occupancy_ratio": occupancy},
            "trusted_source_record_count": len(trusted_facility_rows),
            "identity_guardrail": {
                "ccn_or_provider_name_emitted": False,
                "agent_visible_records_emitted": False,
                "policy": (
                    "Facility identifiers and row-level records stay inside "
                    "the trusted/offline adapter."
                ),
            },
            "unidentifiable_ward_and_contact_structure": {
                "status": "not_identified_by_provider_information",
                "items": list(_UNIDENTIFIABLE_STRUCTURE),
                "simulation_guardrail": (
                    "These elements require a separate source or an explicitly "
                    "labeled modeling assumption. Simulator-generated topology "
                    "must not be reported as CMS-observed or CMS-calibrated."
                ),
            },
        },
        "report_commitments": {
            "normalized_facility_rows_sha256": (
                f"sha256:{_canonical_sha256(trusted_facility_rows)}"
            ),
            "alias_registry_sha256": (
                f"sha256:{_canonical_sha256({spec.key: spec.aliases for spec in _FIELD_SPECS})}"
            ),
            "footnote_definitions": dict(_CMS_FOOTNOTE_DEFINITIONS),
            "canonical_json": (
                "UTF-8 JSON, sorted keys, compact separators, NaN forbidden"
            ),
        },
    }
    report["report_sha256"] = f"sha256:{_canonical_sha256(report)}"
    return report


def _load_and_validate_metadata(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_bytes(),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("Invalid CMS source metadata") from exc
    if not isinstance(value, dict):
        raise ValueError("CMS source metadata must be a JSON object")
    if value.get("contract_version") != CMS_SOURCE_METADATA_CONTRACT_VERSION:
        raise ValueError("Unsupported CMS source metadata contract_version")

    source = _object(value, "source")
    exact_source = {
        "authority": CMS_AUTHORITY,
        "catalog": CMS_CATALOG,
        "dataset_id": CMS_PROVIDER_INFORMATION_DATASET_ID,
        "dataset_title": CMS_PROVIDER_INFORMATION_TITLE,
        "landing_page_url": CMS_PROVIDER_INFORMATION_PAGE,
        "data_dictionary_url": CMS_NURSING_HOME_DATA_DICTIONARY,
    }
    for key, expected in exact_source.items():
        if source.get(key) != expected:
            raise ValueError(
                f"CMS source metadata {key!r} is not the official "
                "Provider Data Catalog commitment"
            )
    projection_note = source.get("projection_note")
    if projection_note is not None and not _clean_text(projection_note):
        raise ValueError("CMS source projection_note must be nonempty")

    artifact = _object(value, "artifact")
    filename = artifact.get("filename")
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise ValueError("CMS artifact filename must be a basename")
    if artifact.get("kind") not in {
        "full_provider_information_csv",
        "filtered_provider_information_csv",
        "development_fixture_projection",
    }:
        raise ValueError("CMS artifact kind is not supported")
    if not _is_sha256_commitment(artifact.get("sha256")):
        raise ValueError("CMS artifact has no valid sha256 commitment")
    if type(artifact.get("bytes")) is not int or artifact["bytes"] <= 0:
        raise ValueError("CMS artifact has no valid byte-size commitment")
    if type(artifact.get("rows")) is not int or artifact["rows"] <= 0:
        raise ValueError("CMS artifact has no valid row-count commitment")
    retrieved_at = _parse_timestamp(
        artifact.get("retrieved_at"), "artifact retrieved_at"
    )

    use = _object(value, "benchmark_use")
    visibility = use.get("visibility")
    role = use.get("role")
    holdout = use.get("holdout")
    if type(holdout) is not bool:
        raise ValueError("CMS benchmark_use holdout must be boolean")
    if visibility != "public" or role != "development_evidence" or holdout:
        raise ValueError(
            "CMS Provider Information is public development evidence and "
            "cannot be declared private, held out, or production evaluation data"
        )

    schema = _object(value, "schema")
    if schema.get("profile") != CMS_ALIAS_PROFILE:
        raise ValueError("Unsupported CMS schema alias profile")
    fields = schema.get("expected_logical_fields")
    if not isinstance(fields, list) or any(
        not isinstance(field, str) for field in fields
    ):
        raise ValueError("CMS schema expected_logical_fields must be a list")
    if len(fields) != len(set(fields)):
        raise ValueError("CMS schema repeats an expected logical field")
    unknown = sorted(set(fields) - set(_FIELD_BY_KEY))
    if unknown:
        raise ValueError(
            "CMS schema has unknown logical fields: " + ", ".join(unknown)
        )
    missing_profile = sorted(_SCIENTIFIC_V3_FIELDS - set(fields))
    if missing_profile:
        raise ValueError(
            "CMS scientific-v3 schema omits fields: "
            + ", ".join(missing_profile)
        )

    vintage = _object(value, "vintage")
    last_modified_date = _parse_date(
        vintage.get("last_modified_date"), "vintage last_modified_date"
    )
    release_date = _parse_date(
        vintage.get("release_date"), "vintage release_date"
    )
    processing_date = _parse_date(
        vintage.get("processing_date"), "vintage processing_date"
    )
    if not (
        processing_date
        <= last_modified_date
        <= release_date
        <= retrieved_at.date()
    ):
        raise ValueError(
            "CMS source dates must satisfy processing_date <= "
            "last_modified_date <= release_date <= retrieved_at"
        )
    if vintage.get("publication_frequency") != "monthly_refresh":
        raise ValueError("CMS vintage must declare monthly_refresh")

    temporal = _object(value, "temporal_semantics")
    required_temporal = {
        "certified_beds": ("release_vintage_snapshot", False),
        "average_resident_census": ("period_average", None),
        "staffing_hprd": ("period_average", False),
        "turnover": ("annual_measure", True),
    }
    if set(temporal) != set(required_temporal):
        raise ValueError("CMS temporal_semantics has the wrong measure groups")
    for group, (kind, annual) in required_temporal.items():
        entry = temporal[group]
        if not isinstance(entry, dict):
            raise ValueError(f"CMS temporal group {group!r} must be an object")
        if entry.get("kind") != kind or entry.get("is_annual") is not annual:
            raise ValueError(f"CMS temporal group {group!r} is inconsistent")
        known = entry.get("exact_interval_known")
        if type(known) is not bool:
            raise ValueError(
                f"CMS temporal group {group!r} needs exact_interval_known"
            )
        start = entry.get("period_start")
        end = entry.get("period_end")
        if known:
            start_date = _parse_date(start, f"{group} period_start")
            end_date = _parse_date(end, f"{group} period_end")
            if start_date > end_date:
                raise ValueError(f"CMS temporal group {group!r} has reversed dates")
        elif start is not None or end is not None:
            raise ValueError(
                f"CMS temporal group {group!r} gives dates but marks them unknown"
            )
        if not _clean_text(entry.get("source_note")):
            raise ValueError(f"CMS temporal group {group!r} needs a source_note")
    return value


def _verify_pinned_artifact(path: Path, metadata: Mapping[str, Any]) -> None:
    artifact = metadata["artifact"]
    if path.name != artifact["filename"]:
        raise ValueError("CMS CSV filename does not match pinned source metadata")
    if path.stat().st_size != artifact["bytes"]:
        raise ValueError("CMS CSV byte size does not match pinned source metadata")
    actual = f"sha256:{_file_sha256(path)}"
    if actual != artifact["sha256"]:
        raise ValueError("CMS CSV sha256 does not match pinned source metadata")


def _read_facilities(
    path: Path,
    *,
    expected_fields: frozenset[str],
    expected_processing_date: str,
) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames is None:
            raise ValueError("CMS CSV has no header")
        resolved, extras = _resolve_columns(reader.fieldnames, expected_fields)
        facilities: list[dict[str, Any]] = []
        seen_ccns: set[str] = set()
        for line_number, source_row in enumerate(reader, start=2):
            if None in source_row:
                raise ValueError(f"CMS CSV has extra cells on line {line_number}")
            if any(value is None for value in source_row.values()):
                raise ValueError(f"CMS CSV has missing cells on line {line_number}")
            row: dict[str, Any] = {}
            for field, source_column in resolved.items():
                spec = _FIELD_BY_KEY[field]
                row[field] = _parse_field(
                    source_row[source_column], spec, line_number=line_number
                )
            ccn = row["ccn"]
            if ccn in seen_ccns:
                raise ValueError(f"CMS CSV repeats CCN {ccn!r}")
            seen_ccns.add(ccn)
            if not row["provider_name"]:
                raise ValueError(
                    f"CMS provider_name is blank on line {line_number}"
                )
            if row["processing_date"] != expected_processing_date:
                raise ValueError(
                    "CMS row Processing Date does not match pinned vintage "
                    f"on line {line_number}"
                )
            facilities.append(row)
    if not facilities:
        raise ValueError("CMS CSV has no facility rows")
    facilities.sort(key=lambda row: row["ccn"])
    return facilities, resolved, extras


def _resolve_columns(
    headers: Sequence[str], expected_fields: frozenset[str]
) -> tuple[dict[str, str], list[str]]:
    normalized_headers: dict[str, str] = {}
    for header in headers:
        if not isinstance(header, str) or not _clean_text(header):
            raise ValueError("CMS CSV contains a blank header")
        normalized = _normalize_header(header)
        if normalized in normalized_headers:
            raise ValueError(
                "CMS CSV repeats a normalized header: "
                f"{normalized_headers[normalized]!r} and {header!r}"
            )
        normalized_headers[normalized] = header

    resolved: dict[str, str] = {}
    used_headers: set[str] = set()
    for spec in _FIELD_SPECS:
        alias_keys = {_normalize_header(alias) for alias in spec.aliases}
        matches = [
            raw for key, raw in normalized_headers.items() if key in alias_keys
        ]
        if len(matches) > 1:
            raise ValueError(
                f"CMS CSV ambiguously maps logical field {spec.key!r}: "
                + ", ".join(repr(match) for match in matches)
            )
        if matches:
            raw = matches[0]
            if raw in used_headers:
                raise ValueError(f"CMS CSV reuses source column {raw!r}")
            resolved[spec.key] = raw
            used_headers.add(raw)

    missing = sorted(expected_fields - set(resolved))
    if missing:
        raise ValueError(
            "CMS CSV is missing expected logical fields: " + ", ".join(missing)
        )
    extras = sorted(header for header in headers if header not in used_headers)
    return resolved, extras


def _parse_field(value: object, spec: _FieldSpec, *, line_number: int) -> Any:
    if spec.kind == "text":
        return _clean_text(value)
    if spec.kind == "ccn":
        text = _clean_text(value).upper()
        if not re.fullmatch(r"[A-Z0-9]{6}", text):
            raise ValueError(f"CMS CCN is invalid on line {line_number}")
        return text
    if spec.kind == "date":
        parsed = _parse_date(_clean_text(value), spec.key)
        return parsed.isoformat()
    if spec.kind == "footnote":
        return _parse_footnote(value, field=spec.key, line_number=line_number)
    if spec.kind in {
        "nonnegative_integer",
        "nonnegative_number",
        "percentage",
    }:
        return _parse_number(
            value, kind=spec.kind, field=spec.key, line_number=line_number
        )
    raise AssertionError(f"Unhandled CMS field kind: {spec.kind}")


def _parse_number(
    value: object,
    *,
    kind: str,
    field: str,
    line_number: int,
) -> int | float | None:
    text = _clean_text(value)
    if text.casefold() in _MISSING_NUMERIC_TOKENS:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"CMS {field} is not numeric on line {line_number}"
        ) from exc
    if not number.is_finite():
        raise ValueError(f"CMS {field} is not finite on line {line_number}")
    if number < 0:
        raise ValueError(f"CMS {field} is negative on line {line_number}")
    if kind == "percentage" and number > 100:
        raise ValueError(f"CMS {field} exceeds 100 on line {line_number}")
    if kind == "nonnegative_integer":
        integral = number.to_integral_value()
        if number != integral:
            raise ValueError(
                f"CMS {field} is not an integer on line {line_number}"
            )
        return int(integral)
    return float(number)


def _parse_footnote(
    value: object, *, field: str, line_number: int
) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"CMS {field} footnote is not numeric on line {line_number}"
        ) from exc
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError(f"CMS {field} footnote is invalid on line {line_number}")
    return str(int(number))


def _metric_report(
    facilities: Sequence[Mapping[str, Any]],
    spec: _MetricSpec,
    *,
    source_column: str,
    temporal_status: Mapping[str, Any],
) -> dict[str, Any]:
    values = [row[spec.key] for row in facilities if row[spec.key] is not None]
    missing_rows = [row for row in facilities if row[spec.key] is None]
    footnote_counts: dict[str, int] = {}
    missing_with_footnote = 0
    if spec.footnote_field is not None:
        for row in missing_rows:
            code = row[spec.footnote_field]
            if code is not None:
                missing_with_footnote += 1
                footnote_counts[code] = footnote_counts.get(code, 0) + 1
    denominator = len(facilities)
    return {
        "label": spec.label,
        "unit": spec.unit,
        "evidence_class": "direct_value_in_pinned_cms_source",
        "source_column": source_column,
        "source_definition": spec.source_definition,
        "temporal_group": spec.temporal_group,
        "temporal_status": dict(temporal_status),
        "summary": _numeric_summary(values, denominator=denominator),
        "missingness": {
            "denominator": denominator,
            "present": len(values),
            "missing": len(missing_rows),
            "missing_fraction": _ratio(len(missing_rows), denominator),
            "missing_with_footnote": missing_with_footnote,
            "missing_without_footnote": len(missing_rows) - missing_with_footnote,
            "footnote_counts_on_missing": dict(sorted(footnote_counts.items())),
        },
    }


def _occupancy_report(
    facilities: Sequence[Mapping[str, Any]],
    temporal: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    values: list[float] = []
    missing_census = 0
    nonpositive_beds = 0
    over_one = 0
    for row in facilities:
        census = row["average_residents_per_day"]
        beds = row["certified_beds"]
        if census is None:
            missing_census += 1
            continue
        if beds is None or beds <= 0:
            nonpositive_beds += 1
            continue
        value = census / beds
        values.append(value)
        if value > 1:
            over_one += 1
    denominator = len(facilities)
    return {
        "label": "derived average occupancy ratio",
        "unit": "average_residents_per_certified_bed",
        "evidence_class": "derived_from_two_values_in_pinned_cms_source",
        "formula": "average_residents_per_day / certified_beds",
        "no_clipping": True,
        "temporal_caveat": (
            "This combines a release-vintage bed count with a period-average "
            "census. It is descriptive conditioning evidence, not a claim "
            "that both quantities were measured at one instant."
        ),
        "input_temporal_status": {
            "certified_beds": dict(temporal["certified_beds"]),
            "average_resident_census": dict(
                temporal["average_resident_census"]
            ),
        },
        "summary": _numeric_summary(values, denominator=denominator),
        "missingness": {
            "denominator": denominator,
            "present": len(values),
            "missing": denominator - len(values),
            "missing_fraction": _ratio(denominator - len(values), denominator),
            "missing_resident_census": missing_census,
            "nonpositive_or_missing_certified_beds": nonpositive_beds,
        },
        "ratios_above_one": over_one,
    }


def _trusted_facility_row(row: Mapping[str, Any]) -> dict[str, Any]:
    margins = {spec.key: row[spec.key] for spec in _METRIC_SPECS}
    beds = row["certified_beds"]
    census = row["average_residents_per_day"]
    occupancy = (
        _round_number(census / beds)
        if census is not None and beds is not None and beds > 0
        else None
    )
    footnotes = {
        spec.key: row[spec.key]
        for spec in _FIELD_SPECS
        if spec.kind == "footnote"
    }
    return {
        "ccn": row["ccn"],
        "provider_name": row["provider_name"],
        "processing_date": row["processing_date"],
        "observed_facility_margins": margins,
        "source_footnotes": footnotes,
        "derived_margins": {"occupancy_ratio": occupancy},
    }


def _numeric_summary(
    values: Sequence[int | float], *, denominator: int
) -> dict[str, int | float | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {
            "n": 0,
            "missing": denominator,
            "min": None,
            "q25": None,
            "median": None,
            "mean": None,
            "q75": None,
            "max": None,
        }
    return {
        "n": len(ordered),
        "missing": denominator - len(ordered),
        "min": _round_number(ordered[0]),
        "q25": _round_number(_quantile(ordered, 0.25)),
        "median": _round_number(_quantile(ordered, 0.50)),
        "mean": _round_number(sum(ordered) / len(ordered)),
        "q75": _round_number(_quantile(ordered, 0.75)),
        "max": _round_number(ordered[-1]),
    }


def _quantile(ordered: Sequence[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _ratio(numerator: int, denominator: int) -> float | None:
    return _round_number(numerator / denominator) if denominator else None


def _round_number(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def _normalize_header(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "_".join(re.findall(r"[a-z0-9]+", normalized))


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def _parse_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"CMS {label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"CMS {label} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"CMS {label} must use YYYY-MM-DD")
    return parsed


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"CMS {label} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"CMS {label} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"CMS {label} must include a timezone")
    return parsed


def _object(parent: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"CMS source metadata {key!r} must be an object")
    return value


def _is_sha256_commitment(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(
        r"sha256:[0-9a-f]{64}", value
    ) is not None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m epiagentbench.cms_nh_morphology",
        description=(
            "Validate a pinned local CMS Provider Information artifact and "
            "emit scientific-v3 facility-morphology margins. No data is "
            "downloaded or discovered."
        ),
    )
    parser.add_argument(
        "--csv", required=True, help="explicit pinned Provider Information CSV"
    )
    parser.add_argument(
        "--metadata", required=True, help="explicit matching source metadata JSON"
    )
    parser.add_argument(
        "--output", help="optional local path for the canonical JSON report"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    csv_input = Path(args.csv).resolve(strict=True)
    metadata_input = Path(args.metadata).resolve(strict=True)
    if args.output:
        output = Path(args.output).resolve(strict=False)
        if output in {csv_input, metadata_input}:
            raise ValueError("CMS report output must not overwrite an input file")
    report = build_cms_nh_morphology_report(args.csv, args.metadata)
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
