#!/usr/bin/env python3
"""Frozen unknown-state quantum-memory test for the BTBC 0-3-6-9 controller.

This test deliberately removes the privileged known-bit reference used by the
first quantum-side experiment.  It uses the [[5,1,3]] perfect stabilizer code,
which protects one *unknown* logical qubit, and an exact Pauli-frame Monte Carlo
under data depolarizing noise plus noisy syndrome measurements.

BTBC operational mapping in this experiment:
    0 = variable/router state
    3 = previous measured stabilizer syndrome
    6 = current measured stabilizer syndrome
    9 = repeated non-zero syndrome -> invoke conventional binary correction
        lookup, verify on later syndrome observations, then return to 0.

The 9 action does NOT reconstruct the logical state from a stored classical bit.
It applies only a syndrome-selected Pauli recovery, which is valid for an
unknown encoded quantum state.  A generic temporal-control arm implements the
identical algorithm with non-BTBC names; it must match BTBC exactly.

Arms:
  bare              one unencoded qubit under the same depolarizing channel
  conventional      [[5,1,3]] code; correct every measured non-zero syndrome
  temporal_control  require two identical consecutive non-zero syndromes
  btbc_full          same rule, named 0->3->6->9->binary-recovery->0
  btbc_no9           observe syndromes but never invoke the 9 recovery
  perfect_syndrome   [[5,1,3]] code with noiseless syndrome measurement

A final *perfect* syndrome recovery is applied to every encoded arm before
logical classification.  This measures accumulated logical damage rather than
penalizing an otherwise-correctable final physical error.

This remains a stabilizer/Pauli-noise simulation.  It is evidence about an
adaptive decoder policy, not proof of quantum advantage or a new quantum code.
"""

from __future__ import annotations

import itertools
import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Tuple

import numpy as np

SEED = 936963
TRIALS = 4000
CYCLES = 100
# (per-qubit depolarizing probability, per-syndrome-bit measurement flip)
NOISE_POINTS = [
    (0.001, 0.001),
    (0.003, 0.003),
    (0.010, 0.010),
    (0.020, 0.020),
]

# [[5,1,3]] perfect code generators: XZZXI, IXZZX, XIXZZ, ZXIXZ
STAB_STRINGS = ("XZZXI", "IXZZX", "XIXZZ", "ZXIXZ")
LOGICAL_X = "XXXXX"
LOGICAL_Z = "ZZZZZ"


def pauli_bits(s: str) -> Tuple[np.ndarray, np.ndarray]:
    x = np.zeros(len(s), dtype=np.uint8)
    z = np.zeros(len(s), dtype=np.uint8)
    for i, p in enumerate(s):
        if p in "XY": x[i] = 1
        if p in "ZY": z[i] = 1
    return x, z


STABS = tuple(pauli_bits(s) for s in STAB_STRINGS)
LX = pauli_bits(LOGICAL_X)
LZ = pauli_bits(LOGICAL_Z)


def mul(a: Tuple[np.ndarray, np.ndarray], b: Tuple[np.ndarray, np.ndarray]):
    # Global phase is irrelevant for syndrome/logical-coset tracking.
    return a[0] ^ b[0], a[1] ^ b[1]


def symplectic(a, b) -> int:
    return int((np.dot(a[0], b[1]) + np.dot(a[1], b[0])) & 1)


def syndrome(p) -> Tuple[int, int, int, int]:
    return tuple(symplectic(p, g) for g in STABS)


def pauli_single(q: int, kind: str):
    x = np.zeros(5, dtype=np.uint8)
    z = np.zeros(5, dtype=np.uint8)
    if kind in "XY": x[q] = 1
    if kind in "ZY": z[q] = 1
    return x, z


def build_decoder() -> Dict[Tuple[int, int, int, int], Tuple[np.ndarray, np.ndarray]]:
    d = {(0, 0, 0, 0): (np.zeros(5, dtype=np.uint8), np.zeros(5, dtype=np.uint8))}
    for q in range(5):
        for kind in "XYZ":
            p = pauli_single(q, kind)
            s = syndrome(p)
            if s in d:
                raise RuntimeError(f"non-unique perfect-code syndrome {s}")
            d[s] = p
    if len(d) != 16:
        raise RuntimeError(f"decoder has {len(d)} syndromes, expected 16")
    return d


DECODER = build_decoder()


def stabilizer_group_keys() -> set[Tuple[int, ...]]:
    out = set()
    zero = (np.zeros(5, dtype=np.uint8), np.zeros(5, dtype=np.uint8))
    for mask in range(16):
        p = zero
        for i, g in enumerate(STABS):
            if (mask >> i) & 1:
                p = mul(p, g)
        out.add(tuple(int(v) for v in np.concatenate(p)))
    return out


STAB_KEYS = stabilizer_group_keys()


def key(p) -> Tuple[int, ...]:
    return tuple(int(v) for v in np.concatenate(p))


def inject_data_error(p, rng: np.random.Generator, p_data: float):
    x, z = p[0].copy(), p[1].copy()
    for q in range(5):
        if rng.random() < p_data:
            r = int(rng.integers(0, 3))
            if r == 0: x[q] ^= 1          # X
            elif r == 1: z[q] ^= 1        # Z
            else: x[q] ^= 1; z[q] ^= 1    # Y
    return x, z


def noisy_syndrome(true_s: Tuple[int, ...], rng: np.random.Generator, p_meas: float):
    return tuple(int(bit ^ (rng.random() < p_meas)) for bit in true_s)


def final_logical_failure(p) -> int:
    # Ideal final recovery, then ask whether residual is merely a stabilizer.
    p = mul(p, DECODER[syndrome(p)])
    return int(key(p) not in STAB_KEYS)


def bare_trial(rng: np.random.Generator, p_data: float) -> int:
    # Any non-identity Pauli accumulated on an unknown bare qubit is a failure.
    x = z = 0
    for _ in range(CYCLES):
        if rng.random() < p_data:
            r = int(rng.integers(0, 3))
            if r == 0: x ^= 1
            elif r == 1: z ^= 1
            else: x ^= 1; z ^= 1
    return int(bool(x or z))


@dataclass
class Stats:
    arm: str
    trials: int = 0
    logical_failures: int = 0
    correction_actions: int = 0
    failsafe_entries: int = 0
    false_correction_actions: int = 0
    true_nonzero_observations: int = 0
    measured_nonzero_observations: int = 0

    def final(self):
        d = asdict(self)
        d["logical_failure_rate"] = self.logical_failures / self.trials
        d["corrections_per_trial"] = self.correction_actions / self.trials
        d["false_corrections_per_trial"] = self.false_correction_actions / self.trials
        d["failsafes_per_trial"] = self.failsafe_entries / self.trials
        return d


def encoded_trial(arm: str, rng: np.random.Generator, p_data: float, p_meas: float):
    p = (np.zeros(5, dtype=np.uint8), np.zeros(5, dtype=np.uint8))
    previous = (0, 0, 0, 0)
    corrections = entries = false_corr = true_obs = measured_obs = 0

    for _ in range(CYCLES):
        p = inject_data_error(p, rng, p_data)
        true_s = syndrome(p)
        true_obs += int(any(true_s))
        if arm == "perfect_syndrome":
            measured = true_s
        else:
            measured = noisy_syndrome(true_s, rng, p_meas)
        measured_obs += int(any(measured))

        act = False
        if arm in ("conventional", "perfect_syndrome"):
            act = any(measured)
        elif arm in ("temporal_control", "btbc_full"):
            # 3=previous, 6=current.  9 fires only on an identical repeated alarm.
            act = any(measured) and measured == previous
        elif arm == "btbc_no9":
            act = False
        else:
            raise ValueError(arm)

        if act:
            if arm in ("temporal_control", "btbc_full"):
                entries += 1
            if not any(true_s):
                false_corr += 1
            p = mul(p, DECODER[measured])
            corrections += 1
            # Return to variable routing; require a fresh pair to trigger again.
            previous = (0, 0, 0, 0)
        else:
            previous = measured

    return final_logical_failure(p), corrections, entries, false_corr, true_obs, measured_obs


def run_arm(arm: str, p_data: float, p_meas: float, seed: int):
    rng = np.random.default_rng(seed)
    s = Stats(arm=arm)
    for _ in range(TRIALS):
        s.trials += 1
        if arm == "bare":
            s.logical_failures += bare_trial(rng, p_data)
            continue
        fail, corr, ent, fc, tobs, mobs = encoded_trial(arm, rng, p_data, p_meas)
        s.logical_failures += fail
        s.correction_actions += corr
        s.failsafe_entries += ent
        s.false_correction_actions += fc
        s.true_nonzero_observations += tobs
        s.measured_nonzero_observations += mobs
    return s.final()


def code_contract() -> Dict[str, object]:
    syndromes = []
    for q in range(5):
        for kind in "XYZ":
            syndromes.append(syndrome(pauli_single(q, kind)))
    single_error_recovery = True
    for q in range(5):
        for kind in "XYZ":
            e = pauli_single(q, kind)
            recovered = mul(e, DECODER[syndrome(e)])
            single_error_recovery &= key(recovered) in STAB_KEYS
    return {
        "decoder_syndrome_count": len(DECODER),
        "single_pauli_syndromes_unique": len(set(syndromes)) == 15,
        "all_single_pauli_errors_recover": bool(single_error_recovery),
        "logical_x_commutes_with_stabilizers": all(symplectic(LX, g) == 0 for g in STABS),
        "logical_z_commutes_with_stabilizers": all(symplectic(LZ, g) == 0 for g in STABS),
        "logical_x_not_stabilizer": key(LX) not in STAB_KEYS,
        "logical_z_not_stabilizer": key(LZ) not in STAB_KEYS,
    }


def main():
    contract = code_contract()
    if not all(v is True or (k == "decoder_syndrome_count" and v == 16)
               for k, v in contract.items()):
        raise SystemExit(f"[[5,1,3]] code contract failed: {contract}")

    arms = ["bare", "conventional", "temporal_control", "btbc_full", "btbc_no9", "perfect_syndrome"]
    rows: List[Dict[str, object]] = []
    for i, (p_data, p_meas) in enumerate(NOISE_POINTS):
        base = SEED + i * 100000
        for j, arm in enumerate(arms):
            # Identical random stream is mandatory for the naming control.
            if arm in ("temporal_control", "btbc_full"):
                arm_seed = base + 777
            else:
                arm_seed = base + j * 997
            row = run_arm(arm, p_data, p_meas, arm_seed)
            row.update({"p_data": p_data, "p_meas": p_meas, "cycles": CYCLES})
            rows.append(row)

    groups: Dict[str, Dict[str, Dict[str, object]]] = {}
    for r in rows:
        k = f"p={r['p_data']:.3f},m={r['p_meas']:.3f}"
        groups.setdefault(k, {})[r["arm"]] = r

    matched = True
    nine_exercised = False
    points_btbc_le_conventional = 0
    points_btbc_lt_no9 = 0
    pooled = {"btbc_fail": 0, "conventional_fail": 0, "no9_fail": 0,
              "btbc_false_corr": 0, "conventional_false_corr": 0}
    for g in groups.values():
        b, t, c, n = g["btbc_full"], g["temporal_control"], g["conventional"], g["btbc_no9"]
        for f in ("logical_failures", "correction_actions", "failsafe_entries",
                  "false_correction_actions", "true_nonzero_observations",
                  "measured_nonzero_observations"):
            matched &= b[f] == t[f]
        nine_exercised |= b["failsafe_entries"] > 0
        points_btbc_le_conventional += int(b["logical_failure_rate"] <= c["logical_failure_rate"])
        points_btbc_lt_no9 += int(b["logical_failure_rate"] < n["logical_failure_rate"])
        pooled["btbc_fail"] += b["logical_failures"]
        pooled["conventional_fail"] += c["logical_failures"]
        pooled["no9_fail"] += n["logical_failures"]
        pooled["btbc_false_corr"] += b["false_correction_actions"]
        pooled["conventional_false_corr"] += c["false_correction_actions"]

    # Predeclared scientific hypothesis.  It is reported, not used as an
    # implementation gate: a negative result remains a valid completed test.
    hypothesis = {
        "btbc_not_worse_than_conventional_at_least_3_of_4_points": points_btbc_le_conventional >= 3,
        "btbc_beats_no9_at_least_3_of_4_points": points_btbc_lt_no9 >= 3,
        "pooled_btbc_failures_not_above_conventional": pooled["btbc_fail"] <= pooled["conventional_fail"],
        "pooled_btbc_false_corrections_below_conventional": pooled["btbc_false_corr"] < pooled["conventional_false_corr"],
    }
    hypothesis["all_primary_criteria"] = all(hypothesis.values())

    checks = {
        "five_qubit_code_contract_passes": True,
        "btbc_matches_generic_temporal_control": bool(matched),
        "nine_failsafe_is_exercised": bool(nine_exercised),
        "no_privileged_logical_value_used_by_encoded_controller": True,
    }

    out = {
        "frozen_config": {"seed": SEED, "trials": TRIALS, "cycles": CYCLES,
                          "noise_points": NOISE_POINTS, "code": "[[5,1,3]] perfect code"},
        "code_contract": contract,
        "rows": rows,
        "pooled": pooled,
        "checks": checks,
        "predeclared_hypothesis": hypothesis,
        "interpretation": {
            "primary_question": "Can the 0->3->6->9 triggered recovery policy help protect an unknown encoded qubit under X/Y/Z Pauli noise when syndrome measurements are noisy, without any stored logical-value reference?",
            "unique_369_question": "Does the 3/6/9 naming add behavior beyond an algorithmically identical generic temporal syndrome filter?",
            "scope_limit": "Exact Pauli-frame stabilizer simulation of the [[5,1,3]] code under depolarizing data noise and independent syndrome-bit flips; not hardware, coherent non-Pauli noise, or proof of quantum advantage."
        }
    }
    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/btbc_unknown_state_qec_results.json", "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    print(json.dumps(out, indent=2, sort_keys=True))

    if not all(checks.values()):
        raise SystemExit("Implementation contract failed")


if __name__ == "__main__":
    main()
