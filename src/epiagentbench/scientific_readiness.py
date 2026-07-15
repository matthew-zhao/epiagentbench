"""Fail-closed local scientific-readiness manifests.

This module deliberately separates an *implemented* benchmark from a benchmark
that has evidence supporting a scientific-use claim.  It does not run, verify,
or authenticate any of the required studies.  It commits a caller-supplied
checklist and can produce a local eligibility record when that checklist is
complete.  It is not a production-freeze authority: artifact retrieval,
custodian signatures, and freezer-side verification remain external gates.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


READINESS_MANIFEST_VERSION = "scientific_readiness_v1"
SCIENTIFIC_ELIGIBILITY_RECORD_VERSION = "scientific_candidate_eligibility_v1"

SCIENTIFIC_GATES = (
    "ltc_estimand_contract",
    "temporal_reporting_drift",
    "joint_posterior_predictive_checks",
    "observation_process_validation",
    "independent_external_validation",
    "intervention_uncertainty_validation",
    "stakeholder_utility_validation",
    "expert_solveability",
    "interactive_shortcut_audit",
)

LEADERBOARD_ONLY_GATES = (
    "provider_neutral_repeated_runs",
    "hostile_linux_execution",
)

ALL_GATES = SCIENTIFIC_GATES + LEADERBOARD_ONLY_GATES

CLAIM_LIMITS = (
    "A complete local checklist supports only the stated intended use.",
    "Validation can falsify a candidate; it cannot prove universal realism.",
    "A future NORS holdout validates reported-outbreak observables only.",
    "This manifest commits caller-supplied claims; it does not authenticate "
    "evidence or authorize a production freeze.",
)

_MANIFEST_KEYS = frozenset(
    {
        "manifest_version",
        "created_at",
        "intended_use",
        "candidate_profile_sha256",
        "generator_fingerprint",
        "gates",
        "readiness",
        "claim_limits",
        "manifest_sha256",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GENERATOR_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_VALID_STATUSES = frozenset({"passed", "failed", "not_run"})


class ScientificReadinessError(ValueError):
    """Raised when readiness evidence is malformed or insufficient."""


@dataclass(frozen=True, slots=True)
class GateEvidence:
    """One committed result from a predeclared scientific gate.

    ``artifact_sha256`` commits the complete underlying report rather than a
    hand-written summary.  ``independent`` and ``blind`` describe the study,
    not the person creating this manifest.
    """

    gate_id: str
    status: str
    artifact_sha256: str | None
    summary: str
    independent: bool = False
    blind: bool = False

    def __post_init__(self) -> None:
        if self.gate_id not in ALL_GATES:
            raise ScientificReadinessError(
                f"unsupported scientific gate: {self.gate_id!r}"
            )
        if self.status not in _VALID_STATUSES:
            raise ScientificReadinessError(
                f"unsupported gate status: {self.status!r}"
            )
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ScientificReadinessError("gate summary must be non-empty")
        if type(self.independent) is not bool or type(self.blind) is not bool:
            raise ScientificReadinessError(
                "independent and blind must be booleans"
            )
        if self.status == "not_run":
            if self.artifact_sha256 is not None:
                raise ScientificReadinessError(
                    "a not-run gate cannot claim an evidence artifact"
                )
        elif not _is_sha256(self.artifact_sha256):
            raise ScientificReadinessError(
                "a completed gate requires a lowercase SHA-256 artifact commitment"
            )


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA-256 digest for immutable artifact bytes."""

    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    return hashlib.sha256(content).hexdigest()


def build_readiness_manifest(
    *,
    candidate_profile: bytes,
    generator_fingerprint: str,
    evidence: Iterable[GateEvidence],
    created_at: str | None = None,
    intended_use: str = (
        "agentic investigation and closed-loop response to suspected "
        "norovirus outbreaks in U.S. long-term-care facilities"
    ),
) -> dict[str, Any]:
    """Build a complete, immutable manifest without asserting readiness.

    Every known gate must be represented exactly once, including gates that
    have not yet run.  This makes omissions visible and prevents a producer
    from redefining readiness by silently dropping a failed requirement.
    """

    if not candidate_profile:
        raise ScientificReadinessError("candidate profile must be non-empty")
    if not _is_generator_fingerprint(generator_fingerprint):
        raise ScientificReadinessError(
            "generator_fingerprint must use the sha256:<lowercase digest> format"
        )
    if not isinstance(intended_use, str) or not intended_use.strip():
        raise ScientificReadinessError("intended_use must be non-empty")

    indexed: dict[str, GateEvidence] = {}
    for item in evidence:
        if not isinstance(item, GateEvidence):
            raise TypeError("evidence items must be GateEvidence instances")
        if item.gate_id in indexed:
            raise ScientificReadinessError(
                f"duplicate scientific gate: {item.gate_id}"
            )
        indexed[item.gate_id] = item
    missing = tuple(gate for gate in ALL_GATES if gate not in indexed)
    extra = tuple(sorted(set(indexed) - set(ALL_GATES)))
    if missing or extra:
        raise ScientificReadinessError(
            f"gate set must be exact; missing={missing!r}, extra={extra!r}"
        )

    created = _validated_timestamp(
        (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        ),
        "created_at",
    )

    manifest: dict[str, Any] = {
        "manifest_version": READINESS_MANIFEST_VERSION,
        "created_at": created,
        "intended_use": intended_use.strip(),
        "candidate_profile_sha256": sha256_bytes(candidate_profile),
        "generator_fingerprint": generator_fingerprint,
        "gates": [asdict(indexed[gate]) for gate in ALL_GATES],
        "readiness": {},
        "claim_limits": list(CLAIM_LIMITS),
    }
    manifest["readiness"] = assess_readiness(manifest)
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def assess_readiness(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Assess scientific and leaderboard tiers from committed gate results."""

    gates = _validated_gate_mapping(manifest)
    scientific_failures = _gate_failures(gates, SCIENTIFIC_GATES)
    leaderboard_failures = _gate_failures(gates, ALL_GATES)

    external = gates["independent_external_validation"]
    if external["status"] == "passed":
        if not external["independent"]:
            scientific_failures.append(
                "independent_external_validation:not_independent"
            )
        if not external["blind"]:
            scientific_failures.append("independent_external_validation:not_blind")

    expert = gates["expert_solveability"]
    if expert["status"] == "passed" and not expert["independent"]:
        scientific_failures.append("expert_solveability:not_independent")

    leaderboard_failures = list(dict.fromkeys(
        leaderboard_failures + scientific_failures
    ))
    scientific_failures = list(dict.fromkeys(scientific_failures))
    return {
        "scientific_candidate_ready": not scientific_failures,
        "leaderboard_ready": not leaderboard_failures,
        "scientific_blockers": scientific_failures,
        "leaderboard_blockers": leaderboard_failures,
    }


def record_scientific_candidate_eligibility(
    *,
    candidate_profile: bytes,
    generator_fingerprint: str,
    manifest: Mapping[str, Any],
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Record local eligibility only when all scientific checklist gates pass.

    This record is deliberately non-authoritative.  A future production cohort
    freezer must additionally verify the committed artifacts and a trusted
    custodian signature.  Leaderboard-only deployment gates are reported
    separately.
    """

    _validate_manifest_commitment(manifest)
    if sha256_bytes(candidate_profile) != manifest.get(
        "candidate_profile_sha256"
    ):
        raise ScientificReadinessError(
            "candidate profile does not match the readiness manifest"
        )
    if generator_fingerprint != manifest.get("generator_fingerprint"):
        raise ScientificReadinessError(
            "generator fingerprint does not match the readiness manifest"
        )
    readiness = assess_readiness(manifest)
    if not readiness["scientific_candidate_ready"]:
        blockers = ", ".join(readiness["scientific_blockers"])
        raise ScientificReadinessError(
            f"scientific eligibility refused; unresolved gates: {blockers}"
        )

    recorded = _validated_timestamp(
        recorded_at
        if recorded_at is not None
        else datetime.now(timezone.utc).isoformat(),
        "recorded_at",
    )
    receipt: dict[str, Any] = {
        "eligibility_version": SCIENTIFIC_ELIGIBILITY_RECORD_VERSION,
        "recorded_at": recorded,
        "authority": "non_authoritative_local_checklist",
        "production_cohort_freeze_authorized": False,
        "candidate_profile_sha256": manifest["candidate_profile_sha256"],
        "generator_fingerprint": generator_fingerprint,
        "readiness_manifest_sha256": manifest["manifest_sha256"],
        "intended_use": manifest["intended_use"],
        "leaderboard_ready": readiness["leaderboard_ready"],
        "leaderboard_blockers": readiness["leaderboard_blockers"],
    }
    receipt["eligibility_sha256"] = _canonical_sha256(receipt)
    return receipt


def validate_readiness_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the manifest commitment and return its recomputed assessment."""

    _validate_manifest_commitment(manifest)
    return assess_readiness(manifest)


def not_run_gate_evidence() -> tuple[GateEvidence, ...]:
    """Return an explicit complete gate set for a new candidate protocol."""

    return tuple(
        GateEvidence(
            gate_id=gate,
            status="not_run",
            artifact_sha256=None,
            summary="Gate has not run; no scientific claim is made.",
        )
        for gate in ALL_GATES
    )


def _read_json_object(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).resolve(strict=True).read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScientificReadinessError(f"unable to read JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ScientificReadinessError("JSON artifact must contain an object")
    return value


def _write_json_exclusive(path: str | Path, value: Mapping[str, Any]) -> Path:
    output = Path(path).expanduser().resolve()
    if not output.parent.is_dir():
        raise ScientificReadinessError("output parent directory must exist")
    try:
        with output.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError:
        raise ScientificReadinessError(
            "output artifact must not already exist"
        ) from None
    return output


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m epiagentbench.scientific_readiness"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser(
        "template", help="create an exact all-not-run readiness manifest"
    )
    template.add_argument("--profile", required=True)
    template.add_argument("--generator-fingerprint", required=True)
    template.add_argument("--output", required=True)

    build = subparsers.add_parser(
        "build", help="build a committed manifest from gate-evidence JSON"
    )
    build.add_argument("--profile", required=True)
    build.add_argument("--generator-fingerprint", required=True)
    build.add_argument("--evidence", required=True)
    build.add_argument("--output", required=True)

    assess = subparsers.add_parser(
        "assess", help="validate and recompute a readiness assessment"
    )
    assess.add_argument("--manifest", required=True)

    eligibility = subparsers.add_parser(
        "record-eligibility",
        help="record non-authoritative local scientific eligibility",
    )
    eligibility.add_argument("--profile", required=True)
    eligibility.add_argument("--generator-fingerprint", required=True)
    eligibility.add_argument("--manifest", required=True)
    eligibility.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dependency-free CLI for constructing and checking readiness artifacts."""

    args = _build_cli_parser().parse_args(argv)
    if args.command in {"template", "build", "record-eligibility"}:
        profile = Path(args.profile).resolve(strict=True).read_bytes()
    if args.command == "template":
        manifest = build_readiness_manifest(
            candidate_profile=profile,
            generator_fingerprint=args.generator_fingerprint,
            evidence=not_run_gate_evidence(),
        )
        output = _write_json_exclusive(args.output, manifest)
        print(json.dumps({"output": str(output), **manifest["readiness"]}, indent=2))
        return 0
    if args.command == "build":
        evidence_artifact = _read_json_object(args.evidence)
        raw_gates = evidence_artifact.get("gates")
        if not isinstance(raw_gates, list):
            raise ScientificReadinessError("evidence JSON requires a gates list")
        try:
            evidence = tuple(GateEvidence(**item) for item in raw_gates)
        except (TypeError, AttributeError) as exc:
            raise ScientificReadinessError("malformed gate evidence") from exc
        manifest = build_readiness_manifest(
            candidate_profile=profile,
            generator_fingerprint=args.generator_fingerprint,
            evidence=evidence,
        )
        output = _write_json_exclusive(args.output, manifest)
        print(json.dumps({"output": str(output), **manifest["readiness"]}, indent=2))
        return 0
    if args.command == "assess":
        manifest = _read_json_object(args.manifest)
        print(
            json.dumps(
                validate_readiness_manifest(manifest), indent=2, sort_keys=True
            )
        )
        return 0
    if args.command == "record-eligibility":
        manifest = _read_json_object(args.manifest)
        receipt = record_scientific_candidate_eligibility(
            candidate_profile=profile,
            generator_fingerprint=args.generator_fingerprint,
            manifest=manifest,
        )
        output = _write_json_exclusive(args.output, receipt)
        print(json.dumps({"output": str(output), **receipt}, indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


def _validated_gate_mapping(
    manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    if manifest.get("manifest_version") != READINESS_MANIFEST_VERSION:
        raise ScientificReadinessError("unsupported readiness manifest version")
    raw_gates = manifest.get("gates")
    if not isinstance(raw_gates, list):
        raise ScientificReadinessError("manifest gates must be a list")
    indexed: dict[str, dict[str, Any]] = {}
    for raw in raw_gates:
        if not isinstance(raw, Mapping):
            raise ScientificReadinessError("manifest gate entries must be objects")
        try:
            item = GateEvidence(**dict(raw))
        except TypeError as exc:
            raise ScientificReadinessError("malformed manifest gate entry") from exc
        if item.gate_id in indexed:
            raise ScientificReadinessError(
                f"duplicate manifest gate: {item.gate_id}"
            )
        indexed[item.gate_id] = asdict(item)
    if tuple(indexed) != ALL_GATES:
        raise ScientificReadinessError(
            "manifest gates must use the canonical complete order"
        )
    return indexed


def _gate_failures(
    gates: Mapping[str, Mapping[str, Any]], required: Iterable[str]
) -> list[str]:
    return [
        f"{gate}:{gates[gate]['status']}"
        for gate in required
        if gates[gate]["status"] != "passed"
    ]


def _validate_manifest_commitment(manifest: Mapping[str, Any]) -> None:
    _validate_loaded_manifest_schema(manifest)
    _validated_gate_mapping(manifest)
    expected = manifest.get("manifest_sha256")
    if not _is_sha256(expected):
        raise ScientificReadinessError("manifest has no valid SHA-256 commitment")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    if _canonical_sha256(unsigned) != expected:
        raise ScientificReadinessError("readiness manifest commitment mismatch")
    recalculated = assess_readiness(manifest)
    if manifest.get("readiness") != recalculated:
        raise ScientificReadinessError("readiness summary does not match gate evidence")


def _validate_loaded_manifest_schema(manifest: Mapping[str, Any]) -> None:
    if not isinstance(manifest, Mapping):
        raise ScientificReadinessError("readiness manifest must be an object")
    supplied = set(manifest)
    if supplied != _MANIFEST_KEYS:
        missing = tuple(sorted(_MANIFEST_KEYS - supplied))
        extra = tuple(sorted(supplied - _MANIFEST_KEYS))
        raise ScientificReadinessError(
            f"readiness manifest fields must be exact; missing={missing!r}, "
            f"extra={extra!r}"
        )
    _validated_timestamp(manifest["created_at"], "created_at")
    intended_use = manifest["intended_use"]
    if not isinstance(intended_use, str) or not intended_use.strip():
        raise ScientificReadinessError("intended_use must be non-empty")
    if not _is_sha256(manifest["candidate_profile_sha256"]):
        raise ScientificReadinessError(
            "candidate_profile_sha256 must be a lowercase SHA-256 digest"
        )
    if not _is_generator_fingerprint(manifest["generator_fingerprint"]):
        raise ScientificReadinessError(
            "generator_fingerprint must use the sha256:<lowercase digest> format"
        )
    if manifest["claim_limits"] != list(CLAIM_LIMITS):
        raise ScientificReadinessError("readiness claim limits do not match schema")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _is_generator_fingerprint(value: object) -> bool:
    return (
        isinstance(value, str)
        and _GENERATOR_FINGERPRINT_RE.fullmatch(value) is not None
    )


def _validated_timestamp(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScientificReadinessError(f"{name} must be ISO-8601")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScientificReadinessError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ScientificReadinessError(f"{name} must include a timezone")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
