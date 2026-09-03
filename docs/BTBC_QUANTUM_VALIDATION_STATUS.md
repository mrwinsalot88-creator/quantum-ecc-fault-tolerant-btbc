# BTBC Quantum Validation Status

**Status date:** 2026-09-03  
**Branch:** `btbc-local-agent`

This document is the evidence ledger for the current BTBC quantum-error-correction work. It separates implemented mechanisms, completed benchmark results, failed criteria, current validation work, and claims that are not yet supported.

## 1. Core interpretation currently being tested

BTBC is being tested here as a native three-level quantum-control architecture with balanced-trinary basis labels

`|-1>`, `|0>`, `|+1>`.

The present operational interpretation is **non-temporal**:

- `0` = simultaneous availability of candidate decision branches / syndrome evidence.
- `3` = raw relational/error evidence.
- `6` = same-cycle consistency/confidence evaluation.
- `9` = immediate fail-safe correction when the same-cycle evidence is sufficiently reliable.

There is **no required 3 -> 6 -> 9 clock delay**. Earlier serialized implementations are retained as negative/ablation evidence, not as the intended BTBC mechanism.

The numerical labels are architectural semantics. Current simulations do not establish that the numbers 3, 6, and 9 have independent physical significance.

## 2. Evidence ladder

### 2.1 Serialized native-qutrit controller — failed primary benchmark

The first native `-1,0,+1` controller interpreted 3 -> 6 -> 9 as repeated observations over time. That implementation was too conservative and allowed errors to accumulate before correction.

Pooled result from the frozen native-qutrit benchmark:

| Arm | Logical failures |
|---|---:|
| Conventional immediate qutrit decoder | 2,060 |
| Serialized BTBC full | 3,231 |
| BTBC no-9 | 13,247 |
| Bare | 13,354 |
| Perfect syndrome | 603 |

The serialized controller therefore **failed** the primary performance criterion. It did, however, strongly suppress false corrections. This result motivated the correction that BTBC should not be implemented as a temporal waiting rule.

### 2.2 Non-temporal same-cycle qutrit corroboration — positive but unequal-information result

A later native-qutrit benchmark removed the temporal delay and allowed the `9` fail-safe to act in the same correction cycle using simultaneous syndrome evidence.

Pooled over 20,000 trials:

| Arm | Logical failures |
|---|---:|
| Conventional two-check decoder | 2,045 |
| BTBC non-temporal | 725 |
| BTBC no-9 | 13,290 |
| Bare | 13,284 |
| Perfect syndrome | 643 |

The result was encouraging, but the BTBC arm used three simultaneous parity checks while the conventional arm used two. Therefore this result demonstrates the value of same-cycle redundant corroboration, but it is **not sufficient evidence of a BTBC-specific advantage**.

### 2.3 Hard matched-information shift-error benchmark — robust mechanism, no label-specific advantage

The next benchmark gave BTBC and the strong generic control the same simultaneous evidence and resource budget, added unseen seeds, asymmetric data/readout noise, and correlated burst faults.

Across 5 unseen seeds, 8 noise profiles, 80,000 trials per arm, and 100 cycles per trial:

- ordinary noisy two-check decoder logical failure rate: about **16.75%**
- three-check same-cycle decoder logical failure rate: about **10.82%**
- false corrections fell from **141,268** to **1,571**
- BTBC and an exact generic same-rule decoder matched exactly
- serialized BTBC was substantially worse, about **22.50%** logical failure

Interpretation: simultaneous redundant syndrome corroboration was useful and robust under that generalized-X / burst model, but the exact match to the generic control means the measured benefit belonged to the operational decoder rule rather than to the labels `3/6/9` themselves.

### 2.4 Hard full-generalized-Pauli `[[9,1,3]]_3` benchmark — mixed / failed primary criteria

Workflow run: `33765752336`  
Artifact: `btbc-qutrit-full-pauli-hard-results`  
Artifact ID: `9898377553`  
Artifact ZIP SHA-256: `5a6bdea4034bda3272eae5f28103a7f3edefe97d8ab3191ba433f9b6182860e7`

This benchmark was deliberately harder:

- native qutrit GF(3) Pauli-frame simulation,
- `[[9,1,3]]_3` Shor-style stabilizer construction,
- generalized X, Z, and mixed X/Z qutrit Pauli faults,
- arbitrary unknown Haar-distributed logical qutrit states,
- 100 correction cycles,
- three full syndrome reads per cycle for all arms,
- noisy syndrome readout,
- extraction back-action,
- recovery-operation faults,
- correlated 3-qutrit block bursts,
- 8 asymmetric noise profiles,
- 5 frozen seeds,
- matched random streams across decoder arms.

Pooled over 40,000 trials per arm:

| Decoder | Logical failure rate | Mean unknown-state fidelity | False corrections |
|---|---:|---:|---:|
| BTBC full / unanimity | 45.620% | 0.657665 | 17 |
| Strong three-read component-ML/plurality | 38.770% | 0.709916 | 14,490 |
| Latest-read conventional | 54.025% | 0.595109 | 250,748 |
| BTBC no-9 | 77.030% | 0.421775 | 0 |
| Perfect-current reference | 34.5275% | 0.740736 | 0 |

Predeclared outcomes:

- BTBC beat latest-read conventional: **PASS**
- BTBC beat no-9: **PASS**
- BTBC false corrections below latest-read: **PASS**
- BTBC non-worse than strong ML on at least 3/5 seeds: **FAIL**
- BTBC pooled non-worse than strong ML: **FAIL**
- BTBC == exact generic-unanimity control: **PASS**
- all primary criteria: **FAIL**

Interpretation:

> The strict same-cycle unanimity/abstention decoder is a high-precision, low-recall policy. It almost eliminates false correction actions but abstains too often to beat a strong same-information three-read ML/plurality decoder on total logical failure and unknown-state fidelity under this hard generalized-Pauli benchmark.

This is a scientifically useful negative result. It identifies the performance bottleneck as the decision policy rather than the native qutrit representation itself.

## 3. Code-contract correction

The full-Pauli benchmark originally included the assertion:

`all_72_single_qutrit_nonidentity_paulis_have_unique_syndromes`

That is too strong as a general stabilizer-code contract because a degenerate code can have multiple physical errors sharing a syndrome while still recovering them to the same logical state.

The important contract is instead:

- stabilizer rank is correct,
- stabilizers commute over GF(3),
- logical operators commute with the stabilizer group and are independent,
- the decoder covers the complete syndrome space,
- every targeted single-qutrit generalized Pauli error is recovered to the correct logical state.

The new confidence validation records syndrome degeneracy diagnostically but uses **logical recoverability**, not global syndrome uniqueness, as the pass/fail condition.

## 4. Current frozen experiment: same-cycle confidence-weighted BTBC

Script: `scripts/test_btbc_qutrit_confidence_hard.py`  
Workflow: `.github/workflows/btbc-qutrit-confidence-hard.yml`

This is an **independent validation**, not a retune-and-retry on the previous held-out seeds.

### New frozen seeds

`5010017, 6020039, 7030061, 8040073, 9050087`

### Same hard environment retained

- same `[[9,1,3]]_3` qutrit stabilizer model,
- same 8 hard data/readout/extraction/recovery/burst profiles,
- 100 cycles,
- 1,000 trials per profile/seed/arm,
- arbitrary unknown logical qutrit states,
- matched physical random streams,
- three full syndrome reads per cycle for all arms.

### Predeclared confidence policy

Within one correction cycle:

1. Build a component-wise 3-read plurality candidate.
2. If any syndrome component is a `1/1/1` contradiction, abstain.
3. If the candidate decodes to minimum physical weight <= 1, correct immediately.
4. If it decodes to weight 2, correct only when at least 6 of 8 syndrome components are unanimous and none is contradictory.
5. For higher decoder weight, abstain.
6. Zero syndrome means no correction.

No previous-cycle state or temporal persistence is used.

### Controls

- `generic_component_ml3`: strong same-information component plurality/ML decoder.
- `generic_confidence`: exact unlabeled copy of the BTBC confidence policy.
- `generic_latest3`: latest-read conventional baseline.
- `btbc_no9`: correction disabled.
- `perfect_current`: ideal current-syndrome reference.

### Predeclared success criteria

For a strong positive result, BTBC must simultaneously:

- pass the corrected native-code contract,
- exactly match the generic-confidence implementation control,
- exercise state 9,
- beat no-9 and latest-read pooled,
- produce fewer false corrections than latest-read and strong ML,
- be non-worse than strong ML on logical failure on at least 3 of 5 new seeds,
- be non-worse than strong ML on fidelity on at least 3 of 5 new seeds,
- be pooled non-worse than strong ML on logical failure,
- be pooled non-worse than strong ML on mean unknown-state fidelity.

A failure of those criteria remains a valid result and will not be hidden or retuned away.

## 5. What is currently supported

The completed simulations support the following narrower statements:

1. Native qutrit balanced-trinary state labels can be implemented consistently in the simulator.
2. Generalized qutrit Pauli syndromes and recovery can be modeled over GF(3).
3. Same-cycle redundant syndrome corroboration can strongly reduce false correction actions.
4. Strict unanimity is substantially safer than naive latest-read correction but can be too conservative compared with a strong same-information ML/plurality decoder.
5. Removing the active correction / `9` branch causes a large performance loss in the tested models.
6. A serialized time-delay interpretation of 3 -> 6 -> 9 is empirically worse and is not the intended BTBC architecture.

## 6. What is not yet supported

Do **not** claim from the current evidence that BTBC has established:

- special physical significance of the numbers 3, 6, or 9,
- a new universal law of quantum mechanics,
- hardware fault tolerance,
- superiority to state-of-the-art qutrit decoders,
- robustness to coherent errors, leakage, non-Pauli noise, calibration drift, or real device crosstalk,
- a resource advantage over surface codes, Steane code, or other established QEC families,
- the previously quoted 4x qubit reduction / 50% depth reduction / 29% gate reduction / 83% resource-efficiency claims,
- AI consciousness or a physical connection between the classical memory experiments and quantum mechanics.

Those require separate evidence.

## 7. Next evidence required after the confidence validation

If the confidence policy survives the frozen new-seed benchmark, the next meaningful steps are:

1. implement physical qutrit syndrome-extraction circuits rather than only a Pauli-frame Monte Carlo,
2. include coherent over/under-rotation and leakage models,
3. compare against statistically principled maximum-likelihood / Bayesian decoders with equal information and compute budgets,
4. measure logical error as a function of physical error rate and look for a threshold/pseudothreshold,
5. report resource counts: qutrits, ancillas, extraction rounds, gates, depth, measurements, and decoder latency,
6. replicate on independent seeds and, ideally, an independent implementation,
7. keep the classical memory track as a separate but potentially analogous error-control architecture until a rigorous coupled experiment exists.

## 8. Publication rule

Every paper, README, pitch, or arXiv draft should distinguish:

- **implemented** — present in code,
- **measured** — observed in a frozen benchmark,
- **replicated** — repeated on independent seeds/implementations,
- **hypothesized** — plausible but not yet demonstrated,
- **symbolic** — BTBC conceptual mapping without empirical physical evidence.

Negative results are part of the evidence record and must not be removed when later versions improve.
