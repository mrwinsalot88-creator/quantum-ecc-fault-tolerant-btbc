#!/usr/bin/env python3
"""Frozen non-temporal BTBC native-qutrit benchmark.

This test keeps the user's native balanced-trinary quantum alphabet {-1,0,+1}
and removes the earlier serialized 3->6->9 timing interpretation.

Data code: 3-qutrit repetition code for generalized-X (cyclic shift) errors.
The protected logical state may be an arbitrary qutrit state
alpha|-1> + beta|0> + gamma|+1>.

Same-cycle syndrome evidence:
  s01 = q0-q1 mod 3
  s12 = q1-q2 mod 3
  s02 = q0-q2 mod 3
The three checks are measured in the same cycle. Exact checks satisfy
s02 == s01+s12 (mod 3).

BTBC controller register:
  |0_BTBC> := (|3>+|6>+|9>)/sqrt(3), an available decision superposition.
  A same-cycle consistency oracle marks |9> when the measured triple is
  self-consistent and the implied standard syndrome is decodable.
  One qutrit Grover-style diffusion step gives P(9)=25/27 for a marked state;
  the controller triggers immediately when P(9)>0.9. There is no prior-cycle
  memory and no timing delay.

The statevector controller is a mathematical decision-register model, not a
claim that this exact oracle/diffusion circuit is already hardware-realized.
Generalized-Z phase errors remain out of scope.
"""
from __future__ import annotations

import cmath
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

BASIS = (-1, 0, +1)
NOISE_POINTS = (0.001, 0.003, 0.01, 0.02)
TRIALS = 5000
CYCLES = 100
SEED = 3690369
SQRT3 = math.sqrt(3.0)
CTRL0 = (1/SQRT3, 1/SQRT3, 1/SQRT3)  # |3>, |6>, |9>


def mod3(x: int) -> int:
    return x % 3


def syndrome2(frame: tuple[int, int, int]) -> tuple[int, int]:
    a,b,c = frame
    return mod3(a-b), mod3(b-c)


def syndrome3(frame: tuple[int, int, int]) -> tuple[int, int, int]:
    a,b,c = frame
    return mod3(a-b), mod3(b-c), mod3(a-c)


def build_decoder():
    dec = {(0,0): None}
    for site in range(3):
        for shift in (1,2):
            f=[0,0,0]; f[site]=shift
            syn=syndrome2(tuple(f))
            if syn in dec:
                raise AssertionError(f"non-unique syndrome {syn}")
            dec[syn]=(site,mod3(-shift))
    return dec

DECODER=build_decoder()
VALID=frozenset(k for k,v in DECODER.items() if v is not None)


def apply_correction(frame:list[int], syn:tuple[int,int]) -> bool:
    corr=DECODER.get(syn)
    if corr is None:
        return False
    site,inv=corr
    frame[site]=mod3(frame[site]+inv)
    return True


def inject_data_noise(frame:list[int], p:float, rng:random.Random):
    for i in range(3):
        if rng.random()<p:
            frame[i]=mod3(frame[i]+rng.choice((1,2)))


def noisy_digit(x:int,p:float,rng:random.Random)->int:
    if rng.random()<p:
        x=mod3(x+rng.choice((1,2)))
    return x


def measured3(true3:tuple[int,int,int], p:float, rng:random.Random):
    return tuple(noisy_digit(x,p,rng) for x in true3)


def measured2(true2:tuple[int,int], p:float, rng:random.Random):
    return tuple(noisy_digit(x,p,rng) for x in true2)


def controller_state(mark9:bool):
    """Oracle phase flip on |9>, then diffusion about CTRL0."""
    v=list(CTRL0)
    if mark9:
        v[2] *= -1
    mean=sum(v)/3.0
    out=tuple(2*mean-x for x in v)
    return out


def p9_for(meas:tuple[int,int,int])->float:
    s01,s12,s02=meas
    consistent=(s02==mod3(s01+s12))
    decodable=(s01,s12) in VALID
    st=controller_state(consistent and decodable)
    norm=sum(abs(x)**2 for x in st)
    if abs(norm-1.0)>1e-12:
        raise AssertionError(norm)
    return abs(st[2])**2


def logical_failure(frame:tuple[int,int,int])->bool:
    syn=syndrome2(frame)
    if syn!=(0,0):
        return True
    return not (frame[0]==frame[1]==frame[2]==0)

@dataclass
class M:
    fail:int=0
    corrections:int=0
    false_corr:int=0
    state9:int=0
    rejected_inconsistent:int=0


def run_arm(arm:str,p:float,rng:random.Random)->M:
    m=M()
    for _ in range(TRIALS):
        frame=[0,0,0]
        for _ in range(CYCLES):
            inject_data_noise(frame,p,rng)
            t2=syndrome2(tuple(frame)); t3=syndrome3(tuple(frame))
            if arm=="bare":
                continue
            if arm=="perfect":
                if t2 in VALID and apply_correction(frame,t2): m.corrections+=1
                continue
            if arm=="conventional":
                s2=measured2(t2,p,rng)
                if s2 in VALID:
                    if t2==(0,0): m.false_corr+=1
                    if apply_correction(frame,s2): m.corrections+=1
                continue

            s3=measured3(t3,p,rng)
            s01,s12,s02=s3
            consistent=(s02==mod3(s01+s12))
            decodable=(s01,s12) in VALID
            if not consistent and decodable:
                m.rejected_inconsistent+=1
            prob9=p9_for(s3)
            trigger=prob9>0.9
            if arm=="btbc_no9":
                trigger=False
            if trigger:
                m.state9+=1
                if t2==(0,0): m.false_corr+=1
                if apply_correction(frame,(s01,s12)): m.corrections+=1
        if logical_failure(tuple(frame)): m.fail+=1
    return m


def random_qutrit(rng:random.Random):
    z=[complex(rng.gauss(0,1),rng.gauss(0,1)) for _ in range(3)]
    n=math.sqrt(sum(abs(x)**2 for x in z))
    return tuple(x/n for x in z)


def encode(alpha):
    v=[0j]*27
    v[0]=alpha[0]; v[13]=alpha[1]; v[26]=alpha[2]
    return v


def shift_site(v,site,shift):
    out=[0j]*27
    for idx,amp in enumerate(v):
        if amp==0: continue
        d0=idx//9; d1=(idx//3)%3; d2=idx%3
        ds=[d0,d1,d2]; ds[site]=mod3(ds[site]+shift)
        j=ds[0]*9+ds[1]*3+ds[2]
        out[j]+=amp
    return out


def fidelity(a,b):
    inn=sum(x.conjugate()*y for x,y in zip(a,b))
    return abs(inn)**2


def contract_checks():
    rng=random.Random(963)
    min_fid=1.0
    for _ in range(50):
        psi=encode(random_qutrit(rng))
        for site in range(3):
            for sh in (1,2):
                err=shift_site(psi,site,sh)
                f=[0,0,0]; f[site]=sh
                syn=syndrome2(tuple(f)); corr=DECODER[syn]
                assert corr is not None
                cs,inv=corr
                rec=shift_site(err,cs,inv)
                min_fid=min(min_fid,fidelity(psi,rec))
    marked=controller_state(True); unmarked=controller_state(False)
    return {
        "balanced_trinary_basis_exact": BASIS==(-1,0,+1),
        "arbitrary_qutrit_single_shift_min_fidelity": min_fid,
        "all_arbitrary_state_repairs_unit_fidelity": min_fid>1-1e-12,
        "controller_zero_is_equal_369_superposition": all(abs(abs(x)**2-1/3)<1e-12 for x in CTRL0),
        "marked_p9": abs(marked[2])**2,
        "unmarked_p9": abs(unmarked[2])**2,
        "marked_p9_above_trigger": abs(marked[2])**2>0.9,
        "unmarked_p9_below_trigger": abs(unmarked[2])**2<0.9,
    }


def main():
    arms=("bare","conventional","btbc_superposition","btbc_no9","perfect")
    rows=[]; pooled={a:{"fail":0,"false_corr":0,"state9":0} for a in arms}
    for pi,p in enumerate(NOISE_POINTS):
        for ai,arm in enumerate(arms):
            rng=random.Random(SEED+100000*pi+1000*ai)
            m=run_arm(arm,p,rng)
            r={"arm":arm,"p_data":p,"p_meas":p,"trials":TRIALS,"cycles":CYCLES,
               "logical_failures":m.fail,"logical_failure_rate":m.fail/TRIALS,
               "corrections":m.corrections,"false_corrections":m.false_corr,
               "state9_triggers":m.state9,"rejected_inconsistent":m.rejected_inconsistent}
            rows.append(r)
            pooled[arm]["fail"]+=m.fail; pooled[arm]["false_corr"]+=m.false_corr; pooled[arm]["state9"]+=m.state9
    byp={p:{r["arm"]:r for r in rows if r["p_data"]==p} for p in NOISE_POINTS}
    checks=contract_checks()
    primary={
      "native_statevector_contract_passes": checks["all_arbitrary_state_repairs_unit_fidelity"] and checks["controller_zero_is_equal_369_superposition"] and checks["marked_p9_above_trigger"] and checks["unmarked_p9_below_trigger"],
      "btbc_beats_no9_at_least_3_of_4": sum(byp[p]["btbc_superposition"]["logical_failure_rate"]<byp[p]["btbc_no9"]["logical_failure_rate"] for p in NOISE_POINTS)>=3,
      "btbc_not_worse_than_conventional_at_least_3_of_4": sum(byp[p]["btbc_superposition"]["logical_failure_rate"]<=byp[p]["conventional"]["logical_failure_rate"] for p in NOISE_POINTS)>=3,
      "pooled_btbc_not_worse_than_conventional": pooled["btbc_superposition"]["fail"]<=pooled["conventional"]["fail"],
      "btbc_false_corrections_below_conventional": pooled["btbc_superposition"]["false_corr"]<pooled["conventional"]["false_corr"],
      "state9_exercised": pooled["btbc_superposition"]["state9"]>0,
    }
    primary["all_primary_criteria"]=all(primary.values())
    result={
      "frozen_config":{"basis":["|-1>","|0>","|+1>"],"trials":TRIALS,"cycles":CYCLES,"noise_points":list(NOISE_POINTS),"seed":SEED,"timing_history_used":False},
      "controller":{"zero":"equal statevector superposition over |3>,|6>,|9>","9":"same-cycle consistency oracle plus diffusion; trigger if P9>0.9","binary_fallback":"represented by applying the decoded inverse shift only after immediate 9 trigger"},
      "contract_checks":checks,"primary":primary,"pooled":pooled,"rows":rows,
      "scope_limit":"Statevector contract + stochastic generalized-X qutrit shift simulation. No generalized-Z phase errors and no hardware-level coherent syndrome-extraction circuit yet."
    }
    out=Path("artifacts/btbc_native_qutrit_superposition_results.json"); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    if not primary["all_primary_criteria"]:
        raise SystemExit("predeclared non-temporal superposition criteria did not all pass")

if __name__=="__main__": main()
