#!/usr/bin/env python3
"""Frozen robustness sweep for the previously validated BTBC-confidence decoder.

Purpose: test whether the exact same confidence/abstention rule survives a new,
predeclared set of isolated and mixed stochastic qutrit-Pauli stress profiles.
No decoder thresholds are retuned here.
"""

from __future__ import annotations

import json
from pathlib import Path

import test_btbc_qutrit_confidence_hard as conf

base = conf.base

# Fresh seeds, frozen before seeing this sweep's results.
base.SEEDS = [11010019, 12020031, 13030043, 14040057, 15050069]
base.TRIALS = 1000
base.CYCLES = 100
base.ARMS = [
    "generic_latest3",
    "generic_component_ml3",
    "generic_confidence",
    "btbc_full",
    "btbc_no9",
    "perfect_current",
]

# p_data, p_meas, p_extract, p_recovery, p_block_burst
# Designed to isolate failure modes and then combine them at substantially
# harder settings than the prior validation. These values are frozen here.
PROFILE_NAMES = [
    "reference_low",
    "data_heavy",
    "measurement_heavy",
    "extraction_heavy",
    "recovery_heavy",
    "burst_heavy",
    "mixed_high",
    "extreme_mixed",
]
base.PROFILES = [
    (0.003, 0.003, 0.001, 0.0005, 0.000),
    (0.030, 0.005, 0.003, 0.0010, 0.000),
    (0.005, 0.050, 0.002, 0.0010, 0.000),
    (0.005, 0.010, 0.015, 0.0020, 0.000),
    (0.005, 0.010, 0.003, 0.0200, 0.000),
    (0.005, 0.010, 0.003, 0.0010, 0.010),
    (0.030, 0.050, 0.010, 0.0050, 0.010),
    (0.050, 0.080, 0.020, 0.0100, 0.020),
]


def aggregate_by_profile(rows):
    out = {}
    for name, profile in zip(PROFILE_NAMES, base.PROFILES):
        out[name] = {}
        for arm in base.ARMS:
            selected = [
                r for r in rows
                if r["arm"] == arm
                and (r["p_data"], r["p_meas"], r["p_extract"], r["p_recovery"], r["p_block_burst"]) == profile
            ]
            trials = sum(r["trials"] for r in selected)
            failures = sum(r["logical_failures"] for r in selected)
            fidelity_sum = sum(r["mean_unknown_state_fidelity"] * r["trials"] for r in selected)
            corrections = sum(r["corrections"] for r in selected)
            false_corrections = sum(r["false_corrections"] for r in selected)
            abstentions = sum(r["abstentions"] for r in selected)
            state9 = sum(r["state9_triggers"] for r in selected)
            out[name][arm] = {
                "trials": trials,
                "logical_failures": failures,
                "logical_failure_rate": failures / trials,
                "mean_unknown_state_fidelity": fidelity_sum / trials,
                "corrections": corrections,
                "false_corrections": false_corrections,
                "abstentions": abstentions,
                "state9_triggers": state9,
            }
    return out


def main():
    checks, contract_diag = conf.degeneracy_safe_contracts()
    rows, per_seed, pooled = base.aggregate()
    by_profile = aggregate_by_profile(rows)

    identity = all(
        per_seed[str(seed)]["generic_confidence"][k] == per_seed[str(seed)]["btbc_full"][k]
        for seed in base.SEEDS
        for k in ("logical_failures", "fidelity_sum", "corrections", "false_corrections", "abstentions")
    )

    profile_nonworse = sum(
        by_profile[name]["btbc_full"]["logical_failure_rate"]
        <= by_profile[name]["generic_component_ml3"]["logical_failure_rate"]
        for name in PROFILE_NAMES
    )
    profile_fidelity_nonworse = sum(
        by_profile[name]["btbc_full"]["mean_unknown_state_fidelity"]
        >= by_profile[name]["generic_component_ml3"]["mean_unknown_state_fidelity"]
        for name in PROFILE_NAMES
    )

    criteria = {
        "native_code_contract_passes": all(checks.values()),
        "matched_generic_confidence_identity": identity,
        "state9_exercised": pooled["btbc_full"]["state9_triggers"] > 0,
        "btbc_pooled_nonworse_than_strong_ml": pooled["btbc_full"]["logical_failure_rate"] <= pooled["generic_component_ml3"]["logical_failure_rate"],
        "btbc_pooled_fidelity_nonworse_than_strong_ml": pooled["btbc_full"]["mean_unknown_state_fidelity"] >= pooled["generic_component_ml3"]["mean_unknown_state_fidelity"],
        "btbc_false_corrections_below_strong_ml": pooled["btbc_full"]["false_corrections"] < pooled["generic_component_ml3"]["false_corrections"],
        "btbc_nonworse_than_strong_ml_on_at_least_5_of_8_profiles": profile_nonworse >= 5,
        "btbc_fidelity_nonworse_than_strong_ml_on_at_least_5_of_8_profiles": profile_fidelity_nonworse >= 5,
    }
    criteria["all_primary_criteria"] = all(criteria.values())

    result = {
        "scope": "Frozen stress-profile robustness sweep of the unchanged same-cycle confidence/abstention decoder on the exact GF(3) [[9,1,3]]_3 generalized-Pauli-frame benchmark. New seeds; 100 cycles; isolated data, measurement, extraction, recovery and correlated-burst stresses plus mixed high-noise profiles. Still stochastic Pauli-frame simulation, not coherent/leakage noise or physical qutrit hardware.",
        "frozen_config": {
            "cycles": base.CYCLES,
            "trials_per_profile_seed_arm": base.TRIALS,
            "new_seeds": base.SEEDS,
            "profile_names": PROFILE_NAMES,
            "profiles_pdata_pmeas_pextract_precovery_pburst": base.PROFILES,
            "decoder_rule_changed_from_prior_successful_validation": False,
            "matched_random_streams_across_arms": True,
        },
        "contract_checks": checks,
        "contract_diagnostics": contract_diag,
        "predeclared_criteria": criteria,
        "profile_nonworse_count_vs_strong_ml": profile_nonworse,
        "profile_fidelity_nonworse_count_vs_strong_ml": profile_fidelity_nonworse,
        "interpretation_contract": {
            "if_all_primary_criteria_pass": "The frozen confidence/abstention mechanism remains competitive with or better than the same-information component-ML baseline across a substantially broader stochastic Pauli stress sweep and merits circuit-level/non-Pauli validation.",
            "if_pooled_passes_but_profile_count_fails": "The average advantage is not uniformly robust; report the specific stress regimes where it breaks.",
            "if_pooled_fails": "The prior advantage does not survive this broader stress distribution; characterize the boundary rather than claiming general superiority.",
            "label_control": "generic_confidence is intentionally identical to btbc_full; equality means the operational confidence rule, not the numeric 3/6/9 labels, is causal in this simulator.",
            "hard_limit": "No result here establishes special physical significance of 3/6/9, hardware fault tolerance, or superiority under coherent/leakage noise.",
        },
        "by_profile": by_profile,
        "per_seed": per_seed,
        "pooled": pooled,
        "rows": rows,
    }

    out = Path("artifacts/btbc_qutrit_confidence_noise_sweep_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps({
        "scope": result["scope"],
        "frozen_config": result["frozen_config"],
        "contract_checks": checks,
        "predeclared_criteria": criteria,
        "profile_nonworse_count_vs_strong_ml": profile_nonworse,
        "profile_fidelity_nonworse_count_vs_strong_ml": profile_fidelity_nonworse,
        "by_profile": by_profile,
        "pooled": pooled,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
