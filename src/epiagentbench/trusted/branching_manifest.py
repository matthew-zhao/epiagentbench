"""Development-only caller-attested rollout contracts.

SECURITY WARNING: this legacy module accepts caller-supplied outcome rows and
pre-action digests.  Its hashes detect accidental substitution but do not prove
that Starsim ran or that branches shared an opening state.  It must not award
benchmark credit.  The evaluator-owned LTC path is :mod:`ltc_branching`, which
replays the engine and authenticates receipts before evaluation.

The manifest binds the opening state, runtime, policy definitions, and all
uncertainty axes before outcome rows are admitted to decision analysis.  The
post-rollout attestation then binds the exact balanced row panel and verifies
that every policy branch had the same pre-action state commitment.

These digests detect substitution; they do not prove when a manifest was made,
who made it, that a simulator executed it, or that the simulator is realistic.
External custody/signing is required for those claims.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .intervention_evaluation import (
    InterventionEvaluationReport,
    OpeningHistoryCommitment,
    PolicyOutcomeDraw,
    StakeholderWeightProfile,
    evaluate_policy_panel,
)


MANIFEST_VERSION = "epiagentbench.branching-manifest.v1"
SECURITY_STATUS = "development_untrusted_caller_attested"
ATTESTATION_VERSION = "epiagentbench.rollout-panel-attestation.v1"
COUNTERFACTUAL_PROTOCOL = "common_random_numbers_no_pre_action_divergence_v1"
CLAIM_LIMITS = (
    "Digests detect content substitution but do not prove execution order.",
    "Caller-supplied timestamps and commitments are not external attestation.",
    "Passing this contract is not epidemiologic calibration or validation.",
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MANIFEST_DOMAIN = b"EpiAgentBench branching manifest v1\x00"
_SEED_BANK_DOMAIN = b"EpiAgentBench future seed bank v1\x00"
_ROW_PANEL_DOMAIN = b"EpiAgentBench rollout row panel v1\x00"


class BranchingManifestError(ValueError):
    """Raised when a rollout contract is incomplete or has been substituted."""


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise BranchingManifestError(f"invalid {label}")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise BranchingManifestError(f"invalid {label}")
    return value


def _json_value(value: Any, path: str = "value") -> Any:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise BranchingManifestError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        detached: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise BranchingManifestError(f"{path} contains a non-string key")
            if key in detached:
                raise BranchingManifestError(f"{path} repeats a key")
            detached[key] = _json_value(child, f"{path}.{key}")
        return detached
    if isinstance(value, (list, tuple)):
        return [
            _json_value(child, f"{path}[{index}]")
            for index, child in enumerate(value)
        ]
    raise BranchingManifestError(f"{path} is not canonical JSON data")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        _json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _committed_mapping(
    value: Mapping[str, str], label: str, *, minimum: int = 2
) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or len(value) < minimum:
        raise BranchingManifestError(
            f"{label} must contain at least {minimum} committed entries"
        )
    detached: dict[str, str] = {}
    for key, digest in value.items():
        detached[_identifier(key, f"{label} id")] = _sha256(
            digest, f"{label} digest"
        )
    if len(detached) != len(value):
        raise BranchingManifestError(f"{label} repeats an id")
    return MappingProxyType(dict(sorted(detached.items())))


def future_seed_bank_sha256(future_seeds: Sequence[int]) -> str:
    if isinstance(future_seeds, (str, bytes)):
        raise BranchingManifestError("future_seeds must be a sequence")
    seeds = tuple(future_seeds)
    if len(seeds) < 2 or any(
        type(seed) is not int or not 0 <= seed <= 2**53 - 1 for seed in seeds
    ):
        raise BranchingManifestError(
            "future_seeds must contain at least two non-negative integers"
        )
    if len(set(seeds)) != len(seeds):
        raise BranchingManifestError("future_seeds must be unique")
    digest = hashlib.sha256(
        _SEED_BANK_DOMAIN + _canonical_json(sorted(seeds))
    ).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True, slots=True)
class BranchingManifest:
    manifest_id: str
    opening_history: OpeningHistoryCommitment
    hidden_opening_state_sha256: str
    generator_fingerprint: str
    simulator_fingerprint: str
    evaluator_image_digest: str
    policy_definitions: Mapping[str, Any]
    posterior_draw_commitments: Mapping[str, str]
    intervention_effect_draw_commitments: Mapping[str, str]
    future_seed_count: int
    future_seed_bank_sha256: str
    counterfactual_protocol: str = COUNTERFACTUAL_PROTOCOL
    manifest_version: str = MANIFEST_VERSION

    def __post_init__(self) -> None:
        _identifier(self.manifest_id, "manifest_id")
        if not isinstance(self.opening_history, OpeningHistoryCommitment):
            raise BranchingManifestError("invalid opening_history")
        for value, label in (
            (self.hidden_opening_state_sha256, "hidden opening-state digest"),
            (self.generator_fingerprint, "generator fingerprint"),
            (self.simulator_fingerprint, "simulator fingerprint"),
            (self.evaluator_image_digest, "evaluator image digest"),
            (self.future_seed_bank_sha256, "future seed-bank digest"),
        ):
            _sha256(value, label)
        if self.manifest_version != MANIFEST_VERSION:
            raise BranchingManifestError("unsupported branching manifest version")
        if self.counterfactual_protocol != COUNTERFACTUAL_PROTOCOL:
            raise BranchingManifestError("unsupported counterfactual protocol")
        if type(self.future_seed_count) is not int or self.future_seed_count < 2:
            raise BranchingManifestError("future_seed_count must be at least two")
        if not isinstance(self.policy_definitions, Mapping) or len(
            self.policy_definitions
        ) < 2:
            raise BranchingManifestError("at least two policy definitions required")
        policies: dict[str, Any] = {}
        for policy_id, definition in self.policy_definitions.items():
            policy_id = _identifier(policy_id, "policy id")
            if policy_id in policies:
                raise BranchingManifestError("duplicate policy id")
            policies[policy_id] = _json_value(
                definition, f"policy_definitions.{policy_id}"
            )
        object.__setattr__(
            self, "policy_definitions", MappingProxyType(dict(sorted(policies.items())))
        )
        object.__setattr__(
            self,
            "posterior_draw_commitments",
            _committed_mapping(
                self.posterior_draw_commitments, "posterior draws"
            ),
        )
        object.__setattr__(
            self,
            "intervention_effect_draw_commitments",
            _committed_mapping(
                self.intervention_effect_draw_commitments,
                "intervention-effect draws",
            ),
        )

    @property
    def policy_ids(self) -> tuple[str, ...]:
        return tuple(self.policy_definitions)

    @property
    def commitment(self) -> str:
        digest = hashlib.sha256(
            _MANIFEST_DOMAIN + _canonical_json(self.as_dict())
        ).hexdigest()
        return f"sha256:{digest}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "manifest_id": self.manifest_id,
            "opening_history": self.opening_history.as_dict(),
            "hidden_opening_state_sha256": self.hidden_opening_state_sha256,
            "generator_fingerprint": self.generator_fingerprint,
            "simulator_fingerprint": self.simulator_fingerprint,
            "evaluator_image_digest": self.evaluator_image_digest,
            "policy_definitions": dict(self.policy_definitions),
            "posterior_draw_commitments": dict(
                self.posterior_draw_commitments
            ),
            "intervention_effect_draw_commitments": dict(
                self.intervention_effect_draw_commitments
            ),
            "future_seed_count": self.future_seed_count,
            "future_seed_bank_sha256": self.future_seed_bank_sha256,
            "counterfactual_protocol": self.counterfactual_protocol,
            "claim_limits": list(CLAIM_LIMITS),
        }


def build_branching_manifest(
    *,
    manifest_id: str,
    opening_history: OpeningHistoryCommitment,
    hidden_opening_state_sha256: str,
    generator_fingerprint: str,
    simulator_fingerprint: str,
    evaluator_image_digest: str,
    policy_definitions: Mapping[str, Any],
    posterior_draw_commitments: Mapping[str, str],
    intervention_effect_draw_commitments: Mapping[str, str],
    future_seeds: Sequence[int],
) -> BranchingManifest:
    seeds = tuple(future_seeds)
    return BranchingManifest(
        manifest_id=manifest_id,
        opening_history=opening_history,
        hidden_opening_state_sha256=hidden_opening_state_sha256,
        generator_fingerprint=generator_fingerprint,
        simulator_fingerprint=simulator_fingerprint,
        evaluator_image_digest=evaluator_image_digest,
        policy_definitions=policy_definitions,
        posterior_draw_commitments=posterior_draw_commitments,
        intervention_effect_draw_commitments=(
            intervention_effect_draw_commitments
        ),
        future_seed_count=len(seeds),
        future_seed_bank_sha256=future_seed_bank_sha256(seeds),
    )


def _row_payload(row: PolicyOutcomeDraw) -> dict[str, Any]:
    return {
        "opening_history": row.opening_history.as_dict(),
        "policy_id": row.policy_id,
        "future_seed": row.future_seed,
        "posterior_draw_id": row.posterior_draw_id,
        "intervention_effect_draw_id": row.intervention_effect_draw_id,
        "outcomes": row.outcomes.as_dict(),
    }


def _row_panel_sha256(rows: Sequence[PolicyOutcomeDraw]) -> str:
    ordered = sorted(
        (_row_payload(row) for row in rows),
        key=lambda value: (
            value["policy_id"],
            value["future_seed"],
            value["posterior_draw_id"],
            value["intervention_effect_draw_id"],
        ),
    )
    digest = hashlib.sha256(
        _ROW_PANEL_DOMAIN + _canonical_json(ordered)
    ).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True, slots=True)
class RolloutPanelAttestation:
    manifest_commitment: str
    row_panel_sha256: str
    row_count: int
    draw_count_per_policy: int
    policy_ids: tuple[str, ...]
    pre_action_state_commitments: Mapping[str, str]
    shared_pre_action_state_sha256: str
    counterfactual_protocol: str = COUNTERFACTUAL_PROTOCOL
    attestation_version: str = ATTESTATION_VERSION

    def __post_init__(self) -> None:
        _sha256(self.manifest_commitment, "manifest commitment")
        _sha256(self.row_panel_sha256, "row-panel digest")
        _sha256(
            self.shared_pre_action_state_sha256,
            "shared pre-action state digest",
        )
        if self.attestation_version != ATTESTATION_VERSION:
            raise BranchingManifestError("unsupported rollout attestation version")
        if self.counterfactual_protocol != COUNTERFACTUAL_PROTOCOL:
            raise BranchingManifestError("unsupported counterfactual protocol")
        if type(self.row_count) is not int or self.row_count < 1:
            raise BranchingManifestError("invalid rollout row count")
        if (
            type(self.draw_count_per_policy) is not int
            or self.draw_count_per_policy < 1
        ):
            raise BranchingManifestError("invalid draw count per policy")
        policies = tuple(
            _identifier(policy_id, "policy id") for policy_id in self.policy_ids
        )
        if len(set(policies)) != len(policies):
            raise BranchingManifestError("duplicate attested policy id")
        if set(self.pre_action_state_commitments) != set(policies):
            raise BranchingManifestError(
                "pre-action commitments must exactly cover policies"
            )
        states = {
            policy_id: _sha256(digest, "pre-action state digest")
            for policy_id, digest in self.pre_action_state_commitments.items()
        }
        if set(states.values()) != {self.shared_pre_action_state_sha256}:
            raise BranchingManifestError(
                "policy branches diverged before the action boundary"
            )
        object.__setattr__(self, "policy_ids", policies)
        object.__setattr__(
            self,
            "pre_action_state_commitments",
            MappingProxyType(dict(sorted(states.items()))),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "attestation_version": self.attestation_version,
            "manifest_commitment": self.manifest_commitment,
            "row_panel_sha256": self.row_panel_sha256,
            "row_count": self.row_count,
            "draw_count_per_policy": self.draw_count_per_policy,
            "policy_ids": list(self.policy_ids),
            "pre_action_state_commitments": dict(
                self.pre_action_state_commitments
            ),
            "shared_pre_action_state_sha256": (
                self.shared_pre_action_state_sha256
            ),
            "counterfactual_protocol": self.counterfactual_protocol,
            "claim_limits": list(CLAIM_LIMITS),
        }


def _validated_panel(
    rows: Iterable[PolicyOutcomeDraw], manifest: BranchingManifest
) -> tuple[tuple[PolicyOutcomeDraw, ...], int]:
    if not isinstance(manifest, BranchingManifest):
        raise BranchingManifestError("invalid branching manifest")
    materialized = tuple(rows)
    if not materialized or any(
        not isinstance(row, PolicyOutcomeDraw) for row in materialized
    ):
        raise BranchingManifestError("rollout panel must contain outcome rows")
    policies = set(manifest.policy_ids)
    indexed: dict[str, set[tuple[int, str, str]]] = {
        policy_id: set() for policy_id in manifest.policy_ids
    }
    for row in materialized:
        if row.opening_history != manifest.opening_history:
            raise BranchingManifestError("row opening history does not match manifest")
        if row.policy_id not in policies:
            raise BranchingManifestError("row policy is absent from manifest")
        if row.posterior_draw_id not in manifest.posterior_draw_commitments:
            raise BranchingManifestError("row posterior draw is absent from manifest")
        if (
            row.intervention_effect_draw_id
            not in manifest.intervention_effect_draw_commitments
        ):
            raise BranchingManifestError(
                "row intervention-effect draw is absent from manifest"
            )
        key = (
            row.future_seed,
            row.posterior_draw_id,
            row.intervention_effect_draw_id,
        )
        if key in indexed[row.policy_id]:
            raise BranchingManifestError("duplicate policy uncertainty draw")
        indexed[row.policy_id].add(key)
    reference = indexed[manifest.policy_ids[0]]
    if not reference or any(keys != reference for keys in indexed.values()):
        raise BranchingManifestError(
            "rollout panel must be balanced across identical draws"
        )
    if {key[1] for key in reference} != set(
        manifest.posterior_draw_commitments
    ) or {key[2] for key in reference} != set(
        manifest.intervention_effect_draw_commitments
    ):
        raise BranchingManifestError("rollout panel does not cover committed axes")
    seeds = sorted({key[0] for key in reference})
    if len(seeds) != manifest.future_seed_count or not hmac.compare_digest(
        future_seed_bank_sha256(seeds), manifest.future_seed_bank_sha256
    ):
        raise BranchingManifestError("rollout future seeds do not match manifest")
    return materialized, len(reference)


def attest_rollout_panel(
    rows: Iterable[PolicyOutcomeDraw],
    *,
    manifest: BranchingManifest,
    pre_action_state_commitments: Mapping[str, str],
) -> RolloutPanelAttestation:
    materialized, draw_count = _validated_panel(rows, manifest)
    if not isinstance(pre_action_state_commitments, Mapping):
        raise BranchingManifestError("pre-action commitments must be a mapping")
    if set(pre_action_state_commitments) != set(manifest.policy_ids):
        raise BranchingManifestError(
            "pre-action commitments must exactly cover policies"
        )
    states = {
        policy_id: _sha256(digest, "pre-action state digest")
        for policy_id, digest in pre_action_state_commitments.items()
    }
    if len(set(states.values())) != 1:
        raise BranchingManifestError(
            "policy branches diverged before the action boundary"
        )
    shared = next(iter(states.values()))
    return RolloutPanelAttestation(
        manifest_commitment=manifest.commitment,
        row_panel_sha256=_row_panel_sha256(materialized),
        row_count=len(materialized),
        draw_count_per_policy=draw_count,
        policy_ids=manifest.policy_ids,
        pre_action_state_commitments=states,
        shared_pre_action_state_sha256=shared,
    )


def verify_rollout_attestation(
    rows: Iterable[PolicyOutcomeDraw],
    *,
    manifest: BranchingManifest,
    attestation: RolloutPanelAttestation,
) -> tuple[PolicyOutcomeDraw, ...]:
    if not isinstance(attestation, RolloutPanelAttestation):
        raise BranchingManifestError("invalid rollout attestation")
    materialized = tuple(rows)
    rebuilt = attest_rollout_panel(
        materialized,
        manifest=manifest,
        pre_action_state_commitments=attestation.pre_action_state_commitments,
    )
    if rebuilt != attestation:
        raise BranchingManifestError("rollout attestation does not match rows")
    return materialized


def evaluate_attested_policy_panel(
    rows: Iterable[PolicyOutcomeDraw],
    *,
    manifest: BranchingManifest,
    attestation: RolloutPanelAttestation,
    weight_profiles: Sequence[StakeholderWeightProfile],
    interval_probability: float = 0.90,
    severe_tail_probability: float = 0.10,
    minimum_axis_draws: int = 2,
) -> InterventionEvaluationReport:
    materialized = verify_rollout_attestation(
        rows, manifest=manifest, attestation=attestation
    )
    return evaluate_policy_panel(
        materialized,
        policy_ids=manifest.policy_ids,
        weight_profiles=weight_profiles,
        opening_history=manifest.opening_history,
        interval_probability=interval_probability,
        severe_tail_probability=severe_tail_probability,
        minimum_axis_draws=minimum_axis_draws,
    )
