"""Leakage-aware calibration contracts for the public CDC NORS extract.

The streamlined NORS data can identify reported outbreak-size distributions and
setting/mode margins.  It cannot separately identify biological transmission,
case ascertainment, false-alert prevalence, reporting artifacts, or intervention
effects.  This module therefore freezes observable targets and temporal splits;
it does not label a simulator as calibrated merely because it can read NORS.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Iterable, Mapping, Sequence
import unicodedata
from urllib.error import URLError
from urllib.request import Request, urlopen


NORS_DATASET_ID = "5xkq-dg7x"
NORS_DATA_URL = (
    "https://data.cdc.gov/api/views/5xkq-dg7x/rows.csv?accessType=DOWNLOAD"
)
NORS_METADATA_URL = "https://data.cdc.gov/api/views/5xkq-dg7x"
NORS_PUBLIC_PAGE = "https://data.cdc.gov/d/5xkq-dg7x"
CALIBRATION_PLAN_VERSION = "nors_temporal_v2"

TEMPORAL_SPLITS: Mapping[str, tuple[int, ...]] = {
    "calibration": tuple(range(2009, 2019)),
    "model_selection": (2019,),
    "disruption_stress": (2020, 2021),
    "temporal_generalization": (2022, 2023),
}

_INSTITUTION_SETTINGS = frozenset(
    {
        "Long-term care/nursing home/assisted living facility",
        "School/college/university",
        "Child daycare/preschool",
        "Hospital",
        "Other healthcare facility",
        "Correctional/detention facility",
        "Shelter/group home/transitional housing",
        "Military facility",
    }
)

_COHORTS: Mapping[str, Mapping[str, Any]] = {
    "institution_person_to_person": {
        "primary_mode": "Person-to-person",
        "settings": tuple(sorted(_INSTITUTION_SETTINGS)),
        "setting_prefixes": (),
        "simulator_mode": "person_to_person",
    },
    "restaurant_common_source": {
        "primary_mode": "Food",
        "settings": (),
        "setting_prefixes": ("Restaurant:",),
        "simulator_mode": "common_source",
    },
}

_HEADER_ALIASES = {
    "year": "year",
    "month": "month",
    "state": "state",
    "primary_mode": "primary_mode",
    "etiology": "etiology",
    "serotype_or_genotype": "serotype_or_genotype",
    "etiology_status": "etiology_status",
    "setting": "setting",
    "illnesses": "illnesses",
    "hospitalizations": "hospitalizations",
    "info_on_hospitalizations": "info_on_hospitalizations",
    "deaths": "deaths",
    "info_on_deaths": "info_on_deaths",
    "food_vehicle": "food_vehicle",
    "food_contaminated_ingredient": "food_contaminated_ingredient",
    "ifsac_category": "ifsac_category",
    "water_exposure": "water_exposure",
    "water_type": "water_type",
    "animal_type": "animal_type",
}
_REQUIRED_FIELDS = frozenset(_HEADER_ALIASES.values())
_INTEGER_FIELDS = frozenset(
    {
        "year",
        "month",
        "illnesses",
        "hospitalizations",
        "info_on_hospitalizations",
        "deaths",
        "info_on_deaths",
    }
)


@dataclass(frozen=True, slots=True)
class NorsSnapshot:
    csv_path: Path
    metadata_path: Path
    csv_sha256: str
    metadata_sha256: str
    rows: int
    data_last_updated: str


def fetch_nors_snapshot(
    output_directory: str | os.PathLike[str],
    *,
    timeout_seconds: int = 120,
) -> NorsSnapshot:
    """Fetch one revision-consistent, version-stamped public NORS snapshot.

    Network retrieval is explicit and never occurs while importing the package.
    Metadata is fetched before and after the CSV.  The download is rejected if
    the dataset revision or schema changes in between; this is a consistency
    check, not a claim that two independent HTTP requests are atomic.
    """

    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
        raise ValueError("Invalid download timeout")
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    metadata_before = _parse_downloaded_metadata(
        _download(NORS_METADATA_URL, timeout_seconds)
    )
    csv_bytes = _download(NORS_DATA_URL, timeout_seconds)
    metadata_after = _parse_downloaded_metadata(
        _download(NORS_METADATA_URL, timeout_seconds)
    )
    if _metadata_revision_identity(metadata_before) != _metadata_revision_identity(
        metadata_after
    ):
        raise ValueError("NORS dataset changed during CSV download")
    metadata = metadata_after
    rows_updated = metadata.get("rowsUpdatedAt")
    assert type(rows_updated) is int and rows_updated > 0
    updated = datetime.fromtimestamp(rows_updated, tz=timezone.utc)
    stamp = updated.strftime("%Y%m%dT%H%M%SZ")
    if not csv_bytes.startswith(b"Year,"):
        raise ValueError("Unexpected NORS CSV header")

    csv_path = output / f"nors_{stamp}.csv"
    metadata_path = output / f"nors_{stamp}.metadata.json"
    _atomic_write(csv_path, csv_bytes)
    _atomic_write(
        metadata_path,
        json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode(),
    )
    row_count = _count_csv_rows(csv_path)
    expected_rows = metadata.get("rowsUpdatedBy")
    # Socrata does not expose a stable row-count field in every metadata version;
    # row_count is always computed from the downloaded artifact itself.
    del expected_rows
    return NorsSnapshot(
        csv_path=csv_path,
        metadata_path=metadata_path,
        csv_sha256=_file_sha256(csv_path),
        metadata_sha256=_file_sha256(metadata_path),
        rows=row_count,
        data_last_updated=updated.isoformat(),
    )


def _parse_downloaded_metadata(payload: bytes) -> dict[str, Any]:
    try:
        metadata = json.loads(payload)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Invalid NORS metadata response") from exc
    if not isinstance(metadata, dict) or metadata.get("id") != NORS_DATASET_ID:
        raise ValueError("Unexpected NORS dataset metadata")
    rows_updated = metadata.get("rowsUpdatedAt")
    if type(rows_updated) is not int or rows_updated <= 0:
        raise ValueError("NORS metadata has no update timestamp")
    return metadata


def _metadata_revision_identity(metadata: Mapping[str, Any]) -> str:
    """Commit revision and schema fields while ignoring counters like views."""

    columns = metadata.get("columns")
    if columns is not None and not isinstance(columns, list):
        raise ValueError("Invalid NORS metadata columns")
    column_identity: list[dict[str, Any]] = []
    for column in columns or []:
        if not isinstance(column, Mapping):
            raise ValueError("Invalid NORS metadata column")
        column_identity.append(
            {
                key: column.get(key)
                for key in ("id", "name", "fieldName", "dataTypeName", "position")
            }
        )
    identity = {
        "id": metadata.get("id"),
        "rowsUpdatedAt": metadata.get("rowsUpdatedAt"),
        "viewLastModified": metadata.get("viewLastModified"),
        "publicationDate": metadata.get("publicationDate"),
        "tableId": metadata.get("tableId"),
        "viewType": metadata.get("viewType"),
        "query": metadata.get("query"),
        "columns": column_identity,
    }
    return _canonical_sha256(identity)


def build_nors_calibration_plan(
    csv_path: str | os.PathLike[str],
    metadata_path: str | os.PathLike[str],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build public fit targets while keeping later temporal outcomes sealed.

    The returned plan reveals summaries only for ``calibration`` and
    ``model_selection``.  Later partitions are represented by commitments over
    canonical rows, preventing silent replacement after a model is frozen.
    """

    csv_file = Path(csv_path).resolve(strict=True)
    metadata_file = Path(metadata_path).resolve(strict=True)
    metadata = _load_metadata(metadata_file)
    records = tuple(_read_records(csv_file))
    if not records:
        raise ValueError("NORS snapshot is empty")
    source_years = sorted(
        {record["year"] for record in records if record["year"] is not None}
    )
    required_years = set().union(*TEMPORAL_SPLITS.values())
    if not required_years.issubset(source_years):
        raise ValueError("NORS snapshot does not cover the preregistered split")

    cohorts: dict[str, Any] = {}
    for cohort_name, cohort_spec in _COHORTS.items():
        selected = tuple(
            record
            for record in records
            if _record_in_cohort(record, cohort_spec)
        )
        partitions = {
            split: tuple(
                record
                for record in selected
                if record["year"] in split_years
            )
            for split, split_years in TEMPORAL_SPLITS.items()
        }
        cohorts[cohort_name] = {
            "selection": {
                "etiology_contains_case_insensitive": "norovirus",
                "primary_mode": cohort_spec["primary_mode"],
                "settings": list(cohort_spec["settings"]),
                "setting_prefixes": list(cohort_spec["setting_prefixes"]),
                "minimum_reported_illnesses": 2,
                "simulator_mode": cohort_spec["simulator_mode"],
            },
            "released_targets": {
                "calibration": _summarize(partitions["calibration"]),
                "model_selection": _summarize(partitions["model_selection"]),
            },
            "sealed_partitions": {
                split: {
                    "years": list(TEMPORAL_SPLITS[split]),
                    "canonical_rows_sha256": _records_sha256(partitions[split]),
                    "summary_released": False,
                }
                for split in ("disruption_stress", "temporal_generalization")
            },
        }

    plan: dict[str, Any] = {
        "plan_version": CALIBRATION_PLAN_VERSION,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "source": {
            "dataset_id": NORS_DATASET_ID,
            "public_page": NORS_PUBLIC_PAGE,
            "csv_sha256": _file_sha256(csv_file),
            "metadata_sha256": _file_sha256(metadata_file),
            "rows": len(records),
            "data_last_updated": _metadata_update_time(metadata),
            "dynamic_source_warning": (
                "NORS reports can be amended after close-out; reproduce only "
                "from the recorded snapshot hashes."
            ),
        },
        "temporal_split": {
            key: list(years) for key, years in TEMPORAL_SPLITS.items()
        },
        "cohorts": cohorts,
        "fit_scope": {
            "may_fit": [
                "reported illnesses per outbreak distribution",
                "setting and month margins within each released cohort",
            ],
            "not_identified_by_this_dataset": [
                "biological transmission versus case ascertainment",
                "growth rate or outbreak duration",
                "non-outbreak alert prevalence",
                "reporting-artifact prevalence",
                "repeated-introduction mechanism",
                "intervention effectiveness or response burden",
            ],
        },
        "holdout_policy": {
            "rule": (
                "Freeze the fitted profile plus the complete package, project, "
                "dependency, and runtime implementation fingerprint before "
                "releasing either sealed temporal partition."
            ),
            "released": False,
            "current_snapshot_has_blind_holdout": False,
            "temporal_generalization_caveat": (
                "Aggregate 2022-2023 summaries were inspected during source "
                "characterization, so this partition is an out-of-time check "
                "rather than a blind holdout."
            ),
            "true_blind_holdout": (
                "A future NORS vintage containing 2024+ outbreaks, ingested by "
                "an independent evaluator after the profile, code, metrics, "
                "and thresholds are frozen."
            ),
        },
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def freeze_calibration_candidate(
    plan: Mapping[str, Any],
    fitted_profile_bytes: bytes,
    *,
    frozen_at: str | None = None,
) -> dict[str, Any]:
    """Commit the profile and complete installed implementation before release."""

    _validate_plan(plan)
    if type(fitted_profile_bytes) is not bytes or not fitted_profile_bytes:
        raise ValueError("A nonempty fitted profile is required")
    # This computes its own canonical inventory.  A caller cannot bless one
    # hand-selected source file while omitting the generator, scorer, profile
    # loader, project declaration, or scientific runtime dependencies.
    from .trusted.cohort_freezer import compute_generator_fingerprint

    implementation_fingerprint = compute_generator_fingerprint(
        candidate_profile_bytes=fitted_profile_bytes
    )
    freeze: dict[str, Any] = {
        "freeze_version": "nors_candidate_freeze_v2",
        "frozen_at": frozen_at or datetime.now(timezone.utc).isoformat(),
        "plan_sha256": plan["plan_sha256"],
        "fitted_profile_sha256": hashlib.sha256(fitted_profile_bytes).hexdigest(),
        "candidate_implementation_fingerprint": implementation_fingerprint,
        "implementation_scope": (
            "package source/data, fitted profile, pyproject, Python runtime, "
            "and relevant installed distribution identities"
        ),
        "sealed_outcomes_used_during_fit": False,
        "development_exposure_note": (
            "The 2022-2023 partition is not claimed as blind; only its "
            "automated post-freeze evaluation remains sealed here."
        ),
        "claim": "candidate_frozen_before_temporal_generalization_release",
    }
    freeze["freeze_sha256"] = _canonical_sha256(freeze)
    return freeze


def release_nors_partition(
    csv_path: str | os.PathLike[str],
    plan: Mapping[str, Any],
    freeze: Mapping[str, Any],
    *,
    partition: str = "temporal_generalization",
    acknowledge_sealed_release: bool = False,
) -> dict[str, Any]:
    """Release a committed temporal summary after a candidate freeze."""

    if partition not in {"disruption_stress", "temporal_generalization"}:
        raise ValueError("Only sealed partitions may be released")
    if acknowledge_sealed_release is not True:
        raise ValueError("Explicit acknowledgement of sealed release is required")
    _validate_plan(plan)
    _validate_freeze(freeze, plan)
    csv_file = Path(csv_path).resolve(strict=True)
    if _file_sha256(csv_file) != plan["source"]["csv_sha256"]:
        raise ValueError("NORS snapshot differs from the preregistered source")
    records = tuple(_read_records(csv_file))
    released: dict[str, Any] = {}
    for cohort_name, cohort_spec in _COHORTS.items():
        selected = tuple(
            record
            for record in records
            if record["year"] in TEMPORAL_SPLITS[partition]
            and _record_in_cohort(record, cohort_spec)
        )
        expected = plan["cohorts"][cohort_name]["sealed_partitions"][partition][
            "canonical_rows_sha256"
        ]
        if _records_sha256(selected) != expected:
            raise ValueError("Sealed NORS partition commitment mismatch")
        released[cohort_name] = _summarize(selected)
    report: dict[str, Any] = {
        "release_version": "nors_partition_release_v1",
        "partition": partition,
        "years": list(TEMPORAL_SPLITS[partition]),
        "plan_sha256": plan["plan_sha256"],
        "freeze_sha256": freeze["freeze_sha256"],
        "targets": released,
        "post_freeze_only": True,
    }
    report["release_sha256"] = _canonical_sha256(report)
    return report


def compare_reported_outbreak_sizes(
    simulated_values: Sequence[int], target: Mapping[str, Any]
) -> dict[str, Any]:
    """Posterior-predictive comparison on a like-for-like observable estimand."""

    if not simulated_values or any(
        type(value) is not int or value < 2 for value in simulated_values
    ):
        raise ValueError("Simulated reported outbreak sizes must be integers >= 2")
    target_size = target.get("reported_outbreak_size")
    if not isinstance(target_size, dict):
        raise ValueError("Missing reported-outbreak-size target")
    simulated = _numeric_summary(simulated_values)
    target_median = _finite_positive(target_size.get("median"))
    target_q25 = _finite_positive(target_size.get("q25"))
    target_q75 = _finite_positive(target_size.get("q75"))
    simulated_median = _finite_positive(simulated["median"])
    simulated_q25 = _finite_positive(simulated["q25"])
    simulated_q75 = _finite_positive(simulated["q75"])
    log_errors = {
        "q25": abs(math.log(simulated_q25 / target_q25)),
        "median": abs(math.log(simulated_median / target_median)),
        "q75": abs(math.log(simulated_q75 / target_q75)),
    }
    return {
        "estimand": "reported_illnesses_per_outbreak",
        "simulated": simulated,
        "target": dict(target_size),
        "absolute_log_quantile_errors": {
            key: round(value, 6) for key, value in log_errors.items()
        },
        "mean_absolute_log_quantile_error": round(
            sum(log_errors.values()) / len(log_errors), 6
        ),
        "target_iqr_coverage": round(
            sum(target_q25 <= value <= target_q75 for value in simulated_values)
            / len(simulated_values),
            6,
        ),
    }


def write_json_artifact(
    path: str | os.PathLike[str], value: Mapping[str, Any]
) -> Path:
    """Write a canonical JSON artifact atomically and return its resolved path."""

    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        destination,
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True).encode()
        + b"\n",
    )
    return destination


def load_json_artifact(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read one duplicate-key-free JSON object from a trusted workflow path."""

    try:
        value = json.loads(
            Path(path).resolve(strict=True).read_bytes(),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("Invalid calibration JSON artifact") from exc
    if not isinstance(value, dict):
        raise ValueError("Calibration artifact must be a JSON object")
    return value


def _summarize(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    illnesses = [
        int(record["illnesses"])
        for record in records
        if type(record.get("illnesses")) is int and record["illnesses"] >= 2
    ]
    if not illnesses:
        raise ValueError("A calibration partition has no usable outbreak sizes")
    log_values = [math.log(value) for value in illnesses]
    settings: dict[str, int] = {}
    months: dict[str, int] = {}
    statuses: dict[str, int] = {}
    for record in records:
        setting = str(record.get("setting") or "missing")
        month = str(record.get("month") or "missing")
        status = str(record.get("etiology_status") or "missing")
        settings[setting] = settings.get(setting, 0) + 1
        months[month] = months.get(month, 0) + 1
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "eligible_outbreaks": len(records),
        "reported_outbreak_size": {
            **_numeric_summary(illnesses),
            "log_mean": round(sum(log_values) / len(log_values), 6),
            "log_sd": round(_sample_sd(log_values), 6),
            "estimand": "estimated primary probable plus confirmed cases",
        },
        "setting_counts": dict(sorted(settings.items())),
        "month_counts": dict(sorted(months.items(), key=lambda item: item[0])),
        "etiology_status_counts": dict(sorted(statuses.items())),
    }


def _record_in_cohort(
    record: Mapping[str, Any], cohort_spec: Mapping[str, Any]
) -> bool:
    etiology = str(record.get("etiology") or "").casefold()
    setting = str(record.get("setting") or "")
    setting_matches = setting in cohort_spec["settings"] or any(
        setting.startswith(prefix) for prefix in cohort_spec["setting_prefixes"]
    )
    return (
        "norovirus" in etiology
        and record.get("primary_mode") == cohort_spec["primary_mode"]
        and setting_matches
        and type(record.get("illnesses")) is int
        and record["illnesses"] >= 2
    )


def _read_records(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("NORS CSV has no header")
        mapping: dict[str, str] = {}
        for header in reader.fieldnames:
            normalized = _normalize_header(header)
            canonical = _HEADER_ALIASES.get(normalized)
            if canonical is not None:
                mapping[header] = canonical
        if set(mapping.values()) != _REQUIRED_FIELDS:
            raise ValueError("NORS CSV schema differs from the frozen contract")
        for row in reader:
            record: dict[str, Any] = {}
            for source, destination in mapping.items():
                raw = row.get(source, "")
                if destination in _INTEGER_FIELDS:
                    record[destination] = _optional_integer(raw)
                else:
                    record[destination] = _clean_text(raw)
            yield record


def _normalize_header(value: str) -> str:
    normalized = _clean_text(value).casefold()
    return "_".join(normalized.replace("/", " ").split())


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def _optional_integer(value: object) -> int | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError("NORS numeric field is not an integer") from exc
    if number < 0:
        raise ValueError("NORS numeric field is negative")
    return number


def _numeric_summary(values: Sequence[int]) -> dict[str, int | float]:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot summarize an empty sample")
    return {
        "n": len(ordered),
        "min": ordered[0],
        "q25": round(_quantile(ordered, 0.25), 6),
        "median": round(_quantile(ordered, 0.5), 6),
        "q75": round(_quantile(ordered, 0.75), 6),
        "p90": round(_quantile(ordered, 0.9), 6),
        "max": ordered[-1],
        "mean": round(sum(ordered) / len(ordered), 6),
    }


def _quantile(ordered: Sequence[int], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _sample_sd(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _records_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    canonical_rows = sorted(
        json.dumps(record, sort_keys=True, separators=(",", ":"))
        for record in records
    )
    digest = hashlib.sha256()
    for row in canonical_rows:
        digest.update(row.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, timeout_seconds: int) -> bytes:
    request = Request(url, headers={"User-Agent": "EpiAgentBench/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise RuntimeError("NORS download failed")
            data = response.read(100_000_001)
    except URLError:
        # Some managed macOS hosts install their verified enterprise CA only in
        # the system curl trust store. Fall back without disabling verification.
        curl = shutil.which("curl")
        if curl is None:
            raise RuntimeError("NORS TLS verification failed") from None
        process = subprocess.run(
            [
                curl,
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--max-time",
                str(timeout_seconds),
                "--max-filesize",
                "100000000",
                url,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds + 5,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError("NORS download failed")
        data = process.stdout
    if not data or len(data) > 100_000_000:
        raise ValueError("NORS response is empty or too large")
    return data


def _atomic_write(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration as exc:
            raise ValueError("NORS CSV is empty") from exc
        return sum(1 for _ in reader)


def _load_metadata(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Invalid NORS metadata snapshot") from exc
    if not isinstance(value, dict) or value.get("id") != NORS_DATASET_ID:
        raise ValueError("Metadata is not for the frozen NORS dataset")
    return value


def _metadata_update_time(metadata: Mapping[str, Any]) -> str:
    timestamp = metadata.get("rowsUpdatedAt")
    if type(timestamp) is not int or timestamp <= 0:
        raise ValueError("NORS metadata has no valid update timestamp")
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _validate_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("plan_version") != CALIBRATION_PLAN_VERSION:
        raise ValueError("Unsupported calibration plan")
    supplied = plan.get("plan_sha256")
    if not isinstance(supplied, str):
        raise ValueError("Calibration plan has no commitment")
    unsigned = dict(plan)
    del unsigned["plan_sha256"]
    if _canonical_sha256(unsigned) != supplied:
        raise ValueError("Calibration plan commitment mismatch")
    if plan.get("holdout_policy", {}).get("released") is not False:
        raise ValueError("Calibration plan already exposes the holdout")


def _validate_freeze(freeze: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    if freeze.get("freeze_version") != "nors_candidate_freeze_v2":
        raise ValueError("Unsupported calibration freeze")
    if freeze.get("plan_sha256") != plan["plan_sha256"]:
        raise ValueError("Calibration freeze belongs to another plan")
    supplied = freeze.get("freeze_sha256")
    if not isinstance(supplied, str):
        raise ValueError("Calibration freeze has no commitment")
    unsigned = dict(freeze)
    del unsigned["freeze_sha256"]
    if _canonical_sha256(unsigned) != supplied:
        raise ValueError("Calibration freeze commitment mismatch")
    if freeze.get("sealed_outcomes_used_during_fit") is not False:
        raise ValueError("Candidate used sealed temporal outcomes during fit")
    implementation = freeze.get("candidate_implementation_fingerprint")
    if (
        not isinstance(implementation, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", implementation)
    ):
        raise ValueError("Calibration freeze lacks an implementation fingerprint")


def _finite_positive(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("Target statistic is not numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Target statistic must be finite and positive")
    return number


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("Non-finite JSON number")
