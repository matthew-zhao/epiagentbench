from __future__ import annotations

from dataclasses import replace
from itertools import product

import pytest

from epiagentbench.trusted.branching_manifest import (
    BranchingManifestError,
    attest_rollout_panel,
    build_branching_manifest,
    evaluate_attested_policy_panel,
    verify_rollout_attestation,
)
from epiagentbench.trusted.intervention_evaluation import (
    OUTCOME_FIELDS,
    InterventionOutcomes,
    PolicyOutcomeDraw,
    StakeholderWeightProfile,
    commit_opening_history,
    stakeholder_weight_profile_sha256,
)


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64


def _opening():
    return commit_opening_history(
        {"alerts": [{"available_minute": 0, "count": 4}]},
        cutoff_minute=720,
    )


def _manifest(opening):
    return build_branching_manifest(
        manifest_id="ltc-development-panel-1",
        opening_history=opening,
        hidden_opening_state_sha256=DIGEST_A,
        generator_fingerprint=DIGEST_B,
        simulator_fingerprint=DIGEST_C,
        evaluator_image_digest=DIGEST_D,
        policy_definitions={
            "off": {"controls": []},
            "control": {
                "controls": [{"kind": "cohort", "level": "standard"}]
            },
        },
        posterior_draw_commitments={"post-a": DIGEST_A, "post-b": DIGEST_B},
        intervention_effect_draw_commitments={
            "effect-a": DIGEST_C,
            "effect-b": DIGEST_D,
        },
        future_seeds=(101, 102),
    )


def _rows(opening):
    rows = []
    for index, (seed, posterior, effect) in enumerate(
        product((101, 102), ("post-a", "post-b"), ("effect-a", "effect-b"))
    ):
        for policy in ("off", "control"):
            rows.append(
                PolicyOutcomeDraw(
                    opening_history=opening,
                    policy_id=policy,
                    future_seed=seed,
                    posterior_draw_id=posterior,
                    intervention_effect_draw_id=effect,
                    outcomes=InterventionOutcomes(
                        resident_symptomatic_cases=(
                            10.0 + index - (2.0 if policy == "control" else 0.0)
                        ),
                        restriction_days=2.0 if policy == "control" else 0.0,
                    ),
                )
            )
    return rows


def _profile():
    weights = {field: 0.0 for field in OUTCOME_FIELDS}
    weights["resident_symptomatic_cases"] = 1.0
    arguments = {
        "profile_id": "health",
        "profile_version": "v1",
        "stakeholder_group": "residents",
        "registration_reference": "frozen:test",
        "outcome_loss_weights": weights,
    }
    return StakeholderWeightProfile(
        **arguments,
        registration_sha256=stakeholder_weight_profile_sha256(**arguments),
    )


def test_attested_panel_can_be_evaluated_but_makes_no_realism_claim():
    opening = _opening()
    manifest = _manifest(opening)
    rows = _rows(opening)
    states = {"off": DIGEST_A, "control": DIGEST_A}
    attestation = attest_rollout_panel(
        rows, manifest=manifest, pre_action_state_commitments=states
    )

    report = evaluate_attested_policy_panel(
        rows,
        manifest=manifest,
        attestation=attestation,
        weight_profiles=(_profile(),),
    )

    assert report.draw_count == 8
    assert report.weight_profile_evaluations["health"].ranking[0] == "control"
    assert "do not prove execution order" in manifest.as_dict()["claim_limits"][0]


def test_row_mutation_breaks_attestation():
    opening = _opening()
    manifest = _manifest(opening)
    rows = _rows(opening)
    attestation = attest_rollout_panel(
        rows,
        manifest=manifest,
        pre_action_state_commitments={"off": DIGEST_A, "control": DIGEST_A},
    )
    changed = list(rows)
    changed[0] = replace(
        changed[0], outcomes=InterventionOutcomes(resident_symptomatic_cases=999)
    )
    with pytest.raises(BranchingManifestError, match="does not match"):
        verify_rollout_attestation(
            changed, manifest=manifest, attestation=attestation
        )


def test_manifest_substitution_breaks_attestation():
    opening = _opening()
    manifest = _manifest(opening)
    rows = _rows(opening)
    attestation = attest_rollout_panel(
        rows,
        manifest=manifest,
        pre_action_state_commitments={"off": DIGEST_A, "control": DIGEST_A},
    )
    changed_manifest = replace(manifest, simulator_fingerprint=DIGEST_D)
    with pytest.raises(BranchingManifestError, match="does not match"):
        verify_rollout_attestation(
            rows, manifest=changed_manifest, attestation=attestation
        )


def test_unbalanced_or_uncommitted_draw_panels_fail_closed():
    opening = _opening()
    manifest = _manifest(opening)
    rows = _rows(opening)
    rows.pop()
    with pytest.raises(BranchingManifestError, match="balanced"):
        attest_rollout_panel(
            rows,
            manifest=manifest,
            pre_action_state_commitments={"off": DIGEST_A, "control": DIGEST_A},
        )


def test_pre_action_divergence_is_rejected():
    opening = _opening()
    with pytest.raises(BranchingManifestError, match="diverged"):
        attest_rollout_panel(
            _rows(opening),
            manifest=_manifest(opening),
            pre_action_state_commitments={"off": DIGEST_A, "control": DIGEST_B},
        )


def test_policy_definitions_reject_noncanonical_numbers():
    opening = _opening()
    with pytest.raises(BranchingManifestError, match="non-finite"):
        build_branching_manifest(
            manifest_id="bad",
            opening_history=opening,
            hidden_opening_state_sha256=DIGEST_A,
            generator_fingerprint=DIGEST_B,
            simulator_fingerprint=DIGEST_C,
            evaluator_image_digest=DIGEST_D,
            policy_definitions={"off": {}, "bad": {"level": float("nan")}},
            posterior_draw_commitments={"a": DIGEST_A, "b": DIGEST_B},
            intervention_effect_draw_commitments={"a": DIGEST_C, "b": DIGEST_D},
            future_seeds=(1, 2),
        )
