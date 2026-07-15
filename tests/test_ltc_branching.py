from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

pytest.importorskip("starsim")

from epiagentbench.trusted.engine import EngineControl
from epiagentbench.trusted.intervention_evaluation import (
    InterventionOutcomes,
    PolicyOutcomeDraw,
    commit_opening_history,
)
from epiagentbench.trusted.ltc_branching import (
    AuthenticatedLtcBranchReceipt,
    LtcBranchingError,
    LtcFutureDraw,
    LtcInterventionEffectDraw,
    LtcParameterDraw,
    LtcPolicyDefinition,
    LtcRuntimeFingerprint,
    _derive_outcomes,
    evaluate_verified_ltc_policy_panel,
    execute_ltc_branch,
    freeze_ltc_branch_plan,
    verify_ltc_branch_receipt,
)
from epiagentbench.trusted.starsim_ltc_v3 import (
    BACKEND_NAME,
    COMMON_SOURCE,
    CONTACT_REDUCTION_LEVEL,
    DESIGN_PLACEHOLDER,
    INFECTIOUS_SYMPTOMATIC,
    LtcLatentFrame,
    LtcPersonLatentState,
    LtcStarsimV3Config,
    RESIDENT,
    STAFF,
    SUPPORTED_STARSIM_VERSION,
    ScheduledLtcExposure,
)


TEST_AUTHENTICATION_KEY = b"\xa5" * 32


@dataclass(frozen=True)
class _Person:
    person_id: str
    role: str
    ward_id: str | None
    room_id: str | None


@dataclass(frozen=True)
class _Contact:
    contact_id: str
    person_a_id: str
    person_b_id: str
    start_minute: int
    duration_minutes: int
    setting: str
    location_id: str | None


@dataclass(frozen=True)
class _Trace:
    people: tuple[_Person, ...]
    contacts: tuple[_Contact, ...]


def _trace() -> _Trace:
    return _Trace(
        people=(
            _Person("resident-alpha", RESIDENT, "ward-a", "room-a"),
            _Person("resident-beta", RESIDENT, "ward-a", "room-b"),
            _Person("staff-alpha", STAFF, "ward-a", None),
        ),
        contacts=(
            _Contact(
                "contact-a",
                "resident-alpha",
                "staff-alpha",
                0,
                60,
                "direct_care",
                "ward-a",
            ),
            _Contact(
                "contact-b",
                "staff-alpha",
                "resident-beta",
                60,
                60,
                "direct_care",
                "ward-a",
            ),
        ),
    )


def _plan():
    control = EngineControl(
        control_id="contact-level",
        kind=CONTACT_REDUCTION_LEVEL,
        effective_minute=1440,
        magnitude=1.0,
    )
    return freeze_ltc_branch_plan(
        manifest_id="private-pilot-1",
        trace=_trace(),
        cutoff_minute=1440,
        scenario_version="scenario-v1",
        profile_version="profile-v1",
        generator_version="generator-v1",
        runtime_fingerprint=LtcRuntimeFingerprint(
            simulator_name=BACKEND_NAME,
            simulator_version=SUPPORTED_STARSIM_VERSION,
            evaluator_runtime_sha256="sha256:" + "a" * 64,
            evaluator_image_digest="sha256:" + "b" * 64,
        ),
        policies=(
            LtcPolicyDefinition("no-control", "v1", ()),
            LtcPolicyDefinition("contact-control", "v1", (control,)),
        ),
        parameter_draws=(
            LtcParameterDraw(
                "parameter-a",
                LtcStarsimV3Config(
                    random_seed=0,
                    seed_person_ids=("resident-alpha",),
                    evidence_status=DESIGN_PLACEHOLDER,
                    horizon_days=3,
                ),
            ),
        ),
        intervention_effect_draws=(
            LtcInterventionEffectDraw("effect-a", {"contact-level": 0.0}),
        ),
        future_draws=(LtcFutureDraw("future-a", 42, ()),),
        authentication_key=TEST_AUTHENTICATION_KEY,
    )


def _execute(plan, policy_id: str) -> AuthenticatedLtcBranchReceipt:
    return execute_ltc_branch(
        plan,
        policy_id=policy_id,
        parameter_draw_id="parameter-a",
        intervention_effect_draw_id="effect-a",
        future_draw_id="future-a",
    )


def test_trusted_freeze_replays_opening_and_issues_hmac_receipt():
    plan = _plan()
    public = plan.public_commitment()
    assert public.manifest_sha256 == plan.manifest_sha256
    assert "resident-alpha" not in repr(public)
    assert repr(TEST_AUTHENTICATION_KEY) not in repr(public)

    receipt = _execute(plan, "contact-control")
    assert receipt.opening_snapshot_sha256 == plan.opening_snapshot_sha256[0][2]
    assert verify_ltc_branch_receipt(plan, receipt) == receipt


def test_receipt_relabel_or_outcome_tampering_fails_authentication():
    plan = _plan()
    receipt = _execute(plan, "contact-control")
    with pytest.raises(LtcBranchingError, match="authentication"):
        verify_ltc_branch_receipt(
            plan,
            replace(receipt, policy_id="no-control"),
            replay=False,
        )
    with pytest.raises(LtcBranchingError, match="authentication"):
        verify_ltc_branch_receipt(
            plan,
            replace(
                receipt,
                outcomes=replace(receipt.outcomes, total_infections=999),
            ),
            replay=False,
        )


def test_verified_evaluator_rejects_raw_self_attested_rows_and_missing_branches():
    plan = _plan()
    raw = PolicyOutcomeDraw(
        opening_history=commit_opening_history({}, cutoff_minute=1440),
        policy_id="no-control",
        future_seed=42,
        posterior_draw_id="parameter-a",
        intervention_effect_draw_id="effect-a",
        outcomes=InterventionOutcomes(resident_symptomatic_cases=0),
    )
    with pytest.raises(LtcBranchingError, match="only evaluator-issued"):
        evaluate_verified_ltc_policy_panel(plan, (raw,), replay_receipts=False)  # type: ignore[arg-type]

    no_control = _execute(plan, "no-control")
    with pytest.raises(LtcBranchingError, match="exactly one receipt"):
        evaluate_verified_ltc_policy_panel(plan, (no_control,), replay_receipts=False)


def test_complete_authenticated_panel_is_balanced_and_summarized():
    plan = _plan()
    receipts = (
        _execute(plan, "no-control"),
        _execute(plan, "contact-control"),
    )
    report = evaluate_verified_ltc_policy_panel(plan, receipts, replay_receipts=False)
    assert report.branch_count == 2
    assert report.draws_per_policy == 1
    assert {row.policy_id for row in report.policy_summaries} == {
        "no-control",
        "contact-control",
    }


def test_freeze_rejects_policy_that_can_change_the_opening():
    control = EngineControl(
        control_id="contact-level",
        kind=CONTACT_REDUCTION_LEVEL,
        effective_minute=0,
        magnitude=1.0,
    )
    with pytest.raises(LtcBranchingError, match="on or after"):
        freeze_ltc_branch_plan(
            manifest_id="bad-plan",
            trace=_trace(),
            cutoff_minute=1440,
            scenario_version="scenario-v1",
            profile_version="profile-v1",
            generator_version="generator-v1",
            runtime_fingerprint=LtcRuntimeFingerprint(
                simulator_name=BACKEND_NAME,
                simulator_version=SUPPORTED_STARSIM_VERSION,
                evaluator_runtime_sha256="sha256:" + "a" * 64,
                evaluator_image_digest="sha256:" + "b" * 64,
            ),
            policies=(
                LtcPolicyDefinition("no-control", "v1", ()),
                LtcPolicyDefinition("bad", "v1", (control,)),
            ),
            parameter_draws=(
                LtcParameterDraw(
                    "parameter-a",
                    LtcStarsimV3Config(
                        random_seed=0,
                        seed_person_ids=("resident-alpha",),
                        evidence_status=DESIGN_PLACEHOLDER,
                        horizon_days=3,
                    ),
                ),
            ),
            intervention_effect_draws=(
                LtcInterventionEffectDraw("effect-a", {"contact-level": 0.0}),
            ),
            future_draws=(LtcFutureDraw("future-a", 42, ()),),
            authentication_key=TEST_AUTHENTICATION_KEY,
        )


def test_freeze_rejects_time_travel_and_inconsistent_evaluation_windows():
    base = _plan()
    with pytest.raises(LtcBranchingError, match="strictly after"):
        freeze_ltc_branch_plan(
            manifest_id="time-travel",
            trace=_trace(),
            cutoff_minute=base.cutoff_minute,
            scenario_version=base.scenario_version,
            profile_version=base.profile_version,
            generator_version=base.generator_version,
            runtime_fingerprint=base.runtime_fingerprint,
            policies=base.policies,
            parameter_draws=base.parameter_draws,
            intervention_effect_draws=base.intervention_effect_draws,
            future_draws=(
                LtcFutureDraw(
                    "future-a",
                    42,
                    (
                        ScheduledLtcExposure(
                            mechanism=COMMON_SOURCE,
                            target_person_id="resident-beta",
                            exposure_minute=base.cutoff_minute,
                            threshold=0.25,
                        ),
                    ),
                ),
            ),
            authentication_key=TEST_AUTHENTICATION_KEY,
        )

    mismatched = LtcParameterDraw(
        "parameter-b",
        replace(base.parameter_draws[0].config, horizon_days=4),
    )
    with pytest.raises(LtcBranchingError, match="same horizon and timestep"):
        freeze_ltc_branch_plan(
            manifest_id="mixed-window",
            trace=_trace(),
            cutoff_minute=base.cutoff_minute,
            scenario_version=base.scenario_version,
            profile_version=base.profile_version,
            generator_version=base.generator_version,
            runtime_fingerprint=base.runtime_fingerprint,
            policies=base.policies,
            parameter_draws=(*base.parameter_draws, mismatched),
            intervention_effect_draws=base.intervention_effect_draws,
            future_draws=base.future_draws,
            authentication_key=TEST_AUTHENTICATION_KEY,
        )


def test_branch_outcomes_count_only_symptoms_observed_by_the_horizon():
    resident = LtcPersonLatentState(
        person_id="resident-alpha",
        role=RESIDENT,
        ward_id="ward-a",
        room_id="room-a",
        state=INFECTIOUS_SYMPTOMATIC,
        symptom_onset_minute=1441,
        infection_minute=0,
        recovery_minute=2880,
        relative_infectiousness=1.0,
    )
    staff = replace(
        resident,
        person_id="staff-alpha",
        role=STAFF,
        room_id=None,
        symptom_onset_minute=1440,
    )
    outcomes = _derive_outcomes(
        LtcLatentFrame(
            minute=1440,
            people=(resident, staff),
            transmission_events=(),
            applied_control_ids=(),
            terminal=False,
        )
    )
    assert outcomes.resident_symptomatic_cases == 0
    assert outcomes.staff_symptomatic_cases == 1
