#!/usr/bin/env python3
"""Frozen hard validation of a same-cycle confidence-weighted BTBC qutrit decoder.

This deliberately does NOT retune the previously failed held-out benchmark.
It reuses the full-Pauli [[9,1,3]]_3 generalized-Pauli-frame simulator and its
hard noise profiles, but uses new frozen seeds and a predeclared same-cycle rule.

BTBC interpretation tested here:
  0 = simultaneous availability of the three syndrome reads / decision branches
  3 = raw evidence
  6 = consistency/confidence evaluation in the same correction cycle
  9 = immediate fail-safe correction when confidence is sufficient
There is no temporal 3->6->9 waiting period.

The key scientific controls are:
- generic_component_ml3: strong same-information component plurality/ML baseline
- generic_confidence: exact unlabeled copy of the BTBC confidence rule
- btbc_no9: same environment, correction disabled
- perfect_current: ideal current syndrome reference

If btbc_full == generic_confidence, any benefit belongs to the operational
confidence/abstention rule, not to the numerical labels themselves.
"""

from __future__ import annotations

import json
from pathlib import Path

import test_btbc_qutrit_full_pauli_hard as base

# New seeds not used in the previous hard run. Frozen before validation.
base.SEEDS = [5010017, 6020039, 7030061, 8040073, 9050087]
base.ARMS = [
    "generic_latest3",
    "generic_component_ml3",
    "generic_confidence",
    "btbc_full",
    "btbc_no9",
    "perfect_current",
]


def confidence_choice(reads):
    """Predeclared same-cycle code-aware confidence rule.

    Construct the component-wise plurality candidate from all three full reads.
    A qutrit syndrome component is 'supported' when at least two of three reads
    agree; 1/1/1 components are contradictory. Decoder Hamming weight is used
    only as an observable code-space risk proxy, never hidden ground truth.

    Act immediately when:
      * no syndrome component is 1/1/1 contradictory, AND
      * minimum-weight decoder representative has weight <= 1; OR
      * representative has weight 2 AND at least 6/8 components are unanimous.
    Otherwise abstain. Zero candidate means no correction.
    """
    candidate = base.component_ml3(reads)
    if candidate == base.ZERO_SYNDROME:
        return candidate

    supported = 0
    unanimous = 0
    contradictory = 0
    for j in range(len(base.STABILIZERS)):
        vals = (reads[0][j], reads[1][j], reads[2][j])
        counts = [vals.count(k) for k in range(base.D)]
        m = max(counts)
        if m >= 2:
            supported += 1
        else:
            contradictory += 1
        if m == 3:
            unanimous += 1

    if contradictory:
        return None

    weight = base.DECODER[candidate][0]
    if weight <= 1:
        return candidate
    if weight == 2 and unanimous >= 6 and supported == len(base.STABILIZERS):
        return candidate
    return None


def decide(arm, reads, current_true):
    if arm == "generic_latest3":
        return reads[2]
    if arm == "generic_component_ml3":
        return base.component_ml3(reads)
    if arm in ("generic_confidence", "btbc_full"):
        return confidence_choice(reads)
    if arm == "btbc_no9":
        return None
    if arm == "perfect_current":
        return current_true
    raise ValueError(arm)


base.decide = decide


def degeneracy_safe_contracts():
    # Degenerate stabilizer codes do not require every correctable physical
    # error to have a unique syndrome. The correct condition is that every
    # targeted single-qutrit error is recovered to the same logical state.
    commute = all(
        base.symp(a, b) == 0
        for i, a in enumerate(base.STABILIZERS)
        for b in base.STABILIZERS[i + 1:]
    )
    syndrome_classes = {}
    all_recover = True
    for q in range(base.N):
        for a, b in base.NONIDENTITY_LOCAL:
            e = base.local_frame(q, a, b)
            s = base.syndrome(e)
            syndrome_classes.setdefault(s, []).append((q, a, b))
            c = base.decode_correction(s)
            residue = base.addv(e, c)
            if base.syndrome(residue) != base.ZERO_SYNDROME:
                all_recover = False
            if base.final_logical_label(e) != (0, 0):
                all_recover = False

    checks = {
        "balanced_trinary_dimension_is_3": base.D == 3,
        "stabilizer_rank_is_8": base.rank_mod3(base.STABILIZERS) == 8,
        "stabilizers_commute_mod3": commute,
        "logical_x_commutes_with_stabilizers": all(base.symp(s, base.LOGICAL_X) == 0 for s in base.STABILIZERS),
        "logical_z_commutes_with_stabilizers": all(base.symp(s, base.LOGICAL_Z) == 0 for s in base.STABILIZERS),
        "logical_pair_symplectic_product_is_1": base.symp(base.LOGICAL_X, base.LOGICAL_Z) == 1,
        "logical_x_not_stabilizer": base.rank_mod3(base.STABILIZERS + [base.LOGICAL_X]) == 9,
        "logical_z_independent": base.rank_mod3(base.STABILIZERS + [base.LOGICAL_X, base.LOGICAL_Z]) == 10,
        "all_single_qutrit_generalized_paulis_recover_logically": all_recover,
        "decoder_covers_all_3pow8_syndromes": len(base.DECODER) == 3 ** 8,
    }
    diagnostics = {
        "targeted_single_qutrit_nonidentity_errors": base.N * len(base.NONIDENTITY_LOCAL),
        "distinct_single_error_syndromes": len(syndrome_classes),
        "degenerate_syndrome_classes": sum(len(v) > 1 for v in syndrome_classes.values()),
        "largest_single_error_syndrome_class": max(len(v) for v in syndrome_classes.values()),
        "note": "Syndrome uniqueness is not required for a degenerate stabilizer code; logical recoverability is the contract.",
    }
    return checks, diagnostics


def main():
    checks, contract_diag = degeneracy_safe_contracts()
    rows, per_seed, pooled = base.aggregate()

    identity = all(
        per_seed[str(seed)]["generic_confidence"][k] == per_seed[str(seed)]["btbc_full"][k]
        for seed in base.SEEDS
        for k in ("logical_failures", "fidelity_sum", "corrections", "false_corrections", "abstentions")
    )
    nonworse_ml_seeds = sum(
        per_seed[str(seed)]["btbc_full"]["logical_failure_rate"]
        <= per_seed[str(seed)]["generic_component_ml3"]["logical_failure_rate"]
        for seed in base.SEEDS
    )
    fidelity_nonworse_ml_seeds = sum(
        per_seed[str(seed)]["btbc_full"]["mean_unknown_state_fidelity"]
        >= per_seed[str(seed)]["generic_component_ml3"]["mean_unknown_state_fidelity"]
        for seed in base.SEEDS
    )

    criteria = {
        "native_code_contract_passes": all(checks.values()),
        "matched_generic_confidence_identity": identity,
        "state9_exercised": pooled["btbc_full"]["state9_triggers"] > 0,
        "btbc_beats_no9_pooled": pooled["btbc_full"]["logical_failure_rate"] < pooled["btbc_no9"]["logical_failure_rate"],
        "btbc_beats_latest3_pooled": pooled["btbc_full"]["logical_failure_rate"] < pooled["generic_latest3"]["logical_failure_rate"],
        "btbc_false_corrections_below_latest3": pooled["btbc_full"]["false_corrections"] < pooled["generic_latest3"]["false_corrections"],
        "btbc_false_corrections_below_strong_ml": pooled["btbc_full"]["false_corrections"] < pooled["generic_component_ml3"]["false_corrections"],
        "btbc_nonworse_than_strong_ml_on_at_least_3_of_5_new_seeds": nonworse_ml_seeds >= 3,
        "btbc_fidelity_nonworse_than_strong_ml_on_at_least_3_of_5_new_seeds": fidelity_nonworse_ml_seeds >= 3,
        "btbc_pooled_nonworse_than_strong_ml": pooled["btbc_full"]["logical_failure_rate"] <= pooled["generic_component_ml3"]["logical_failure_rate"],
        "btbc_pooled_fidelity_nonworse_than_strong_ml": pooled["btbc_full"]["mean_unknown_state_fidelity"] >= pooled["generic_component_ml3"]["mean_unknown_state_fidelity"],
    }
    criteria["all_primary_criteria"] = all(criteria.values())

    result = {
        "scope": "Frozen independent validation of a same-cycle confidence/abstention decoder on the exact GF(3) [[9,1,3]]_3 full generalized-Pauli benchmark: arbitrary unknown logical qutrit states, X/Z/mixed faults, noisy three-read syndrome extraction, extraction back-action, recovery faults, correlated block bursts, 100 cycles, matched random streams. Not physical qutrit hardware, coherent leakage, or non-Pauli noise.",
        "frozen_config": {
            "dimension": base.D,
            "balanced_trinary_basis": ["|-1>", "|0>", "|+1>"],
            "cycles": base.CYCLES,
            "trials_per_profile_seed_arm": base.TRIALS,
            "new_validation_seeds": base.SEEDS,
            "profiles_pdata_pmeas_pextract_precovery_pburst": base.PROFILES,
            "matched_random_streams_across_arms": True,
            "three_full_syndrome_reads_per_cycle_for_all_arms": True,
            "confidence_policy": {
                "temporal_history": False,
                "component_1_1_1_contradiction": "abstain",
                "decoder_weight_le_1": "correct immediately if no contradictory component",
                "decoder_weight_eq_2": "correct immediately only if >=6/8 components unanimous and none contradictory",
                "decoder_weight_gt_2": "abstain",
            },
        },
        "contract_checks": checks,
        "contract_diagnostics": contract_diag,
        "predeclared_criteria": criteria,
        "interpretation_contract": {
            "if_btbc_equals_generic_confidence": "Any measured benefit belongs to the same-cycle confidence/abstention mechanism; 3/6/9 labels are not independently causal.",
            "if_btbc_beats_ml": "The frozen code-aware confidence policy outperformed the strong same-information component-ML baseline on these new seeds and merits circuit-level validation.",
            "if_btbc_loses_ml_but_reduces_false_corrections": "The policy remains a precision/safety tradeoff rather than a lower-logical-error decoder.",
            "hard_limit": "No result here establishes special physical significance of 3/6/9 or hardware fault tolerance.",
        },
        "per_seed": per_seed,
        "pooled": pooled,
        "rows": rows,
    }

    out = Path("artifacts/btbc_qutrit_confidence_hard_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps({k: result[k] for k in ("scope", "frozen_config", "contract_checks", "contract_diagnostics", "predeclared_criteria", "pooled")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
