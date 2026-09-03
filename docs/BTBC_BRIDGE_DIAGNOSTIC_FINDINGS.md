# BTBC categorical-bridge diagnostic findings

Status: internal diagnostic evidence only. These results do **not** establish real-world LLM-memory efficacy and do not alter the frozen BTBC v1.1-v1.4 research implementation.

## Scope

The frozen controller is exercised through `btbc/llm_state_bridge.py`, which maps arbitrary categorical memory values into deterministic fixed-width `{-1,+1}` codewords and reserves `0` for unknown state. The frozen source, `router.joblib`, and locked `operating.json` remain unchanged.

Two targeted 20-world diagnostics were run against the same deterministic generated-world configuration.

## Diagnostic 1: pre-risk-gate and permissive routing

GitHub Actions run: `33593462234`.

Across 20 worlds:

- pre-gate recovery candidate cells: **0**
- stage-1 escalated cells: **28**
- worlds with any pre-gate candidate: **0 / 20**

Locked v1.4:

- routed escalations: **0**
- blocked escalations: **28**
- changed cells: **0**
- final actions: `KEEP=14972`, `RISK_BUDGET_KEEP=28`

Debug-only permissive profiles (`low_harm`, `moderate`, and `route_all_escalations`) routed all 28 escalations, but still changed **0** cells. The routed actions became `REVIEW_KEEP`, not repairs.

### Interpretation

The locked v1.4 risk budget is **not the primary cause** of inert repair behavior on the present categorical bridge. Even when the v1.4 router is made maximally permissive for diagnosis, the frozen v1.1/v1.2 recovery branch has no alternate cell values to apply. The bottleneck occurs earlier, in evidence formation / candidate generation.

## Diagnostic 2: oracle synthetic independent corroboration

GitHub Actions run: `33738871811`, branch head `44d81b7c2bd2e64d50d4fe51f6564acff6b4b029`.

This experiment deliberately injects ground-truth-derived high-trust relation observations in memory **only for causal diagnosis**. It is not a deployable method and must not be reported as BTBC efficacy.

Across the same 20-world configuration, 1,416 diagnostic relation edges were added.

### Baseline, unchanged bridge

- pre-gate candidate cells: **0**
- escalated cells: **28**
- locked routed / blocked: **0 / 28**
- changed cells: **0**
- repaired corrupted fields: **0**

Routing every escalation still produced:

- routed: **28**
- changed cells: **0**
- repaired corrupted fields: **0**

### With oracle independent relation evidence

Pre-gate behavior changed sharply:

- pre-gate candidate cells: **123**
- worlds with pre-gate candidates: **17 / 20**
- escalated cells: **125**
- stage-1 repairs: **1**
- stage-2 repairs: **123**

Under the original locked v1.4 operating point:

- routed: **111**
- blocked: **14**
- changed cells: **110**
- repaired corrupted fields: **19**
- worlds with at least one repaired corrupted field: **15 / 20**

With route-all debug routing:

- routed: **125**
- blocked: **0**
- changed cells: **124**
- repaired corrupted fields: **21**
- worlds with at least one repaired corrupted field: **16 / 20**

### Interpretation

This is a causal localization result, not an efficacy result. It demonstrates that the unchanged frozen decoder/reviewer/router **can become active through the categorical bridge when supplied with independent relational evidence that supports the correct state**. The original generated relationships supplied topology but not independent semantic relation observations, so the ordinary bridge mostly recomputed relations from the same categorical codewords it was trying to validate.

The risk budget does reject some useful-looking diagnostic recovery calls (14 of 125 corroborated escalations), but this is secondary. The dominant failure in the ordinary bridge is absence of independent evidence before the risk gate.

## Engineering conclusion

Do not lower the frozen safety threshold and do not retrain or modify frozen v1.x to solve this bridge problem.

The next bridge iteration should preserve frozen v1.4 and surface **non-oracle independent evidence**, for example:

1. explicit relation observations derived from independently stored relationship facts or external corroborating observations;
2. multiple independently sourced observations of the same canonical fact, rather than only a latest categorical value and its self-derived bit relations;
3. deterministic canonical/equality relations where the semantics justify them, with provenance and trust attached separately from the target state;
4. a benchmark that distinguishes independent evidence from relations mathematically derived from the same state being checked.

A new bridge representation must be evaluated first at the memory level on paired generated worlds. LLM A/B testing should remain downstream until the non-oracle bridge shows reproducible repairs with controlled false corrections and legitimate-change damage.

## Scientific boundary

The synthetic corroboration result intentionally uses ground truth to manufacture supporting relation observations. Therefore numbers such as 19 repaired corrupted fields under locked routing **cannot** be presented as performance of BTBC on realistic memory. They only show that independent relational evidence is sufficient to activate the frozen machinery and localize the present integration bottleneck.
