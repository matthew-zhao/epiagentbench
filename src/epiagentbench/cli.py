from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Sequence

from .baseline import run_scripted_baseline
from .environment import InvestigationEnvironment
from .scenario import FAMILIES, generate_episode
from .scoring import score_episode
from .trusted.service import launch_secure_episode


LIVE_STARSIM_FAMILIES = (
    "institution_person_to_person",
    "restaurant_point_source",
    "repeated_introduction",
    "coincidental_venue",
    "reporting_artifact",
)


def _demo(seed: int, family: str | None) -> int:
    bundle = generate_episode(seed=seed, family=family)
    environment = InvestigationEnvironment(bundle.public)
    submission = run_scripted_baseline(environment)
    scorecard = score_episode(
        oracle=bundle.oracle,
        manifest=bundle.public.manifest,
        ledger=environment.ledger,
        seen_ids=environment.seen_ids,
        submission=submission,
    )
    output = {
        "development_truth": {
            "family": bundle.oracle.family,
            "is_outbreak": bundle.oracle.is_outbreak,
            "source_id": bundle.oracle.source_id,
        },
        "public_manifest": environment.manifest,
        "submission": submission,
        "scorecard": scorecard.as_dict(),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _secure_demo(seed: int, family: str | None, backend: str) -> int:
    session, client = launch_secure_episode(
        seed=seed, family=family, backend=backend
    )
    try:
        submission = run_scripted_baseline(client)
        scorecard = session.score(submission)
        output = {
            "public_manifest": client.manifest,
            "submission": submission,
            "scorecard": scorecard,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    finally:
        client.close()
        session.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="epiagentbench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser("demo", help="run the scripted development baseline")
    demo.add_argument("--seed", type=int, default=7)
    demo.add_argument("--family", choices=FAMILIES)
    secure_demo = subparsers.add_parser(
        "secure-demo", help="run through the isolated JSON broker"
    )
    secure_demo.add_argument("--seed", type=int, default=7)
    secure_demo.add_argument(
        "--family", choices=tuple(dict.fromkeys(FAMILIES + LIVE_STARSIM_FAMILIES))
    )
    secure_demo.add_argument(
        "--backend", choices=("reference", "starsim"), default="reference"
    )
    validation = subparsers.add_parser(
        "validate-starsim",
        help="run an experimental Starsim seed-panel diagnostic",
    )
    validation.add_argument("--start-seed", type=int, default=0)
    validation.add_argument("--seeds", type=int, default=10)
    closed_loop_validation = subparsers.add_parser(
        "validate-closed-loop",
        help="run the experimental live-policy diversity diagnostic",
    )
    closed_loop_validation.add_argument("--start-seed", type=int, default=0)
    closed_loop_validation.add_argument("--seeds", type=int, default=10)
    live_mode_validation = subparsers.add_parser(
        "validate-live-modes",
        help="probe all five live modes and simple response shortcuts",
    )
    live_mode_validation.add_argument("--start-seed", type=int, default=0)
    live_mode_validation.add_argument(
        "--seeds-per-mode", type=int, default=4
    )
    adversarial_validation = subparsers.add_parser(
        "audit-adversarial",
        help=(
            "fit adaptive shortcut agents on development episodes and test "
            "reward hacking, metadata leakage, tampering, and injection guards"
        ),
    )
    adversarial_validation.add_argument(
        "--training-start-seed", type=int, default=0
    )
    adversarial_validation.add_argument(
        "--training-seeds-per-mode", type=int, default=8
    )
    adversarial_validation.add_argument(
        "--heldout-start-seed", type=int, default=10_000
    )
    adversarial_validation.add_argument(
        "--heldout-seeds-per-mode", type=int, default=8
    )
    adversarial_validation.add_argument("--output")
    private_cohort = subparsers.add_parser(
        "freeze-private-cohort",
        help=(
            "freeze balanced private Starsim identities without simulating "
            "outcomes or running Docker"
        ),
    )
    private_cohort.add_argument("--cohort-id", required=True)
    private_cohort.add_argument("--output-directory", required=True)
    private_cohort.add_argument("--authentication-key-file", required=True)
    private_cohort.add_argument("--episodes", type=int, default=100)
    nors_fetch = subparsers.add_parser(
        "fetch-nors-snapshot",
        help="download and hash one public CDC NORS snapshot",
    )
    nors_fetch.add_argument(
        "--output-directory", default="run_artifacts/nors"
    )
    nors_plan = subparsers.add_parser(
        "prepare-nors-calibration",
        help="freeze temporal splits and release calibration-only targets",
    )
    nors_plan.add_argument("--csv", required=True)
    nors_plan.add_argument("--metadata", required=True)
    nors_plan.add_argument("--output", required=True)
    starsim_calibration = subparsers.add_parser(
        "calibrate-starsim-nors",
        help=(
            "fit a gate-free composite Starsim candidate on released NORS "
            "targets and check it once on 2019"
        ),
    )
    starsim_calibration.add_argument("--plan", required=True)
    starsim_calibration.add_argument("--output-report", required=True)
    starsim_calibration.add_argument("--output-profile", required=True)
    starsim_calibration.add_argument("--fit-start-seed", type=int, default=0)
    starsim_calibration.add_argument("--fit-seeds", type=int, default=80)
    starsim_calibration.add_argument(
        "--validation-start-seed", type=int, default=10_000
    )
    starsim_calibration.add_argument("--validation-seeds", type=int, default=80)
    clustered_refinement = subparsers.add_parser(
        "refine-starsim-nors-clustered",
        help=(
            "refine the preregistered clustered-institution candidate on "
            "released targets and check it once on 2019"
        ),
    )
    clustered_refinement.add_argument("--plan", required=True)
    clustered_refinement.add_argument("--base-profile", required=True)
    clustered_refinement.add_argument("--output-report", required=True)
    clustered_refinement.add_argument("--output-profile", required=True)
    clustered_refinement.add_argument(
        "--fit-start-seed", type=int, default=2_000
    )
    clustered_refinement.add_argument("--fit-seeds", type=int, default=80)
    clustered_refinement.add_argument(
        "--validation-start-seed", type=int, default=12_000
    )
    clustered_refinement.add_argument(
        "--validation-seeds", type=int, default=80
    )
    nors_freeze = subparsers.add_parser(
        "freeze-calibration-candidate",
        help="commit a fitted profile before releasing sealed temporal targets",
    )
    nors_freeze.add_argument("--plan", required=True)
    nors_freeze.add_argument("--profile", required=True)
    nors_freeze.add_argument("--output", required=True)
    nors_release = subparsers.add_parser(
        "release-nors-partition",
        help="explicitly release a sealed post-freeze NORS partition",
    )
    nors_release.add_argument("--csv", required=True)
    nors_release.add_argument("--plan", required=True)
    nors_release.add_argument("--freeze", required=True)
    nors_release.add_argument(
        "--partition",
        choices=("disruption_stress", "temporal_generalization"),
        default="temporal_generalization",
    )
    nors_release.add_argument("--output", required=True)
    nors_release.add_argument(
        "--acknowledge-sealed-partition-release",
        action="store_true",
        help="required for either sealed partition after candidate freeze",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        return _demo(args.seed, args.family)
    if args.command == "secure-demo":
        return _secure_demo(args.seed, args.family, args.backend)
    if args.command == "validate-starsim":
        from .validation import run_starsim_seed_panel

        print(
            json.dumps(
                run_starsim_seed_panel(
                    start_seed=args.start_seed, seeds=args.seeds
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "validate-closed-loop":
        from .validation import run_closed_loop_policy_panel

        print(
            json.dumps(
                run_closed_loop_policy_panel(
                    start_seed=args.start_seed, seeds=args.seeds
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "validate-live-modes":
        from .validation import run_live_mode_panel

        print(
            json.dumps(
                run_live_mode_panel(
                    start_seed=args.start_seed,
                    seeds_per_mode=args.seeds_per_mode,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "audit-adversarial":
        from .calibration import write_json_artifact
        from .validation import run_adaptive_live_mode_audit

        report = run_adaptive_live_mode_audit(
            training_start_seed=args.training_start_seed,
            training_seeds_per_mode=args.training_seeds_per_mode,
            heldout_start_seed=args.heldout_start_seed,
            heldout_seeds_per_mode=args.heldout_seeds_per_mode,
        )
        if args.output:
            write_json_artifact(args.output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "freeze-private-cohort":
        from .trusted.cohort_freezer import (
            CohortFreezeError,
            freeze_private_starsim_cohort,
        )

        try:
            frozen = freeze_private_starsim_cohort(
                cohort_id=args.cohort_id,
                output_directory=args.output_directory,
                authentication_key_file=args.authentication_key_file,
                episodes=args.episodes,
            )
        except CohortFreezeError as exc:
            raise SystemExit(str(exc)) from None
        print(json.dumps(frozen.as_public_dict(), indent=2, sort_keys=True))
        return 0
    if args.command == "fetch-nors-snapshot":
        from .calibration import fetch_nors_snapshot

        snapshot = fetch_nors_snapshot(args.output_directory)
        payload = {
            **asdict(snapshot),
            "csv_path": str(snapshot.csv_path),
            "metadata_path": str(snapshot.metadata_path),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "prepare-nors-calibration":
        from .calibration import (
            build_nors_calibration_plan,
            write_json_artifact,
        )

        plan = build_nors_calibration_plan(args.csv, args.metadata)
        output = write_json_artifact(args.output, plan)
        print(
            json.dumps(
                {
                    "output": str(output),
                    "plan_sha256": plan["plan_sha256"],
                    "sealed_temporal_partitions_released": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "calibrate-starsim-nors":
        from .calibration import load_json_artifact, write_json_artifact
        from .trusted.calibration_panel import fit_nors_composite_candidate

        if (
            args.fit_start_seed < 0
            or args.validation_start_seed < 0
            or args.fit_seeds < 5
            or args.validation_seeds < 5
        ):
            raise SystemExit(
                "calibration seed starts must be non-negative and panels need "
                "at least five seeds"
            )
        fit_seeds = tuple(
            range(args.fit_start_seed, args.fit_start_seed + args.fit_seeds)
        )
        validation_seeds = tuple(
            range(
                args.validation_start_seed,
                args.validation_start_seed + args.validation_seeds,
            )
        )
        plan = load_json_artifact(args.plan)
        report, profile = fit_nors_composite_candidate(
            plan,
            fit_seeds=fit_seeds,
            validation_seeds=validation_seeds,
        )
        report_path = write_json_artifact(args.output_report, report)
        profile_path = write_json_artifact(args.output_profile, profile)
        print(
            json.dumps(
                {
                    "output_report": str(report_path),
                    "output_profile": str(profile_path),
                    "report_sha256": report["report_sha256"],
                    "visible_validation_passed": report[
                        "visible_validation_passed"
                    ],
                    "true_blind_holdout_status": report[
                        "true_blind_holdout_status"
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "refine-starsim-nors-clustered":
        from .calibration import load_json_artifact, write_json_artifact
        from .trusted.calibration_panel import (
            refine_nors_clustered_topology_candidate,
        )

        if (
            args.fit_start_seed < 0
            or args.validation_start_seed < 0
            or args.fit_seeds < 5
            or args.validation_seeds < 5
        ):
            raise SystemExit(
                "refinement seed starts must be non-negative and panels need "
                "at least five seeds"
            )
        fit_seeds = tuple(
            range(args.fit_start_seed, args.fit_start_seed + args.fit_seeds)
        )
        validation_seeds = tuple(
            range(
                args.validation_start_seed,
                args.validation_start_seed + args.validation_seeds,
            )
        )
        plan = load_json_artifact(args.plan)
        base_profile = load_json_artifact(args.base_profile)
        report, profile = refine_nors_clustered_topology_candidate(
            plan,
            fit_seeds=fit_seeds,
            validation_seeds=validation_seeds,
            profile=base_profile,
        )
        report_path = write_json_artifact(args.output_report, report)
        profile_path = write_json_artifact(args.output_profile, profile)
        print(
            json.dumps(
                {
                    "output_report": str(report_path),
                    "output_profile": str(profile_path),
                    "report_sha256": report["report_sha256"],
                    "selected_parameters": report["selected_parameters"],
                    "p2p_visible_gate_passed": report[
                        "p2p_visible_gate_passed"
                    ],
                    "true_blind_holdout_status": report[
                        "true_blind_holdout_status"
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "freeze-calibration-candidate":
        from .calibration import (
            freeze_calibration_candidate,
            load_json_artifact,
            write_json_artifact,
        )

        plan = load_json_artifact(args.plan)
        freeze = freeze_calibration_candidate(
            plan,
            Path(args.profile).resolve(strict=True).read_bytes(),
        )
        output = write_json_artifact(args.output, freeze)
        print(
            json.dumps(
                {
                    "output": str(output),
                    "freeze_sha256": freeze["freeze_sha256"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "release-nors-partition":
        from .calibration import (
            load_json_artifact,
            release_nors_partition,
            write_json_artifact,
        )

        if not args.acknowledge_sealed_partition_release:
            raise SystemExit(
                f"{args.partition} release requires "
                "--acknowledge-sealed-partition-release"
            )
        plan = load_json_artifact(args.plan)
        freeze = load_json_artifact(args.freeze)
        report = release_nors_partition(
            args.csv,
            plan,
            freeze,
            partition=args.partition,
            acknowledge_sealed_release=True,
        )
        output = write_json_artifact(args.output, report)
        print(
            json.dumps(
                {
                    "output": str(output),
                    "release_sha256": report["release_sha256"],
                    "partition": args.partition,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
