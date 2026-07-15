"""Visible external curve-shape checks for nursing-home norovirus outbreaks.

This module deliberately does not tune Starsim or assign a leaderboard gate.
It pins and parses the CC0 Adams et al. S1 line list, preregisters descriptive
metrics, and compares those metrics with simulator-reported line lists.  The
source contains only six outbreaks from one state and is visible development
evidence, not a blind holdout or proof of scientific realism.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen


ADAMS_ARTICLE_DOI = "10.1371/journal.pcbi.1007271"
ADAMS_ARTICLE_URL = (
    "https://journals.plos.org/ploscompbiol/article?id="
    "10.1371/journal.pcbi.1007271"
)
ADAMS_S1_URL = (
    "https://journals.plos.org/ploscompbiol/article/file?type=supplementary&"
    "id=info:doi/10.1371/journal.pcbi.1007271.s001"
)
ADAMS_LICENSE = "Creative Commons CC0 1.0 Universal"
ADAMS_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
ADAMS_S1_SHA256 = (
    "498efcf4ab49aaf8eb77d1c2c61ff7cfff0a8ca9c859029b25adf041041d4e8a"
)
ADAMS_S1_BYTES = 35_374
ADAMS_PUBLISHED_CASES = 209
ADAMS_PUBLISHED_OUTBREAK_IDS = frozenset(str(value) for value in range(1, 7))
REFERENCE_VERSION = "adams_visible_curve_reference_v1"
COMPARISON_VERSION = "adams_visible_curve_comparison_v1"

ADAMS_HEADERS = (
    "Outbreak_Number", "Onset_Day", "Index", "Diarrhea", "Vomit",
    "Resident", "Age", "Female", "R", "var_R", "Lower CI", "Upper CI",
    "logR", "R_1.5", "var_R_1.5", "R_2.0", "var_R_2.0", "R_2.5",
    "var_R_2.5", "R_3.0", "var_R_3.0", "R_3.5", "var_R_3.5", "R_4.0",
    "var_R_4.0", "log_R_1.5", "log_R_2.0", "log_R_2.5", "log_R_3.0",
    "log_R_3.5", "log_R_4.0",
)
_BINARY_FIELDS = frozenset({"Index", "Diarrhea", "Vomit", "Resident", "Female"})
_NONNEGATIVE_FIELDS = frozenset(
    field
    for field in ADAMS_HEADERS[6:]
    if not field.startswith("log")
)
_NUMERIC_FIELDS = frozenset(ADAMS_HEADERS[6:])
_INTEGER_PATTERN = re.compile(r"[0-9]+")


METRIC_CONTRACT: Mapping[str, Mapping[str, str]] = {
    "duration_days": {
        "role": "primary_curve_shape",
        "definition": "maximum observed onset day minus minimum observed onset day plus one",
        "missingness": "requires at least one observed onset; missing onsets remain counted separately",
        "unit": "days",
    },
    "peak_timing_fraction": {
        "role": "primary_curve_shape",
        "definition": "(earliest peak day - first onset day) / (last onset day - first onset day)",
        "missingness": "requires an observed onset; defined as zero for a one-day outbreak",
        "unit": "fraction_of_observed_duration",
    },
    "peak_case_fraction": {
        "role": "primary_curve_shape",
        "definition": "cases on the peak onset day divided by cases with observed onset",
        "missingness": "requires an observed onset; earliest day breaks peak-count ties",
        "unit": "fraction",
    },
    "resident_fraction": {
        "role": "primary_case_mix",
        "definition": "resident cases divided by cases with known resident/staff status",
        "missingness": "unknown status is excluded only from this denominator and reported",
        "unit": "fraction",
    },
    "vomiting_fraction": {
        "role": "primary_symptom_margin",
        "definition": "vomiting cases divided by cases with known vomiting status",
        "missingness": "unknown vomiting status is excluded only from this denominator and reported",
        "unit": "fraction",
    },
    "diarrhea_fraction": {
        "role": "primary_symptom_margin",
        "definition": "diarrhea cases divided by cases with known diarrhea status",
        "missingness": "unknown diarrhea status is excluded only from this denominator and reported",
        "unit": "fraction",
    },
    "vomiting_and_diarrhea_fraction": {
        "role": "secondary_joint_symptom_margin",
        "definition": "cases with both symptoms divided by cases with both symptom fields known",
        "missingness": "a case enters the denominator only when both symptom fields are known",
        "unit": "fraction",
    },
    "first_day_case_count": {
        "role": "secondary_seeding_check",
        "definition": "cases on the first observed onset day",
        "missingness": "requires an observed onset",
        "unit": "cases",
    },
    "reported_case_count": {
        "role": "context_not_an_independent_shape_target",
        "definition": "all rows in the reported outbreak line list",
        "missingness": "none",
        "unit": "cases",
    },
}


@dataclass(frozen=True, slots=True)
class CurveShapeCase:
    """Common observable schema for empirical or simulated reported cases."""

    outbreak_id: str
    case_id: str
    onset_day: int | None
    is_resident: bool | None
    vomited: bool | None
    diarrhea: bool | None
    is_index: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outbreak_id, str) or not self.outbreak_id.strip():
            raise ValueError("outbreak_id must be a non-empty string")
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("case_id must be a non-empty string")
        if self.onset_day is not None and (
            type(self.onset_day) is not int or abs(self.onset_day) > 100_000
        ):
            raise ValueError("onset_day must be a bounded integer or null")
        for name in ("is_resident", "vomited", "diarrhea", "is_index"):
            if (value := getattr(self, name)) is not None and type(value) is not bool:
                raise ValueError(f"{name} must be boolean or null")


@dataclass(frozen=True, slots=True)
class AdamsSnapshot:
    csv_path: Path
    metadata_path: Path
    csv_sha256: str
    bytes: int
    cases: int
    outbreaks: int


def fetch_adams_snapshot(
    output_directory: str | os.PathLike[str], *, timeout_seconds: int = 120
) -> AdamsSnapshot:
    """Download and pin the exact public S1 CSV; reject silent source drift."""

    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
        raise ValueError("Invalid download timeout")
    data = _download(ADAMS_S1_URL, timeout_seconds)
    digest = hashlib.sha256(data).hexdigest()
    if digest != ADAMS_S1_SHA256 or len(data) != ADAMS_S1_BYTES:
        raise ValueError("Adams S1 source differs from the pinned public snapshot")
    cases = parse_adams_line_list_bytes(data, require_published_shape=True)
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stem = f"adams_2020_s1_{digest[:12]}"
    csv_path = output / f"{stem}.csv"
    metadata_path = output / f"{stem}.metadata.json"
    _write_once_or_verify(csv_path, data)
    metadata = {
        "snapshot_version": "adams_s1_snapshot_v1",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": _source_provenance(),
        "csv_sha256": digest,
        "bytes": len(data),
        "cases": len(cases),
        "outbreaks": len({case.outbreak_id for case in cases}),
        "schema": list(ADAMS_HEADERS),
    }
    if metadata_path.exists():
        existing = _load_json(metadata_path)
        for field in ("snapshot_version", "source", "csv_sha256", "bytes", "cases", "outbreaks", "schema"):
            if existing.get(field) != metadata[field]:
                raise ValueError("Existing Adams snapshot metadata conflicts with source")
    else:
        _write_new(
            metadata_path,
            json.dumps(metadata, sort_keys=True, indent=2).encode("ascii") + b"\n",
        )
    return AdamsSnapshot(
        csv_path=csv_path,
        metadata_path=metadata_path,
        csv_sha256=digest,
        bytes=len(data),
        cases=len(cases),
        outbreaks=len({case.outbreak_id for case in cases}),
    )


def parse_adams_line_list(
    path: str | os.PathLike[str], *, require_pinned_snapshot: bool = True
) -> tuple[CurveShapeCase, ...]:
    data = Path(path).resolve(strict=True).read_bytes()
    if require_pinned_snapshot and hashlib.sha256(data).hexdigest() != ADAMS_S1_SHA256:
        raise ValueError("Adams line list does not match the pinned snapshot")
    return parse_adams_line_list_bytes(
        data, require_published_shape=require_pinned_snapshot
    )


def parse_adams_line_list_bytes(
    data: bytes, *, require_published_shape: bool = False
) -> tuple[CurveShapeCase, ...]:
    """Strictly parse exact columns and validate every published numeric cell."""

    if not isinstance(data, bytes) or not data or len(data) > 5_000_000:
        raise ValueError("Adams CSV bytes are empty or too large")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Adams CSV is not UTF-8") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = tuple(next(reader))
    except StopIteration as exc:
        raise ValueError("Adams CSV is empty") from exc
    if header != ADAMS_HEADERS:
        raise ValueError("Adams CSV schema differs from the frozen contract")
    result: list[CurveShapeCase] = []
    for source_row, row in enumerate(reader, start=2):
        if len(row) != len(ADAMS_HEADERS):
            raise ValueError(f"Adams CSV row {source_row} has the wrong width")
        cells = dict(zip(ADAMS_HEADERS, row, strict=True))
        outbreak = _required_integer(cells["Outbreak_Number"], "Outbreak_Number")
        if outbreak < 1:
            raise ValueError("Outbreak_Number must be positive")
        onset = _optional_integer(cells["Onset_Day"], "Onset_Day")
        if onset is not None and onset < 1:
            raise ValueError("Onset_Day must be positive")
        parsed_binary = {
            field: _optional_binary(cells[field], field) for field in _BINARY_FIELDS
        }
        for field in _NUMERIC_FIELDS:
            _validate_numeric_cell(cells[field], field)
        result.append(
            CurveShapeCase(
                outbreak_id=str(outbreak),
                case_id=f"adams-row-{source_row - 1}",
                onset_day=onset,
                is_resident=parsed_binary["Resident"],
                vomited=parsed_binary["Vomit"],
                diarrhea=parsed_binary["Diarrhea"],
                is_index=parsed_binary["Index"],
            )
        )
    cases = tuple(result)
    _validate_case_identity(cases)
    _validate_index_flags(cases)
    if require_published_shape:
        ids = {case.outbreak_id for case in cases}
        if len(cases) != ADAMS_PUBLISHED_CASES or ids != ADAMS_PUBLISHED_OUTBREAK_IDS:
            raise ValueError("Adams CSV does not have the published 209-case, six-outbreak shape")
    if not cases:
        raise ValueError("Adams CSV contains no cases")
    return cases


def parse_simulated_reported_line_list(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[CurveShapeCase, ...]:
    """Normalize a simulator export without silently imputing absent features."""

    required = {"outbreak_id", "case_id", "onset_day", "is_resident", "vomited", "diarrhea"}
    optional = {"is_index"}
    cases: list[CurveShapeCase] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or not required.issubset(row) or not set(row).issubset(required | optional):
            raise ValueError(f"simulated row {index} has the wrong schema")
        cases.append(
            CurveShapeCase(
                outbreak_id=row["outbreak_id"],
                case_id=row["case_id"],
                onset_day=row["onset_day"],
                is_resident=row["is_resident"],
                vomited=row["vomited"],
                diarrhea=row["diarrhea"],
                is_index=row.get("is_index"),
            )
        )
    result = tuple(cases)
    if not result:
        raise ValueError("simulated reported line list is empty")
    _validate_case_identity(result)
    return result


def summarize_curve_shapes(cases: Sequence[CurveShapeCase]) -> dict[str, Any]:
    """Apply the frozen tie, denominator, and missingness rules."""

    rows = tuple(cases)
    if not rows:
        raise ValueError("curve-shape line list is empty")
    _validate_case_identity(rows)
    groups: dict[str, list[CurveShapeCase]] = {}
    for case in rows:
        groups.setdefault(case.outbreak_id, []).append(case)
    outbreaks = [
        _summarize_outbreak(outbreak_id, groups[outbreak_id])
        for outbreak_id in sorted(groups, key=_outbreak_sort_key)
    ]
    metrics: dict[str, Any] = {}
    for name, contract in METRIC_CONTRACT.items():
        values = [row[name] for row in outbreaks if row[name] is not None]
        metrics[name] = {
            "contract": dict(contract),
            "outbreaks_with_metric": len(values),
            "outbreaks_missing_metric": len(outbreaks) - len(values),
            "values": values,
            "summary": _numeric_summary(values) if values else None,
        }
    return {
        "cases": len(rows),
        "outbreaks": len(outbreaks),
        "outbreak_rows": outbreaks,
        "metrics": metrics,
    }


def build_adams_reference_report(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Build the immutable, explicitly visible external reference artifact."""

    source_path = Path(path).resolve(strict=True)
    cases = parse_adams_line_list(source_path, require_pinned_snapshot=True)
    report: dict[str, Any] = {
        "reference_version": REFERENCE_VERSION,
        "evidence_role": "visible_narrow_external_reference",
        "blind_holdout": False,
        "sufficient_to_establish_scientific_realism": False,
        "source": {**_source_provenance(), "csv_sha256": ADAMS_S1_SHA256},
        "metric_contract_frozen_before_simulator_comparison": True,
        "summary": summarize_curve_shapes(cases),
        "limitations": [
            "six nursing-home outbreaks from South Carolina in 2014-2016",
            "confirmed outbreaks and reported probable/confirmed cases, not all infections or non-outbreak alerts",
            "one visible public reference; repeated tuning against it turns it into development data",
            "descriptive margins do not identify a unique transmission mechanism or intervention effect",
        ],
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def compare_simulated_curve_shapes(
    simulated_cases: Sequence[CurveShapeCase],
    reference: Mapping[str, Any],
    *,
    candidate_label: str,
) -> dict[str, Any]:
    """Return metric-wise diagnostics, never a composite reward or pass claim."""

    _validate_reference(reference)
    if not isinstance(candidate_label, str) or not candidate_label.strip():
        raise ValueError("candidate_label must be non-empty")
    simulated = summarize_curve_shapes(simulated_cases)
    comparisons: dict[str, Any] = {}
    target_metrics = reference["summary"]["metrics"]
    for name in METRIC_CONTRACT:
        target = target_metrics[name]
        observed = simulated["metrics"][name]
        target_summary = target["summary"]
        observed_summary = observed["summary"]
        if target_summary is None or observed_summary is None:
            comparisons[name] = {
                "status": "not_comparable",
                "target_outbreaks_with_metric": target["outbreaks_with_metric"],
                "simulated_outbreaks_with_metric": observed["outbreaks_with_metric"],
                "reason": "at least one panel has no observed values for this metric",
            }
            continue
        quantile_differences = {
            key: round(abs(observed_summary[key] - target_summary[key]), 6)
            for key in ("q25", "median", "q75")
        }
        lower, upper = target_summary["min"], target_summary["max"]
        comparisons[name] = {
            "status": "descriptive_only",
            "unit": METRIC_CONTRACT[name]["unit"],
            "target": target_summary,
            "simulated": observed_summary,
            "absolute_quantile_differences": quantile_differences,
            "mean_absolute_quantile_difference": round(
                sum(quantile_differences.values()) / 3, 6
            ),
            "simulated_fraction_in_target_observed_range": round(
                sum(lower <= value <= upper for value in observed["values"])
                / len(observed["values"]),
                6,
            ),
        }
    result: dict[str, Any] = {
        "comparison_version": COMPARISON_VERSION,
        "candidate_label": candidate_label.strip(),
        "reference_report_sha256": reference["report_sha256"],
        "evidence_role": "visible_external_model_check",
        "blind_holdout": False,
        "composite_score": None,
        "pass_fail_gate": None,
        "simulated_summary": simulated,
        "metric_comparisons": comparisons,
        "interpretation": (
            "Use discrepancies for model criticism. This six-outbreak visible "
            "reference cannot by itself validate broad realism; tuning against "
            "it must be declared and evaluated on a genuinely independent set."
        ),
    }
    result["comparison_sha256"] = _canonical_sha256(result)
    return result


def write_json_artifact(path: str | os.PathLike[str], value: Mapping[str, Any]) -> Path:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, indent=2).encode("ascii") + b"\n"
    _write_once_or_verify(destination, data)
    return destination


def _summarize_outbreak(outbreak_id: str, cases: Sequence[CurveShapeCase]) -> dict[str, Any]:
    onsets = [case.onset_day for case in cases if case.onset_day is not None]
    temporal: dict[str, int | float | None] = {
        "duration_days": None,
        "peak_timing_fraction": None,
        "peak_case_fraction": None,
        "first_day_case_count": None,
    }
    if onsets:
        counts: dict[int, int] = {}
        for onset in onsets:
            counts[onset] = counts.get(onset, 0) + 1
        first, last = min(counts), max(counts)
        peak_count = max(counts.values())
        peak_day = min(day for day, count in counts.items() if count == peak_count)
        temporal = {
            "duration_days": last - first + 1,
            "peak_timing_fraction": round(
                (peak_day - first) / (last - first) if last > first else 0.0, 6
            ),
            "peak_case_fraction": round(peak_count / len(onsets), 6),
            "first_day_case_count": counts[first],
        }
    resident = _binary_margin(cases, "is_resident")
    vomit = _binary_margin(cases, "vomited")
    diarrhea = _binary_margin(cases, "diarrhea")
    joint_known = [case for case in cases if case.vomited is not None and case.diarrhea is not None]
    joint_fraction = (
        round(sum(case.vomited and case.diarrhea for case in joint_known) / len(joint_known), 6)
        if joint_known else None
    )
    return {
        "outbreak_id": outbreak_id,
        "reported_case_count": len(cases),
        "observed_onset_count": len(onsets),
        "missing_onset_count": len(cases) - len(onsets),
        **temporal,
        "resident_fraction": resident["fraction"],
        "resident_status_known": resident["known"],
        "resident_status_missing": resident["missing"],
        "vomiting_fraction": vomit["fraction"],
        "vomiting_known": vomit["known"],
        "vomiting_missing": vomit["missing"],
        "diarrhea_fraction": diarrhea["fraction"],
        "diarrhea_known": diarrhea["known"],
        "diarrhea_missing": diarrhea["missing"],
        "vomiting_and_diarrhea_fraction": joint_fraction,
        "joint_symptoms_known": len(joint_known),
        "joint_symptoms_missing": len(cases) - len(joint_known),
    }


def _binary_margin(cases: Sequence[CurveShapeCase], field: str) -> dict[str, Any]:
    known = [getattr(case, field) for case in cases if getattr(case, field) is not None]
    return {
        "fraction": round(sum(known) / len(known), 6) if known else None,
        "known": len(known),
        "missing": len(cases) - len(known),
    }


def _numeric_summary(values: Sequence[int | float]) -> dict[str, int | float]:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot summarize an empty sample")
    return {
        "n": len(ordered),
        "min": ordered[0],
        "q25": round(_quantile(ordered, 0.25), 6),
        "median": round(_quantile(ordered, 0.5), 6),
        "q75": round(_quantile(ordered, 0.75), 6),
        "max": ordered[-1],
        "mean": round(sum(ordered) / len(ordered), 6),
    }


def _quantile(values: Sequence[int | float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + fraction * (values[upper] - values[lower])


def _validate_case_identity(cases: Sequence[CurveShapeCase]) -> None:
    identities = [(case.outbreak_id, case.case_id) for case in cases]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate case identity in curve-shape line list")


def _validate_index_flags(cases: Sequence[CurveShapeCase]) -> None:
    groups: dict[str, list[CurveShapeCase]] = {}
    for case in cases:
        groups.setdefault(case.outbreak_id, []).append(case)
    for group in groups.values():
        onsets = [case.onset_day for case in group if case.onset_day is not None]
        if not onsets:
            continue
        first = min(onsets)
        for case in group:
            if case.is_index is not None and case.onset_day is not None:
                if case.is_index != (case.onset_day == first):
                    raise ValueError("Index field conflicts with first observed onset day")


def _required_integer(value: str, field: str) -> int:
    parsed = _optional_integer(value, field)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


def _optional_integer(value: str, field: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    if not _INTEGER_PATTERN.fullmatch(text):
        raise ValueError(f"{field} must be an integer")
    return int(text)


def _optional_binary(value: str, field: str) -> bool | None:
    text = value.strip()
    if not text:
        return None
    if text not in {"0", "1"}:
        raise ValueError(f"{field} must be zero, one, or blank")
    return text == "1"


def _validate_numeric_cell(value: str, field: str) -> None:
    text = value.strip()
    if not text:
        return
    if text == "#NUM!" and field.startswith("log_R_"):
        return
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"{field} is not numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} is not finite")
    if field in _NONNEGATIVE_FIELDS and number < 0:
        raise ValueError(f"{field} must be non-negative")


def _source_provenance() -> dict[str, Any]:
    return {
        "citation": (
            "Adams C, Young D, Gastanaduy PA, et al. (2020), PLOS "
            "Computational Biology 16(3): e1007271"
        ),
        "doi": ADAMS_ARTICLE_DOI,
        "article_url": ADAMS_ARTICLE_URL,
        "supplement": "S1 File",
        "supplement_url": ADAMS_S1_URL,
        "publication_date": "2020-03-25",
        "license": ADAMS_LICENSE,
        "license_url": ADAMS_LICENSE_URL,
        "population": "six South Carolina nursing-home norovirus outbreaks, 2014-2016",
    }


def _validate_reference(reference: Mapping[str, Any]) -> None:
    if reference.get("reference_version") != REFERENCE_VERSION:
        raise ValueError("unsupported Adams reference report")
    supplied = reference.get("report_sha256")
    if not isinstance(supplied, str):
        raise ValueError("Adams reference report has no commitment")
    unsigned = dict(reference)
    del unsigned["report_sha256"]
    if _canonical_sha256(unsigned) != supplied:
        raise ValueError("Adams reference report commitment mismatch")
    if reference.get("blind_holdout") is not False:
        raise ValueError("Adams reference must not be represented as blind")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def _outbreak_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def _download(url: str, timeout_seconds: int) -> bytes:
    request = Request(url, headers={"User-Agent": "EpiAgentBench/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise RuntimeError("Adams S1 download failed")
            data = response.read(5_000_001)
    except URLError:
        curl = shutil.which("curl")
        if curl is None:
            raise RuntimeError("Adams S1 TLS verification failed") from None
        process = subprocess.run(
            [curl, "--fail", "--location", "--silent", "--show-error",
             "--proto", "=https", "--tlsv1.2", "--max-time",
             str(timeout_seconds), "--max-filesize", "5000000", url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds + 5,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError("Adams S1 download failed")
        data = process.stdout
    if not data or len(data) > 5_000_000:
        raise ValueError("Adams S1 response is empty or too large")
    return data


def _write_once_or_verify(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Existing artifact conflicts with {path.name}")
        return
    _write_new(path, data)


def _write_new(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise ValueError(f"Artifact already exists: {path}") from None
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Invalid Adams snapshot metadata") from exc
    if not isinstance(value, dict):
        raise ValueError("Adams snapshot metadata must be an object")
    return value
