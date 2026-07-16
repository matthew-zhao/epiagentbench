# Human solveability and expert-adjudication protocol

Status: **protocol scaffold; no participant study has been run.** Final sample
size, recruitment, compensation, analysis thresholds, and ethics review must be
registered before examining private-episode results.

## Questions

1. Can public-health experts reach a defensible conclusion from only the
   evidence available to an evaluated agent?
2. Do experts agree on the likely causal process, case set, forecast, next
   investigation, and proportionate response?
3. Are disagreements legitimate alternatives, missing evidence, or scenario
   defects?
4. Does an AI system outperform strong heuristics without causing more severe
   false escalations or missed outbreaks?

Simulator truth is not automatically a valid answer key. Episodes that experts
cannot solve or that admit several defensible actions must be revised, scored
with adjudicated alternatives, or excluded under a rule fixed before model
evaluation.

## Participants and independence

- Recruit epidemiologists, infection-prevention professionals, and long-term-
  care outbreak investigators with documented relevant experience.
- Use a development group for interface and cognitive walkthroughs.
- Use different experts as independent adjudicators for the frozen study set.
- Record expertise, role, and prior exposure to the benchmark. Do not expose
  latent parameters, generator code, private mode labels, or private outcomes.
- Complete applicable human-subjects/ethics review and obtain informed consent.

## Episode sampling

- Sample episodes from the frozen candidate before observing human or model
  performance and without retries based on the winning action.
- Include true outbreaks, non-norovirus illness, quiet/false alerts, reporting
  errors within real outbreaks, common sources, outside introductions, and
  uncertain mixed cases at the intended deployment prevalence.
- Preserve whole matched sets and predeclare any opening-evidence admission
  rule. Do not drop an episode because a participant or model answered it
  incorrectly.
- Keep a separate public practice set; practice episodes never enter the
  reported comparison.

## Interface and budgets

Experts and AI systems receive the same substantive public observations,
request catalog, delays, action catalog, deadline, and evidence cutoff. A human
UI may differ from an agent API for usability, but it must not reveal additional
fields or omit costs. Log every observation viewed, request, action, forecast,
revision, and timestamp.

## Required outputs

Each participant provides:

- probability that a causal outbreak exists;
- probabilities over the predeclared causal hypotheses, including “other”;
- proposed case set with confidence or inclusion probabilities;
- next investigation request and rationale;
- forecast distribution for the declared horizon;
- response components, targets, intensity, and timing;
- evidence citations limited to observations available by the cutoff;
- confidence and a flag for insufficient or contradictory evidence.

## Adjudication

Independent adjudicators review the public transcript and participant answers
without seeing model identities. They define acceptable answer sets and serious
harm categories using a rubric frozen before leaderboard runs. When reasonable
experts disagree, retain that uncertainty in scoring rather than forcing the
simulator’s hidden label as the only valid answer.

## Outcomes

Report at least:

- completion and valid-submission rate;
- probability calibration and proper scores;
- case-set precision/recall with uncertainty-aware adjudication;
- causal-hypothesis and action agreement among experts;
- inter-rater reliability with confidence intervals;
- forecast calibration and sharpness;
- investigation/action sequence, time, and evidence use;
- expected policy regret and severe-tail harm under every registered utility
  profile;
- performance above always-escalate, always-do-nothing, inspect-all,
  request-everything, and value-of-information heuristics.

Report per-episode outcomes and uncertainty distributions where disclosure is
safe; do not publish only one aggregate score.

## Failure rules

Before the study, register what constitutes:

- insufficient expert solveability;
- inadequate agreement for a unique gold action;
- a serious scenario inconsistency or hidden-information dependency;
- a harmful false escalation or missed severe outbreak;
- a change requiring the study set to be discarded and regenerated.

Any threshold changed after results are visible creates a new development study.
It cannot be used to claim the same sample was a confirmatory test.

## Reproducible record

The final study artifact must commit the protocol version, recruitment and
exclusion flow, episode-set commitment, interface version, participant and
adjudicator blinding, analysis code, all registered thresholds, aggregate
results, and deviations. Its SHA-256 is the evidence artifact for the
`expert_solveability` scientific gate; the gate additionally requires
independent adjudication.
