#!/usr/bin/env python3
"""Hard qutrit-QEC benchmark for BTBC decoder claims.

This benchmark deliberately removes several easy assumptions from earlier tests:
- native balanced-trinary qutrit Pauli algebra (dimension 3)
- a valid [[9,1,3]]_3 Shor-style stabilizer code
- both generalized-X and generalized-Z errors (all 8 nonidentity qutrit Paulis)
- arbitrary unknown logical qutrit states, scored by exact state fidelity
- 100 correction cycles
- asymmetric data/readout noise, correlated block bursts, extraction back-action,
  and noisy recovery operations
- five frozen unseen seeds
- matched physical random streams across decoder arms
- a strong same-information generic three-read ML/plurality decoder
- an exactly identical generic-unanimity control for the BTBC consensus rule

The simulation is an exact generalized-Pauli-frame stabilizer Monte Carlo for the
specified stochastic Pauli channel. It is not a gate-level unitary simulation of
real qutrit hardware and it does not model coherent leakage/non-Pauli noise.
"""

from __future__ import annotations

import cmath
import json
import math
import random
from pathlib import Path

D = 3
N = 9
CYCLES = 100
TRIALS = 1000
SEEDS = [471103, 822367, 1190339, 2103691, 3906007]
# p_data, p_meas, p_extract, p_recovery, p_block_burst
PROFILES = [
    (0.001, 0.001, 0.0005, 0.0002, 0.0),
    (0.003, 0.003, 0.0010, 0.0005, 0.0),
    (0.010, 0.010, 0.0030, 0.0010, 0.0),
    (0.020, 0.020, 0.0050, 0.0020, 0.0),
    (0.003, 0.020, 0.0010, 0.0005, 0.0005),
    (0.020, 0.003, 0.0030, 0.0010, 0.0010),
    (0.010, 0.010, 0.0030, 0.0010, 0.0030),
    (0.020, 0.030, 0.0060, 0.0030, 0.0050),
]
ARMS = [
    "generic_latest3",
    "generic_component_ml3",
    "generic_unanimity",
    "btbc_full",
    "btbc_no9",
    "perfect_current",
]

NONIDENTITY_LOCAL = [(a, b) for a in range(D) for b in range(D) if (a, b) != (0, 0)]
ZERO_SYNDROME = (0,) * 8


def addv(a, b):
    return tuple((x + y) % D for x, y in zip(a, b))


def subv(a, b):
    return tuple((x - y) % D for x, y in zip(a, b))


def scalev(c, a):
    return tuple((c * x) % D for x in a)


def symp(a, b):
    # vectors are (x_0..x_8, z_0..z_8)
    return sum((a[i] * b[N + i] - a[N + i] * b[i]) for i in range(N)) % D


def stab_z_pair(i, j):
    v = [0] * (2 * N)
    v[N + i] = 1
    v[N + j] = 2  # -1 mod 3
    return tuple(v)


def stab_x_block_difference(a0, b0):
    v = [0] * (2 * N)
    for i in range(a0, a0 + 3):
        v[i] = 1
    for i in range(b0, b0 + 3):
        v[i] = 2
    return tuple(v)


STABILIZERS = [
    stab_z_pair(0, 1), stab_z_pair(1, 2),
    stab_z_pair(3, 4), stab_z_pair(4, 5),
    stab_z_pair(6, 7), stab_z_pair(7, 8),
    stab_x_block_difference(0, 3),
    stab_x_block_difference(3, 6),
]


def rank_mod3(rows):
    if not rows:
        return 0
    a = [list(r) for r in rows]
    m, n = len(a), len(a[0])
    r = 0
    for c in range(n):
        piv = next((i for i in range(r, m) if a[i][c] % D), None)
        if piv is None:
            continue
        a[r], a[piv] = a[piv], a[r]
        inv = 1 if a[r][c] % D == 1 else 2
        a[r] = [(inv * x) % D for x in a[r]]
        for i in range(m):
            if i != r and a[i][c] % D:
                f = a[i][c] % D
                a[i] = [(a[i][j] - f * a[r][j]) % D for j in range(n)]
        r += 1
        if r == m:
            break
    return r


def nullspace_mod3(a):
    # Solutions x to A x = 0 over GF(3).
    m, n = len(a), len(a[0])
    rref = [list(row) for row in a]
    pivots = []
    r = 0
    for c in range(n):
        piv = next((i for i in range(r, m) if rref[i][c] % D), None)
        if piv is None:
            continue
        rref[r], rref[piv] = rref[piv], rref[r]
        inv = 1 if rref[r][c] % D == 1 else 2
        rref[r] = [(inv * x) % D for x in rref[r]]
        for i in range(m):
            if i != r and rref[i][c] % D:
                f = rref[i][c] % D
                rref[i] = [(rref[i][j] - f * rref[r][j]) % D for j in range(n)]
        pivots.append(c)
        r += 1
        if r == m:
            break
    free = [c for c in range(n) if c not in pivots]
    basis = []
    for f in free:
        v = [0] * n
        v[f] = 1
        for rr, pc in enumerate(pivots):
            v[pc] = (-rref[rr][f]) % D
        basis.append(tuple(v))
    return basis


def solve_coefficients(rows, target):
    # Solve sum_i c_i rows[i] = target; return one coefficient vector.
    k = len(rows)
    equations = [[rows[j][i] % D for j in range(k)] + [target[i] % D] for i in range(len(target))]
    r = 0
    pivots = []
    for c in range(k):
        piv = next((i for i in range(r, len(equations)) if equations[i][c] % D), None)
        if piv is None:
            continue
        equations[r], equations[piv] = equations[piv], equations[r]
        inv = 1 if equations[r][c] % D == 1 else 2
        equations[r] = [(inv * x) % D for x in equations[r]]
        for i in range(len(equations)):
            if i != r and equations[i][c] % D:
                f = equations[i][c] % D
                equations[i] = [(equations[i][j] - f * equations[r][j]) % D for j in range(k + 1)]
        pivots.append(c)
        r += 1
    for row in equations:
        if all(x % D == 0 for x in row[:k]) and row[k] % D:
            return None
    out = [0] * k
    for rr, pc in enumerate(pivots):
        out[pc] = equations[rr][k] % D
    return tuple(out)


def centralizer_basis():
    # symp(stabilizer, v)=0 gives linear equations in v=(x,z).
    a = []
    for s in STABILIZERS:
        # coefficients for x_v are -z_s; for z_v are x_s
        a.append(tuple([(-s[N + i]) % D for i in range(N)] + [s[i] % D for i in range(N)]))
    return nullspace_mod3(a)


def find_logicals():
    cb = centralizer_basis()
    span = list(STABILIZERS)
    lx = None
    for v in cb:
        if rank_mod3(span + [v]) > rank_mod3(span):
            lx = v
            break
    assert lx is not None
    span2 = span + [lx]
    lz = None
    for v in cb:
        if rank_mod3(span2 + [v]) > rank_mod3(span2) and symp(lx, v) != 0:
            lz = v
            break
    if lz is None:
        # Search simple combinations of centralizer basis vectors.
        for a in cb:
            for b in cb:
                v = addv(a, b)
                if rank_mod3(span2 + [v]) > rank_mod3(span2) and symp(lx, v) != 0:
                    lz = v
                    break
            if lz is not None:
                break
    assert lz is not None
    # Normalize symp(lx,lz)=1.
    if symp(lx, lz) == 2:
        lz = scalev(2, lz)
    return lx, lz


LOGICAL_X, LOGICAL_Z = find_logicals()
LOGICAL_BASIS_ROWS = STABILIZERS + [LOGICAL_X, LOGICAL_Z]


def syndrome(frame):
    return tuple(symp(s, frame) for s in STABILIZERS)


def local_frame(q, a, b):
    v = [0] * (2 * N)
    v[q] = a % D
    v[N + q] = b % D
    return tuple(v)


def build_decoder():
    # Dynamic programming over qutrits: minimum Hamming-weight generalized-Pauli
    # representative for every one of 3^8 possible syndrome vectors.
    dp = {ZERO_SYNDROME: (0, ())}
    for q in range(N):
        nxt = {}
        for s0, (cost0, path0) in dp.items():
            for a in range(D):
                for b in range(D):
                    loc = local_frame(q, a, b)
                    s1 = addv(s0, syndrome(loc))
                    cost = cost0 + (1 if (a, b) != (0, 0) else 0)
                    old = nxt.get(s1)
                    path = path0 + ((a, b),)
                    if old is None or cost < old[0]:
                        nxt[s1] = (cost, path)
        dp = nxt
    table = {}
    for s, (cost, path) in dp.items():
        v = [0] * (2 * N)
        for q, (a, b) in enumerate(path):
            v[q] = a
            v[N + q] = b
        table[s] = (cost, tuple(v))
    assert len(table) == D ** len(STABILIZERS)
    return table


DECODER = build_decoder()


def decode_correction(measured_syndrome):
    # Representative E has the measured syndrome; applying -E cancels it.
    return scalev(2, DECODER[tuple(measured_syndrome)][1])


def apply_local(frame, q, a, b):
    if a == 0 and b == 0:
        return frame
    v = list(frame)
    v[q] = (v[q] + a) % D
    v[N + q] = (v[N + q] + b) % D
    return tuple(v)


def random_state(rng):
    vals = []
    for _ in range(D):
        # Box-Muller from fixed uniform draws for reproducibility.
        u1 = max(rng.random(), 1e-15)
        u2 = rng.random()
        radius = math.sqrt(-2.0 * math.log(u1))
        vals.append(complex(radius * math.cos(2 * math.pi * u2), radius * math.sin(2 * math.pi * u2)))
    norm = math.sqrt(sum(abs(z) ** 2 for z in vals))
    return tuple(z / norm for z in vals)


def logical_pauli_fidelity(psi, a, b):
    if (a, b) == (0, 0):
        return 1.0
    omega = cmath.exp(2j * math.pi / D)
    out = [0j] * D
    # X^a Z^b |j> = omega^(b*j) |j+a>
    for j, amp in enumerate(psi):
        out[(j + a) % D] += (omega ** (b * j)) * amp
    overlap = sum(psi[j].conjugate() * out[j] for j in range(D))
    return float(abs(overlap) ** 2)


def final_logical_label(frame):
    # Ideal final syndrome recovery removes the observable syndrome, then the
    # centralizer residue is decomposed into stabilizer + logical X/Z powers.
    s = syndrome(frame)
    frame = addv(frame, decode_correction(s))
    assert syndrome(frame) == ZERO_SYNDROME
    coeff = solve_coefficients(LOGICAL_BASIS_ROWS, frame)
    assert coeff is not None
    # Coefficients on LOGICAL_X and LOGICAL_Z.
    return coeff[-2] % D, coeff[-1] % D


def noisy_syndrome(true_s, rng, p_meas):
    out = []
    for t in true_s:
        hit = rng.random() < p_meas
        direction = 1 if rng.random() < 0.5 else 2
        out.append((t + direction) % D if hit else t)
    return tuple(out)


def component_ml3(reads):
    out = []
    for j in range(len(STABILIZERS)):
        vals = [reads[0][j], reads[1][j], reads[2][j]]
        counts = [vals.count(k) for k in range(D)]
        best = max(counts)
        winners = [k for k, c in enumerate(counts) if c == best]
        # With three reads, ties only occur as 1/1/1; latest is a deterministic
        # tie-break that does not use hidden truth.
        out.append(vals[2] if len(winners) > 1 else winners[0])
    return tuple(out)


def decide(arm, reads, current_true):
    if arm == "generic_latest3":
        return reads[2]
    if arm == "generic_component_ml3":
        return component_ml3(reads)
    if arm in ("generic_unanimity", "btbc_full"):
        return reads[0] if reads[0] == reads[1] == reads[2] else None
    if arm == "btbc_no9":
        return None
    if arm == "perfect_current":
        return current_true
    raise ValueError(arm)


def simulate_trial(arm, profile, seed, trial_index):
    p_data, p_meas, p_extract, p_recovery, p_burst = profile
    # Same stream for every arm at a fixed (seed, profile, trial). Control-flow
    # never changes how many RNG draws are consumed.
    profile_id = PROFILES.index(profile)
    rng = random.Random(seed * 10_000_019 + profile_id * 1_000_003 + trial_index * 97_409)
    psi = random_state(rng)
    frame = (0,) * (2 * N)
    corrections = 0
    false_corrections = 0
    abstentions = 0
    state9 = 0

    for _cycle in range(CYCLES):
        # Base stochastic data Pauli faults: all 8 nonidentity qutrit Paulis.
        for q in range(N):
            hit = rng.random() < p_data
            a, b = NONIDENTITY_LOCAL[rng.randrange(len(NONIDENTITY_LOCAL))]
            if hit:
                frame = apply_local(frame, q, a, b)

        # Correlated same-Pauli burst on one 3-qutrit block.
        burst_hit = rng.random() < p_burst
        block = rng.randrange(3)
        ba, bb = NONIDENTITY_LOCAL[rng.randrange(len(NONIDENTITY_LOCAL))]
        if burst_hit:
            for q in range(3 * block, 3 * block + 3):
                frame = apply_local(frame, q, ba, bb)

        reads = []
        # Three full syndrome extractions. Each extraction has aggregate
        # back-action on each data qutrit, so redundancy is not free.
        for _read in range(3):
            for q in range(N):
                hit = rng.random() < p_extract
                a, b = NONIDENTITY_LOCAL[rng.randrange(len(NONIDENTITY_LOCAL))]
                if hit:
                    frame = apply_local(frame, q, a, b)
            true_s = syndrome(frame)
            reads.append(noisy_syndrome(true_s, rng, p_meas))

        current_true = syndrome(frame)
        choice = decide(arm, reads, current_true)
        if choice is None or choice == ZERO_SYNDROME:
            if choice is None:
                abstentions += 1
        else:
            if current_true == ZERO_SYNDROME:
                false_corrections += 1
            corr = decode_correction(choice)
            frame = addv(frame, corr)
            corrections += 1
            if arm == "btbc_full":
                state9 += 1

        # Draw potential recovery-gate faults for every qutrit regardless of
        # whether the arm corrected, keeping physical randomness matched.
        for q in range(N):
            hit = rng.random() < p_recovery
            a, b = NONIDENTITY_LOCAL[rng.randrange(len(NONIDENTITY_LOCAL))]
            # A recovery fault is physically relevant only if this cycle had
            # a recovery operation acting on that qutrit. We conservatively
            # model the decoder representative as parallel local gates.
            if choice not in (None, ZERO_SYNDROME):
                corr = decode_correction(choice)
                if (corr[q], corr[N + q]) != (0, 0) and hit:
                    frame = apply_local(frame, q, a, b)

    la, lb = final_logical_label(frame)
    failed = int((la, lb) != (0, 0))
    fidelity = logical_pauli_fidelity(psi, la, lb)
    return failed, fidelity, corrections, false_corrections, abstentions, state9


def aggregate():
    rows = []
    per_seed = {str(seed): {} for seed in SEEDS}
    pooled = {arm: {"trials": 0, "logical_failures": 0, "fidelity_sum": 0.0,
                    "corrections": 0, "false_corrections": 0, "abstentions": 0,
                    "state9_triggers": 0} for arm in ARMS}

    for seed in SEEDS:
        seed_acc = {arm: {"trials": 0, "logical_failures": 0, "fidelity_sum": 0.0,
                          "corrections": 0, "false_corrections": 0, "abstentions": 0,
                          "state9_triggers": 0} for arm in ARMS}
        for profile in PROFILES:
            for arm in ARMS:
                acc = {"trials": TRIALS, "logical_failures": 0, "fidelity_sum": 0.0,
                       "corrections": 0, "false_corrections": 0, "abstentions": 0,
                       "state9_triggers": 0}
                for t in range(TRIALS):
                    f, fid, c, fc, ab, s9 = simulate_trial(arm, profile, seed, t)
                    acc["logical_failures"] += f
                    acc["fidelity_sum"] += fid
                    acc["corrections"] += c
                    acc["false_corrections"] += fc
                    acc["abstentions"] += ab
                    acc["state9_triggers"] += s9
                row = {
                    "seed": seed,
                    "p_data": profile[0], "p_meas": profile[1], "p_extract": profile[2],
                    "p_recovery": profile[3], "p_block_burst": profile[4],
                    "arm": arm,
                    "trials": TRIALS,
                    "logical_failures": acc["logical_failures"],
                    "logical_failure_rate": acc["logical_failures"] / TRIALS,
                    "mean_unknown_state_fidelity": acc["fidelity_sum"] / TRIALS,
                    "corrections": acc["corrections"],
                    "false_corrections": acc["false_corrections"],
                    "abstentions": acc["abstentions"],
                    "state9_triggers": acc["state9_triggers"],
                }
                rows.append(row)
                for dest in (seed_acc[arm], pooled[arm]):
                    for k in dest:
                        dest[k] += acc[k]
        for arm, d in seed_acc.items():
            per_seed[str(seed)][arm] = {
                **d,
                "logical_failure_rate": d["logical_failures"] / d["trials"],
                "mean_unknown_state_fidelity": d["fidelity_sum"] / d["trials"],
            }

    pooled_out = {}
    for arm, d in pooled.items():
        pooled_out[arm] = {
            **d,
            "logical_failure_rate": d["logical_failures"] / d["trials"],
            "mean_unknown_state_fidelity": d["fidelity_sum"] / d["trials"],
        }

    return rows, per_seed, pooled_out


def contracts():
    commute = all(symp(a, b) == 0 for i, a in enumerate(STABILIZERS) for b in STABILIZERS[i + 1:])
    single = {}
    unique = True
    recover = True
    for q in range(N):
        for a, b in NONIDENTITY_LOCAL:
            e = local_frame(q, a, b)
            s = syndrome(e)
            if s in single:
                unique = False
            single[s] = (q, a, b)
            c = decode_correction(s)
            residue = addv(e, c)
            if syndrome(residue) != ZERO_SYNDROME:
                recover = False
            la, lb = final_logical_label(e)
            if (la, lb) != (0, 0):
                recover = False
    return {
        "balanced_trinary_dimension_is_3": D == 3,
        "stabilizer_rank_is_8": rank_mod3(STABILIZERS) == 8,
        "stabilizers_commute_mod3": commute,
        "logical_x_commutes_with_stabilizers": all(symp(s, LOGICAL_X) == 0 for s in STABILIZERS),
        "logical_z_commutes_with_stabilizers": all(symp(s, LOGICAL_Z) == 0 for s in STABILIZERS),
        "logical_pair_symplectic_product_is_1": symp(LOGICAL_X, LOGICAL_Z) == 1,
        "logical_x_not_stabilizer": rank_mod3(STABILIZERS + [LOGICAL_X]) == 9,
        "logical_z_independent": rank_mod3(STABILIZERS + [LOGICAL_X, LOGICAL_Z]) == 10,
        "all_72_single_qutrit_nonidentity_paulis_have_unique_syndromes": unique and len(single) == N * 8,
        "all_single_qutrit_generalized_paulis_recover": recover,
        "decoder_covers_all_3pow8_syndromes": len(DECODER) == 3 ** 8,
    }


def main():
    checks = contracts()
    rows, per_seed, pooled = aggregate()

    # Exact identity control: same evidence, same physical streams, same rule;
    # any mismatch is an implementation defect.
    identity = all(
        per_seed[str(seed)]["generic_unanimity"][k] == per_seed[str(seed)]["btbc_full"][k]
        for seed in SEEDS
        for k in ("logical_failures", "corrections", "false_corrections", "abstentions")
    )
    btbc_nonworse_ml_seeds = sum(
        per_seed[str(seed)]["btbc_full"]["logical_failure_rate"]
        <= per_seed[str(seed)]["generic_component_ml3"]["logical_failure_rate"]
        for seed in SEEDS
    )
    criteria = {
        "native_code_contract_passes": all(checks.values()),
        "matched_unanimity_identity": identity,
        "state9_exercised": pooled["btbc_full"]["state9_triggers"] > 0,
        "btbc_beats_no9_pooled": pooled["btbc_full"]["logical_failure_rate"] < pooled["btbc_no9"]["logical_failure_rate"],
        "btbc_beats_latest3_pooled": pooled["btbc_full"]["logical_failure_rate"] < pooled["generic_latest3"]["logical_failure_rate"],
        "btbc_false_corrections_below_latest3": pooled["btbc_full"]["false_corrections"] < pooled["generic_latest3"]["false_corrections"],
        "btbc_nonworse_than_strong_ml_on_at_least_3_of_5_seeds": btbc_nonworse_ml_seeds >= 3,
        "btbc_pooled_nonworse_than_strong_ml": pooled["btbc_full"]["logical_failure_rate"] <= pooled["generic_component_ml3"]["logical_failure_rate"],
    }
    criteria["all_primary_criteria"] = all(criteria.values())

    result = {
        "scope": "Exact GF(3) generalized-Pauli-frame simulation of a [[9,1,3]]_3 Shor-style stabilizer code with X/Z/Y-like qutrit Pauli faults, noisy repeated syndrome readout, extraction back-action, recovery faults, correlated block bursts, and arbitrary unknown logical-qutrit fidelity scoring. Not coherent/leakage noise or physical qutrit hardware.",
        "frozen_config": {
            "dimension": D,
            "balanced_trinary_basis": ["|-1>", "|0>", "|+1>"],
            "code": "[[9,1,3]]_3 Shor-style qutrit stabilizer",
            "cycles": CYCLES,
            "trials_per_profile_seed_arm": TRIALS,
            "seeds": SEEDS,
            "profiles_pdata_pmeas_pextract_precovery_pburst": PROFILES,
            "matched_random_streams_across_arms": True,
            "three_full_syndrome_reads_per_cycle_for_all_arms": True,
            "unknown_logical_state_distribution": "complex Gaussian / Haar-distributed pure qutrit states",
        },
        "contract_checks": checks,
        "predeclared_criteria": criteria,
        "interpretation_contract": {
            "if_btbc_equals_generic_unanimity": "The useful behavior is the unanimity/abstention decoder rule; the 3/6/9 labels are not independently causal.",
            "if_btbc_beats_latest_but_loses_ml": "BTBC-style conservative corroboration is useful versus naive noisy-syndrome correction, but a conventional same-information ML/plurality decoder is stronger.",
            "if_btbc_matches_or_beats_ml": "The conservative unanimity rule remains competitive with a strong same-information conventional decoder under this frozen Pauli-channel benchmark and merits circuit/hardware study.",
            "hard_limit": "This cannot establish special physical significance of 3/6/9, hardware fault tolerance, or robustness to coherent/leakage/non-Pauli errors.",
        },
        "per_seed": per_seed,
        "pooled": pooled,
        "rows": rows,
    }
    out = Path("artifacts/btbc_qutrit_full_pauli_hard_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps({k: result[k] for k in ("scope", "frozen_config", "contract_checks", "predeclared_criteria", "pooled")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
