from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile

import pytest

from epiagentbench.scientific_readiness import (
    ALL_GATES,
    GateEvidence,
    ScientificReadinessError,
    assess_readiness,
    build_readiness_manifest,
    main,
    record_scientific_candidate_eligibility,
    validate_readiness_manifest,
)


PROFILE = b'{"profile":"ltc_v3"}'
FINGERPRINT = "sha256:" + hashlib.sha256(b"generator-v3").hexdigest()


def _evidence(
    *,
    status: str = "passed",
    external_independent: bool = True,
    external_blind: bool = True,
    expert_independent: bool = True,
) -> list[GateEvidence]:
    result = []
    for gate in ALL_GATES:
        result.append(
            GateEvidence(
                gate_id=gate,
                status=status,
                artifact_sha256=(
                    None
                    if status == "not_run"
                    else hashlib.sha256(gate.encode()).hexdigest()
                ),
                summary=f"Synthetic fixture result for {gate}",
                independent=(
                    external_independent
                    if gate == "independent_external_validation"
                    else expert_independent
                    if gate == "expert_solveability"
                    else False
                ),
                blind=(
                    external_blind
                    if gate == "independent_external_validation"
                    else False
                ),
            )
        )
    return result


def test_incomplete_gate_set_is_rejected() -> None:
    with pytest.raises(ScientificReadinessError, match="gate set must be exact"):
        build_readiness_manifest(
            candidate_profile=PROFILE,
            generator_fingerprint=FINGERPRINT,
            evidence=_evidence()[:-1],
        )


def test_not_run_manifest_is_explicitly_not_ready() -> None:
    manifest = build_readiness_manifest(
        candidate_profile=PROFILE,
        generator_fingerprint=FINGERPRINT,
        evidence=_evidence(status="not_run"),
        created_at="2026-07-14T12:00:00+00:00",
    )
    readiness = assess_readiness(manifest)
    assert not readiness["scientific_candidate_ready"]
    assert not readiness["leaderboard_ready"]
    assert "ltc_estimand_contract:not_run" in readiness["scientific_blockers"]
    with pytest.raises(ScientificReadinessError, match="eligibility refused"):
        record_scientific_candidate_eligibility(
            candidate_profile=PROFILE,
            generator_fingerprint=FINGERPRINT,
            manifest=manifest,
        )


@pytest.mark.parametrize(
    ("independent", "blind", "expected"),
    [
        (False, True, "not_independent"),
        (True, False, "not_blind"),
    ],
)
def test_external_validation_must_be_independent_and_blind(
    independent: bool, blind: bool, expected: str
) -> None:
    manifest = build_readiness_manifest(
        candidate_profile=PROFILE,
        generator_fingerprint=FINGERPRINT,
        evidence=_evidence(
            external_independent=independent,
            external_blind=blind,
        ),
    )
    assert not manifest["readiness"]["scientific_candidate_ready"]
    assert any(
        blocker.endswith(expected)
        for blocker in manifest["readiness"]["scientific_blockers"]
    )


def test_expert_study_requires_independent_adjudication() -> None:
    manifest = build_readiness_manifest(
        candidate_profile=PROFILE,
        generator_fingerprint=FINGERPRINT,
        evidence=_evidence(expert_independent=False),
    )
    assert "expert_solveability:not_independent" in manifest["readiness"][
        "scientific_blockers"
    ]


def test_scientific_eligibility_can_precede_deployment_certification() -> None:
    evidence = _evidence()
    for index, item in enumerate(evidence):
        if item.gate_id in {
            "provider_neutral_repeated_runs",
            "hostile_linux_execution",
        }:
            evidence[index] = GateEvidence(
                gate_id=item.gate_id,
                status="not_run",
                artifact_sha256=None,
                summary="Deployment gate has not run",
            )
    manifest = build_readiness_manifest(
        candidate_profile=PROFILE,
        generator_fingerprint=FINGERPRINT,
        evidence=evidence,
        created_at="2026-07-14T12:00:00+00:00",
    )
    assert manifest["readiness"]["scientific_candidate_ready"]
    assert not manifest["readiness"]["leaderboard_ready"]
    receipt = record_scientific_candidate_eligibility(
        candidate_profile=PROFILE,
        generator_fingerprint=FINGERPRINT,
        manifest=manifest,
        recorded_at="2026-07-14T13:00:00+00:00",
    )
    assert not receipt["leaderboard_ready"]
    assert receipt["production_cohort_freeze_authorized"] is False
    assert receipt["readiness_manifest_sha256"] == manifest["manifest_sha256"]


def test_tampering_and_profile_substitution_are_rejected() -> None:
    manifest = build_readiness_manifest(
        candidate_profile=PROFILE,
        generator_fingerprint=FINGERPRINT,
        evidence=_evidence(),
    )
    tampered = copy.deepcopy(manifest)
    tampered["gates"][0]["summary"] = "Changed after commitment"
    with pytest.raises(ScientificReadinessError, match="commitment mismatch"):
        record_scientific_candidate_eligibility(
            candidate_profile=PROFILE,
            generator_fingerprint=FINGERPRINT,
            manifest=tampered,
        )
    with pytest.raises(ScientificReadinessError, match="profile does not match"):
        record_scientific_candidate_eligibility(
            candidate_profile=b"different profile",
            generator_fingerprint=FINGERPRINT,
            manifest=manifest,
        )


def test_gate_evidence_cannot_claim_completed_without_artifact() -> None:
    with pytest.raises(ScientificReadinessError, match="requires"):
        GateEvidence(
            gate_id="ltc_estimand_contract",
            status="passed",
            artifact_sha256=None,
            summary="No artifact",
        )


@pytest.mark.parametrize("field", ("independent", "blind"))
def test_gate_evidence_requires_real_booleans(field: str) -> None:
    arguments = {
        "gate_id": "independent_external_validation",
        "status": "passed",
        "artifact_sha256": hashlib.sha256(b"artifact").hexdigest(),
        "summary": "External validation artifact",
        "independent": True,
        "blind": True,
    }
    arguments[field] = "false"
    with pytest.raises(ScientificReadinessError, match="must be booleans"):
        GateEvidence(**arguments)


def test_eligibility_record_rejects_invalid_timestamp() -> None:
    manifest = build_readiness_manifest(
        candidate_profile=PROFILE,
        generator_fingerprint=FINGERPRINT,
        evidence=_evidence(),
    )
    with pytest.raises(ScientificReadinessError, match="recorded_at"):
        record_scientific_candidate_eligibility(
            candidate_profile=PROFILE,
            generator_fingerprint=FINGERPRINT,
            manifest=manifest,
            recorded_at="not-a-timestamp",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("created_at", "not-a-timestamp", "created_at"),
        ("intended_use", "", "intended_use"),
        ("candidate_profile_sha256", "bad", "candidate_profile_sha256"),
        ("generator_fingerprint", "bad", "generator_fingerprint"),
        ("claim_limits", [], "claim limits"),
    ),
)
def test_rehashed_malformed_loaded_manifest_is_rejected(
    field: str, value: object, message: str
) -> None:
    manifest = build_readiness_manifest(
        candidate_profile=PROFILE,
        generator_fingerprint=FINGERPRINT,
        evidence=_evidence(),
        created_at="2026-07-14T12:00:00+00:00",
    )
    manifest[field] = value
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256")
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ScientificReadinessError, match=message):
        validate_readiness_manifest(manifest)


def test_loaded_manifest_rejects_extra_top_level_fields() -> None:
    manifest = build_readiness_manifest(
        candidate_profile=PROFILE,
        generator_fingerprint=FINGERPRINT,
        evidence=_evidence(),
    )
    manifest["unregistered_authority"] = True
    with pytest.raises(ScientificReadinessError, match="fields must be exact"):
        validate_readiness_manifest(manifest)


def test_cli_template_is_explicitly_not_ready_and_refuses_overwrite() -> None:
    with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
        root = Path(directory)
        profile = root / "profile.json"
        output = root / "manifest.json"
        profile.write_bytes(PROFILE)
        assert main(
            [
                "template",
                "--profile",
                str(profile),
                "--generator-fingerprint",
                FINGERPRINT,
                "--output",
                str(output),
            ]
        ) == 0
        saved = json.loads(output.read_text("utf-8"))
        assert not saved["readiness"]["scientific_candidate_ready"]
        with pytest.raises(ScientificReadinessError, match="must not already exist"):
            main(
                [
                    "template",
                    "--profile",
                    str(profile),
                    "--generator-fingerprint",
                    FINGERPRINT,
                    "--output",
                    str(output),
                ]
            )
