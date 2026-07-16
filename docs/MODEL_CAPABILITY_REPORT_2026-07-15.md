# Disease-surveillance agent capability report

This report explains what the pilot scores mean behaviorally. Each result belongs to a model **plus its coding-agent interface**, not to the base model in isolation.

## New three-profile panel

This panel used five fresh private episodes, one from each causal family. Every scheduled run remains in the denominator; invalid runs score zero.

| Profile | Overall score | Valid-only mean | Reliability |
|---|---:|---:|---:|
| Codex + GPT-5.6 Luna (medium) | **64.571** | **64.571** | **5/5** |
| Claude + Sonnet 5 (high) | 42.389 | 52.986 | 4/5 |
| Cursor + Kimi K2.7 Code | 30.486 | 50.811 | 3/5 |

The valid-only column is diagnostic, not an alternate ranking: the systems failed on different scenarios, so those means are not fully paired.

### Scenario results

| Scenario | Luna | Sonnet | Kimi |
|---|---:|---:|---:|
| Institutional person-to-person spread | **54.779** | 49.761 | invalid: unauthorized tool |
| Restaurant point source | **75.988** | 53.300 | 55.114 |
| Repeated introduction | **53.878** | 49.892 | 51.117 |
| Coincidental venue | 52.041 | **58.990** | invalid: provider capacity |
| Reporting artifact | **86.169** | invalid: rejected report | 46.201 |

### Capability profile

Percentages are the share of points available in each scoring dimension. The first table treats invalid runs as zero and therefore measures end-to-end system performance. The second shows task performance only when a run was valid.

| Capability, all scheduled runs | Luna | Sonnet | Kimi |
|---|---:|---:|---:|
| Outbreak judgment | **99.1%** | 78.6% | 59.6% |
| Case finding | **89.3%** | 72.3% | 40.0% |
| Causal diagnosis | **69.8%** | 51.1% | 37.4% |
| Intervention utility | **40.0%** | 0% | 0% |
| Evidence selection | **39.6%** | 20.4% | 23.4% |
| Forecasting | **53.9%** | 46.3% | 40.3% |
| Efficiency | **49.7%** | 39.8% | 24.4% |
| Complete handoff | **100%** | 80% | 60% |

| Capability, valid runs only | Luna | Sonnet | Kimi |
|---|---:|---:|---:|
| Outbreak judgment | 99.1% | 98.2% | **99.4%** |
| Case finding | 89.3% | **90.4%** | 66.7% |
| Causal diagnosis | **69.8%** | 63.8% | 62.3% |
| Intervention utility | **40.0%** | 0% | 0% |
| Evidence selection | **39.6%** | 25.5% | 39.0% |
| Forecasting | 53.9% | 57.9% | **67.1%** |
| Efficiency | 49.7% | **49.8%** | 40.7% |
| Complete handoff | 100% | 100% | 100% |

Outbreak judgment and handoff completeness are near ceiling on valid runs, so they do little to separate the systems. Intervention execution, causal diagnosis, focused evidence use, and reliability are more informative.

### What each new profile did well and poorly

#### Codex + GPT-5.6 Luna

Luna was the most reliable and the only profile to convert an investigation into beneficial intervention utility. It matched the best realized policy branch on the restaurant episode (standard source control) and the reporting-artifact episode (standard reporting audit). It also had the strongest average causal-diagnosis and evidence scores and was much faster in wall-clock time: 101 seconds per run, compared with 231 for Sonnet's valid runs and 327 for Kimi's.

Its weaknesses were mechanism-specific. It put only 0.08 probability on repeated introduction and used infection control instead of the useful entry-control response. On the restaurant episode it found all true cases but added false positives (case precision 0.60). It also violated the forecast-review-interval rule in every episode. On the coincidental-venue episode it correctly avoided harmful control, but its final report still described an unexecuted action.

#### Claude + Sonnet 5

On valid runs, Sonnet was precise about who counted as a case: mean precision was 1.0, and it had the strongest valid-only line-list score. It was the best profile on the coincidental-venue episode and assigned 0.65 probability to the correct sporadic-background explanation.

Its main weakness was closing the loop. It earned no intervention points. It over-intervened on the institutional and coincidental scenarios, gave only 0.20 probability to the restaurant common source, and assigned zero probability to the true repeated-introduction target. On the reporting-artifact episode its one-shot `submit_report` omitted required fields. The trusted evaluator rejected it; subsequent tool activity triggered the post-submission guard, and no scoreable report was produced.

#### Cursor + Kimi K2.7 Code

When valid, Kimi had excellent outbreak calibration and the strongest average forecast accuracy (mean absolute error 1.0). It assigned the highest common-source probability among the three profiles on the restaurant episode (0.40), although it did not turn that into beneficial intervention utility.

Reliability was the central problem. One run attempted an unauthorized Cursor tool and was hard-zeroed. Another ended when Cursor returned `resource_exhausted` after reconnect attempts; that is a provider/interface failure, not demonstrated epidemiologic reasoning. On the reporting-artifact episode Kimi identified the mechanism and forecast perfectly, but retained artifact records as suspected patients and used an overly costly intensive audit.

### Intervention behavior

| Scenario | Best policy on the realized branch | Luna | Sonnet | Kimi |
|---|---|---|---|---|
| Institutional spread | All controls off | Over-treated | Over-treated more | Invalid |
| Restaurant point source | Standard source control | **Matched best realized branch** | Broader, costly policy | Broader, costly policy |
| Repeated introduction | Standard entry control | Missed; used infection control | Mixed broad controls; too costly | Missed; used infection control |
| Coincidental venue | All controls off | Correctly abstained; report mismatch | Over-treated | Provider failure |
| Reporting artifact | Standard reporting audit | **Matched best realized branch** | Correct direction; invalid handoff | Intensive, costly audit |

The two all-off scenarios have no positive intervention utility available, so the response dimension returns zero even for correct abstention. The cleanest opportunity-based summary is: Luna succeeded on two of three episodes with a beneficial-policy opportunity; Sonnet and Kimi succeeded on zero of three.

All three missed repeated introduction. The correct-target probabilities were Luna 0.08, Kimi 0.05, and Sonnet 0.00, and none produced the useful, economical entry-control response. This is the strongest shared scientific weakness in the panel.

### Why the overall gap is not simply “Luna reasons much better”

Across the four episodes where both Luna and Sonnet were valid, their average **non-intervention** points were almost identical: Luna 52.922 versus Sonnet 52.986. Luna's paired total advantage came from one 25-point intervention success. The larger fixed-denominator gap also includes Sonnet's failed reporting-artifact handoff.

Kimi and Sonnet were both valid only on the restaurant and repeated-introduction episodes. Kimi averaged 53.116 there versus Sonnet's 51.596. Their valid-only means across different subsets are not a clean head-to-head comparison.

## Interpretation of the previously published four-profile panel

The earlier headline scores were close—Opus 59.212, Sol 58.938, and Grok 56.625—but the systems got there in different ways.

| Profile | Outbreak judgment | Case finding | Causal diagnosis | Intervention | Evidence | Forecasting | Efficiency | Valid runs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude + Opus 4.8 High | 97.7% | **78.5%** | 66.7% | 20.0% | 36.2% | **66.8%** | **58.2%** | 5/5 |
| Codex + GPT-5.6 Sol | **99.6%** | 76.7% | **93.4%** | 20.0% | 35.3% | 64.9% | 31.4% | 5/5 |
| Cursor + Grok 4.5 | 98.2% | 69.6% | 82.0% | 20.0% | **42.4%** | 65.3% | 24.9% | 5/5 |
| Cursor + GLM 5.2 | 51.1% | 25.7% | 50.1% | 0% | 20.4% | 37.8% | 25.4% | 3/5 |

- Sol was the strongest causal diagnostician and had the best outbreak calibration, but it investigated exhaustively and inefficiently.
- Opus was the most efficient and the only profile to produce beneficial reporting-audit utility. It was weaker at causal discrimination.
- Grok was best at finding and citing decisive evidence and handled restaurant source control well. It was the least efficient of the three reliable systems and tended to over-intervene.
- GLM's low mean mainly reflected two unauthorized-tool hard zeros. Those failures belong to the GLM-plus-Cursor system rather than safely to the model alone.

Opus beat Sol by only 0.274 points, but this was a cancellation of different abilities: Opus gained about 2.68 aggregate points from efficiency while losing about 2.67 on causal diagnosis. Their per-episode differences ranged from -31.233 to +28.278. A ranking from one episode per family is not scientifically stable.

## Scientific limits and next step

- Each completed panel has one seed per causal family. These are integration pilots, not stable leaderboards or statistically distinguishable model rankings.
- The panels use different private cohorts. Their means must not be merged into a single ranking.
- Results are non-hermetic local cloud-agent runs. Exact model identity was observed for Claude and Cursor; Codex identity is command-attested.
- Episode 2 of the new panel used a disclosed continuity recovery after two results were durable and before the third assignment started. No inference was retried, but the continuation remains a protocol deviation.
- A scientifically useful comparison needs multiple fresh private seeds per family and paired confidence intervals, causal-mode confusion, outbreak calibration, case precision/recall, intervention regret by policy opportunity, forecast error, resource burden, and guardrail failure rate.

The next panel therefore uses 50 unopened episodes—10 per causal family—and all six requested full-system profiles on one precommitted schedule. It remains a development comparison, not held-out external validation or a leaderboard.
