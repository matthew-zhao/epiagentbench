from __future__ import annotations

from dataclasses import replace
import inspect
import json

import pytest

from epiagentbench.trusted.institution_traces import (
    DAY_MINUTES,
    InstitutionTrace,
    InstitutionTraceConfig,
    SymptomRecord,
    TraceContact,
    generate_institution_trace,
    project_trace_evidence,
)
from epiagentbench.trusted.starsim_ltc_v3 import _read_trace


KEY = b"trace-presentation-key-32-bytes!!"


def _trace():
    return generate_institution_trace(
        InstitutionTraceConfig(
            seed=17,
            ward_count=2,
            residents_per_ward=4,
            staff_per_ward=2,
            visitor_count=2,
            days=4,
        )
    )


def _symptoms():
    return (
        SymptomRecord("symptom-a", "resident-0000", 2 * DAY_MINUTES, 2 * DAY_MINUTES + 30),
        SymptomRecord("symptom-b", "staff-0000", 2 * DAY_MINUTES + 120, 2 * DAY_MINUTES + 180),
    )


def test_trace_is_deterministic_role_ward_and_temporal_record_complete():
    first = _trace()
    second = _trace()
    assert first == second
    assert first.commitment == second.commitment
    assert {person.role for person in first.people} == {"resident", "staff", "visitor"}
    assert first.shifts and first.meals and first.entries and first.contacts
    assert {contact.setting for contact in first.contacts} >= {
        "roommate",
        "direct_care",
        "shared_meal",
        "visitor_contact",
    }
    assert all(
        contact.start_minute + contact.duration_minutes <= first.horizon_minutes
        for contact in first.contacts
    )
    changed = generate_institution_trace(replace(InstitutionTraceConfig(seed=17), seed=18))
    assert changed.commitment != generate_institution_trace(InstitutionTraceConfig(seed=17)).commitment


def test_trace_satisfies_the_starsim_structural_contract_without_importing_answers():
    people, contacts = _read_trace(_trace())
    assert len(people) == len(_trace().people)
    assert len(contacts) == len(_trace().contacts)
    parameters = set(inspect.signature(project_trace_evidence).parameters)
    assert not any("causal" in name or "mode" in name for name in parameters)


def test_public_projection_is_deterministic_and_contains_no_private_ids():
    trace = _trace()
    first = project_trace_evidence(
        trace,
        _symptoms(),
        presentation_key=KEY,
        observation_seed=5,
        record_capture_probability=1.0,
    )
    second = project_trace_evidence(
        trace,
        _symptoms(),
        presentation_key=KEY,
        observation_seed=5,
        record_capture_probability=1.0,
    )
    assert first == second
    serialized = json.dumps(first.public_payload(), sort_keys=True)
    private_tokens = [
        *(person.person_id for person in trace.people),
        *(person.ward_id for person in trace.people if person.ward_id),
        *(person.room_id for person in trace.people if person.room_id),
        trace.commitment,
    ]
    assert all(token not in serialized for token in private_tokens)
    assert any(line.private_subject_id == "resident-0000" for line in first.private_lineage)
    assert "private_trace_commitment" not in json.dumps(first.public_payload())


def test_interview_counts_come_from_pre_onset_records_and_exclude_time_travel():
    trace = _trace()
    symptom = SymptomRecord("symptom-time", "resident-0000", DAY_MINUTES, DAY_MINUTES + 10)
    future = TraceContact(
        "future-contact",
        "resident-0000",
        "staff-0000",
        3 * DAY_MINUTES,
        15,
        "direct_care",
        "ward-00",
    )
    with_future = replace(trace, contacts=(*trace.contacts, future))
    baseline = project_trace_evidence(
        trace,
        (symptom,),
        presentation_key=KEY,
        observation_seed=1,
        record_capture_probability=1.0,
    )
    changed = project_trace_evidence(
        with_future,
        (symptom,),
        presentation_key=KEY,
        observation_seed=1,
        record_capture_probability=1.0,
    )
    baseline_interview = next(
        item for item in baseline.public_evidence if item.kind == "record_review_interview"
    )
    changed_interview = next(
        item for item in changed.public_evidence if item.kind == "record_review_interview"
    )
    assert baseline_interview.payload["records_reviewed"] == changed_interview.payload["records_reviewed"]
    assert all(
        "future-contact" not in line.source_record_ids
        for line in changed.private_lineage
        if line.evidence_id == changed_interview.evidence_id
    )


def test_inspection_matches_are_derived_from_record_inventory():
    projection = project_trace_evidence(
        _trace(),
        _symptoms(),
        presentation_key=KEY,
        observation_seed=9,
        record_capture_probability=1.0,
    )
    inspections = [
        item for item in projection.public_evidence if item.kind == "operational_record_inspection"
    ]
    assert inspections
    assert all(item.payload["records_reviewed"] >= 0 for item in inspections)
    assert all(
        item.payload["symptomatic_record_matches"] <= len(_symptoms())
        for item in inspections
    )


def test_invalid_private_references_fail_closed():
    trace = _trace()
    bad = replace(
        trace.contacts[0],
        person_b_id="unknown-person",
    )
    with pytest.raises(ValueError, match="contact references"):
        InstitutionTrace(
            people=trace.people,
            shifts=trace.shifts,
            meals=trace.meals,
            entries=trace.entries,
            contacts=(bad, *trace.contacts[1:]),
            horizon_minutes=trace.horizon_minutes,
        )


def test_projection_key_and_symptom_references_fail_closed():
    trace = _trace()
    with pytest.raises(ValueError, match="presentation_key"):
        project_trace_evidence(trace, _symptoms(), presentation_key=b"short", observation_seed=1)
    with pytest.raises(ValueError, match="unknown person"):
        project_trace_evidence(
            trace,
            (SymptomRecord("bad", "unknown", 1, 2),),
            presentation_key=KEY,
            observation_seed=1,
        )
