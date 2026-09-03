# BTBC v1.4 — Validation and Component Ablation Summary

## Status

BTBC v1.4 is the current frozen classical AI-memory prototype used as the reference implementation for the local-agent experiment.

The current results are internal and synthetic. They are not independent validation.

## Locked synthetic result

The frozen v1.4 locked test used 270 fresh worlds across 135 adversarial scenario types after the false-correction budget and operating point had been selected on separate validation worlds.

| Metric | Result |
|---|---:|
| Raw memory error | 22.4091% |
| SAFE error | 20.3406% |
| Full RECOVERY error | 16.4815% |
| BTBC v1.4 adaptive error | 17.6323% |
| Relative error reduction vs raw | 21.3163% |
| Repair precision | 96.9089% |
| False-correction rate | 0.09590% / cell |
| Declared false-correction budget | 0.10000% / cell |
| Corrupted-cell recovery fraction | 21.7443% |
| Scenario averages non-worse than raw | 98.52% |
| Recovery routing fraction of escalations | 37.89% |

The unrestricted RECOVERY branch obtains lower absolute error, but at a much higher false-correction rate. v1.4 deliberately sacrifices some recovery to remain under a predeclared safety budget.

## Component ablation

The component ablation was designed to determine which parts of the architecture actually produce the measured result.

| Variant | Error | Relative reduction vs raw | Repair precision | False-correction rate/cell | Corruption recovered |
|---|---:|---:|---:|---:|---:|
| Full v1.4 | 17.6323% | 21.3163% | 96.91% | 0.09590% | 21.74% |
| No risk budget | 16.4633% | 26.5329% | 92.10% | 0.37698% | 28.22% |
| No provenance/trust | 18.2110% | 18.7339% | 96.61% | 0.09590% | 19.16% |
| No temporal history* | 21.2467% | 5.1870% | 91.04% | 0.09755% | 5.62% |
| No relational evidence | 22.4091% | 0.0000% | 0.00% | 0.00000% | 0.00% |
| No router-confidence feature | 17.5992% | 21.4639% | 96.59% | 0.10582% | 21.94% |

*The no-temporal version could not find a validation operating point that satisfied the explicit 0.10% false-correction budget. The reported value is the best unconstrained fallback used diagnostically.

## What the ablation supports

### Relational evidence

Removing relational evidence collapses the measured repair advantage to the raw-memory baseline in this implementation. This is the strongest ablation result.

### Temporal history

Removing temporal evidence substantially weakens recovery and prevents the ablated controller from finding a validation operating point that satisfies the declared safety budget.

### Provenance / trust

Removing provenance weakens recovery but does not eliminate the effect. It appears to be a useful supporting information channel rather than the primary source of the advantage.

### Risk budget

The safety budget is not the source of the accuracy improvement. Removing it increases recovery but also increases destructive corrections by roughly fourfold relative to the v1.4 operating point.

### Router confidence

The confidence feature has little effect on raw accuracy in this ablation but appears useful for keeping the locked false-correction rate within the target.

## Current technical interpretation

The strongest defensible interpretation is:

> The measured BTBC memory-repair effect is primarily driven by relational structure plus temporal history. Provenance/trust contributes additional information, and explicit risk control trades some maximum recovery for lower destructive-correction risk.

This ablation does not establish that the numerical 3-6-9 mapping itself causes the improvement.

## Next decisive experiment

Run the frozen full implementation and matching ablations on a real or public persistent-memory workload with conventional baselines and identical fault draws.

At minimum compare:

1. raw / no repair
2. plain persistent memory
3. a conventional graph or probabilistic baseline
4. frozen BTBC v1.4
5. selected BTBC ablations

Preserve raw outputs, seeds, versions, integration changes, and commit/model hashes.
