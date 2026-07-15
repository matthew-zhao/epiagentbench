"""Private LTC operational traces and trace-derived investigation evidence.

This dependency-light module creates deterministic *development* facility
records: people, rooms, wards, staff shifts, meals, outside entries, and
time-stamped contacts.  Interviews and inspections are projected only from
those records and caller-supplied symptom records.  There is deliberately no
causal-mode or answer-label input.

The schedule generator is a design placeholder, not a calibrated model of a
real facility.  ``starsim_ltc_v3`` currently aggregates its temporal contacts
to a static topology; temporal transmission is a later scientific milestone.
Raw identifiers, schedules, lineage, and commitments are evaluator-private.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
import math
import random
from typing import Any, Iterable, Mapping, Sequence


DAY_MINUTES = 24 * 60
RESIDENT = "resident"
STAFF = "staff"
VISITOR = "visitor"
ROLES = frozenset({RESIDENT, STAFF, VISITOR})
TRACE_STATUS = "development_schedule_not_empirically_calibrated"
TRACE_VERSION = "epiagentbench.private-institution-trace.v1"
PROJECTION_VERSION = "epiagentbench.trace-evidence-projection.v1"

_TRACE_DOMAIN = b"EpiAgentBench private institution trace v1\x00"
_PRESENTATION_DOMAIN = b"EpiAgentBench trace presentation v1\x00"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _minute(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _probability(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError(f"{label} must be finite and in [0, 1]")
    return float(value)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


@dataclass(frozen=True, slots=True)
class TracePerson:
    person_id: str
    role: str
    ward_id: str | None
    room_id: str | None
    linked_resident_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.person_id, "person_id")
        if self.role not in ROLES:
            raise ValueError("unsupported institution role")
        for value, label in (
            (self.ward_id, "ward_id"),
            (self.room_id, "room_id"),
            (self.linked_resident_id, "linked_resident_id"),
        ):
            if value is not None:
                _text(value, label)
        if self.role == RESIDENT and (
            self.ward_id is None or self.room_id is None
        ):
            raise ValueError("residents require ward and room assignments")
        if self.role == VISITOR and self.linked_resident_id is None:
            raise ValueError("visitors require a linked resident")


@dataclass(frozen=True, slots=True)
class StaffShift:
    shift_id: str
    staff_person_id: str
    ward_id: str
    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        _text(self.shift_id, "shift_id")
        _text(self.staff_person_id, "staff_person_id")
        _text(self.ward_id, "ward_id")
        _minute(self.start_minute, "shift start")
        if type(self.end_minute) is not int or self.end_minute <= self.start_minute:
            raise ValueError("shift end must follow shift start")


@dataclass(frozen=True, slots=True)
class MealSession:
    meal_id: str
    location_id: str
    ward_id: str
    start_minute: int
    duration_minutes: int
    participant_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.meal_id, "meal_id")
        _text(self.location_id, "meal location")
        _text(self.ward_id, "meal ward")
        _minute(self.start_minute, "meal start")
        if type(self.duration_minutes) is not int or self.duration_minutes < 1:
            raise ValueError("meal duration must be positive")
        if not isinstance(self.participant_ids, tuple) or len(
            self.participant_ids
        ) < 2:
            raise ValueError("meal requires at least two participants")
        if len(set(self.participant_ids)) != len(self.participant_ids):
            raise ValueError("meal participants must be unique")
        for person_id in self.participant_ids:
            _text(person_id, "meal participant")


@dataclass(frozen=True, slots=True)
class OutsideEntry:
    entry_id: str
    person_id: str
    entry_minute: int
    entry_kind: str
    destination_ward_id: str

    def __post_init__(self) -> None:
        _text(self.entry_id, "entry_id")
        _text(self.person_id, "entry person")
        _minute(self.entry_minute, "entry minute")
        if self.entry_kind not in {"staff_shift", "visitor_arrival"}:
            raise ValueError("unsupported outside entry kind")
        _text(self.destination_ward_id, "entry destination")


@dataclass(frozen=True, slots=True)
class TraceContact:
    contact_id: str
    person_a_id: str
    person_b_id: str
    start_minute: int
    duration_minutes: int
    setting: str
    location_id: str | None

    def __post_init__(self) -> None:
        _text(self.contact_id, "contact_id")
        _text(self.person_a_id, "contact person_a_id")
        _text(self.person_b_id, "contact person_b_id")
        if self.person_a_id == self.person_b_id:
            raise ValueError("self contacts are invalid")
        _minute(self.start_minute, "contact start")
        if type(self.duration_minutes) is not int or self.duration_minutes < 1:
            raise ValueError("contact duration must be positive")
        if self.setting not in {
            "roommate",
            "direct_care",
            "shared_meal",
            "staff_handoff",
            "visitor_contact",
        }:
            raise ValueError("unsupported contact setting")
        if self.location_id is not None:
            _text(self.location_id, "contact location")


@dataclass(frozen=True, slots=True)
class SymptomRecord:
    symptom_id: str
    person_id: str
    onset_minute: int
    recorded_minute: int
    syndrome: str = "acute_gastrointestinal"
    severity: str = "moderate"

    def __post_init__(self) -> None:
        _text(self.symptom_id, "symptom_id")
        _text(self.person_id, "symptom person")
        _minute(self.onset_minute, "symptom onset")
        if (
            type(self.recorded_minute) is not int
            or self.recorded_minute < self.onset_minute
        ):
            raise ValueError("recorded_minute must not precede symptom onset")
        if self.syndrome != "acute_gastrointestinal":
            raise ValueError("unsupported symptom syndrome")
        if self.severity not in {"mild", "moderate", "severe"}:
            raise ValueError("unsupported symptom severity")


@dataclass(frozen=True, slots=True)
class InstitutionTraceConfig:
    seed: int
    ward_count: int = 2
    residents_per_ward: int = 6
    staff_per_ward: int = 2
    visitor_count: int = 2
    days: int = 4
    evidence_status: str = TRACE_STATUS

    def __post_init__(self) -> None:
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("trace seed must be a non-negative integer")
        for value, label, minimum, maximum in (
            (self.ward_count, "ward_count", 1, 20),
            (self.residents_per_ward, "residents_per_ward", 2, 100),
            (self.staff_per_ward, "staff_per_ward", 1, 30),
            (self.visitor_count, "visitor_count", 0, 100),
            (self.days, "days", 2, 60),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"invalid {label}")
        if self.evidence_status != TRACE_STATUS:
            raise ValueError("trace generator is development-only")


@dataclass(frozen=True, slots=True)
class InstitutionTrace:
    people: tuple[TracePerson, ...]
    shifts: tuple[StaffShift, ...]
    meals: tuple[MealSession, ...]
    entries: tuple[OutsideEntry, ...]
    contacts: tuple[TraceContact, ...]
    horizon_minutes: int
    evidence_status: str = TRACE_STATUS
    trace_version: str = TRACE_VERSION

    def __post_init__(self) -> None:
        if self.trace_version != TRACE_VERSION or self.evidence_status != TRACE_STATUS:
            raise ValueError("unsupported institution trace contract")
        if type(self.horizon_minutes) is not int or self.horizon_minutes < DAY_MINUTES:
            raise ValueError("trace horizon is invalid")
        for records, record_type, label in (
            (self.people, TracePerson, "people"),
            (self.shifts, StaffShift, "shifts"),
            (self.meals, MealSession, "meals"),
            (self.entries, OutsideEntry, "entries"),
            (self.contacts, TraceContact, "contacts"),
        ):
            if not isinstance(records, tuple) or any(
                not isinstance(record, record_type) for record in records
            ):
                raise ValueError(f"trace {label} have the wrong type")
        people = {person.person_id: person for person in self.people}
        if len(people) != len(self.people) or len(people) < 3:
            raise ValueError("trace people must have unique IDs")
        if not {RESIDENT, STAFF} <= {person.role for person in self.people}:
            raise ValueError("trace requires resident and staff roles")
        residents = {
            person.person_id for person in self.people if person.role == RESIDENT
        }
        wards = {
            person.ward_id for person in self.people if person.ward_id is not None
        }
        for person in self.people:
            if person.linked_resident_id is not None and (
                person.linked_resident_id not in residents
            ):
                raise ValueError("visitor links to an unknown resident")
        self._unique_ids(self.shifts, "shift_id")
        self._unique_ids(self.meals, "meal_id")
        self._unique_ids(self.entries, "entry_id")
        self._unique_ids(self.contacts, "contact_id")
        for shift in self.shifts:
            if (
                shift.staff_person_id not in people
                or people[shift.staff_person_id].role != STAFF
                or shift.ward_id not in wards
                or shift.end_minute > self.horizon_minutes
            ):
                raise ValueError("shift references invalid private state")
        for meal in self.meals:
            if (
                meal.ward_id not in wards
                or any(person_id not in people for person_id in meal.participant_ids)
                or meal.start_minute + meal.duration_minutes > self.horizon_minutes
            ):
                raise ValueError("meal references invalid private state")
        for entry in self.entries:
            if (
                entry.person_id not in people
                or people[entry.person_id].role not in {STAFF, VISITOR}
                or entry.destination_ward_id not in wards
                or entry.entry_minute >= self.horizon_minutes
            ):
                raise ValueError("entry references invalid private state")
        for contact in self.contacts:
            if (
                contact.person_a_id not in people
                or contact.person_b_id not in people
                or contact.start_minute + contact.duration_minutes
                > self.horizon_minutes
            ):
                raise ValueError("contact references invalid private state")

    @staticmethod
    def _unique_ids(records: Sequence[Any], field_name: str) -> None:
        values = [getattr(record, field_name) for record in records]
        if len(values) != len(set(values)):
            raise ValueError(f"trace repeats {field_name}")

    @property
    def commitment(self) -> str:
        payload = {
            "trace_version": self.trace_version,
            "evidence_status": self.evidence_status,
            "horizon_minutes": self.horizon_minutes,
            "people": [asdict(record) for record in self.people],
            "shifts": [asdict(record) for record in self.shifts],
            "meals": [asdict(record) for record in self.meals],
            "entries": [asdict(record) for record in self.entries],
            "contacts": [asdict(record) for record in self.contacts],
        }
        return "sha256:" + hashlib.sha256(
            _TRACE_DOMAIN + _canonical_json(payload)
        ).hexdigest()


def generate_institution_trace(config: InstitutionTraceConfig) -> InstitutionTrace:
    """Generate one deterministic, uncalibrated LTC operations trace."""

    if not isinstance(config, InstitutionTraceConfig):
        raise ValueError("config must be an InstitutionTraceConfig")
    rng = random.Random(config.seed)
    wards = [f"ward-{index:02d}" for index in range(config.ward_count)]
    people: list[TracePerson] = []
    residents_by_ward: dict[str, list[str]] = {ward: [] for ward in wards}
    staff_by_ward: dict[str, list[str]] = {ward: [] for ward in wards}
    resident_index = 0
    staff_index = 0
    for ward in wards:
        for local in range(config.residents_per_ward):
            person_id = f"resident-{resident_index:04d}"
            room_id = f"{ward}-room-{local // 2:03d}"
            people.append(TracePerson(person_id, RESIDENT, ward, room_id))
            residents_by_ward[ward].append(person_id)
            resident_index += 1
        for _ in range(config.staff_per_ward):
            person_id = f"staff-{staff_index:04d}"
            people.append(TracePerson(person_id, STAFF, ward, None))
            staff_by_ward[ward].append(person_id)
            staff_index += 1
    all_residents = [person.person_id for person in people if person.role == RESIDENT]
    for visitor_index in range(config.visitor_count):
        linked = all_residents[visitor_index % len(all_residents)]
        ward = next(person.ward_id for person in people if person.person_id == linked)
        people.append(
            TracePerson(
                f"visitor-{visitor_index:04d}", VISITOR, ward, None, linked
            )
        )

    shifts: list[StaffShift] = []
    meals: list[MealSession] = []
    entries: list[OutsideEntry] = []
    contacts: list[TraceContact] = []
    contact_index = 0
    for day in range(config.days):
        day_start = day * DAY_MINUTES
        for ward in wards:
            residents = residents_by_ward[ward]
            staff = staff_by_ward[ward]
            shuffled = list(residents)
            rng.shuffle(shuffled)
            for staff_local, staff_id in enumerate(staff):
                shift_start = day_start + (staff_local % 2) * 8 * 60
                shift_end = min(day_start + 16 * 60, shift_start + 8 * 60)
                shift_id = f"shift-{day:03d}-{ward}-{staff_local:02d}"
                shifts.append(
                    StaffShift(shift_id, staff_id, ward, shift_start, shift_end)
                )
                entries.append(
                    OutsideEntry(
                        f"entry-{shift_id}",
                        staff_id,
                        shift_start,
                        "staff_shift",
                        ward,
                    )
                )
                assigned = shuffled[staff_local :: len(staff)]
                for care_index, resident_id in enumerate(assigned):
                    start = shift_start + 45 + care_index * 35
                    if start + 20 <= shift_end:
                        contacts.append(
                            TraceContact(
                                f"contact-{contact_index:06d}",
                                staff_id,
                                resident_id,
                                start,
                                20,
                                "direct_care",
                                ward,
                            )
                        )
                        contact_index += 1
            by_room: dict[str, list[str]] = {}
            for person in people:
                if person.role == RESIDENT and person.ward_id == ward:
                    assert person.room_id is not None
                    by_room.setdefault(person.room_id, []).append(person.person_id)
            for room_id, roommates in sorted(by_room.items()):
                if len(roommates) == 2:
                    contacts.append(
                        TraceContact(
                            f"contact-{contact_index:06d}",
                            roommates[0],
                            roommates[1],
                            day_start + 7 * 60,
                            60,
                            "roommate",
                            room_id,
                        )
                    )
                    contact_index += 1
            for meal_name, offset in (("breakfast", 8 * 60), ("lunch", 12 * 60), ("dinner", 18 * 60)):
                active_staff = staff[0] if offset < 16 * 60 else staff[-1]
                participants = tuple(residents + [active_staff])
                meal_id = f"meal-{day:03d}-{ward}-{meal_name}"
                dining = f"{ward}-dining"
                meals.append(MealSession(meal_id, dining, ward, day_start + offset, 45, participants))
                ring = list(participants)
                for left, right in zip(ring, ring[1:] + ring[:1], strict=True):
                    contacts.append(
                        TraceContact(
                            f"contact-{contact_index:06d}",
                            left,
                            right,
                            day_start + offset,
                            45,
                            "shared_meal",
                            dining,
                        )
                    )
                    contact_index += 1
        for visitor_index in range(config.visitor_count):
            visitor_id = f"visitor-{visitor_index:04d}"
            person = next(item for item in people if item.person_id == visitor_id)
            if day != 1 + (visitor_index % max(1, config.days - 1)):
                continue
            assert person.ward_id is not None and person.linked_resident_id is not None
            arrival = day_start + 14 * 60 + visitor_index * 10
            entries.append(
                OutsideEntry(
                    f"entry-visitor-{day:03d}-{visitor_index:04d}",
                    visitor_id,
                    arrival,
                    "visitor_arrival",
                    person.ward_id,
                )
            )
            contacts.append(
                TraceContact(
                    f"contact-{contact_index:06d}",
                    visitor_id,
                    person.linked_resident_id,
                    arrival + 10,
                    60,
                    "visitor_contact",
                    person.ward_id,
                )
            )
            contact_index += 1

    return InstitutionTrace(
        people=tuple(sorted(people, key=lambda item: item.person_id)),
        shifts=tuple(sorted(shifts, key=lambda item: item.shift_id)),
        meals=tuple(sorted(meals, key=lambda item: item.meal_id)),
        entries=tuple(sorted(entries, key=lambda item: item.entry_id)),
        contacts=tuple(sorted(contacts, key=lambda item: item.contact_id)),
        horizon_minutes=config.days * DAY_MINUTES,
    )


@dataclass(frozen=True, slots=True)
class ProjectedEvidence:
    evidence_id: str
    kind: str
    subject_id: str | None
    target_id: str | None
    available_minute: int
    payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "subject_id": self.subject_id,
            "target_id": self.target_id,
            "available_minute": self.available_minute,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class EvidenceLineage:
    evidence_id: str
    private_subject_id: str | None
    private_target_id: str | None
    source_record_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TraceEvidenceProjection:
    public_evidence: tuple[ProjectedEvidence, ...]
    private_lineage: tuple[EvidenceLineage, ...]
    private_trace_commitment: str
    projection_version: str = PROJECTION_VERSION

    def public_payload(self) -> list[dict[str, Any]]:
        """Return the only agent-facing serialization."""

        return [record.as_dict() for record in self.public_evidence]


def _public_id(key: bytes, kind: str, private_id: str) -> str:
    digest = hmac.new(
        key,
        _PRESENTATION_DOMAIN + kind.encode("ascii") + b"\x00" + private_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:24]
    return f"{kind}_{digest}"


def project_trace_evidence(
    trace: InstitutionTrace,
    symptoms: Iterable[SymptomRecord],
    *,
    presentation_key: bytes,
    observation_seed: int,
    lookback_minutes: int = 7 * DAY_MINUTES,
    record_capture_probability: float = 0.80,
) -> TraceEvidenceProjection:
    """Project interviews and inspections from frozen operational records."""

    if not isinstance(trace, InstitutionTrace):
        raise ValueError("trace must be an InstitutionTrace")
    if type(presentation_key) is not bytes or len(presentation_key) < 32:
        raise ValueError("presentation_key must contain at least 32 bytes")
    if type(observation_seed) is not int or observation_seed < 0:
        raise ValueError("observation_seed must be non-negative")
    if type(lookback_minutes) is not int or lookback_minutes < 1:
        raise ValueError("lookback_minutes must be positive")
    capture = _probability(record_capture_probability, "record capture probability")
    people = {person.person_id: person for person in trace.people}
    materialized = tuple(symptoms)
    if any(not isinstance(record, SymptomRecord) for record in materialized):
        raise ValueError("symptoms contain an invalid record")
    if len({record.symptom_id for record in materialized}) != len(materialized):
        raise ValueError("symptom IDs must be unique")
    if any(record.person_id not in people for record in materialized):
        raise ValueError("symptom references an unknown person")
    ordered_symptoms = tuple(
        sorted(materialized, key=lambda record: (record.recorded_minute, record.symptom_id))
    )
    evidence: list[ProjectedEvidence] = []
    lineage: list[EvidenceLineage] = []

    for symptom in ordered_symptoms:
        lower = max(0, symptom.onset_minute - lookback_minutes)
        contact_records = [
            record
            for record in trace.contacts
            if lower <= record.start_minute <= symptom.onset_minute
            and symptom.person_id in {record.person_a_id, record.person_b_id}
        ]
        meal_records = [
            record
            for record in trace.meals
            if lower <= record.start_minute <= symptom.onset_minute
            and symptom.person_id in record.participant_ids
        ]
        entry_records = [
            record
            for record in trace.entries
            if lower <= record.entry_minute <= symptom.onset_minute
            and record.person_id == symptom.person_id
        ]
        shift_records = [
            record
            for record in trace.shifts
            if lower <= record.start_minute <= symptom.onset_minute
            and record.staff_person_id == symptom.person_id
        ]
        all_records: list[tuple[str, str]] = [
            *(('contact', record.contact_id) for record in contact_records),
            *(('meal', record.meal_id) for record in meal_records),
            *(('entry', record.entry_id) for record in entry_records),
            *(('shift', record.shift_id) for record in shift_records),
        ]
        rng_seed = hashlib.sha256(
            f"{trace.commitment}:{observation_seed}:{symptom.symptom_id}".encode("utf-8")
        ).digest()
        rng = random.Random(int.from_bytes(rng_seed[:8], "big"))
        captured = [record for record in all_records if rng.random() < capture]
        counts = {
            kind: sum(item[0] == kind for item in captured)
            for kind in ("contact", "meal", "entry", "shift")
        }
        evidence_id = _public_id(presentation_key, "evidence", f"interview:{symptom.symptom_id}")
        public_subject = _public_id(presentation_key, "person", symptom.person_id)
        evidence.append(
            ProjectedEvidence(
                evidence_id=evidence_id,
                kind="record_review_interview",
                subject_id=public_subject,
                target_id=None,
                available_minute=symptom.recorded_minute + 60,
                payload={
                    "syndrome": symptom.syndrome,
                    "severity": symptom.severity,
                    "lookback_minutes": lookback_minutes,
                    "records_reviewed": len(all_records),
                    "records_captured": len(captured),
                    "record_type_counts": counts,
                    "data_quality": (
                        "complete" if len(captured) == len(all_records) else "partial"
                    ),
                },
            )
        )
        lineage.append(
            EvidenceLineage(
                evidence_id,
                symptom.person_id,
                None,
                tuple(record_id for _, record_id in captured),
            )
        )

    symptom_by_person = {record.person_id: record for record in ordered_symptoms}
    ward_ids = sorted(
        {person.ward_id for person in trace.people if person.ward_id is not None}
    )
    targets = [
        *(('ward', ward_id) for ward_id in ward_ids),
        *(('dining', f"{ward_id}-dining") for ward_id in ward_ids),
        ('entry_log', 'facility-entry-log'),
    ]
    available = max((record.recorded_minute for record in ordered_symptoms), default=0) + 120
    for target_type, private_target in targets:
        source_ids: list[str] = []
        matched_people: set[str] = set()
        if target_type == "ward":
            for contact in trace.contacts:
                if contact.location_id == private_target:
                    source_ids.append(contact.contact_id)
                    matched_people.update(
                        person_id
                        for person_id in (contact.person_a_id, contact.person_b_id)
                        if person_id in symptom_by_person
                    )
            for shift in trace.shifts:
                if shift.ward_id == private_target:
                    source_ids.append(shift.shift_id)
                    if shift.staff_person_id in symptom_by_person:
                        matched_people.add(shift.staff_person_id)
        elif target_type == "dining":
            for meal in trace.meals:
                if meal.location_id == private_target:
                    source_ids.append(meal.meal_id)
                    matched_people.update(
                        person_id
                        for person_id in meal.participant_ids
                        if person_id in symptom_by_person
                    )
        else:
            source_ids.extend(entry.entry_id for entry in trace.entries)
            matched_people.update(
                entry.person_id
                for entry in trace.entries
                if entry.person_id in symptom_by_person
            )
        evidence_id = _public_id(presentation_key, "evidence", f"inspection:{private_target}")
        public_target = _public_id(presentation_key, "target", private_target)
        evidence.append(
            ProjectedEvidence(
                evidence_id=evidence_id,
                kind="operational_record_inspection",
                subject_id=None,
                target_id=public_target,
                available_minute=available,
                payload={
                    "target_type": target_type,
                    "records_reviewed": len(source_ids),
                    "symptomatic_record_matches": len(matched_people),
                    "data_quality": "record_projection",
                },
            )
        )
        lineage.append(
            EvidenceLineage(
                evidence_id,
                None,
                private_target,
                tuple(sorted(source_ids)),
            )
        )

    return TraceEvidenceProjection(
        public_evidence=tuple(sorted(evidence, key=lambda record: record.evidence_id)),
        private_lineage=tuple(sorted(lineage, key=lambda record: record.evidence_id)),
        private_trace_commitment=trace.commitment,
    )
