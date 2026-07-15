# Visible external curve-shape reference

Status: **implemented as a narrow public model check, not a blind holdout and
not sufficient evidence of scientific realism**.

The reference is the Adams et al. S1 case line list for six confirmed
norovirus outbreaks in South Carolina nursing homes during 2014–2016:

- article and methods: <https://doi.org/10.1371/journal.pcbi.1007271>
- S1 CSV: <https://journals.plos.org/ploscompbiol/article/file?type=supplementary&id=info:doi/10.1371/journal.pcbi.1007271.s001>
- license: Creative Commons CC0 1.0 Universal
- pinned CSV size: 35,374 bytes
- pinned CSV SHA-256:
  `498efcf4ab49aaf8eb77d1c2c61ff7cfff0a8ca9c859029b25adf041041d4e8a`
- cases/outbreaks: 209/6

The source is fully visible and may be used for falsification and model
criticism. If parameters are repeatedly changed to match it, it is development
data. A different, independently frozen dataset is then required for a real
external validation claim.

## Frozen metrics

`external_validation.py` freezes the parser, tie rules, denominators, and
missingness rules before comparing simulator output. It calculates each metric
per outbreak and then summarizes the six outbreak-level values:

- onset-to-onset duration;
- normalized peak timing, choosing the earliest day when peak counts tie;
- fraction of onset-observed cases occurring on the peak day;
- resident fraction among cases with known resident/staff status;
- vomiting and diarrhea margins using their own known-value denominators;
- joint vomiting-and-diarrhea margin when both fields are known; and
- first-day and total reported case counts as secondary/context checks.

It never imputes a symptom or resident/staff status that a simulator does not
produce. Such a metric is marked `not_comparable`. It emits metric-wise
quantile differences and target-range coverage, but deliberately emits no
composite reward and no pass/fail gate.

The pinned public reference has these outbreak-level summaries:

| Metric | Six values | Median | Middle 50% |
|---|---|---:|---:|
| Duration, days | 12, 10, 13, 18, 12, 12 | 12 | 12–12.75 |
| Peak timing fraction | 0.364, 0, 0.750, 0.353, 0.455, 0.545 | 0.409 | 0.356–0.523 |
| Peak case fraction | 0.296, 0.273, 0.478, 0.353, 0.250, 0.220 | 0.285 | 0.256–0.339 |
| Resident fraction | 0.852, 1, 0.826, 0.846, 0.667, 0.537 | 0.836 | 0.707–0.850 |
| Vomiting fraction | 0.704, 0.909, 0.609, 0.961, 0.688, 0.659 | 0.696 | 0.666–0.858 |
| Diarrhea fraction | 1, 0.545, 0.756, 0.922, 0.875, 0.537 | 0.815 | 0.598–0.910 |
| First-day cases | 1, 3, 1, 1, 2, 1 | 1 | 1–1.75 |

## Reproducible use

The downloader refuses a source whose bytes do not match the pinned hash. It
writes an immutable CSV plus provenance sidecar; the reference report also has
a canonical SHA-256 commitment.

```python
from epiagentbench.external_validation import (
    build_adams_reference_report,
    compare_simulated_curve_shapes,
    fetch_adams_snapshot,
    parse_simulated_reported_line_list,
)

snapshot = fetch_adams_snapshot("run_artifacts/adams")
reference = build_adams_reference_report(snapshot.csv_path)
simulated = parse_simulated_reported_line_list(simulator_rows)
comparison = compare_simulated_curve_shapes(
    simulated, reference, candidate_label="frozen-candidate-id"
)
```

The local verification run produced reference-report SHA-256
`9b7e2a56d8a88f6a1d2bd03457fd03e328bcb13a6fcb9dff02b225809517e790`.
That commitment is reproducible from the pinned CSV and metric contract.

## Limits

Six outbreaks from one setting, state, and two-season window cannot establish
broad realism. The line list includes reported probable and confirmed cases,
not all infections, non-outbreak alerts, random introductions, or intervention
counterfactuals. The check therefore complements the NORS outbreak-size check;
it does not repair a failed simulator, identify biological parameters, or
replace a future blind empirical cohort.
