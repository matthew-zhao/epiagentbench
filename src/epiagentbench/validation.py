"""Seed-panel diagnostics for the experimental Starsim surveillance slice."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import hmac
import secrets
import time
from typing import Any, Iterable, Mapping

from .scoring import closed_loop_response_fraction
from .trusted.starsim_episode import (
    LIVE_ALERT_ADMISSION_RULE_ID,
    LIVE_ALERT_COUNT_BANDS,
    LIVE_ALERT_COUNT_STRATA,
    StarsimSurveillanceBackend,
    _live_alert_count_stratum,
)
from .trusted.surveillance import load_gi_surveillance_profile


CONSTANT_POLICY_SHORTCUT_THRESHOLD = 0.80
# These policies are intentionally fixed in code rather than optimized on the
# reported panel.  They cover the alert-count triage rule found in the first
# diagnostic plus two broader, plausible count-only heuristics.  None may use
# follow-up evidence, forecasts, or response observations.
ALERT_COUNT_ONLY_POLICIES: Mapping[str, tuple[int, int]] = {
    "alert_triage_10_12": (10, 12),
    "alert_triage_8_16": (8, 16),
    "alert_triage_10_20": (10, 20),
    "alert_binary_10": (10, 10),
}

LIVE_MODE_FAMILIES: Mapping[str, str] = {
    "institution_person_to_person": "person_to_person",
    "restaurant_point_source": "common_source",
    "repeated_introduction": "repeated_introduction",
    "coincidental_venue": "background",
    "reporting_artifact": "reporting_artifact",
}
RESPONSE_ACTION_TYPES = (
    "infection_control",
    "source_control",
    "entry_control",
    "audit_reporting",
)
RESPONSE_LEVELS = ("standard", "intensive")
# These count-only policies are declared in code and are never optimized on a
# validation panel. They are deliberately crude probes for the failure mode in
# which one opening alert count selects a high-reward action without doing an
# investigation.
LIVE_ALERT_COUNT_ACTION_POLICIES: Mapping[
    str, tuple[int, int, str, str, str]
] = {
    "off_source_infection_8_16": (
        8,
        16,
        "off",
        "source_control_standard",
        "infection_control_standard",
    ),
    "audit_entry_infection_10_18": (
        10,
        18,
        "audit_reporting_standard",
        "entry_control_standard",
        "infection_control_standard",
    ),
    "off_entry_source_10_18": (
        10,
        18,
        "off",
        "entry_control_standard",
        "source_control_intensive",
    ),
}


def run_live_mode_panel(
    *, start_seed: int = 0, seeds_per_mode: int = 4
) -> dict[str, Any]:
    """Probe five live causal modes and obvious response-policy shortcuts.

    Episodes with the same seed form a *candidate comparison group*. The
    report measures whether their minute-zero public counts fall within a
    declared caliper, but intentionally does not call them matched causal
    twins: sharing a seed and similar margins is not sufficient causal
    matching.
    """

    if type(start_seed) is not int or start_seed < 0:
        raise ValueError("start_seed must be a non-negative integer")
    if type(seeds_per_mode) is not int or seeds_per_mode < 1:
        raise ValueError("seeds_per_mode must be a positive integer")

    backend = StarsimSurveillanceBackend()
    # Match production's episode-secret boundary: one unpublished random panel
    # key derives a distinct presentation key for every episode.  The key and
    # its derivatives are never included in the report.
    panel_presentation_secret = secrets.token_bytes(32)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    started = time.monotonic()
    for seed in range(start_seed, start_seed + seeds_per_mode):
        for family, expected_mode in LIVE_MODE_FAMILIES.items():
            runtime = None
            episode_started = time.monotonic()
            try:
                runtime = backend.create_runtime(
                    seed=seed,
                    family=family,
                    presentation_key=hmac.new(
                        panel_presentation_secret,
                        f"{seed}:{family}".encode("ascii"),
                        hashlib.sha256,
                    ).digest(),
                )
                mode = getattr(runtime, "causal_mode", expected_mode)
                if mode != expected_mode:
                    raise RuntimeError("live family selected an unexpected mode")
                public_features = _minute_zero_public_features(
                    runtime.public_episode
                )
                oracle = runtime.finalize()
                metrics = oracle.counterfactual_metrics
                fixed_utilities = _live_fixed_response_utilities(metrics)
                expected_fixed_policies = {"off"} | {
                    f"{action}_{level}"
                    for action in RESPONSE_ACTION_TYPES
                    for level in RESPONSE_LEVELS
                }
                if set(fixed_utilities) != expected_fixed_policies:
                    raise RuntimeError(
                        "live oracle is missing fixed single-action utilities"
                    )
                best_fixed_utility = float(
                    metrics.get(
                        "closed_loop_best_fixed_utility",
                        max(fixed_utilities.values()),
                    )
                )
                if best_fixed_utility + 1e-9 < max(fixed_utilities.values()):
                    raise RuntimeError(
                        "best fixed response is worse than a declared fixed policy"
                    )
                rows.append(
                    {
                        "seed": seed,
                        "family": family,
                        "causal_mode": mode,
                        "is_outbreak": oracle.is_outbreak,
                        **public_features,
                        "best_fixed_response_action": str(
                            metrics.get(
                                "best_fixed_response_action", "unknown"
                            )
                        ),
                        "best_fixed_response_bundle": str(
                            metrics.get(
                                "best_fixed_response_bundle", "unknown"
                            )
                        ),
                        "best_fixed_utility": best_fixed_utility,
                        "fixed_response_utilities": fixed_utilities,
                        "generation_and_finalization_seconds": round(
                            time.monotonic() - episode_started, 6
                        ),
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "seed": seed,
                        "family": family,
                        "error_type": type(exc).__name__,
                    }
                )
            finally:
                if runtime is not None:
                    runtime.close()

    candidate_groups = _candidate_match_diagnostics(rows, seeds_per_mode)
    constant_diagnostics = _fixed_response_policy_diagnostics(rows)
    alert_diagnostics = _live_alert_count_policy_diagnostics(rows)
    constant_shortcut = _policy_shortcut_present(constant_diagnostics)
    alert_shortcut = _policy_shortcut_present(alert_diagnostics)
    expected_rows = seeds_per_mode * len(LIVE_MODE_FAMILIES)
    modes_present = {
        str(row["causal_mode"])
        for row in rows
    }
    surface_signatures = {
        str(row["policy_surface_signature"]) for row in rows
    }

    return {
        "profile_id": (
            getattr(backend, "live_profile_id", None)
            or "gi_surveillance_v2"
        ),
        "diagnostic_status": "experimental_not_calibrated",
        "requested_seeds_per_mode": seeds_per_mode,
        "requested_episodes": expected_rows,
        "presentation_secret_commitment": (
            "sha256:" + hashlib.sha256(panel_presentation_secret).hexdigest()
        ),
        "presentation_secret_persisted": False,
        "panel_exactly_replayable": False,
        "replayability_caveat": (
            "seed range is declared, but the fresh unpublished presentation "
            "secret also keys trajectories and is not persisted"
        ),
        "successful_episodes": len(rows),
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "causal_mode_counts": {
            mode: sum(row["causal_mode"] == mode for row in rows)
            for mode in LIVE_MODE_FAMILIES.values()
        },
        "outbreak_truth_by_mode": {
            mode: {
                "outbreak": sum(
                    row["causal_mode"] == mode and bool(row["is_outbreak"])
                    for row in rows
                ),
                "not_outbreak": sum(
                    row["causal_mode"] == mode
                    and not bool(row["is_outbreak"])
                    for row in rows
                ),
            }
            for mode in LIVE_MODE_FAMILIES.values()
        },
        "best_fixed_response_action_counts": {
            action: sum(
                row["best_fixed_response_action"] == action for row in rows
            )
            for action in ("off",) + RESPONSE_ACTION_TYPES
        },
        "candidate_match_diagnostics": candidate_groups,
        "constant_response_policy_diagnostics": constant_diagnostics,
        "alert_count_only_response_policy_diagnostics": alert_diagnostics,
        "shortcut_threshold": CONSTANT_POLICY_SHORTCUT_THRESHOLD,
        "constant_response_shortcut_present": constant_shortcut,
        "alert_count_only_response_shortcut_present": alert_shortcut,
        "simple_response_shortcut_present": (
            constant_shortcut or alert_shortcut
        ),
        "policy_surface_signature_count": len(surface_signatures),
        "claim_status": {
            "five_live_causal_modes": (
                len(rows) == expected_rows
                and modes_present == set(LIVE_MODE_FAMILIES.values())
            ),
            "common_public_policy_surface": (
                bool(rows) and len(surface_signatures) == 1
            ),
            "candidate_group_count_caliper_diagnostic": True,
            "candidate_seed_groups_complete": (
                candidate_groups["complete_groups"] == seeds_per_mode
            ),
            "matched_causal_twins": False,
            "matched_causal_twins_reason": (
                "same-seed groups and count calipers do not establish exchangeable "
                "counterfactual twins"
            ),
            "constant_response_shortcut_guardrail_pass": (
                len(rows) == expected_rows and not constant_shortcut
            ),
            "alert_count_shortcut_guardrail_pass": (
                len(rows) == expected_rows and not alert_shortcut
            ),
            "held_out_calibration": False,
            "calibrated_transmission_model": False,
            "leaderboard_ready": False,
        },
        "episodes": rows,
        "failures": failures,
    }


def run_adaptive_live_mode_audit(
    *,
    training_start_seed: int = 0,
    training_seeds_per_mode: int = 8,
    heldout_start_seed: int = 10_000,
    heldout_seeds_per_mode: int = 8,
) -> dict[str, Any]:
    """Fit reward-seeking shortcut agents and test them on a disjoint panel.

    The policies may use only minute-zero observations or presentation/schema
    metadata.  Private labels remain in trusted rows solely to compute rewards.
    This is an adversarial benchmark audit, not an epidemiologic estimator.
    """

    from .adversarial import (
        run_adaptive_reward_hacking_audit,
        run_reference_integrity_attack_matrix,
        run_secure_public_capability_probe_matrix,
    )

    if (
        type(training_start_seed) is not int
        or type(heldout_start_seed) is not int
        or training_start_seed < 0
        or heldout_start_seed < 0
        or type(training_seeds_per_mode) is not int
        or type(heldout_seeds_per_mode) is not int
        or training_seeds_per_mode < 2
        or heldout_seeds_per_mode < 2
    ):
        raise ValueError("invalid adaptive-audit seed panels")
    training_seeds = set(
        range(
            training_start_seed,
            training_start_seed + training_seeds_per_mode,
        )
    )
    heldout_seeds = set(
        range(
            heldout_start_seed,
            heldout_start_seed + heldout_seeds_per_mode,
        )
    )
    if training_seeds & heldout_seeds:
        raise ValueError("adaptive-audit fit and development-check seeds overlap")

    training = run_live_mode_panel(
        start_seed=training_start_seed,
        seeds_per_mode=training_seeds_per_mode,
    )
    heldout = run_live_mode_panel(
        start_seed=heldout_start_seed,
        seeds_per_mode=heldout_seeds_per_mode,
    )
    expected_training = training_seeds_per_mode * len(LIVE_MODE_FAMILIES)
    expected_heldout = heldout_seeds_per_mode * len(LIVE_MODE_FAMILIES)
    complete = (
        training["successful_episodes"] == expected_training
        and heldout["successful_episodes"] == expected_heldout
    )
    shortcut_report: dict[str, Any] | None = None
    if complete:
        shortcut_report = run_adaptive_reward_hacking_audit(
            training["episodes"],
            heldout["episodes"],
            observation_features=(
                "initial_alert_count",
                "initial_public_patient_count",
                "initial_positive_lab_count",
            ),
            metadata_features=(
                "schema_version",
                "episode_id_bucket",
                "policy_pack_id_bucket",
            ),
            max_depth=3,
            min_leaf=3,
        )
    scorer_tripwires = run_reference_integrity_attack_matrix()
    live_capability_probes = run_secure_public_capability_probe_matrix()
    integrity_pass = (
        scorer_tripwires["guardrail_pass"]
        and live_capability_probes["guardrail_pass"]
    )
    return {
        "audit_version": "adaptive_live_mode_audit_v1",
        "split_status": (
            "declared_disjoint_seed_ranges_with_fresh_unpublished_presentation_"
            "secrets_not_authenticated_private_holdout"
        ),
        "uncertainty_caveat": (
            "single pair of non-replayable panels; presentation-secret and "
            "repeated-split uncertainty are not estimated"
        ),
        "training_split": {
            "role": "development_fit_panel",
            "start_seed": training_start_seed,
            "seeds_per_mode": training_seeds_per_mode,
            "presentation_secret_commitment": training[
                "presentation_secret_commitment"
            ],
            "panel_exactly_replayable": training[
                "panel_exactly_replayable"
            ],
            "successful_episodes": training["successful_episodes"],
            "failures": training["failures"],
        },
        "heldout_split": {
            "role": "disjoint_development_check_panel",
            "start_seed": heldout_start_seed,
            "seeds_per_mode": heldout_seeds_per_mode,
            "presentation_secret_commitment": heldout[
                "presentation_secret_commitment"
            ],
            "panel_exactly_replayable": heldout[
                "panel_exactly_replayable"
            ],
            "successful_episodes": heldout["successful_episodes"],
            "failures": heldout["failures"],
        },
        "adaptive_reward_hacking": shortcut_report,
        "scorer_tripwire_matrix": scorer_tripwires,
        "secure_public_capability_probes": live_capability_probes,
        "guardrail_pass": bool(
            complete
            and shortcut_report is not None
            and shortcut_report["guardrail_pass"]
            and integrity_pass
        ),
        "adversarial_guardrail_gate": (
            "pass"
            if complete
            and shortcut_report is not None
            and shortcut_report["guardrail_pass"]
            and integrity_pass
            else "fail"
        ),
    }


def _minute_zero_public_features(public_episode: Any) -> dict[str, Any]:
    """Extract only records actually visible at the opening transcript."""

    manifest = public_episode.manifest
    visible = [
        observation
        for observation in public_episode.observations
        if observation.available_minute <= 0
        and observation.release_key in {"initial", "stream"}
    ]
    alert_ids = set(manifest.get("initial_alert_ids", []))
    alerts = [
        observation
        for observation in visible
        if observation.observation_id in alert_ids
        and observation.kind == "alert"
    ]
    if len(alerts) != 1 or type(alerts[0].payload.get("observed_count")) is not int:
        raise ValueError("invalid minute-zero alert")
    patient_ids = {
        observation.payload.get("patient_id")
        for observation in visible
        if isinstance(observation.payload.get("patient_id"), str)
    }
    positive_labs = sum(
        observation.kind == "lab"
        and str(observation.payload.get("result", "")).endswith("_positive")
        for observation in visible
    )
    policy = next(
        (observation for observation in visible if observation.kind == "policy"),
        None,
    )
    if policy is None:
        raise ValueError("minute-zero policy is missing")
    catalog = policy.payload.get("response_control_catalog", {})
    catalog_signature: tuple[Any, ...] = ()
    if isinstance(catalog, Mapping):
        catalog_signature = tuple(
            sorted(
                (
                    action,
                    tuple(entry.get("levels", []))
                    if isinstance(entry, Mapping)
                    else (),
                )
                for action, entry in catalog.items()
            )
        )
    surface_signature = (
        tuple(manifest.get("enabled_tools", [])),
        tuple(policy.payload.get("permitted", [])),
        catalog_signature,
    )
    return {
        "initial_alert_count": int(alerts[0].payload["observed_count"]),
        "initial_public_patient_count": len(patient_ids),
        "initial_positive_lab_count": positive_labs,
        "policy_surface_signature": repr(surface_signature),
        # These are intentionally low-capacity transforms of presentation-only
        # fields. A reward-hacking tree should not predict the winning action
        # from them on a disjoint seed split.
        "schema_version": str(manifest.get("schema_version", "missing")),
        "episode_id_bucket": _opaque_id_bucket(manifest.get("episode_id")),
        "policy_pack_id_bucket": _opaque_id_bucket(
            manifest.get("policy_pack")
        ),
    }


def _opaque_id_bucket(value: object) -> int:
    if not isinstance(value, str):
        return -1
    suffix = value.rsplit("_", 1)[-1]
    if len(suffix) != 16:
        return -1
    try:
        return int(suffix[:2], 16) % 16
    except ValueError:
        return -1


def _live_fixed_response_utilities(
    metrics: Mapping[str, float | int | str],
) -> dict[str, float]:
    utilities = {
        "off": float(metrics.get("closed_loop_fixed_off_utility", 0.0))
    }
    for action in RESPONSE_ACTION_TYPES:
        for level in RESPONSE_LEVELS:
            key = f"closed_loop_fixed_{action}_{level}_utility"
            value = metrics.get(key)
            if value is None and action == "infection_control":
                value = metrics.get(f"closed_loop_fixed_{level}_utility")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                utilities[f"{action}_{level}"] = float(value)
    return utilities


def _fixed_response_policy_diagnostics(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, float | int | None]]:
    materialized = tuple(rows)
    policy_names = ("off",) + tuple(
        f"{action}_{level}"
        for action in RESPONSE_ACTION_TYPES
        for level in RESPONSE_LEVELS
    )
    summaries: dict[str, dict[str, float | int | None]] = {}
    for policy_name in policy_names:
        scores: list[float] = []
        regrets: list[float] = []
        harmful = 0
        for row in materialized:
            utilities = row["fixed_response_utilities"]
            if policy_name not in utilities:
                continue
            utility = float(utilities[policy_name])
            off = float(utilities["off"])
            best = float(row["best_fixed_utility"])
            scores.append(
                closed_loop_response_fraction(
                    realized_utility=utility,
                    no_action_utility=off,
                    best_fixed_utility=best,
                )
            )
            regrets.append(best - utility)
            harmful += utility < off
        count = len(scores)
        summaries[policy_name] = {
            "episodes": count,
            "mean_normalized_response_score": (
                round(sum(scores) / count, 6) if count else None
            ),
            "mean_regret_vs_best_fixed": (
                round(sum(regrets) / count, 6) if count else None
            ),
            "harm_rate_below_no_action": (
                round(harmful / count, 6) if count else None
            ),
        }
    return summaries


def _live_alert_count_policy_diagnostics(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, float | int | None]]:
    materialized = tuple(rows)
    summaries: dict[str, dict[str, float | int | None]] = {}
    for name, (low, high, low_policy, mid_policy, high_policy) in (
        LIVE_ALERT_COUNT_ACTION_POLICIES.items()
    ):
        scores: list[float] = []
        regrets: list[float] = []
        harmful = 0
        for row in materialized:
            count = int(row["initial_alert_count"])
            policy = (
                low_policy
                if count <= low
                else mid_policy
                if count <= high
                else high_policy
            )
            utilities = row["fixed_response_utilities"]
            if policy not in utilities:
                continue
            utility = float(utilities[policy])
            off = float(utilities["off"])
            best = float(row["best_fixed_utility"])
            scores.append(
                closed_loop_response_fraction(
                    realized_utility=utility,
                    no_action_utility=off,
                    best_fixed_utility=best,
                )
            )
            regrets.append(best - utility)
            harmful += utility < off
        episodes = len(scores)
        summaries[name] = {
            "episodes": episodes,
            "low_max_alert_count": low,
            "high_max_alert_count": high,
            "mean_normalized_response_score": (
                round(sum(scores) / episodes, 6) if episodes else None
            ),
            "mean_regret_vs_best_fixed": (
                round(sum(regrets) / episodes, 6) if episodes else None
            ),
            "harm_rate_below_no_action": (
                round(harmful / episodes, 6) if episodes else None
            ),
        }
    return summaries


def _candidate_match_diagnostics(
    rows: Iterable[Mapping[str, Any]], seeds_per_mode: int
) -> dict[str, Any]:
    materialized = tuple(rows)
    groups: list[dict[str, Any]] = []
    for seed in sorted({int(row["seed"]) for row in materialized}):
        group = [row for row in materialized if row["seed"] == seed]
        complete = len(group) == len(LIVE_MODE_FAMILIES)
        alert_values = [int(row["initial_alert_count"]) for row in group]
        patient_values = [
            int(row["initial_public_patient_count"]) for row in group
        ]
        alert_spread = max(alert_values) - min(alert_values) if alert_values else None
        patient_spread = (
            max(patient_values) - min(patient_values) if patient_values else None
        )
        within_caliper = bool(
            complete
            and alert_spread is not None
            and patient_spread is not None
            and alert_spread <= 6
            and patient_spread <= 6
        )
        groups.append(
            {
                "seed": seed,
                "episodes": len(group),
                "complete": complete,
                "alert_count_spread": alert_spread,
                "public_patient_count_spread": patient_spread,
                "within_predeclared_count_caliper": within_caliper,
            }
        )
    complete_groups = sum(bool(group["complete"]) for group in groups)
    caliper_groups = sum(
        bool(group["within_predeclared_count_caliper"]) for group in groups
    )
    return {
        "requested_groups": seeds_per_mode,
        "complete_groups": complete_groups,
        "predeclared_alert_count_max_spread": 6,
        "predeclared_public_patient_count_max_spread": 6,
        "groups_within_count_caliper": caliper_groups,
        "count_caliper_rate_among_complete_groups": (
            round(caliper_groups / complete_groups, 6)
            if complete_groups
            else None
        ),
        "causal_match_claim": False,
        "groups": groups,
    }


def run_closed_loop_policy_panel(
    *, start_seed: int = 0, seeds: int = 10
) -> dict[str, Any]:
    """Compare declared fixed policies across hidden closed-loop strata.

    This is a diagnostic of task diversity, not a calibration result. Each
    runtime is left uncontrolled publicly; its trusted finalizer also evaluates
    the preregistered always-standard and always-intensive comparison policies.
    """

    if type(start_seed) is not int or start_seed < 0:
        raise ValueError("start_seed must be a non-negative integer")
    if type(seeds) is not int or seeds < 1:
        raise ValueError("seeds must be a positive integer")

    backend = StarsimSurveillanceBackend()
    presentation_key = b"eab-live-policy-panel-key-0001"
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    started = time.monotonic()
    for seed in range(start_seed, start_seed + seeds):
        runtime = None
        episode_started = time.monotonic()
        try:
            runtime = backend.create_runtime(
                seed=seed,
                family="institution_person_to_person",
                presentation_key=presentation_key,
            )
            regime = runtime.growth_regime
            alert_count_stratum = _live_alert_count_stratum(
                presentation_key, seed
            )
            diagnostics = asdict(runtime.initial_diagnostics)
            oracle = runtime.finalize()
            metrics = oracle.counterfactual_metrics
            utilities = {
                level: float(metrics[f"closed_loop_fixed_{level}_utility"])
                for level in ("off", "standard", "intensive")
            }
            best_policy = max(utilities, key=utilities.get)
            best_utility = utilities[best_policy]
            normalized_scores = {
                level: closed_loop_response_fraction(
                    realized_utility=utility,
                    no_action_utility=utilities["off"],
                    best_fixed_utility=best_utility,
                )
                for level, utility in utilities.items()
            }
            rows.append(
                {
                    "seed": seed,
                    "growth_stratum": regime,
                    "admission_alert_count_stratum": alert_count_stratum,
                    "is_outbreak": oracle.is_outbreak,
                    "initial_alert_count": diagnostics["alert_count"],
                    "no_action_infections": int(
                        metrics["counterfactual_no_action_infections"]
                    ),
                    "best_fixed_policy": best_policy,
                    "fixed_policy_utilities": utilities,
                    "fixed_policy_normalized_response_scores": {
                        level: round(score, 6)
                        for level, score in normalized_scores.items()
                    },
                    "fixed_policy_regrets": {
                        level: round(best_utility - utility, 6)
                        for level, utility in utilities.items()
                    },
                    "generation_and_finalization_seconds": round(
                        time.monotonic() - episode_started, 6
                    ),
                }
            )
        except Exception as exc:
            failures.append(
                {"seed": seed, "error_type": type(exc).__name__}
            )
        finally:
            if runtime is not None:
                runtime.close()

    policy_counts = {
        level: sum(row["best_fixed_policy"] == level for row in rows)
        for level in ("off", "standard", "intensive")
    }
    regime_counts = {
        level: sum(row["growth_stratum"] == level for row in rows)
        for level in ("low", "medium", "high")
    }
    alert_count_stratum_counts = {
        level: sum(
            row["admission_alert_count_stratum"] == level for row in rows
        )
        for level in LIVE_ALERT_COUNT_STRATA
    }
    constant_policy_diagnostics = _constant_policy_diagnostics(rows)
    alert_count_policy_diagnostics = _alert_count_policy_diagnostics(rows)
    constant_shortcut = _constant_policy_shortcut_present(
        constant_policy_diagnostics
    )
    public_feature_shortcut = _policy_shortcut_present(
        alert_count_policy_diagnostics
    )
    return {
        "profile_id": load_gi_surveillance_profile()["profile_id"],
        "diagnostic_status": "experimental_not_calibrated",
        "requested_seeds": seeds,
        "successful_seeds": len(rows),
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "admission_rule_id": LIVE_ALERT_ADMISSION_RULE_ID,
        "admission_alert_count_bands": {
            name: list(LIVE_ALERT_COUNT_BANDS[name])
            for name in LIVE_ALERT_COUNT_STRATA
        },
        "growth_stratum_counts": regime_counts,
        "admission_alert_count_stratum_counts": alert_count_stratum_counts,
        "outbreak_truth_counts": {
            "outbreak": sum(bool(row["is_outbreak"]) for row in rows),
            "not_outbreak": sum(
                not bool(row["is_outbreak"]) for row in rows
            ),
        },
        "best_fixed_policy_counts": policy_counts,
        "constant_policy_diagnostics": constant_policy_diagnostics,
        "alert_count_only_policy_diagnostics": (
            alert_count_policy_diagnostics
        ),
        "constant_policy_shortcut_definition": (
            "any fixed policy with mean normalized response score >= "
            f"{CONSTANT_POLICY_SHORTCUT_THRESHOLD:.2f}"
        ),
        "constant_policy_shortcut_threshold": (
            CONSTANT_POLICY_SHORTCUT_THRESHOLD
        ),
        "max_constant_policy_mean_normalized_response": max(
            (
                float(values["mean_normalized_response_score"] or 0.0)
                for values in constant_policy_diagnostics.values()
            ),
            default=0.0,
        ),
        "constant_policy_shortcut_present": constant_shortcut,
        "public_feature_shortcut_definition": (
            "any preregistered minute-zero alert-count-only policy with mean "
            "normalized response score >= "
            f"{CONSTANT_POLICY_SHORTCUT_THRESHOLD:.2f}"
        ),
        "max_alert_count_only_policy_mean_normalized_response": max(
            (
                float(values["mean_normalized_response_score"] or 0.0)
                for values in alert_count_policy_diagnostics.values()
            ),
            default=0.0,
        ),
        "public_feature_shortcut_present": public_feature_shortcut,
        "simple_policy_shortcut_present": (
            constant_shortcut or public_feature_shortcut
        ),
        "claim_status": {
            "action_dependent_observations": True,
            "closed_loop_intervention": True,
            "natural_false_alerts": True,
            "public_time_zero_admission_only": True,
            "public_alert_count_stratified_admission": True,
            "public_feature_shortcut_guardrail_pass": (
                len(rows) == seeds
                and not (constant_shortcut or public_feature_shortcut)
            ),
            "prospective_forecast_scoring": True,
            "matched_causal_twins": False,
            "multiple_transmission_modes": False,
            "calibrated_transmission_model": False,
            "leaderboard_ready": False,
        },
        "episodes": rows,
        "failures": failures,
    }


def _constant_policy_diagnostics(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, float | int | None]]:
    """Summarize constant policies by reward, regret, and downside harm."""

    materialized = tuple(rows)
    summaries: dict[str, dict[str, float | int | None]] = {}
    for level in ("off", "standard", "intensive"):
        utilities: list[float] = []
        normalized_scores: list[float] = []
        regrets: list[float] = []
        harmful = 0
        for row in materialized:
            fixed = {
                key: float(value)
                for key, value in row["fixed_policy_utilities"].items()
            }
            utility = fixed[level]
            no_action = fixed["off"]
            best = max(fixed.values())
            utilities.append(utility)
            normalized_scores.append(
                closed_loop_response_fraction(
                    realized_utility=utility,
                    no_action_utility=no_action,
                    best_fixed_utility=best,
                )
            )
            regrets.append(best - utility)
            harmful += utility < no_action

        count = len(utilities)
        summaries[level] = {
            "episodes": count,
            "mean_normalized_response_score": (
                round(sum(normalized_scores) / count, 6) if count else None
            ),
            "mean_regret_vs_best_fixed": (
                round(sum(regrets) / count, 6) if count else None
            ),
            "harm_rate_below_no_action": (
                round(harmful / count, 6) if count else None
            ),
            "worst_utility": round(min(utilities), 6) if count else None,
        }
    return summaries


def _constant_policy_shortcut_present(
    diagnostics: Mapping[str, Mapping[str, float | int | None]],
) -> bool:
    return _policy_shortcut_present(diagnostics)


def _policy_shortcut_present(
    diagnostics: Mapping[str, Mapping[str, float | int | None]],
) -> bool:
    return any(
        float(values["mean_normalized_response_score"] or 0.0)
        >= CONSTANT_POLICY_SHORTCUT_THRESHOLD
        for values in diagnostics.values()
    )


def _alert_count_policy_diagnostics(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, float | int | None]]:
    """Evaluate fixed one-shot policies that may read only the initial count."""

    materialized = tuple(rows)
    summaries: dict[str, dict[str, float | int | None]] = {}
    for policy_name, (off_max, standard_max) in ALERT_COUNT_ONLY_POLICIES.items():
        normalized_scores: list[float] = []
        regrets: list[float] = []
        harmful = 0
        for row in materialized:
            alert_count = row["initial_alert_count"]
            if type(alert_count) is not int or alert_count < 0:
                raise ValueError("invalid alert count in policy diagnostic")
            level = (
                "off"
                if alert_count <= off_max
                else "standard"
                if alert_count <= standard_max
                else "intensive"
            )
            fixed = {
                key: float(value)
                for key, value in row["fixed_policy_utilities"].items()
            }
            utility = fixed[level]
            no_action = fixed["off"]
            best = max(fixed.values())
            normalized_scores.append(
                closed_loop_response_fraction(
                    realized_utility=utility,
                    no_action_utility=no_action,
                    best_fixed_utility=best,
                )
            )
            regrets.append(best - utility)
            harmful += utility < no_action

        count = len(materialized)
        summaries[policy_name] = {
            "episodes": count,
            "off_max_alert_count": off_max,
            "standard_max_alert_count": standard_max,
            "mean_normalized_response_score": (
                round(sum(normalized_scores) / count, 6) if count else None
            ),
            "mean_regret_vs_best_fixed": (
                round(sum(regrets) / count, 6) if count else None
            ),
            "harm_rate_below_no_action": (
                round(harmful / count, 6) if count else None
            ),
        }
    return summaries


def run_starsim_seed_panel(*, start_seed: int = 0, seeds: int = 10) -> dict[str, Any]:
    """Generate a reproducible diagnostic panel without claiming calibration.

    The report compares like-for-like observed case counts with the frozen NORS
    reference target.  It deliberately marks attack-rate and reproduction-number
    comparisons as unresolved because the current generic SIR cohort does not
    reproduce those study estimands.
    """

    if type(start_seed) is not int or start_seed < 0:
        raise ValueError("start_seed must be a non-negative integer")
    if type(seeds) is not int or seeds < 1:
        raise ValueError("seeds must be a positive integer")

    profile = load_gi_surveillance_profile()
    population = int(profile["transmission_configuration"]["population_size"])
    backend = StarsimSurveillanceBackend(profile)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    started = time.monotonic()
    for seed in range(start_seed, start_seed + seeds):
        episode_started = time.monotonic()
        try:
            episode = backend.create_scored_episode(seed=seed)
        except Exception as exc:
            failures.append(
                {
                    "seed": seed,
                    "error_type": type(exc).__name__,
                }
            )
            continue
        diagnostics = asdict(episode.diagnostics)
        counterfactual = episode.bundle.oracle.counterfactual_metrics
        rows.append(
            {
                "seed": seed,
                **diagnostics,
                "latent_attack_rate": round(
                    diagnostics["latent_infections"] / population, 6
                ),
                "early_control_infections": int(
                    counterfactual["counterfactual_early_control_infections"]
                ),
                "infections_averted": int(
                    counterfactual["counterfactual_infections_averted"]
                ),
                "generation_seconds": round(
                    time.monotonic() - episode_started, 6
                ),
            }
        )

    observed_cases = [float(row["true_cases"]) for row in rows]
    latent_infections = [float(row["latent_infections"]) for row in rows]
    attack_rates = [float(row["latent_attack_rate"]) for row in rows]
    attempts = [float(row["generation_attempts"]) for row in rows]
    generation_times = [float(row["generation_seconds"]) for row in rows]
    outbreak_target = profile["posterior_predictive_targets"]["outbreak_size"]
    lower, upper = (float(value) for value in outbreak_target["iqr"])
    fraction_in_reported_iqr = (
        sum(lower <= value <= upper for value in observed_cases)
        / len(observed_cases)
        if observed_cases
        else 0.0
    )

    return {
        "profile_id": profile["profile_id"],
        "profile_status": profile["profile_status"],
        "requested_seeds": seeds,
        "successful_seeds": len(rows),
        "generation_success_rate": len(rows) / seeds,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "summaries": {
            "observed_true_cases": _numeric_summary(observed_cases),
            "latent_infections": _numeric_summary(latent_infections),
            "latent_attack_rate": _numeric_summary(attack_rates),
            "generation_attempts": _numeric_summary(attempts),
            "generation_seconds": _numeric_summary(generation_times),
        },
        "target_comparisons": {
            "reported_outbreak_size": {
                "comparable": True,
                "target_median": outbreak_target["median"],
                "target_iqr": outbreak_target["iqr"],
                "panel_fraction_in_target_iqr": round(
                    fraction_in_reported_iqr, 6
                ),
                "interpretation": (
                    "diagnostic only; this panel has not been fit to or held out "
                    "from the cited target"
                ),
            },
            "attack_rate": {
                "comparable": False,
                "reason": (
                    "the current denominator is the entire simulated cohort, "
                    "not the exposed-population estimand in the source study"
                ),
            },
            "effective_reproduction_number": {
                "comparable": False,
                "reason": "the study's final-size estimator is not implemented",
            },
        },
        "claim_status": {
            "starsim_observation_vertical_slice": True,
            "calibrated_transmission_model": False,
            "epidemiologically_validated": False,
            "leaderboard_ready": False,
            "remaining_gates": [
                "matched no-outbreak and alternative-action Starsim families",
                "held-out posterior-predictive calibration",
                "epidemiologist review",
                "human solveability and inter-rater study",
                "stakeholder utility calibration",
            ],
        },
        "episodes": rows,
        "failures": failures,
    }


def _numeric_summary(values: Iterable[float]) -> dict[str, float | int | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {"n": 0, "min": None, "q25": None, "median": None, "q75": None, "max": None}
    return {
        "n": len(ordered),
        "min": ordered[0],
        "q25": _quantile(ordered, 0.25),
        "median": _quantile(ordered, 0.5),
        "q75": _quantile(ordered, 0.75),
        "max": ordered[-1],
    }


def _quantile(ordered: list[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])
