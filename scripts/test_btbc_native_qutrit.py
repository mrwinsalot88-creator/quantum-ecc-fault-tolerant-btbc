#!/usr/bin/env python3
"""Frozen native balanced-trinary BTBC qutrit benchmark.

This test uses a true three-level quantum alphabet with basis labels {-1, 0, +1}.
An arbitrary logical qutrit alpha|-1> + beta|0> + gamma|+1> is represented by the
3-qutrit repetition code alpha|-1,-1,-1> + beta|0,0,0> + gamma|+1,+1,+1>.

Scope: stochastic generalized-X (cyclic qutrit shift) data noise plus noisy
syndrome readout. This code corrects one qutrit shift error; it is NOT a full
arbitrary-qutrit QEC code and does not correct generalized-Z phase errors.

BTBC temporal policy:
  0 = clear/no active candidate
  3 = first nonzero syndrome observation (seed)
  6 = same syndrome repeats once (growth)
  9 = same syndrome repeats a third time -> correct and reset (failsafe)

The controller never reads alpha/beta/gamma or a stored logical basis value.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

BASIS = (-1, 0, +1)
NOISE_POINTS = (0.001, 0.003, 0.01, 0.02)
TRIALS = 5000
CYCLES = 100
SEED = 369963


def mod3(x: int) -> int:
    return x % 3


def label_to_digit(x: int) -> int:
    return {-1: 0, 0: 1, +1: 2}[x]


def digit_to_label(x: int) -> int:
    return {0: -1, 1: 0, 2: +1}[x % 3]


def syndrome(frame: tuple[int, int, int]) -> tuple[int, int]:
    """Shift-error syndrome for the 3-qutrit repetition code.

    frame entries are generalized-X exponents in Z_3.
    Stabilizer-like parity checks compare q0-q1 and q1-q2 modulo 3.
    """
    a, b, c = frame
    return (mod3(a - b), mod3(b - c))


def build_decoder() -> dict[tuple[int, int], tuple[int, int] | None]:
    """Map single-qutrit nonzero shift syndromes to (site, inverse_shift)."""
    dec: dict[tuple[int, int], tuple[int, int] | None] = {(0, 0): None}
    for site in range(3):
        for shift in (1, 2):
            f = [0, 0, 0]
            f[site] = shift
            syn = syndrome(tuple(f))
            if syn in dec:
                raise AssertionError(f"non-unique syndrome {syn}")
            dec[syn] = (site, mod3(-shift))
    return dec


DECODER = build_decoder()


def logical_shift(frame: tuple[int, int, int]) -> int | None:
    """Return residual logical X^k if frame is in code space, else None."""
    if syndrome(frame) != (0, 0):
        return None
    if frame[0] == frame[1] == frame[2]:
        return frame[0] % 3
    raise AssertionError("zero syndrome but inconsistent frame")


def noisy_syndrome(true_syn: tuple[int, int], p_meas: float, rng: random.Random) -> tuple[int, int]:
    out = []
    for s in true_syn:
        if rng.random() < p_meas:
            # A qutrit measurement error adds either +1 or +2 modulo 3.
            s = mod3(s + rng.choice((1, 2)))
        out.append(s)
    return tuple(out)  # type: ignore[return-value]


def inject_data_noise(frame: list[int], p_data: float, rng: random.Random) -> None:
    for i in range(3):
        if rng.random() < p_data:
            frame[i] = mod3(frame[i] + rng.choice((1, 2)))


def apply_correction(frame: list[int], syn: tuple[int, int]) -> bool:
    corr = DECODER.get(syn)
    if corr is None:
        return False
    site, inverse_shift = corr
    frame[site] = mod3(frame[site] + inverse_shift)
    return True


@dataclass
class Metrics:
    logical_failures: int = 0
    correction_actions: int = 0
    false_correction_actions: int = 0
    state3_entries: int = 0
    state6_entries: int = 0
    state9_entries: int = 0


def run_arm(arm: str, p_data: float, p_meas: float, rng: random.Random) -> Metrics:
    m = Metrics()
    for _ in range(TRIALS):
        frame = [0, 0, 0]
        candidate: tuple[int, int] | None = None
        stage = 0

        for _cycle in range(CYCLES):
            inject_data_noise(frame, p_data, rng)
            true_syn = syndrome(tuple(frame))
            measured = noisy_syndrome(true_syn, p_meas, rng)

            if arm == "bare":
                continue

            if arm == "perfect_syndrome":
                if true_syn != (0, 0):
                    if apply_correction(frame, true_syn):
                        m.correction_actions += 1
                continue

            if arm == "conventional":
                if measured != (0, 0):
                    if true_syn == (0, 0):
                        m.false_correction_actions += 1
                    if apply_correction(frame, measured):
                        m.correction_actions += 1
                continue

            # BTBC temporal arms.
            if measured == (0, 0):
                candidate = None
                stage = 0
                continue

            if measured != candidate:
                candidate = measured
                stage = 3
                m.state3_entries += 1
                continue

            if stage == 3:
                stage = 6
                m.state6_entries += 1
                continue

            if stage == 6:
                if arm == "btbc_no9":
                    # Explicit ablation: never enter the corrective fail-safe.
                    continue
                stage = 9
                m.state9_entries += 1
                if true_syn == (0, 0):
                    m.false_correction_actions += 1
                if apply_correction(frame, measured):
                    m.correction_actions += 1
                candidate = None
                stage = 0
                continue

            raise AssertionError((arm, stage))

        # Decode-at-end interpretation: any residual nonzero logical shift or
        # unresolved nonzero syndrome counts as failure.
        ls = logical_shift(tuple(frame))
        if ls is None or ls != 0:
            m.logical_failures += 1

    return m


def contract_checks() -> dict[str, bool | int]:
    syndromes = set()
    recovers = True
    for site in range(3):
        for shift in (1, 2):
            f = [0, 0, 0]
            f[site] = shift
            syn = syndrome(tuple(f))
            syndromes.add(syn)
            g = f[:]
            ok = apply_correction(g, syn)
            recovers &= ok and g == [0, 0, 0]
    return {
        "balanced_trinary_basis_is_exact": BASIS == (-1, 0, +1),
        "single_shift_syndromes_unique": len(syndromes) == 6,
        "all_single_qutrit_shift_errors_recover": recovers,
        "decoder_syndrome_count": len(DECODER),
    }


def row(arm: str, p: float, m: Metrics) -> dict:
    return {
        "arm": arm,
        "p_data": p,
        "p_meas": p,
        "trials": TRIALS,
        "cycles": CYCLES,
        "logical_failures": m.logical_failures,
        "logical_failure_rate": m.logical_failures / TRIALS,
        "correction_actions": m.correction_actions,
        "false_correction_actions": m.false_correction_actions,
        "state3_entries": m.state3_entries,
        "state6_entries": m.state6_entries,
        "state9_entries": m.state9_entries,
    }


def main() -> None:
    arms = ("bare", "conventional", "btbc_full", "btbc_no9", "perfect_syndrome")
    rows = []
    pooled = {a: {"fail": 0, "false_corr": 0, "state9": 0} for a in arms}

    for p_index, p in enumerate(NOISE_POINTS):
        # Common random-number seeds per arm/noise point for reproducibility.
        for a_index, arm in enumerate(arms):
            rng = random.Random(SEED + 100000 * p_index + 1000 * a_index)
            m = run_arm(arm, p, p, rng)
            rows.append(row(arm, p, m))
            pooled[arm]["fail"] += m.logical_failures
            pooled[arm]["false_corr"] += m.false_correction_actions
            pooled[arm]["state9"] += m.state9_entries

    by_p = {}
    for p in NOISE_POINTS:
        by_p[p] = {r["arm"]: r for r in rows if r["p_data"] == p}

    checks = contract_checks()
    hypotheses = {
        "native_basis_contract_passes": all(bool(v) for k, v in checks.items() if k != "decoder_syndrome_count"),
        "btbc_beats_no9_at_least_3_of_4_points": sum(
            by_p[p]["btbc_full"]["logical_failure_rate"] < by_p[p]["btbc_no9"]["logical_failure_rate"]
            for p in NOISE_POINTS
        ) >= 3,
        "btbc_not_worse_than_conventional_at_least_3_of_4_points": sum(
            by_p[p]["btbc_full"]["logical_failure_rate"] <= by_p[p]["conventional"]["logical_failure_rate"]
            for p in NOISE_POINTS
        ) >= 3,
        "pooled_btbc_failures_not_above_conventional": pooled["btbc_full"]["fail"] <= pooled["conventional"]["fail"],
        "pooled_btbc_false_corrections_below_conventional": pooled["btbc_full"]["false_corr"] < pooled["conventional"]["false_corr"],
        "state9_is_exercised": pooled["btbc_full"]["state9"] > 0,
    }
    hypotheses["all_primary_criteria"] = all(hypotheses.values())

    result = {
        "frozen_config": {
            "quantum_alphabet": ["|-1>", "|0>", "|+1>"],
            "encoding": "3-qutrit repetition code for generalized-X shift errors",
            "cycles": CYCLES,
            "trials": TRIALS,
            "noise_points": [[p, p] for p in NOISE_POINTS],
            "seed": SEED,
        },
        "controller_definition": {
            "0": "clear/reset",
            "3": "first nonzero syndrome observation",
            "6": "same nonzero syndrome observed again",
            "9": "third matching observation triggers correction then reset",
        },
        "contract_checks": checks,
        "predeclared_hypothesis": hypotheses,
        "pooled": pooled,
        "rows": rows,
        "scope_limit": (
            "Native qutrit generalized-X shift-error simulation with noisy qutrit syndrome readout. "
            "Not a full arbitrary-qutrit QEC code: generalized-Z phase errors are outside this first clarity test."
        ),
    }

    out = Path("artifacts/btbc_native_qutrit_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))

    if not hypotheses["all_primary_criteria"]:
        raise SystemExit("predeclared native-qutrit criteria did not all pass")


if __name__ == "__main__":
    main()
