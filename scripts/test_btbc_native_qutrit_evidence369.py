#!/usr/bin/env python3
"""Frozen BTBC native balanced-trinary evidence-trigger benchmark.

This is a follow-up to test_btbc_native_qutrit.py. The original failed frozen
benchmark remains untouched. Here the 3/6/9 controller is interpreted as an
evidence composition rather than a three-cycle delay:

  0 = clear/reset
  3 = matching historical syndrome evidence
  6 = current valid nonzero syndrome evidence
  9 = combined evidence threshold (3+6) -> correction, verification/reset

Thus 9 can trigger on the second matching observation. The controller never
reads the encoded logical qutrit amplitudes or a stored logical basis value.

Scope remains the same: 3-qutrit repetition protection against generalized-X
(cyclic qutrit shift) errors with noisy syndrome readout. Generalized-Z phase
errors are out of scope for this test.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

BASIS = (-1, 0, +1)
NOISE_POINTS = (0.001, 0.003, 0.01, 0.02)
TRIALS = 5000
CYCLES = 100
SEED = 963369


def mod3(x: int) -> int:
    return x % 3


def syndrome(frame: tuple[int, int, int]) -> tuple[int, int]:
    a, b, c = frame
    return (mod3(a - b), mod3(b - c))


def build_decoder() -> dict[tuple[int, int], tuple[int, int] | None]:
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
VALID_NONZERO = frozenset(k for k, v in DECODER.items() if v is not None)


def logical_shift(frame: tuple[int, int, int]) -> int | None:
    if syndrome(frame) != (0, 0):
        return None
    if frame[0] == frame[1] == frame[2]:
        return frame[0] % 3
    raise AssertionError("zero syndrome but inconsistent frame")


def noisy_syndrome(true_syn: tuple[int, int], p_meas: float, rng: random.Random) -> tuple[int, int]:
    out = []
    for s in true_syn:
        if rng.random() < p_meas:
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
    state3_evidence: int = 0
    state6_evidence: int = 0
    state9_triggers: int = 0
    verified_resets: int = 0


def run_arm(arm: str, p_data: float, p_meas: float, rng: random.Random) -> Metrics:
    m = Metrics()
    for _ in range(TRIALS):
        frame = [0, 0, 0]
        previous_valid: tuple[int, int] | None = None

        for _cycle in range(CYCLES):
            inject_data_noise(frame, p_data, rng)
            true_syn = syndrome(tuple(frame))
            measured = noisy_syndrome(true_syn, p_meas, rng)

            if arm == "bare":
                continue

            if arm == "perfect_syndrome":
                if true_syn in VALID_NONZERO and apply_correction(frame, true_syn):
                    m.correction_actions += 1
                continue

            if arm == "conventional":
                if measured in VALID_NONZERO:
                    if true_syn == (0, 0):
                        m.false_correction_actions += 1
                    if apply_correction(frame, measured):
                        m.correction_actions += 1
                continue

            # Evidence-composed BTBC arms.
            current_valid = measured in VALID_NONZERO
            if not current_valid:
                previous_valid = None
                continue

            # 6 = current valid syndrome evidence.
            m.state6_evidence += 1
            historical_match = previous_valid == measured
            if historical_match:
                # 3 = corroborating history; 3 + 6 = 9 risk threshold.
                m.state3_evidence += 1
                if arm == "btbc_evidence_no9":
                    previous_valid = measured
                    continue

                m.state9_triggers += 1
                if true_syn == (0, 0):
                    m.false_correction_actions += 1
                if apply_correction(frame, measured):
                    m.correction_actions += 1

                # Verification/reset is represented by recomputing the exact
                # protected-frame syndrome after the action. This is a test
                # diagnostic, not extra information used to choose correction.
                if syndrome(tuple(frame)) == (0, 0):
                    m.verified_resets += 1
                previous_valid = None
            else:
                previous_valid = measured

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
            recovers &= apply_correction(g, syn) and g == [0, 0, 0]
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
        "state3_evidence": m.state3_evidence,
        "state6_evidence": m.state6_evidence,
        "state9_triggers": m.state9_triggers,
        "verified_resets": m.verified_resets,
    }


def main() -> None:
    arms = ("bare", "conventional", "btbc_evidence", "btbc_evidence_no9", "perfect_syndrome")
    rows = []
    pooled = {a: {"fail": 0, "false_corr": 0, "state9": 0} for a in arms}

    # Predeclared before observing this run:
    # 1. Native qutrit contract must pass.
    # 2. Evidence BTBC must beat no-9 at >=3/4 noise points.
    # 3. Evidence BTBC must improve on the prior three-observation design's
    #    frozen pooled failure count (3231/20000).
    # 4. It must retain lower false corrections than conventional.
    # 5. 9 must actually be exercised.
    # Conventional parity is reported but deliberately NOT required here: this
    # experiment tests whether removing the third-cycle delay fixes the identified
    # weakness without tuning after observation.
    PRIOR_THREE_OBSERVATION_POOLED_FAILURES = 3231

    for p_index, p in enumerate(NOISE_POINTS):
        for a_index, arm in enumerate(arms):
            rng = random.Random(SEED + 100000 * p_index + 1000 * a_index)
            m = run_arm(arm, p, p, rng)
            rows.append(row(arm, p, m))
            pooled[arm]["fail"] += m.logical_failures
            pooled[arm]["false_corr"] += m.false_correction_actions
            pooled[arm]["state9"] += m.state9_triggers

    by_p = {p: {r["arm"]: r for r in rows if r["p_data"] == p} for p in NOISE_POINTS}
    checks = contract_checks()
    hypotheses = {
        "native_basis_contract_passes": all(bool(v) for k, v in checks.items() if k != "decoder_syndrome_count"),
        "btbc_beats_no9_at_least_3_of_4_points": sum(
            by_p[p]["btbc_evidence"]["logical_failure_rate"] < by_p[p]["btbc_evidence_no9"]["logical_failure_rate"]
            for p in NOISE_POINTS
        ) >= 3,
        "pooled_failure_count_below_prior_three_observation_btbc": pooled["btbc_evidence"]["fail"] < PRIOR_THREE_OBSERVATION_POOLED_FAILURES,
        "pooled_false_corrections_below_conventional": pooled["btbc_evidence"]["false_corr"] < pooled["conventional"]["false_corr"],
        "state9_is_exercised": pooled["btbc_evidence"]["state9"] > 0,
    }
    hypotheses["all_primary_criteria"] = all(hypotheses.values())

    secondary = {
        "pooled_btbc_failures_not_above_conventional": pooled["btbc_evidence"]["fail"] <= pooled["conventional"]["fail"],
        "btbc_not_worse_than_conventional_points": sum(
            by_p[p]["btbc_evidence"]["logical_failure_rate"] <= by_p[p]["conventional"]["logical_failure_rate"]
            for p in NOISE_POINTS
        ),
    }

    result = {
        "frozen_config": {
            "quantum_alphabet": ["|-1>", "|0>", "|+1>"],
            "encoding": "3-qutrit repetition code for generalized-X shift errors",
            "cycles": CYCLES,
            "trials": TRIALS,
            "noise_points": [[p, p] for p in NOISE_POINTS],
            "seed": SEED,
            "prior_three_observation_pooled_failures": PRIOR_THREE_OBSERVATION_POOLED_FAILURES,
        },
        "controller_definition": {
            "0": "clear/reset",
            "3": "matching historical syndrome evidence",
            "6": "current valid nonzero syndrome evidence",
            "9": "3+6 combined evidence threshold triggers correction then reset",
        },
        "contract_checks": checks,
        "predeclared_primary_hypothesis": hypotheses,
        "secondary_comparison": secondary,
        "pooled": pooled,
        "rows": rows,
        "scope_limit": "Native qutrit generalized-X shift-error simulation with noisy qutrit syndrome readout; generalized-Z phase errors remain out of scope.",
    }

    out = Path("artifacts/btbc_native_qutrit_evidence369_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not hypotheses["all_primary_criteria"]:
        raise SystemExit("predeclared evidence369 criteria did not all pass")


if __name__ == "__main__":
    main()
