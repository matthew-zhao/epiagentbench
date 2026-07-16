"""LTC norovirus diagnostics for a caller-supplied NORS-shaped snapshot.

This module deliberately describes *reported outbreak observations*.  NORS is
not a line list of every infection and cannot identify latent transmission
parameters, ascertainment, or the probability that an outbreak is reported.

The adapter computes reproducibility hashes after reading its inputs. Those
hashes do not authenticate acquisition from CDC. Scientific use therefore
requires a separate, custodian-verified source manifest that this development
adapter does not yet implement.

Run the dependency-free command line interface with::

    python -m epiagentbench.nors_ltc_observation --csv SNAPSHOT.csv \
        --metadata SNAPSHOT.metadata.json
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import unicodedata

from .calibration import NORS_DATASET_ID, NORS_PUBLIC_PAGE


LTC_NORS_OBSERVATION_CONTRACT_VERSION = (
    "ltc_nors_reported_outbreak_observation_v1"
)
LTC_SETTING = "Long-term care/nursing home/assisted living facility"
PERSON_TO_PERSON_MODE = "Person-to-person"
OBSERVATION_YEARS = tuple(range(2009, 2020))
REPORTING_ERAS: Mapping[str, tuple[int, ...]] = {
    "2009-2012": (2009, 2010, 2011, 2012),
    "2013-2016": (2013, 2014, 2015, 2016),
    "2017-2019": (2017, 2018, 2019),
}

_REQUIRED_FIELDS = frozenset(
    {
        "year",
        "month",
        "state",
        "primary_mode",
        "etiology",
        "etiology_status",
        "setting",
        "illnesses",
    }
)
_INTEGER_FIELDS = frozenset({"year", "month", "illnesses"})
_STATUS_CATEGORIES = (
    "confirmed_only",
    "suspected_only",
    "mixed_confirmed_and_suspected",
    "unresolved_or_other",
)
_SEASONS = ("winter", "spring", "summer", "autumn", "missing")


@dataclass(frozen=True, slots=True)
class _NorsRecord:
    year: int | None
    month: int | None
    state: str
    primary_mode: str
    etiology: str
    etiology_status: str
    setting: str
    illnesses: int | None

    def as_canonical_dict(self) -> dict[str, int | str | None]:
        return {
            "etiology": self.etiology,
            "etiology_status": self.etiology_status,
            "illnesses": self.illnesses,
            "month": self.month,
            "primary_mode": self.primary_mode,
            "setting": self.setting,
            "state": self.state,
            "year": self.year,
        }


def build_ltc_nors_observation_diagnostics(
    csv_path: str | Path,
    metadata_path: str | Path,
) -> dict[str, Any]:
    """Build a deterministic diagnostic under the LTC observation contract.

    The estimand is the distribution of estimated illnesses *conditional on a
    qualifying outbreak appearing in NORS*.  It is not a distribution of true
    infections or any latent transmission parameter.
    """

    csv_file = Path(csv_path).resolve(strict=True)
    metadata_file = Path(metadata_path).resolve(strict=True)
    metadata = _load_and_validate_metadata(metadata_file)
    source_records = tuple(_read_nors_records(csv_file))
    if not source_records:
        raise ValueError("NORS CSV has no data rows")

    eligible_any_year = tuple(
        record for record in source_records if _is_eligible_except_year(record)
    )
    eligible = tuple(
        record for record in eligible_any_year if record.year in OBSERVATION_YEARS
    )
    if not eligible:
        raise ValueError("The LTC NORS observation cohort is empty")

    annual = {
        str(year): _annual_diagnostic(
            tuple(record for record in eligible if record.year == year)
        )
        for year in OBSERVATION_YEARS
    }
    eras = {
        era: _era_diagnostic(
            tuple(record for record in eligible if record.year in years), years
        )
        for era, years in REPORTING_ERAS.items()
    }
    overall = _era_diagnostic(eligible, OBSERVATION_YEARS)

    report: dict[str, Any] = {
        "contract_version": LTC_NORS_OBSERVATION_CONTRACT_VERSION,
        "scope_label": (
            "reported-outbreak observation diagnostics; not latent transmission"
        ),
        "admissibility": {
            "scientific_use_authorized": False,
            "calibration_admissible": False,
            "external_validation_admissible": False,
            "source_authenticity": "caller_supplied_unverified",
            "requires_custodian_verified_source_manifest": True,
            "declared_fixture_or_synthetic": _declared_fixture_or_synthetic(
                metadata
            ),
            "reason": (
                "The adapter validates CDC dataset identifiers and schema, "
                "then records after-the-fact hashes. It does not authenticate "
                "where the bytes came from or when they were acquired."
            ),
        },
        "scientific_scope": {
            "observation_type": "reported_outbreak_observation",
            "latent_transmission_estimand": False,
            "interpretation": (
                "These summaries describe qualifying outbreak reports recorded "
                "in NORS. They do not describe every infection or every outbreak."
            ),
            "not_identified": [
                "infection-level transmission rate or reproduction number",
                "generation interval, growth rate, or outbreak duration",
                "case ascertainment or outbreak reporting probability",
                "population incidence or state-level risk",
                "causal intervention effectiveness",
            ],
        },
        "estimand_contract": {
            "unit": "one qualifying reported NORS outbreak",
            "outcome": (
                "NORS Illnesses: estimated primary cases, including "
                "laboratory-confirmed and probable cases"
            ),
            "conditioning": (
                "conditional on being recorded in the caller-supplied snapshot and "
                "meeting every cohort rule"
            ),
            "observation_years": list(OBSERVATION_YEARS),
            "cohort_rules": {
                "setting_equals": LTC_SETTING,
                "primary_mode_equals": PERSON_TO_PERSON_MODE,
                "etiology_rule": (
                    "at least one semicolon-delimited etiology token is "
                    "Norovirus or begins with 'Norovirus '"
                ),
                "minimum_estimated_illnesses": 2,
                "co-reported_etiologies": (
                    "retained when at least one aligned etiology is norovirus"
                ),
            },
            "quantile_method": (
                "linear interpolation at (n - 1) * p (Hyndman-Fan type 7)"
            ),
            "reporting_margin_definitions": {
                "state": (
                    "NORS exposure-state field; Multistate is retained as its "
                    "own category and blank values are labeled missing"
                ),
                "season_from_earliest_onset_month": {
                    "winter": [12, 1, 2],
                    "spring": [3, 4, 5],
                    "summer": [6, 7, 8],
                    "autumn": [9, 10, 11],
                    "missing": [],
                },
            },
        },
        "source_commitments": {
            "dataset_id": NORS_DATASET_ID,
            "public_page": NORS_PUBLIC_PAGE,
            "csv_filename": csv_file.name,
            "csv_sha256": f"sha256:{_file_sha256(csv_file)}",
            "metadata_filename": metadata_file.name,
            "metadata_sha256": f"sha256:{_file_sha256(metadata_file)}",
            "metadata_declared_name": metadata.get("name"),
            "data_last_updated": _metadata_update_time(metadata),
            "source_rows": len(source_records),
            "eligible_normalized_rows_sha256": (
                f"sha256:{_records_sha256(eligible)}"
            ),
            "commitment_note": (
                "These hashes are computed after input selection. Once recorded "
                "they commit exact bytes, but they do not prove CDC provenance. "
                "The eligible-row hash commits normalized cohort observations."
            ),
            "authenticity_claim": "not established by this adapter",
        },
        "cohort_flow": {
            "source_rows": len(source_records),
            "eligible_rows_before_year_restriction": len(eligible_any_year),
            "eligible_rows_2009_2019": len(eligible),
            "otherwise_eligible_rows_outside_2009_2019": (
                len(eligible_any_year) - len(eligible)
            ),
        },
        "reporting_regime_diagnostics": {
            "interpretation_guardrail": (
                "Changes across years or eras may reflect reporting coverage, "
                "laboratory confirmation, jurisdiction mix, season mix, or true "
                "outbreak changes; this diagnostic does not separate them."
            ),
            "annual": annual,
            "eras": eras,
            "overall_2009_2019": overall,
        },
    }
    report["diagnostic_sha256"] = f"sha256:{_canonical_sha256(report)}"
    return report


def _annual_diagnostic(records: Sequence[_NorsRecord]) -> dict[str, Any]:
    return {
        "reported_outbreak_size": _size_summary(records),
        "confirmed_vs_suspected_mix": _status_mix(records),
        "exposure_state_category_count": len(
            {record.state or "missing" for record in records}
        ),
    }


def _era_diagnostic(
    records: Sequence[_NorsRecord], years: Sequence[int]
) -> dict[str, Any]:
    return {
        "years": list(years),
        "reported_outbreak_size": _size_summary(records),
        "confirmed_vs_suspected_mix": _status_mix(records),
        "state_reporting_margin": _margin(
            (record.state or "missing" for record in records)
        ),
        "season_of_earliest_illness_onset_margin": _margin(
            (_season(record.month) for record in records), order=_SEASONS
        ),
    }


def _size_summary(records: Sequence[_NorsRecord]) -> dict[str, int | float | None]:
    values = sorted(
        record.illnesses
        for record in records
        if type(record.illnesses) is int and record.illnesses >= 2
    )
    if not values:
        return {"n": 0, "q25": None, "median": None, "q75": None}
    return {
        "n": len(values),
        "q25": round(_quantile(values, 0.25), 6),
        "median": round(_quantile(values, 0.50), 6),
        "q75": round(_quantile(values, 0.75), 6),
    }


def _quantile(ordered: Sequence[int], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _status_mix(records: Sequence[_NorsRecord]) -> dict[str, Any]:
    counts = {category: 0 for category in _STATUS_CATEGORIES}
    for record in records:
        counts[_norovirus_status_category(record)] += 1
    denominator = len(records)
    return {
        "unit": "qualifying reported outbreaks",
        "classification_note": (
            "Status tokens are aligned to semicolon-delimited etiology tokens. "
            "Mixed means the same report contains confirmed and suspected "
            "norovirus etiologies; malformed or nonstandard alignments are "
            "unresolved rather than guessed."
        ),
        "denominator": denominator,
        "counts": counts,
        "shares": {
            category: round(counts[category] / denominator, 6)
            if denominator
            else None
            for category in _STATUS_CATEGORIES
        },
    }


def _norovirus_status_category(record: _NorsRecord) -> str:
    etiologies = _tokens(record.etiology)
    statuses = _tokens(record.etiology_status)
    if not etiologies or len(etiologies) != len(statuses):
        return "unresolved_or_other"
    relevant = {
        status.casefold()
        for etiology, status in zip(etiologies, statuses, strict=True)
        if _is_norovirus_etiology(etiology)
    }
    if relevant == {"confirmed"}:
        return "confirmed_only"
    if relevant == {"suspected"}:
        return "suspected_only"
    if relevant == {"confirmed", "suspected"}:
        return "mixed_confirmed_and_suspected"
    return "unresolved_or_other"


def _margin(
    values: Iterable[str], *, order: Sequence[str] | None = None
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    denominator = sum(counts.values())
    keys = (
        [key for key in order if key in counts]
        if order is not None
        else sorted(counts)
    )
    return {
        "denominator": denominator,
        "categories": {
            key: {
                "n": counts[key],
                "share": round(counts[key] / denominator, 6),
            }
            for key in keys
        },
    }


def _season(month: int | None) -> str:
    if month in {12, 1, 2}:
        return "winter"
    if month in {3, 4, 5}:
        return "spring"
    if month in {6, 7, 8}:
        return "summer"
    if month in {9, 10, 11}:
        return "autumn"
    return "missing"


def _is_eligible_except_year(record: _NorsRecord) -> bool:
    return (
        record.setting == LTC_SETTING
        and record.primary_mode == PERSON_TO_PERSON_MODE
        and any(
            _is_norovirus_etiology(etiology)
            for etiology in _tokens(record.etiology)
        )
        and type(record.illnesses) is int
        and record.illnesses >= 2
    )


def _is_norovirus_etiology(value: str) -> bool:
    normalized = value.casefold()
    return normalized == "norovirus" or normalized.startswith("norovirus ")


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in (_clean_text(part) for part in value.split(";"))
        if token
    )


def _read_nors_records(path: Path) -> Iterable[_NorsRecord]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("NORS CSV has no header")
        mapping: dict[str, str] = {}
        seen: set[str] = set()
        for header in reader.fieldnames:
            canonical = _normalize_header(header)
            if canonical not in _REQUIRED_FIELDS:
                continue
            if canonical in seen:
                raise ValueError(f"NORS CSV repeats the {canonical!r} field")
            seen.add(canonical)
            mapping[header] = canonical
        missing = sorted(_REQUIRED_FIELDS - seen)
        if missing:
            raise ValueError(
                "NORS CSV is missing required fields: " + ", ".join(missing)
            )

        for line_number, row in enumerate(reader, start=2):
            parsed: dict[str, int | str | None] = {}
            for source, destination in mapping.items():
                raw = row.get(source, "")
                if destination in _INTEGER_FIELDS:
                    parsed[destination] = _optional_integer(
                        raw, field=destination, line_number=line_number
                    )
                else:
                    parsed[destination] = _clean_text(raw)
            month = parsed["month"]
            if month is not None and (type(month) is not int or not 1 <= month <= 12):
                raise ValueError(f"NORS month is outside 1-12 on line {line_number}")
            year = parsed["year"]
            if year is not None and (type(year) is not int or not 1 <= year <= 9999):
                raise ValueError(f"NORS year is invalid on line {line_number}")
            yield _NorsRecord(
                year=year if type(year) is int else None,
                month=month if type(month) is int else None,
                state=str(parsed["state"]),
                primary_mode=str(parsed["primary_mode"]),
                etiology=str(parsed["etiology"]),
                etiology_status=str(parsed["etiology_status"]),
                setting=str(parsed["setting"]),
                illnesses=(
                    parsed["illnesses"]
                    if type(parsed["illnesses"]) is int
                    else None
                ),
            )


def _normalize_header(value: str) -> str:
    return "_".join(_clean_text(value).casefold().replace("/", " ").split())


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def _optional_integer(
    value: object, *, field: str, line_number: int
) -> int | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError(
            f"NORS {field} is not an integer on line {line_number}"
        ) from exc
    if number < 0:
        raise ValueError(f"NORS {field} is negative on line {line_number}")
    return number


def _load_and_validate_metadata(path: Path) -> dict[str, Any]:
    try:
        metadata = json.loads(
            path.read_bytes(),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("Invalid NORS metadata snapshot") from exc
    if not isinstance(metadata, dict) or metadata.get("id") != NORS_DATASET_ID:
        raise ValueError("Metadata is not for the pinned NORS dataset")
    timestamp = metadata.get("rowsUpdatedAt")
    if type(timestamp) is not int or timestamp <= 0:
        raise ValueError("NORS metadata has no valid rowsUpdatedAt timestamp")
    columns = metadata.get("columns")
    if not isinstance(columns, list):
        raise ValueError("NORS metadata has no column schema")
    metadata_fields = {
        _normalize_header(column.get("fieldName", ""))
        for column in columns
        if isinstance(column, dict)
    }
    missing = sorted(_REQUIRED_FIELDS - metadata_fields)
    if missing:
        raise ValueError(
            "NORS metadata is missing required fields: " + ", ".join(missing)
        )
    return metadata


def _metadata_update_time(metadata: Mapping[str, Any]) -> str:
    timestamp = metadata["rowsUpdatedAt"]
    assert type(timestamp) is int
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _declared_fixture_or_synthetic(metadata: Mapping[str, Any]) -> bool:
    name = metadata.get("name")
    if not isinstance(name, str):
        return False
    normalized = name.casefold()
    return "fixture" in normalized or "synthetic" in normalized


def _records_sha256(records: Sequence[_NorsRecord]) -> str:
    rows = sorted(
        json.dumps(
            record.as_canonical_dict(), sort_keys=True, separators=(",", ":")
        )
        for record in records
    )
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m epiagentbench.nors_ltc_observation",
        description=(
            "Build LTC person-to-person norovirus reported-outbreak "
            "observation diagnostics from caller-supplied NORS-shaped files. "
            "This adapter records hashes but does not authenticate provenance."
        ),
    )
    parser.add_argument("--csv", required=True, help="caller-supplied NORS CSV path")
    parser.add_argument(
        "--metadata", required=True, help="matching caller-supplied metadata path"
    )
    parser.add_argument(
        "--output", help="optional path for the canonical JSON report"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_ltc_nors_observation_diagnostics(args.csv, args.metadata)
    if args.output:
        from .calibration import write_json_artifact

        write_json_artifact(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
