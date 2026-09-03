#!/usr/bin/env python3
"""Frozen first-pass quantum-side BTBC fail-safe benchmark.

Scope
-----
This is deliberately narrow.  It tests the user's stated control rule on a
valid three-qubit repetition-code substrate under Pauli-X noise:

    0 = variable/router
    3 = past/previous observation
    6 = present/current observation
    9 = automatic fail-safe when an error/loop repeats
    9 -> binary fallback -> repair -> return to variable 0 after verification

The experiment does NOT claim a qutrit implementation, arbitrary-state QEC,
or a special physical law for 3/6/9.  The long Monte-Carlo portion uses the
Pauli frame of a repetition code (exact for the tested computational-basis
X-error channel).  A Qiskit/Aer circuit sanity check first verifies the
three-qubit quantum substrate and all single-X recovery cases.

Controls
--------
* bare: one physical bit/qubit under the same X channel.
* repetition: conventional 3-bit majority correction each cycle.
* temporal_control: same temporal side-information/fail-safe algorithm as
  BTBC, but with generic names.  This is the critical control for whether the
  3/6/9 labels themselves add measurable behavior.
* btbc_full: 0->3->6->9->binary fallback->0 controller.
* btbc_no9: ablation with the 9/binary fail-safe disabled.

Because BTBC full and temporal_control are intentionally algorithmically
matched, any difference between them is a bug.  A BTBC-specific numerical
advantage requires a future operational mapping that differs from the generic
control and survives ablation.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

import numpy as np


SEED = 369963
TRIALS = 3000
CYCLES = 100
NOISE_POINTS = [
    # independent X probability, correlated 2/3-bit burst probability
    (0.005, 0.000),
    (0.010, 0.001),
    (0.020, 0.002),
    (0.050, 0.005),
]


def majority(bits: np.ndarray) -> int:
    return int(np.count_nonzero(bits) >= 2)


def syndrome(bits: np.ndarray) -> Tuple[int, int, int]:
    m = majority(bits)
    return tuple(int(x != m) for x in bits)


def inject_three(bits: np.ndarray, rng: np.random.Generator,
                 p_x: float, p_burst: float) -> None:
    bits ^= (rng.random(3) < p_x).astype(np.int8)
    if rng.random() < p_burst:
        n = 2 if rng.random() < 0.8 else 3
        idx = rng.choice(3, size=n, replace=False)
        bits[idx] ^= 1


def qiskit_substrate_sanity() -> Dict[str, object]:
    """Verify basis-state repetition encoding and every single-X recovery."""
    from qiskit import QuantumCircuit, transpile
    from qiskit_aer import AerSimulator

    backend = AerSimulator()
    cases = []
    for logical in (0, 1):
        for error_q in (None, 0, 1, 2):
            qc = QuantumCircuit(3, 3)
            if logical:
                qc.x(0)
            qc.cx(0, 1)
            qc.cx(0, 2)
            if error_q is not None:
                qc.x(error_q)
            qc.measure([0, 1, 2], [0, 1, 2])
            tqc = transpile(qc, backend)
            counts = backend.run(tqc, shots=128,
                                 seed_simulator=SEED + logical * 10 + (error_q or 0)).result().get_counts()
            bad = 0
            total = 0
            for bitstring, count in counts.items():
                # Qiskit prints c2 c1 c0; majority is order invariant.
                decoded = int(bitstring.count('1') >= 2)
                total += count
                if decoded != logical:
                    bad += count
            ok = bad == 0
            cases.append({
                'logical': logical,
                'single_x_qubit': error_q,
                'shots': total,
                'bad_majority_decodes': bad,
                'pass': ok,
            })
    return {'all_pass': all(c['pass'] for c in cases), 'cases': cases}


@dataclass
class ArmStats:
    arm: str
    trials: int = 0
    logical_failures: int = 0
    bad_cycles: int = 0
    correction_actions: int = 0
    failsafe_entries: int = 0
    return_to_variable: int = 0

    def finalize(self) -> Dict[str, object]:
        d = asdict(self)
        d['logical_failure_rate'] = self.logical_failures / self.trials
        d['bad_cycle_rate'] = self.bad_cycles / (self.trials * CYCLES)
        d['corrections_per_trial'] = self.correction_actions / self.trials
        d['failsafes_per_trial'] = self.failsafe_entries / self.trials
        return d


def simulate_bare(logical: int, rng: np.random.Generator,
                  p_x: float, p_burst: float) -> Tuple[int, int, int]:
    value = logical
    bad_cycles = 0
    for _ in range(CYCLES):
        if rng.random() < p_x:
            value ^= 1
        # A burst is a common-mode event for the bare channel too.
        if rng.random() < p_burst:
            value ^= 1
        bad_cycles += int(value != logical)
    return int(value != logical), bad_cycles, 0


def simulate_repetition(logical: int, rng: np.random.Generator,
                        p_x: float, p_burst: float) -> Tuple[int, int, int]:
    bits = np.full(3, logical, dtype=np.int8)
    bad_cycles = 0
    corrections = 0
    for _ in range(CYCLES):
        inject_three(bits, rng, p_x, p_burst)
        m = majority(bits)
        bad_cycles += int(m != logical)
        if not np.all(bits == m):
            corrections += 1
        bits[:] = m
    return int(majority(bits) != logical), bad_cycles, corrections


def simulate_temporal(logical: int, rng: np.random.Generator,
                      p_x: float, p_burst: float, enable_failsafe: bool,
                      btbc_names: bool) -> Tuple[int, int, int, int, int]:
    """Temporal repetition controller.

    The benchmark stores a computational-basis logical memory, so the encoded
    value is available as temporal side information.  That is NOT valid for an
    unknown arbitrary qubit and is why this benchmark is explicitly scoped.
    """
    bits = np.full(3, logical, dtype=np.int8)
    verified = logical
    previous_syndrome = (0, 0, 0)  # state 3 / previous observation
    alarm_streak = 0
    in_failsafe = False
    bad_cycles = 0
    corrections = 0
    entries = 0
    returns = 0

    for _ in range(CYCLES):
        # state 0 routes into observation; state 6 is the present syndrome.
        inject_three(bits, rng, p_x, p_burst)
        current_majority = majority(bits)
        current_syndrome = syndrome(bits)
        disagreement = current_majority != verified
        nonclean = current_syndrome != (0, 0, 0)

        # Relational stabilization handles an isolated minority while the
        # current majority still agrees with the verified temporal state.
        if current_majority == verified and nonclean:
            bits[:] = verified
            corrections += 1
            current_syndrome = (0, 0, 0)
            nonclean = False

        alarm = disagreement or nonclean
        if alarm:
            # Repetition/loop criterion: two consecutive alarmed observations.
            # Same-syndrome recurrence is recorded explicitly, but either a
            # persistent logical disagreement or recurring nonclean syndrome
            # advances the streak.
            alarm_streak += 1
        else:
            alarm_streak = 0

        if enable_failsafe and alarm_streak >= 2:
            # state 9: automatic binary fail-safe.  Freeze the variable mapping,
            # restore the encoded computational-basis value from the verified
            # temporal state, then require a clean verification before return.
            if not in_failsafe:
                entries += 1
            in_failsafe = True
            bits[:] = verified
            corrections += 1
            alarm_streak = 0
            current_syndrome = (0, 0, 0)

        current_majority = majority(bits)
        bad_cycles += int(current_majority != logical)

        if in_failsafe and current_majority == verified and current_syndrome == (0, 0, 0):
            # verified clean -> 9 returns control to variable state 0.
            in_failsafe = False
            returns += 1

        previous_syndrome = current_syndrome
        _ = previous_syndrome, btbc_names  # names do not alter the control law.

    return int(majority(bits) != logical), bad_cycles, corrections, entries, returns


def run_arm(arm: str, p_x: float, p_burst: float, seed: int) -> Dict[str, object]:
    rng = np.random.default_rng(seed)
    s = ArmStats(arm=arm)
    for _ in range(TRIALS):
        logical = int(rng.integers(0, 2))
        s.trials += 1
        if arm == 'bare':
            fail, bad, corr = simulate_bare(logical, rng, p_x, p_burst)
            entries = returns = 0
        elif arm == 'repetition':
            fail, bad, corr = simulate_repetition(logical, rng, p_x, p_burst)
            entries = returns = 0
        elif arm == 'temporal_control':
            fail, bad, corr, entries, returns = simulate_temporal(
                logical, rng, p_x, p_burst, True, False)
        elif arm == 'btbc_full':
            fail, bad, corr, entries, returns = simulate_temporal(
                logical, rng, p_x, p_burst, True, True)
        elif arm == 'btbc_no9':
            fail, bad, corr, entries, returns = simulate_temporal(
                logical, rng, p_x, p_burst, False, True)
        else:
            raise ValueError(arm)
        s.logical_failures += fail
        s.bad_cycles += bad
        s.correction_actions += corr
        s.failsafe_entries += entries
        s.return_to_variable += returns
    return s.finalize()


def main() -> None:
    substrate = qiskit_substrate_sanity()
    if not substrate['all_pass']:
        raise SystemExit('Qiskit repetition-code substrate sanity check failed')

    arms = ['bare', 'repetition', 'temporal_control', 'btbc_full', 'btbc_no9']
    rows: List[Dict[str, object]] = []
    for i, (p_x, p_burst) in enumerate(NOISE_POINTS):
        # Common random seed for matched temporal-control and BTBC-full arms.
        base = SEED + i * 10000
        for j, arm in enumerate(arms):
            if arm in ('temporal_control', 'btbc_full'):
                arm_seed = base + 777
            else:
                arm_seed = base + j * 137
            row = run_arm(arm, p_x, p_burst, arm_seed)
            row.update({'p_x': p_x, 'p_burst': p_burst, 'cycles': CYCLES})
            rows.append(row)

    by_noise: Dict[str, Dict[str, Dict[str, object]]] = {}
    for row in rows:
        key = f"px={row['p_x']:.3f},burst={row['p_burst']:.3f}"
        by_noise.setdefault(key, {})[row['arm']] = row

    checks = {
        'qiskit_substrate_passes': substrate['all_pass'],
        'btbc_matches_generic_temporal_control': True,
        'nine_failsafe_is_exercised': False,
        'nine_failsafe_returns_to_variable': True,
        'btbc_not_worse_than_no9_on_final_failure_all_points': True,
    }
    for group in by_noise.values():
        b = group['btbc_full']
        t = group['temporal_control']
        n = group['btbc_no9']
        for field in ('logical_failures', 'bad_cycles', 'correction_actions',
                      'failsafe_entries', 'return_to_variable'):
            checks['btbc_matches_generic_temporal_control'] &= b[field] == t[field]
        checks['nine_failsafe_is_exercised'] |= b['failsafe_entries'] > 0
        checks['nine_failsafe_returns_to_variable'] &= b['return_to_variable'] == b['failsafe_entries']
        checks['btbc_not_worse_than_no9_on_final_failure_all_points'] &= (
            b['logical_failure_rate'] <= n['logical_failure_rate'])

    interpretation = {
        'primary_question': (
            'Does the stated 0->3->6->9->binary-fallback->0 controller operate '
            'and change error behavior on a valid repetition-code X-noise substrate?'
        ),
        'unique_369_question': (
            'Does 3/6/9 naming itself outperform an algorithmically identical generic temporal control?'
        ),
        'scope_limit': (
            'Computational-basis quantum memory under Pauli-X noise only; temporal side '
            'information knows the encoded classical logical value. This is not arbitrary-state '
            'quantum error correction and cannot establish quantum advantage.'
        ),
    }

    out = {
        'frozen_config': {
            'seed': SEED,
            'trials': TRIALS,
            'cycles': CYCLES,
            'noise_points': NOISE_POINTS,
        },
        'qiskit_substrate': substrate,
        'rows': rows,
        'checks': checks,
        'interpretation': interpretation,
    }
    os.makedirs('artifacts', exist_ok=True)
    with open('artifacts/btbc_quantum_failsafe_results.json', 'w') as f:
        json.dump(out, f, indent=2, sort_keys=True)
    print(json.dumps(out, indent=2, sort_keys=True))

    # Contract checks are implementation/sanity checks, not claims of advantage.
    if not all(checks.values()):
        raise SystemExit('One or more frozen controller contract checks failed')


if __name__ == '__main__':
    main()
