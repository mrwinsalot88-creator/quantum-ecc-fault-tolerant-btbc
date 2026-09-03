#!/usr/bin/env python3
"""Hard matched-information benchmark for native balanced-trinary BTBC.

Purpose
-------
The earlier non-temporal qutrit benchmark gave BTBC three simultaneous parity
checks while the conventional arm used only two. This test removes that
advantage. BTBC and the strongest generic control receive the *same three noisy
same-cycle checks*, the same data faults, and matched random streams.

This is deliberately adversarial:
- 5 unseen seeds
- 8 asymmetric data/measurement-noise profiles
- independent generalized-X qutrit shifts
- correlated two-site burst shifts
- 100 correction cycles per trial
- 2,000 trials per profile per seed

Native alphabet: |-1>, |0>, |+1>.
Encoding: three-qutrit repetition code for generalized-X shifts only.
Generalized-Z phase errors are NOT corrected by this code and remain out of
scope; this benchmark is a decoder/control-policy stress test, not a universal
qutrit QEC claim.

Arms
----
bare                 : no correction
conventional_2check  : immediate two-check decoder
matched_generic      : ordinary same-cycle three-check consistency-gated decoder
btbc_superposition   : same evidence and action rule as matched_generic, expressed
                       through 0 = simultaneous {3,6,9} decision register and
                       immediate 9 fail-safe
btbc_no9             : same BTBC evidence but 9 correction disabled
serialized_btbc      : intentionally incorrect temporal 3->6->9 waiting ablation
perfect              : exact true-syndrome upper reference

The key falsification test is btbc_superposition vs matched_generic. They are
intentionally matched in information and operational correction rule. If they
are identical, the useful result is that the gain comes from simultaneous
redundant corroboration/consistency gating, not the numerical labels themselves.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict
from pathlib import Path

BASIS = (-1, 0, +1)
SEEDS = (471103, 822367, 1190339, 2103691, 3906007)
TRIALS = 2000
CYCLES = 100
# (p_data, p_meas, p_burst)
PROFILES = (
    (0.001, 0.001, 0.0000),
    (0.003, 0.003, 0.0000),
    (0.010, 0.010, 0.0000),
    (0.020, 0.020, 0.0000),
    (0.003, 0.010, 0.0005),
    (0.010, 0.003, 0.0010),
    (0.010, 0.020, 0.0020),
    (0.020, 0.010, 0.0040),
)
ARMS = (
    "bare",
    "conventional_2check",
    "matched_generic",
    "btbc_superposition",
    "btbc_no9",
    "serialized_btbc",
    "perfect",
)


def mod3(x: int) -> int:
    return x % 3


def checks3(frame: tuple[int, int, int]) -> tuple[int, int, int]:
    a, b, c = frame
    # Redundant cycle of pair differences. For any physical frame these satisfy
    # s01 + s12 + s20 == 0 mod 3.
    return (mod3(a-b), mod3(b-c), mod3(c-a))


def checks2(frame: tuple[int, int, int]) -> tuple[int, int]:
    s = checks3(frame)
    return s[0], s[1]


def build_decoder2():
    dec = {(0,0): None}
    for site in range(3):
        for shift in (1,2):
            f=[0,0,0]; f[site]=shift
            syn=checks2(tuple(f))
            if syn in dec: raise AssertionError(("nonunique2",syn))
            dec[syn]=(site, mod3(-shift))
    return dec


def build_decoder3():
    dec = {(0,0,0): None}
    for site in range(3):
        for shift in (1,2):
            f=[0,0,0]; f[site]=shift
            syn=checks3(tuple(f))
            if syn in dec: raise AssertionError(("nonunique3",syn))
            dec[syn]=(site, mod3(-shift))
    return dec

DEC2=build_decoder2(); DEC3=build_decoder3()
VALID3=frozenset(k for k,v in DEC3.items() if v is not None)


def inject(frame: list[int], p_data: float, p_burst: float, rng: random.Random):
    for i in range(3):
        if rng.random() < p_data:
            frame[i]=mod3(frame[i]+rng.choice((1,2)))
    # Correlated two-site burst: same nonzero shift on two randomly chosen sites.
    if rng.random() < p_burst:
        sites=rng.sample(range(3),2); sh=rng.choice((1,2))
        for i in sites: frame[i]=mod3(frame[i]+sh)


def noisy_value(x:int,p:float,rng:random.Random)->int:
    if rng.random()<p:
        return mod3(x+rng.choice((1,2)))
    return x


def noisy3(true3,p,rng):
    return tuple(noisy_value(x,p,rng) for x in true3)


def noisy2(true2,p,rng):
    return tuple(noisy_value(x,p,rng) for x in true2)


def apply(frame:list[int], corr)->bool:
    if corr is None: return False
    site,inv=corr; frame[site]=mod3(frame[site]+inv); return True


def logical_failure(frame:tuple[int,int,int])->bool:
    # End-of-run success requires return to the original logical frame exactly.
    return frame != (0,0,0)

@dataclass
class Metrics:
    trials:int=0
    logical_failures:int=0
    corrections:int=0
    false_corrections:int=0
    rejected_inconsistent:int=0
    state9_triggers:int=0


def run_trial(arm,pd,pm,pb,seed):
    rng=random.Random(seed)
    frame=[0,0,0]
    m=Metrics(trials=1)
    candidate=None; stage=0
    for _ in range(CYCLES):
        inject(frame,pd,pb,rng)
        true3=checks3(tuple(frame)); true2=(true3[0],true3[1])

        # Generate a shared three-check noisy observation first. The two-check
        # arm consumes the first two entries, ensuring no hidden extra evidence.
        measured3=noisy3(true3,pm,rng)
        measured2=(measured3[0],measured3[1])

        if arm=="bare": continue
        if arm=="perfect":
            corr=DEC3.get(true3)
            if apply(frame,corr): m.corrections+=1
            continue
        if arm=="conventional_2check":
            corr=DEC2.get(measured2)
            if corr is not None:
                if true3==(0,0,0): m.false_corrections+=1
                if apply(frame,corr): m.corrections+=1
            continue

        # Same-cycle three-check consistency gate. A physically valid syndrome
        # must sum to zero mod 3 and be a known single-error syndrome.
        consistent=(sum(measured3)%3==0 and measured3 in VALID3)

        if arm in ("matched_generic","btbc_superposition"):
            if not consistent:
                if measured3!=(0,0,0): m.rejected_inconsistent+=1
                continue
            # BTBC language: controller zero contains 3/6/9 simultaneously;
            # same-cycle consistency marks 9 and invokes the fail-safe now.
            if arm=="btbc_superposition": m.state9_triggers+=1
            corr=DEC3.get(measured3)
            if corr is not None:
                if true3==(0,0,0): m.false_corrections+=1
                if apply(frame,corr): m.corrections+=1
            continue

        if arm=="btbc_no9":
            if not consistent and measured3!=(0,0,0): m.rejected_inconsistent+=1
            # 9 action removed: no corrective action.
            continue

        if arm=="serialized_btbc":
            if measured3==(0,0,0) or measured3 not in VALID3:
                candidate=None; stage=0; continue
            if measured3!=candidate:
                candidate=measured3; stage=3; continue
            if stage==3:
                stage=6; continue
            if stage==6:
                m.state9_triggers+=1
                corr=DEC3.get(measured3)
                if corr is not None:
                    if true3==(0,0,0): m.false_corrections+=1
                    if apply(frame,corr): m.corrections+=1
                candidate=None; stage=0
            continue
        raise AssertionError(arm)

    if logical_failure(tuple(frame)): m.logical_failures=1
    return m


def accumulate(dst:Metrics,src:Metrics):
    for k in asdict(dst): setattr(dst,k,getattr(dst,k)+getattr(src,k))


def contract_checks():
    unique2=len(DEC2)==7; unique3=len(DEC3)==7
    recovered=True
    for site in range(3):
        for sh in (1,2):
            f=[0,0,0]; f[site]=sh
            syn=checks3(tuple(f)); g=f[:]
            recovered &= apply(g,DEC3[syn]) and g==[0,0,0]
    return {
        "balanced_trinary_basis_exact": BASIS==(-1,0,+1),
        "two_check_single_shift_decoder_complete": unique2,
        "three_check_single_shift_decoder_complete": unique3,
        "all_single_qutrit_shifts_recover": recovered,
        "three_check_constraint_valid": all(sum(s)%3==0 for s in DEC3),
    }


def main():
    rows=[]
    pooled={a:Metrics() for a in ARMS}
    per_seed={}
    # matched trial seeds across arms are crucial: generic and BTBC get exactly
    # the same faults and observations.
    for seed_index,seed in enumerate(SEEDS):
        per_seed[str(seed)]={a:Metrics() for a in ARMS}
        for pi,(pd,pm,pb) in enumerate(PROFILES):
            local={a:Metrics() for a in ARMS}
            for t in range(TRIALS):
                trial_seed=seed + pi*10_000_000 + t*101
                for arm in ARMS:
                    r=run_trial(arm,pd,pm,pb,trial_seed)
                    accumulate(local[arm],r); accumulate(pooled[arm],r); accumulate(per_seed[str(seed)][arm],r)
            for arm in ARMS:
                m=local[arm]
                rows.append({
                    "seed":seed,"p_data":pd,"p_meas":pm,"p_burst":pb,"arm":arm,
                    **asdict(m),"logical_failure_rate":m.logical_failures/m.trials,
                })

    checks=contract_checks()
    generic=pooled["matched_generic"]; btbc=pooled["btbc_superposition"]
    no9=pooled["btbc_no9"]; serial=pooled["serialized_btbc"]
    conv=pooled["conventional_2check"]

    # Frozen criteria deliberately distinguish mechanism validation from label novelty.
    criteria={
        "native_contract_passes": all(checks.values()),
        "btbc_beats_no9_pooled": btbc.logical_failures < no9.logical_failures,
        "btbc_beats_serialized_pooled": btbc.logical_failures < serial.logical_failures,
        "btbc_beats_two_check_conventional_pooled": btbc.logical_failures < conv.logical_failures,
        "btbc_false_corrections_below_two_check_conventional": btbc.false_corrections < conv.false_corrections,
        "state9_exercised": btbc.state9_triggers > 0,
        "matched_information_identity": (
            btbc.logical_failures==generic.logical_failures and
            btbc.corrections==generic.corrections and
            btbc.false_corrections==generic.false_corrections
        ),
        "btbc_nonworse_than_generic_on_every_seed": all(
            per_seed[str(s)]["btbc_superposition"].logical_failures <= per_seed[str(s)]["matched_generic"].logical_failures
            for s in SEEDS
        ),
    }
    # This benchmark passes if architecture is robust AND the matched-control
    # falsification is resolved honestly. Identity is expected if labels add no
    # operational effect.
    criteria["all_predeclared_criteria"] = all(criteria.values())

    result={
        "frozen_config":{"basis":["|-1>","|0>","|+1>"],"seeds":SEEDS,"trials_per_profile_seed":TRIALS,"cycles":CYCLES,"profiles":PROFILES,"timing_history_used_by_btbc_superposition":False},
        "contract_checks":checks,
        "predeclared_criteria":criteria,
        "pooled":{a:{**asdict(m),"logical_failure_rate":m.logical_failures/m.trials} for a,m in pooled.items()},
        "per_seed":{s:{a:{**asdict(m),"logical_failure_rate":m.logical_failures/m.trials} for a,m in d.items()} for s,d in per_seed.items()},
        "rows":rows,
        "interpretation_contract":{
            "if_btbc_equals_matched_generic":"Useful effect is attributable to same-cycle redundant syndrome consistency gating; 3/6/9 labels are not independently causal in this implementation.",
            "if_btbc_beats_matched_generic":"Would justify investigating a distinct BTBC operational rule, but only if both arms had exactly matched information and resources.",
            "scope_limit":"Generalized-X qutrit shifts only; no generalized-Z phase correction and no hardware gate-level qutrit syndrome extraction."
        }
    }
    out=Path("artifacts/btbc_native_qutrit_hard_matched_results.json"); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    if not criteria["all_predeclared_criteria"]:
        raise SystemExit("hard matched-information criteria did not all pass")

if __name__=="__main__": main()
