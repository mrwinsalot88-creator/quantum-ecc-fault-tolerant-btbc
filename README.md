# BTBC — Brown's Trinary-Binary Codex

BTBC is an experimental adaptive information architecture. The repository currently contains **two separate research tracks**:

1. **Classical AI memory integrity** — provenance/history-aware conservative correction.
2. **Native qutrit quantum error-control experiments** — balanced-trinary `|-1>`, `|0>`, `|+1>` simulations with matched conventional controls.

Both tracks are being tested with frozen benchmarks, ablations, negative-result retention, and explicit limits on what the evidence supports.

For the current quantum evidence ledger, including failed criteria and the active hard confidence validation, see:

**[`docs/BTBC_QUANTUM_VALIDATION_STATUS.md`](docs/BTBC_QUANTUM_VALIDATION_STATUS.md)**

---

## Current primary track: AI memory integrity

The present BTBC memory architecture treats a stored memory as more than an isolated fact. It combines:

- the current observed fact,
- relationships to other facts,
- temporal history,
- source / provenance trust,
- confidence,
- and an explicit risk budget.

The controller can choose to:

- **KEEP** a memory,
- **REPAIR** it,
- **QUARANTINE / ABSTAIN** when evidence is insufficient,
- or **ESCALATE** a difficult case to a stronger recovery path.

### BTBC control interpretation

- **0 — ROUTE:** decide how much processing the case requires.
- **3 — RELATE:** evaluate relational structure and provenance/trust evidence.
- **6 — STABILIZE:** combine relational and temporal evidence.
- **9 — FAIL-SAFE:** keep, repair, quarantine, abstain, or escalate.
- **0 — RETURN:** route escalated cases through the selected safe/recovery path.

The 3-6-9 mapping is currently used as an architectural naming / control framework. The present experiments do **not** establish a special physical law or prove that the numerical 3-6-9 mapping itself causes the measured improvement.

---

## Current internal v1.4 result

The frozen BTBC v1.4 synthetic locked test used **270 fresh worlds across 135 adversarial scenario types** after the risk target and operating point had been selected on separate validation worlds.

| Metric | Internal locked result |
|---|---:|
| Raw memory error | 22.4091% |
| BTBC v1.4 error | 17.6323% |
| Relative error reduction vs raw | 21.3163% |
| Repair precision | 96.9089% |
| False-correction rate | 0.09590% / cell |
| Declared false-correction budget | 0.10000% / cell |
| Corrupted-cell recovery fraction | 21.7443% |
| Scenario averages non-worse than raw | 98.52% |

These results are **internal and synthetic**. They are not independent validation and are not evidence of universal superiority over existing memory systems.

---

## Component ablation result

A component-ablation test was run to identify what is actually producing the measured effect.

### Main findings

- **Relational evidence was essential.** Removing it collapsed the repair advantage to the raw-memory baseline in this implementation.
- **Temporal history contributed strongly.** Removing it reduced the measured relative error reduction from about 21.3% to about 5.2%, and the ablated controller could not find a validation operating point that satisfied the 0.10% safety budget.
- **Provenance / trust contributed incremental value.** Removing it weakened recovery but did not destroy the system.
- **The explicit risk budget is a safety mechanism, not the source of accuracy.** Removing the budget improved raw recovery but increased false corrections to roughly 0.377% per cell, far above the declared 0.10% target.
- **Router confidence appears mainly useful for safety calibration.** Removing only that feature left accuracy nearly unchanged but pushed false corrections slightly above the target.

The strongest current technical interpretation is therefore:

> The measured BTBC memory-repair effect is primarily coming from relational structure plus temporal history. Provenance/trust adds useful information, while the Layer-0 / Layer-9 risk-control mechanism trades some maximum recovery for lower destructive-correction risk.

---

## New branch: `btbc-local-agent`

This branch is for the first **real LLM-level A/B memory experiment** and the current frozen qutrit validation work.

The memory goal is to run the **same local GGUF model** in two conditions:

### Agent A — plain memory

- same LLM,
- same prompts,
- same context size,
- same conversations,
- same injected faults,
- ordinary persistent-memory retrieval,
- **no BTBC integrity repair**.

### Agent B — BTBC memory

Everything is identical except stored memory is passed through the BTBC integrity layer before trusted context is returned to the LLM.

This isolates the memory architecture as the experimental variable.

---

## Planned local-agent structure

```text
BTBC_LOCAL_AGENT/
├── model/
│   └── model.gguf
├── btbc/
│   ├── llm_wrapper.py
│   ├── memory_engine.py
│   ├── btbc_controller.py
│   └── v1_4_config.json
├── plain_agent/
│   └── plain_memory.py
├── tests/
│   ├── scenarios.json
│   ├── inject_faults.py
│   └── compare_agents.py
├── data/
│   ├── plain_memory.db
│   └── btbc_memory.db
└── results/
```

The model file itself should **not** be committed to GitHub.

---

## Local LLM runtime

The current plan uses a quantized **GGUF** instruct/chat model with `llama-cpp-python`.

Default model path:

```text
model/model.gguf
```

Default hardware mode:

```text
n_gpu_layers=0
```

GPU layers should remain configurable so CUDA / Vulkan / other supported acceleration can be enabled later without redesigning the agent.

For chat/instruct models, prefer `create_chat_completion(...)` rather than constructing one raw text prompt.

---

## A/B experimental rule

The A/B test must hold everything constant except memory handling.

Both agents must use the same:

- GGUF model file,
- model parameters,
- temperature,
- random seed where available,
- context window,
- system prompt,
- user messages,
- scenario order,
- memory-fault injections,
- and scoring rules.

The **only intended experimental variable** is:

> plain memory vs BTBC memory integrity.

---

## Faults to test

The local-agent harness should support at least:

- stale facts,
- contradictory updates,
- deliberately wrong facts,
- relationship corruption,
- poisoned / low-trust sources,
- duplicate memories,
- burst corruption,
- missing facts,
- legitimate preference changes,
- legitimate state changes that must **not** be "repaired" back to an older value.

---

## Metrics

Primary deterministic metrics:

- current-fact accuracy,
- historical-fact accuracy,
- corrupted-memory recovery,
- false-correction rate,
- stale-memory error,
- false-memory insertion,
- contradiction resolution,
- legitimate-change preservation,
- quarantine / abstention rate,
- escalation rate,
- latency,
- storage overhead,
- approximate compute / operation count.

Where possible, scenario ground truth must determine the score directly. **Do not use another LLM as the primary judge of whether BTBC won.**

---

## Success criteria

A BTBC-specific advantage is supported only if the frozen implementation provides a materially better accuracy / safety / cost tradeoff than conventional controls under identical conditions, and component ablation shows that at least one BTBC-specific mechanism materially contributes.

A useful result may be:

- **positive:** BTBC improves the tradeoff,
- **mixed:** BTBC helps only on identifiable fault classes,
- **negative:** BTBC does not generalize outside the simulator.

All three outcomes are scientifically useful.

---

## Important boundaries

The current experiments do **not** establish:

- AI consciousness or sentience,
- a universal physical 3-6-9 law,
- hardware quantum-computing advantage,
- or superiority over every existing AI-memory or QEC system.

The memory and quantum tracks remain experimentally separate unless a future coupled benchmark demonstrates a shared mechanism under controlled conditions.

---

## Quantum / native balanced-trinary qutrit track

The current native quantum interpretation uses a three-level qutrit basis labeled:

`|-1>`, `|0>`, `|+1>`.

For the quantum controller, **3/6/9 are not implemented as a timing delay**. The intended interpretation is same-cycle evaluation:

- `0` = simultaneous decision space,
- `3` = raw syndrome/error evidence,
- `6` = same-cycle consistency/confidence evaluation,
- `9` = immediate fail-safe correction when the evidence passes the rule.

### Current hardest completed result

The completed full-generalized-Pauli `[[9,1,3]]_3` benchmark used arbitrary unknown logical qutrit states, generalized X/Z/mixed faults, noisy syndrome readout, extraction back-action, recovery faults, correlated block bursts, 100 cycles, 8 asymmetric noise profiles, 5 frozen seeds, and matched random streams.

Pooled over **40,000 trials per arm**:

| Decoder | Logical failure rate | Mean unknown-state fidelity | False corrections |
|---|---:|---:|---:|
| BTBC strict same-cycle unanimity | 45.620% | 0.657665 | 17 |
| Strong three-read component ML/plurality | 38.770% | 0.709916 | 14,490 |
| Latest-read conventional | 54.025% | 0.595109 | 250,748 |
| BTBC no-9 | 77.030% | 0.421775 | 0 |
| Perfect-current reference | 34.5275% | 0.740736 | 0 |

This result is **mixed and did not pass all primary criteria**. Strict BTBC unanimity strongly suppressed false corrections and beat the naive latest-read decoder, but it lost to the stronger same-information ML/plurality decoder on logical failure and fidelity.

The exact generic-unanimity control matched BTBC, so the measured behavior belongs to the decoder rule, not independently to the numerical labels.

### Active hard validation

A new frozen experiment is now testing a **same-cycle confidence-weighted** rule on new seeds. It can correct immediately from strong 2-of-3 evidence when the syndrome is internally consistent, while still abstaining on contradictory evidence. The strong same-information ML baseline remains in the test.

The previous held-out results are not being rewritten or discarded.

Full methodology, exact completed results, contract correction, active test criteria, and publication boundaries are maintained in:

**[`docs/BTBC_QUANTUM_VALIDATION_STATUS.md`](docs/BTBC_QUANTUM_VALIDATION_STATUS.md)**

---

## Installation — existing quantum environment

```bash
git clone https://github.com/mrwinsalot88-creator/quantum-ecc-fault-tolerant-btbc
cd quantum-ecc-fault-tolerant-btbc
pip install -r requirements.txt
```

The local-agent branch should use a separate dependency file such as:

```bash
pip install -r requirements-local-agent.txt
```

so the LLM runtime does not unnecessarily disturb the quantum environment.

---

## Immediate next milestones

### Memory track

Build and run the local A/B harness, then freeze:

1. model hash,
2. branch commit,
3. scenario file,
4. fault seeds,
5. BTBC policy/config,
6. raw CSV / JSON results,
7. environment versions.

After the local result is reproducible, move the frozen controller to an external or public long-term-memory workload and seek independent reproduction.

### Quantum track

1. Finish the independent confidence-weighted hard validation on new seeds.
2. If it survives, move from Pauli-frame Monte Carlo to explicit qutrit syndrome-extraction circuits.
3. Add coherent-error and leakage models.
4. Measure logical-error curves and pseudothreshold behavior.
5. Compare equal-resource qutrit decoders and report qutrit/ancilla/gate/depth/measurement/latency costs.
6. Seek independent reproduction before using strong performance claims in publication materials.

---

## Author

Daniel Brown

BTBC / Brown's Trinary-Binary Codex