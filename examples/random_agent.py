"""Low-skill protocol baseline that fits in the client-only agent image."""

from __future__ import annotations

import json

from epiagentbench_client import InvestigationClient


def main() -> None:
    client = InvestigationClient.from_environment()
    try:
        initial = client.initial_observations()
        evidence_ids = [record["observation_id"] for record in initial]
        client.recommend_action("monitor", None, evidence_ids)
        submission = {
            "incident_assessment": {
                "outbreak_probability": 0.5,
                "status": "indeterminate",
                "evidence_ids": evidence_ids,
            },
            "case_definition": {
                "clinical": "Acute gastrointestinal illness",
                "person": "Person associated with the alert",
                "place": "Investigating jurisdiction",
                "time": "Alert window",
                "laboratory": "Compatible enteric result when available",
            },
            "line_list": [],
            "hypotheses": [
                {
                    "type": "sporadic_background",
                    "target_id": None,
                    "probability": 0.5,
                    "supporting_evidence_ids": evidence_ids,
                    "contradicting_evidence_ids": [],
                }
            ],
            "recommended_actions": [
                {
                    "action_type": "monitor",
                    "target_id": None,
                    "urgency": "monitor",
                    "evidence_ids": evidence_ids,
                }
            ],
            "uncertainties": ["No follow-up evidence was acquired."],
            "next_evidence": ["Acquire interviews and laboratory evidence."],
            "executive_brief": (
                "The signal remains indeterminate; continue monitoring while "
                "acquiring discriminating evidence."
            ),
        }
    finally:
        client.close()
    print(json.dumps(submission, allow_nan=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
