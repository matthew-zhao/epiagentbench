from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Protocol


class InvestigationTools(Protocol):
    """Structural API shared by the legacy environment and secure client."""

    @property
    def manifest(self) -> dict[str, Any]: ...

    def initial_observations(self) -> list[dict[str, Any]]: ...

    def search_observations(
        self, kind: str | None = None, **filters: Any
    ) -> list[dict[str, Any]]: ...

    def request_interview(self, patient_id: str) -> dict[str, Any]: ...

    def advance_time(self, minutes: int) -> list[dict[str, Any]]: ...

    def recommend_action(
        self,
        action_type: str,
        target_id: str | None,
        evidence_ids: list[str] | tuple[str, ...],
    ) -> dict[str, Any]: ...

    def set_institution_control(
        self,
        level: str,
        target_id: str,
        evidence_ids: list[str] | tuple[str, ...],
    ) -> dict[str, Any]: ...

    def set_response_control(
        self,
        action_type: str,
        level: str,
        target_id: str,
        evidence_ids: list[str] | tuple[str, ...],
    ) -> dict[str, Any]: ...

    def request_inspection(self, target_id: str) -> dict[str, Any]: ...

    def submit_forecast(self, expected_new_encounters: int) -> dict[str, Any]: ...


def run_scripted_baseline(env: InvestigationTools) -> dict[str, Any]:
    """Run a transparent baseline policy against the reference environment.

    The baseline is deliberately simple. It exists to smoke-test the task and
    scorer, not to represent epidemiologic best practice.
    """

    initial = env.initial_observations()
    enabled_tools = set(env.manifest.get("enabled_tools", []))
    policy = next(
        (
            record
            for record in initial
            if record.get("kind") == "policy"
            and isinstance(record.get("payload"), dict)
        ),
        None,
    )
    response_catalog = (
        policy["payload"].get("response_control_catalog", {})
        if policy is not None
        else {}
    )
    if not isinstance(response_catalog, dict):
        response_catalog = {}
    encounters = env.search_observations(kind="encounter")
    case_reports = env.search_observations(kind="case_report")
    labs = env.search_observations(kind="lab")
    env.search_observations(kind="external_note")  # Read as untrusted data.

    patient_ids = sorted(
        {
            record["payload"]["patient_id"]
            for record in encounters + case_reports + labs
            if record["payload"].get("patient_id")
        }
    )
    for patient_id in patient_ids:
        env.request_interview(patient_id)
    env.advance_time(120)
    interviews = env.search_observations(kind="interview")

    record_ids_by_patient: dict[str, list[str]] = defaultdict(list)
    for record in encounters + case_reports + labs + interviews:
        patient_id = record["payload"].get("patient_id")
        if patient_id:
            record_ids_by_patient[patient_id].append(record["observation_id"])

    report_patients = [
        record["payload"]["patient_id"] for record in case_reports
    ]
    duplicate_ratio = (
        1.0 - len(set(report_patients)) / len(report_patients)
        if report_patients
        else 0.0
    )

    positive_labs = [
        record
        for record in labs
        if str(record["payload"].get("result", "")).endswith("_positive")
    ]
    pathogen_counts = Counter(
        record["payload"]["result"] for record in positive_labs
    )
    dominant_pathogen_count = max(pathogen_counts.values(), default=0)

    symptomatic_patients = {
        record["payload"]["patient_id"]
        for record in encounters + case_reports
        if record["payload"].get("syndrome") == "acute_gastrointestinal"
    }
    relevant_interviews = [
        record
        for record in interviews
        if record["payload"].get("patient_id") in symptomatic_patients
    ]
    exposure_counts = Counter(
        record["payload"].get("exposure_id")
        for record in relevant_interviews
        if record["payload"].get("exposure_id")
    )
    source_id, source_count = (
        exposure_counts.most_common(1)[0] if exposure_counts else (None, 0)
    )
    source_interviews = [
        record
        for record in relevant_interviews
        if record["payload"].get("exposure_id") == source_id
    ]
    exposure_type = (
        source_interviews[0]["payload"].get("exposure_type")
        if source_interviews
        else None
    )

    exposure_type_counts = Counter(
        record["payload"].get("exposure_type")
        for record in relevant_interviews
        if record["payload"].get("exposure_type")
    )
    institution_interviews = [
        record
        for record in relevant_interviews
        if record["payload"].get("exposure_type") == "institution"
    ]
    introduction_interviews = [
        record
        for record in relevant_interviews
        if record["payload"].get("exposure_type")
        == "different_each_case"
    ]
    restaurant_interviews = [
        record
        for record in relevant_interviews
        if record["payload"].get("exposure_type") == "restaurant"
    ]

    generic_controls = (
        "set_response_control" in enabled_tools and bool(response_catalog)
    )

    def catalog_target(action: str) -> str | None:
        entry = response_catalog.get(action)
        if not isinstance(entry, dict):
            return None
        target = entry.get("target_id")
        return target if isinstance(target, str) and target else None

    # When the live task offers the same four targets in every episode, inspect
    # all of them before committing to a mechanism. This is deliberately a
    # public, costly investigation step rather than an evaluator-side hint.
    elapsed_minutes = 120
    inspections: list[dict[str, Any]] = []
    if (
        "request_inspection" in enabled_tools
        and hasattr(env, "request_inspection")
    ):
        inspection_targets = list(
            dict.fromkeys(
                target
                for action in (
                    "infection_control",
                    "source_control",
                    "entry_control",
                    "audit_reporting",
                )
                if (target := catalog_target(action)) is not None
            )
        )
        latest_available = elapsed_minutes
        for target in inspection_targets:
            receipt = env.request_inspection(target)
            available_at = receipt.get("available_at_minute")
            if (
                receipt.get("status") == "scheduled"
                and type(available_at) is int
            ):
                latest_available = max(latest_available, available_at)
        if latest_available > elapsed_minutes:
            env.advance_time(latest_available - elapsed_minutes)
            elapsed_minutes = latest_available
        inspections = env.search_observations(kind="inspection")

    material_inspections = {
        record["payload"].get("target_id"): record
        for record in inspections
        if record["payload"].get("finding") == "material_concern"
    }

    if len(case_reports) >= 5 and duplicate_ratio >= 0.5:
        outbreak_probability = 0.05
        explanation_type = "reporting_artifact"
        hypothesis_target = catalog_target("audit_reporting")
        action_type = "audit_reporting"
        action_target = hypothesis_target
        support = [record["observation_id"] for record in case_reports[:4] + labs]
        case_interviews: list[dict[str, Any]] = []
    elif (
        dominant_pathogen_count >= 3
        and exposure_type_counts["different_each_case"] >= 3
    ):
        outbreak_probability = 0.88
        explanation_type = "repeated_introduction"
        hypothesis_target = catalog_target("entry_control")
        action_type = "entry_control" if generic_controls else "monitor"
        action_target = hypothesis_target
        support = [
            record["observation_id"]
            for record in positive_labs + introduction_interviews
        ]
        case_interviews = introduction_interviews
    elif dominant_pathogen_count >= 3 and source_count >= 3:
        outbreak_probability = 0.92
        hypothesis_target = source_id
        if exposure_type == "institution":
            explanation_type = "propagated"
            action_type = "infection_control"
            if generic_controls:
                hypothesis_target = (
                    catalog_target("infection_control") or hypothesis_target
                )
            case_interviews = institution_interviews
        else:
            explanation_type = "common_source"
            action_type = (
                "source_control" if generic_controls else "request_inspection"
            )
            if generic_controls:
                hypothesis_target = (
                    catalog_target("source_control") or hypothesis_target
                )
            case_interviews = source_interviews
        action_target = source_id
        if generic_controls:
            action_target = hypothesis_target
        support = [
            record["observation_id"]
            for record in positive_labs + source_interviews
        ]
    elif generic_controls and material_inspections:
        # Sparse routine testing can make the simple three-lab rule miss an
        # otherwise coherent mechanism. Combine the requested inspection with
        # whatever interview/lab support is present, and require more than the
        # inspection alone to avoid chasing a noisy false-positive finding.
        inspection_candidates = []
        for (
            candidate_explanation,
            candidate_action,
            candidate_interviews,
        ) in (
            (
                "propagated",
                "infection_control",
                institution_interviews,
            ),
            ("common_source", "source_control", restaurant_interviews),
            (
                "repeated_introduction",
                "entry_control",
                introduction_interviews,
            ),
        ):
            candidate_target = catalog_target(candidate_action)
            inspection = material_inspections.get(candidate_target)
            if inspection is None:
                continue
            score = (
                3
                + 2 * len(candidate_interviews)
                + min(3, len(positive_labs))
            )
            if candidate_interviews or positive_labs:
                inspection_candidates.append(
                    (
                        score,
                        candidate_explanation,
                        candidate_action,
                        candidate_target,
                        candidate_interviews,
                        inspection,
                    )
                )
        if inspection_candidates:
            (
                _,
                explanation_type,
                action_type,
                hypothesis_target,
                case_interviews,
                inspection,
            ) = max(inspection_candidates, key=lambda item: item[0])
            outbreak_probability = 0.90
            action_target = hypothesis_target
            support = [
                record["observation_id"]
                for record in positive_labs + case_interviews
            ] + [inspection["observation_id"]]
        else:
            outbreak_probability = 0.15
            explanation_type = "sporadic_background"
            hypothesis_target = None
            action_type = "monitor"
            action_target = None
            support = [
                record["observation_id"]
                for record in encounters[:3] + labs + interviews[:3]
            ]
            case_interviews = []
    else:
        outbreak_probability = 0.15
        explanation_type = "sporadic_background"
        hypothesis_target = None
        action_type = "monitor"
        action_target = None
        support = [
            record["observation_id"]
            for record in encounters[:3] + labs + interviews[:3]
        ]
        case_interviews = []

    # Live episodes may offer a request-only inspection for the target inferred
    # from interviews. The result is useful evidence, but the task remains
    # solvable when the legacy/reference interface does not expose this tool.
    if (
        action_target is not None
        and "request_inspection" in enabled_tools
        and hasattr(env, "request_inspection")
    ):
        targeted_inspections = [
            record
            for record in inspections
            if record["payload"].get("target_id") == action_target
        ]
        if not targeted_inspections:
            receipt = env.request_inspection(action_target)
            available_at = receipt.get("available_at_minute")
            if (
                receipt.get("status") == "scheduled"
                and type(available_at) is int
                and available_at > elapsed_minutes
            ):
                env.advance_time(available_at - elapsed_minutes)
                elapsed_minutes = available_at
            targeted_inspections = env.search_observations(
                kind="inspection", target_id=action_target
            )
        support.extend(
            record["observation_id"] for record in targeted_inspections
        )
        if any(
            record["payload"].get("finding") == "material_concern"
            for record in targeted_inspections
        ):
            if explanation_type == "reporting_artifact":
                outbreak_probability = min(outbreak_probability, 0.03)
            else:
                outbreak_probability = max(outbreak_probability, 0.94)

    line_list: list[dict[str, Any]] = []
    if outbreak_probability >= 0.5:
        source_patients = {
            record["payload"]["patient_id"] for record in case_interviews
        }
        positive_patients = {
            record["payload"]["patient_id"] for record in positive_labs
        }
        for patient_id in sorted(source_patients):
            line_list.append(
                {
                    "patient_id": patient_id,
                    "classification": (
                        "confirmed" if patient_id in positive_patients else "probable"
                    ),
                    "evidence_ids": record_ids_by_patient[patient_id],
                }
            )

    action_evidence = list(dict.fromkeys(support))
    env.recommend_action(action_type, action_target, action_evidence)
    live_forecasts = "submit_forecast" in enabled_tools
    if live_forecasts:
        initial_encounter_patients = {
            record["payload"].get("patient_id") for record in encounters
        }
        env.submit_forecast(max(0, len(initial_encounter_patients) // 2))

    control_scheduled = False
    reported_control_level: str | None = None
    if (
        action_type in response_catalog
        and action_target is not None
        and generic_controls
    ):
        receipt = env.set_response_control(
            action_type, "standard", action_target, action_evidence
        )
        control_scheduled = receipt.get("status") in {
            "scheduled",
            "no_change",
        }
        if control_scheduled:
            reported_control_level = "standard"
    elif (
        action_type == "infection_control"
        and action_target is not None
        and "set_institution_control" in enabled_tools
    ):
        receipt = env.set_institution_control("standard", action_target, action_evidence)
        control_scheduled = receipt.get("status") in {
            "scheduled",
            "no_change",
        }
        if control_scheduled:
            reported_control_level = "standard"

    if live_forecasts or control_scheduled:
        env.advance_time(1440)
        followup_encounters = env.search_observations(kind="encounter")
        newly_observed = [
            record
            for record in followup_encounters
            if record["observation_id"]
            not in {item["observation_id"] for item in encounters}
        ]
        if live_forecasts:
            env.submit_forecast(
                len(
                    {
                        record["payload"].get("patient_id")
                        for record in newly_observed
                    }
                )
            )
        if control_scheduled:
            followup_evidence = [
                record["observation_id"] for record in newly_observed
            ]
            worsening_signal_count = len(
                {
                    record["payload"].get("patient_id")
                    for record in newly_observed
                }
            )
            if action_type == "audit_reporting":
                all_followup_reports = env.search_observations(kind="case_report")
                initial_report_ids = {
                    record["observation_id"] for record in case_reports
                }
                new_reports = [
                    record
                    for record in all_followup_reports
                    if record["observation_id"] not in initial_report_ids
                ]
                followup_evidence.extend(
                    record["observation_id"] for record in new_reports
                )
                worsening_signal_count = len(new_reports)
            # A few first-day reports commonly reflect people infected before
            # the control became effective. Escalate only when the new signal
            # exceeds the entire opening patient count (and a small absolute
            # floor), rather than treating predictable reporting lag as failure.
            if worsening_signal_count > max(
                6, len(initial_encounter_patients)
            ):
                if generic_controls and action_type in response_catalog:
                    intensive_receipt = env.set_response_control(
                        action_type,
                        "intensive",
                        action_target,
                        followup_evidence,
                    )
                else:
                    intensive_receipt = env.set_institution_control(
                        "intensive",
                        action_target,
                        followup_evidence,
                    )
                if intensive_receipt.get("status") in {
                    "scheduled",
                    "no_change",
                }:
                    reported_control_level = "intensive"
                env.advance_time(1440)
    status = "outbreak" if outbreak_probability >= 0.5 else "not_outbreak"
    initial_evidence = [record["observation_id"] for record in initial]

    return {
        "incident_assessment": {
            "outbreak_probability": outbreak_probability,
            "status": status,
            "evidence_ids": action_evidence + initial_evidence,
        },
        "case_definition": {
            "clinical": "Acute gastrointestinal illness",
            "person": "Person linked to the investigated cluster",
            "place": hypothesis_target or "jurisdiction-wide",
            "time": "Seven-day alert window",
            "laboratory": "Compatible enteric result when available",
        },
        "line_list": line_list,
        "hypotheses": [
            {
                "type": explanation_type,
                "target_id": hypothesis_target,
                "probability": 0.85,
                "supporting_evidence_ids": action_evidence,
                "contradicting_evidence_ids": [],
            }
        ],
        "recommended_actions": [
            {
                "action_type": action_type,
                "target_id": action_target,
                "urgency": "immediate" if outbreak_probability >= 0.5 else "monitor",
                "evidence_ids": action_evidence,
                **(
                    {"control_level": reported_control_level}
                    if reported_control_level is not None
                    else {}
                ),
            }
        ],
        "uncertainties": [
            "The simple baseline does not model all reporting and selection biases."
        ],
        "next_evidence": [
            "Review additional laboratory, exposure, and onset information as it arrives."
        ],
        "executive_brief": (
            f"The alert is assessed as {status} with probability "
            f"{outbreak_probability:.2f}; the leading explanation is "
            f"{explanation_type}. The recommended action is {action_type}."
        ),
    }
