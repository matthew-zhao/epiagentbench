# Operational data request for scientific v3

Status: **request specification only. No private operational dataset has been
obtained, reviewed, or incorporated into the benchmark.**

Public outbreak summaries cannot calibrate alert false positives, quiet periods,
active case finding, missingness, investigation delays, or the effect of actions.
Scientific v3 therefore seeks a privacy-preserving partnership with long-term-
care facilities and state or local public-health agencies.

## Intended use

The data would be used to estimate and validate the observation process for a
synthetic benchmark: how symptoms become facility records, alerts,
notifications, investigations, tests, amendments, and final dispositions. Raw
records would not be distributed with the public benchmark or shown to evaluated
agents.

## Required sampling frame

The sample must include more than confirmed norovirus outbreaks:

- quiet facility-days or weeks;
- alerts that were investigated and closed;
- clusters caused by other gastrointestinal pathogens or noninfectious causes;
- suspected and confirmed norovirus outbreaks;
- reporting errors, duplicates, late reports, and amended reports, including
  errors that coexist with a real outbreak.

Without this denominator, alert specificity and false-escalation cost are not
identifiable.

## Minimum deidentified tables

### Facility and time

- stable pseudonymous facility ID;
- coarse facility type and capacity;
- daily resident census and staffing totals by role;
- coarse ward or unit IDs and unit capacity;
- a consistently date-shifted calendar preserving intervals, weekday, and
  season, with the shift withheld from benchmark developers where feasible.

### Symptom surveillance

- pseudonymous person ID scoped to one facility;
- resident/staff/visitor role and coarse unit assignment;
- symptom onset and resolution interval;
- vomiting, diarrhea, fever, and other case-definition fields;
- first recognition time, recognizer/channel, severity, and care encounter;
- whether the record was discovered only through active case finding.

### Alert and notification log

- alert timestamp, algorithm/version, window, threshold, and public input
  counts;
- facility review and health-department notification timestamps;
- preliminary and final disposition with adjudication source;
- linked outbreak/investigation ID where applicable;
- suppressed, duplicate, reopened, and amended alerts.

### Investigation activity

- requested interview, roster, shift, contact, meal, vendor, entry, or
  environmental record;
- request, availability, and completion timestamps;
- nonresponse, missingness, unusable sample, and reason codes;
- structured finding fields and confidence, not unrestricted narrative text.

### Laboratory process

- specimen requested, collected, rejected, and resulted timestamps;
- assay family and laboratory-confirmed result;
- specimen quality and time since symptom onset;
- link to the preliminary and final outbreak record.

### Response and outcomes

- action component, target, order, effective time, adherence, relaxation, and
  stop time;
- cohorting/isolation, staff exclusion, hand hygiene/PPE, environmental
  cleaning, testing, admission/transfer/visitor restrictions, and source
  removal as separate fields;
- staff absence/replacement, restriction days, cleaning/testing effort,
  hospitalizations, deaths, final case count, and outbreak end date.

## Explicit exclusions

Do not transfer names, addresses, exact birth dates, contact details, medical
record numbers, unredacted free text, or secrets used to derive public benchmark
identifiers. Rare categories and small cells require expert disclosure review.
No raw private record becomes an agent-visible prompt or a public episode.

## Governance and validation split

- Establish the legal basis, IRB/privacy review, data-use agreement, retention
  period, access list, and deletion process before transfer.
- Keep data encrypted in a restricted analysis environment with auditable
  access and no model-provider training permission.
- Split by whole facility or jurisdiction before fitting. Records from one
  outbreak, facility, or reporter must not cross fit and validation partitions.
- Reserve at least one independently held source for a single blind evaluation.
  The independent custodian releases only the predeclared aggregate metrics and
  signed/committed validation report.
- Publish the schema, missingness rules, estimands, parser hash, and aggregate
  diagnostics. Do not publish small-cell or reidentifiable outputs.

## Minimum useful contribution

A partner does not need to supply every table. The first high-value contribution
is a deidentified alert/disposition log with quiet periods and final outcomes;
the second is a complete symptom line list with notification and laboratory
timestamps. Either would close a scientific gap that NORS cannot address.
