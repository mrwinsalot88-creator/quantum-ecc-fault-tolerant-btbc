# BTBC Local Agent — Architecture Specification

## Purpose

This document defines the first local LLM experiment for the BTBC memory-integrity architecture.

The experiment is intentionally narrow: determine whether a BTBC relational-temporal memory layer improves persistent-memory reliability compared with a plain-memory control when both agents use the exact same local LLM.

## Experimental arms

### Agent A — Plain Memory Control

The control agent stores and retrieves persistent memories without BTBC repair, quarantine, or escalation.

### Agent B — BTBC Memory Integrity

The experimental agent uses the same LLM and the same conversations, but its persistent memories pass through the BTBC integrity controller before retrieval.

## Required controls

Both agents must use the same:

- GGUF model file and model hash
- chat template
- system instructions
- temperature and generation settings
- context-window size
- conversation scenarios
- fault-injection seeds
- retrieval limits
- timing/measurement method

The intended experimental variable is only:

**plain memory vs BTBC memory integrity**

## BTBC memory record

A memory record should support at least:

- `memory_id`
- `session_id`
- `entity`
- `attribute`
- `value`
- `valid_from`
- `valid_to`
- `source`
- `source_trust`
- `confidence`
- `created_at`
- `updated_at`
- relationship links
- status: active / quarantined / superseded
- controller decision and reason

## BTBC controller

### 0 — ROUTE

Inspect observable evidence and determine whether the memory can remain on the conservative path or requires escalation.

### 3 — RELATE

Evaluate consistency with connected memories and source/provenance evidence.

### 6 — STABILIZE

Combine relational evidence with temporal history and legitimate-change detection.

### 9 — FAIL-SAFE

Choose one of:

- KEEP
- REPAIR
- QUARANTINE / ABSTAIN
- ESCALATE

### 0 — RETURN

Route escalated cases through SAFE or RECOVERY according to the configured safety policy.

## Local model interface

Default model location:

```text
model/model.gguf
```

Preferred Python runtime:

```text
llama-cpp-python
```

For instruct/chat GGUF models, use `create_chat_completion(...)`.

Default CPU-safe setting:

```text
n_gpu_layers=0
```

Make GPU layers configurable by environment variable or CLI argument.

## Planned project layout

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

Do not commit the GGUF model or generated SQLite databases.

## Fault classes

The first scenario suite should include:

1. stale facts
2. contradictory facts
3. false inserted facts
4. relationship corruption
5. poisoned high-trust or low-trust source cases
6. duplicates
7. missing memories
8. burst corruption
9. legitimate preference changes
10. legitimate state changes
11. historical-vs-current fact questions

## Deterministic scoring

Use scenario ground truth as the primary judge. Avoid using another LLM as the main evaluator.

Measure:

- current-fact accuracy
- historical-fact accuracy
- corrupted-memory recovery
- false corrections
- stale-memory errors
- contradiction resolution
- legitimate-change preservation
- quarantine / abstention
- escalation
- latency
- storage overhead
- approximate compute

## Frozen-test requirements

Before final testing, record:

- repository commit SHA
- model SHA256
- model parameters
- scenario-file hash
- BTBC config hash
- random seeds
- Python/package versions
- operating-system information

Do not retune BTBC after viewing final-test results.

## Interpretation boundary

This experiment tests a classical memory-integrity architecture. It does not test AI consciousness, a universal 3-6-9 law, or quantum error-correction advantage.
