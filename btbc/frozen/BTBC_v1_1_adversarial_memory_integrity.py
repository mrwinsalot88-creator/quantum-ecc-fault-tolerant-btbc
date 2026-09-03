#!/usr/bin/env python3
"""BTBC v1.1 — Adversarial Adaptive Memory Integrity

Original project implementation derived from BTBC v1 code developed in this project.
No third-party memory-system source code is used.

Upgrade from v1:
  * Layer 9 no longer stops at ESCALATE.
  * ESCALATE invokes a distinct second-stage robust reviewer.
  * The reviewer separates direct, relational, and temporal evidence families,
    trims low-trust relational evidence, detects change-points, and changes a
    memory only when independent evidence families agree.
  * Adversarial test worlds include burst faults, targeted relation sabotage,
    source-trust spoofing, stale-memory carryover, contradiction injection,
    and legitimate identity/state changes.

This is classical structured-memory research code, not quantum error correction.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple
import json
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
SYMS = np.array([-1, 0, 1], dtype=np.int8)
SEED = 369_112026

@dataclass(frozen=True)
class Policy:
    repair_conf: float = 0.65
    quarantine_conf: float = 0.22
    max_global_relation_mismatch: float = 0.40
    min_source_trust: float = 0.25
    max_temporal_disagreement: float = 1.01
    passes: int = 3
    review_min_margin: float = 0.24
    review_min_support_families: int = 2
    review_min_relation_weight: float = 0.48
    review_change_guard: float = 0.58

@dataclass
class Counters:
    score_ops: int = 0
    policy_ops: int = 0
    review_ops: int = 0
    repairs_stage1: int = 0
    repairs_stage2: int = 0
    keeps: int = 0
    quarantines: int = 0
    escalations: int = 0
    review_rejects: int = 0


def relation(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return 1 if a == b else -1


def make_edges(rng, n, degree=4):
    edges=set()
    target=min(n*(n-1)//2, n*degree//2)
    for i in range(n):
        edges.add(tuple(sorted((i,(i+1)%n))))
    while len(edges)<target:
        i,j=rng.choice(n,2,replace=False)
        edges.add(tuple(sorted((int(i),int(j)))))
    return sorted(edges)


def incident_lists(n, edges):
    inc=[[] for _ in range(n)]
    for k,(i,j) in enumerate(edges):
        inc[i].append((k,j)); inc[j].append((k,i))
    return inc


def other_values(rng,a):
    out=a.copy()
    for idx in np.ndindex(a.shape):
        choices=SYMS[SYMS != int(a[idx])]
        out[idx]=rng.choice(choices)
    return out


def generate_sequence(rng,tmax,n,persistence,shock=False,identity_change=False):
    x=np.empty((tmax,n),dtype=np.int8)
    x[0]=rng.choice(SYMS,size=n)
    legit=np.zeros_like(x,dtype=bool)
    for t in range(1,tmax):
        x[t]=x[t-1]
        changed=rng.random(n)>persistence
        if changed.any(): x[t,changed]=other_values(rng,x[t,changed])
    if shock or identity_change:
        s=tmax//2
        frac=.65 if shock else .35
        changed=rng.random(n)<frac
        if changed.any():
            x[s,changed]=other_values(rng,x[s-1,changed]); legit[s,changed]=True
        for t in range(s+1,tmax):
            x[t]=x[t-1]
            changed2=rng.random(n)>persistence
            if changed2.any(): x[t,changed2]=other_values(rng,x[t,changed2])
    return x,legit


def encode_relations(x,edges):
    out=np.empty((x.shape[0],len(edges)),dtype=np.int8)
    for t in range(x.shape[0]):
        for k,(i,j) in enumerate(edges): out[t,k]=relation(int(x[t,i]),int(x[t,j]))
    return out


def make_provenance(rng,shape,mean_trust=.82):
    concentration=10.0; a=max(.5,mean_trust*concentration); b=max(.5,(1-mean_trust)*concentration)
    return np.clip(rng.beta(a,b,size=shape),.05,.995)


def corrupt_base(rng,truth,base_p,trust,burst=False):
    denom=max(1e-6,np.mean(1-trust))
    risk=base_p*(.40+1.20*(1-trust)/denom)
    risk=np.clip(risk,0,min(.95,base_p*3.5+.02))
    mask=rng.random(truth.shape)<risk
    if burst and truth.ndim==2 and truth.shape[0]>=4:
        start=int(rng.integers(1,truth.shape[0]-2)); width=int(rng.integers(1,min(4,truth.shape[0]-start)+1))
        cols=rng.random(truth.shape[1])<.35
        if cols.any(): mask[start:start+width,cols] |= rng.random((width,int(cols.sum()))) < min(.9,base_p*4+.15)
    out=truth.copy()
    if mask.any(): out[mask]=other_values(rng,out[mask])
    return out,mask


def inject_adversary(rng,obs,obs_r,state_trust,rel_trust,truth,rel_truth,cfg):
    """Inject faults without giving truth to the decoder; truth is used only to construct test corruption."""
    attack_cells=np.zeros_like(obs,dtype=bool); attack_rels=np.zeros_like(obs_r,dtype=bool)
    mode=cfg['attack']
    if mode=='none': return obs,obs_r,state_trust,rel_trust,attack_cells,attack_rels
    tmax,n=obs.shape
    if mode in ('poison','mixed'):
        # high-trust spoof: malicious observations look trustworthy
        t=int(rng.integers(1,tmax-1)); cols=rng.random(n)<.28
        if cols.any():
            obs[t,cols]=other_values(rng,truth[t,cols]); state_trust[t,cols]=np.maximum(state_trust[t,cols],.94); attack_cells[t,cols]=True
    if mode in ('relations','mixed'):
        t=int(rng.integers(1,tmax-1)); cols=rng.random(obs_r.shape[1])<.40
        if cols.any():
            obs_r[t,cols]=other_values(rng,rel_truth[t,cols]); rel_trust[t,cols]=np.maximum(rel_trust[t,cols],.90); attack_rels[t,cols]=True
    if mode in ('stale','mixed'):
        # stale carryover: copy old values over a later window after legitimate evolution
        start=max(2,tmax//2); width=min(3,tmax-start); cols=rng.random(n)<.25
        if width>0 and cols.any():
            stale=truth[start-2,cols].copy()
            for t in range(start,start+width):
                obs[t,cols]=stale; attack_cells[t,cols]=obs[t,cols]!=truth[t,cols]
    if mode in ('contradict','mixed'):
        # opposing pockets across adjacent timestamps
        t=max(1,tmax//2-1); cols=rng.random(n)<.20
        if cols.any():
            obs[t,cols]=other_values(rng,truth[t,cols]); obs[t+1,cols]=other_values(rng,truth[t+1,cols])
            attack_cells[t,cols]=True; attack_cells[t+1,cols]=True
    return obs,obs_r,state_trust,rel_trust,attack_cells,attack_rels


def global_relation_mismatch(obs,obs_r,edges): return float(np.mean(encode_relations(obs,edges)!=obs_r))


def temporal_disagreement(cur,t,i):
    vals=[]
    if t>0: vals.append(int(cur[t-1,i])!=int(cur[t,i]))
    if t+1<cur.shape[0]: vals.append(int(cur[t+1,i])!=int(cur[t,i]))
    return float(np.mean(vals)) if vals else 0.0


def candidate_scores(obs,obs_r,state_trust,rel_trust,cur,inc,t,i,counters):
    scores=[]; dt=float(state_trust[t,i])
    for cand in (-1,0,1):
        s=1.15*dt*(cand==int(obs[t,i])); counters.score_ops+=1
        for k,j in inc[i]:
            rw=float(rel_trust[t,k]); s+=.95*rw*(relation(cand,int(cur[t,j]))==int(obs_r[t,k])); counters.score_ops+=1
        if t>0: s+=.42*(cand==int(cur[t-1,i])); counters.score_ops+=1
        if t+1<cur.shape[0]: s+=.30*(cand==int(cur[t+1,i])); counters.score_ops+=1
        scores.append(float(s))
    return np.array(scores)


def confidence(scores):
    order=np.sort(scores); margin=float(order[-1]-order[-2]); span=float(max(1e-9,order[-1]-order[0]))
    return float(np.clip(margin/max(1.0,span),0,1))


def decode_candidate(obs,obs_r,state_trust,rel_trust,edges,passes,counters):
    cur=obs.copy(); inc=incident_lists(obs.shape[1],edges); conf=np.zeros(obs.shape,float)
    for _ in range(passes):
        new=cur.copy()
        for t in range(obs.shape[0]):
            for i in range(obs.shape[1]):
                sc=candidate_scores(obs,obs_r,state_trust,rel_trust,cur,inc,t,i,counters)
                best=np.flatnonzero(sc==sc.max()); oi=int(obs[t,i])+1
                choice=oi if oi in best else (1 if 1 in best else int(best[0]))
                new[t,i]=choice-1; conf[t,i]=confidence(sc)
        cur=new
    return cur,conf


def stage1_route(obs,proposed,conf,state_trust,rel_mismatch,policy,counters):
    out=obs.copy(); action=np.full(obs.shape,'KEEP',dtype=object)
    for t in range(obs.shape[0]):
        for i in range(obs.shape[1]):
            counters.policy_ops+=1
            if proposed[t,i]==obs[t,i]: counters.keeps+=1; continue
            td=temporal_disagreement(obs,t,i); trust=float(state_trust[t,i]); c=float(conf[t,i])
            bad_context=rel_mismatch>policy.max_global_relation_mismatch; low_source=trust<policy.min_source_trust
            unstable=td>policy.max_temporal_disagreement
            if (not bad_context) and (not low_source) and (not unstable) and c>=policy.repair_conf:
                out[t,i]=proposed[t,i]; action[t,i]='REPAIR1'; counters.repairs_stage1+=1
            elif c<=policy.quarantine_conf:
                action[t,i]='QUARANTINE'; counters.quarantines+=1
            else:
                action[t,i]='ESCALATE'; counters.escalations+=1
    return out,action


def family_votes(obs,obs_r,state_trust,rel_trust,cur,inc,t,i,policy,counters):
    """Return score vectors for independent evidence families: direct, relations, time."""
    direct=np.zeros(3,float); rel=np.zeros(3,float); temp=np.zeros(3,float)
    oi=int(obs[t,i])+1; direct[oi]=float(state_trust[t,i]); counters.review_ops+=3
    # robust relation family: ignore low-weight edges and cap each edge contribution
    used=0
    for k,j in inc[i]:
        w=float(rel_trust[t,k])
        if w<policy.review_min_relation_weight: continue
        used+=1
        for qi,cand in enumerate((-1,0,1)):
            rel[qi]+=min(.85,w)*(relation(cand,int(cur[t,j]))==int(obs_r[t,k])); counters.review_ops+=1
    if used: rel/=used
    # temporal family with change guard: equal neighbors are strong; disagreeing neighbors weak
    neighbors=[]
    if t>0: neighbors.append(int(cur[t-1,i]))
    if t+1<cur.shape[0]: neighbors.append(int(cur[t+1,i]))
    if neighbors:
        if len(neighbors)==2 and neighbors[0]!=neighbors[1]:
            # likely transition region: do not let time erase a plausible new state
            for v in neighbors: temp[v+1]+=.25
        else:
            for v in neighbors: temp[v+1]+=1.0/len(neighbors)
        counters.review_ops+=3*len(neighbors)
    return direct,rel,temp


def second_stage_review(obs,obs_r,state_trust,rel_trust,edges,base_out,actions,policy,counters):
    out=base_out.copy(); act=actions.copy(); inc=incident_lists(obs.shape[1],edges)
    # use stage-1 output as context, but review only escalated cells
    cur=base_out.copy()
    for t in range(obs.shape[0]):
        for i in range(obs.shape[1]):
            if actions[t,i] != 'ESCALATE': continue
            direct,rel,temp=family_votes(obs,obs_r,state_trust,rel_trust,cur,inc,t,i,policy,counters)
            # normalized combined score; relations get most weight only when locally coherent
            combo=.80*direct + 1.35*rel + .90*temp
            order=np.argsort(combo); best=int(order[-1]); second=int(order[-2])
            margin=float(combo[best]-combo[second])
            proposed=best-1; observed=int(obs[t,i])
            # count evidence families whose own winner supports proposed
            supports=0
            for fam in (direct,rel,temp):
                if fam.sum()>0 and int(np.argmax(fam))==best: supports+=1
            # change-point guard: if past/future disagree, require stronger non-temporal support
            transition=(t>0 and t+1<obs.shape[0] and int(cur[t-1,i])!=int(cur[t+1,i]))
            if transition:
                enough = supports>=2 and margin >= max(policy.review_change_guard, policy.review_min_margin)
            else:
                enough = supports>=policy.review_min_support_families and margin>=policy.review_min_margin
            if proposed!=observed and enough:
                out[t,i]=proposed; act[t,i]='REPAIR2'; counters.repairs_stage2+=1
            else:
                act[t,i]='REVIEW_KEEP'; counters.review_rejects+=1
    return out,act


def btbc_v11(obs,obs_r,state_trust,rel_trust,edges,policy):
    ctr=Counters(); rm=global_relation_mismatch(obs,obs_r,edges)
    proposed,conf=decode_candidate(obs,obs_r,state_trust,rel_trust,edges,policy.passes,ctr)
    stage1,actions=stage1_route(obs,proposed,conf,state_trust,rm,policy,ctr)
    final,actions=second_stage_review(obs,obs_r,state_trust,rel_trust,edges,stage1,actions,policy,ctr)
    return final,actions,conf,rm,ctr


def raw_error(x,truth): return float(np.mean(x!=truth))


def make_world(rng,cfg):
    edges=make_edges(rng,cfg['n'],cfg['degree'])
    truth,legit=generate_sequence(rng,cfg['tmax'],cfg['n'],cfg['persistence'],cfg['shock'],cfg['identity_change'])
    rel_truth=encode_relations(truth,edges)
    st=make_provenance(rng,truth.shape,cfg['state_trust']); rt=make_provenance(rng,rel_truth.shape,cfg['rel_trust'])
    obs,_=corrupt_base(rng,truth,cfg['p_state'],st,cfg['burst']); obs_r,_=corrupt_base(rng,rel_truth,cfg['p_rel'],rt,cfg['burst'])
    obs,obs_r,st,rt,attack_cells,attack_rels=inject_adversary(rng,obs,obs_r,st,rt,truth,rel_truth,cfg)
    return edges,truth,legit,rel_truth,obs,obs_r,st,rt,attack_cells,attack_rels


def eval_world(rng,cfg,policy):
    edges,truth,legit,rel_truth,obs,obs_r,st,rt,attack_cells,attack_rels=make_world(rng,cfg)
    repaired,actions,conf,rm,ctr=btbc_v11(obs,obs_r,st,rt,edges,policy)
    changed=np.isin(actions,['REPAIR1','REPAIR2'])
    true_rep=changed&(obs!=truth)&(repaired==truth)
    false_corr=changed&(obs==truth)&(repaired!=truth)
    attack_bad=attack_cells&(obs!=truth)
    attack_fixed=attack_bad&(repaired==truth)
    legit_damage=legit&(repaired!=truth)
    return {
        'raw_error':raw_error(obs,truth),'btbc_error':raw_error(repaired,truth),
        'delta_error':raw_error(repaired,truth)-raw_error(obs,truth),
        'repairs1':int((actions=='REPAIR1').sum()),'repairs2':int((actions=='REPAIR2').sum()),
        'true_repairs':int(true_rep.sum()),'false_corrections':int(false_corr.sum()),
        'quarantines':int((actions=='QUARANTINE').sum()),'escalations':int((actions=='ESCALATE').sum()),
        'review_keeps':int((actions=='REVIEW_KEEP').sum()),'corrupted_cells':int((obs!=truth).sum()),
        'attack_bad_cells':int(attack_bad.sum()),'attack_fixed_cells':int(attack_fixed.sum()),
        'legit_change_cells':int(legit.sum()),'legit_change_damage':int(legit_damage.sum()),
        'relation_mismatch':rm,'mean_confidence':float(np.mean(conf)),
        'ops':ctr.score_ops+ctr.policy_ops+ctr.review_ops,
    }


def scenario_grid():
    rows=[]
    # 144 scenarios: enough breadth while keeping runtime modest.
    for persistence in (.80,.94,.98):
        for p_state in (.03,.12,.22):
            for p_rel in (.03,.18,.38):
                for attack in ('none','poison','relations','stale','mixed'):
                    # alternate legitimate-change/burst dimensions deterministically to avoid cartesian explosion
                    idx=len(rows)
                    rows.append(dict(tmax=14,n=16,degree=4,persistence=persistence,
                                     shock=(idx%3==0),identity_change=(idx%4==0),burst=(idx%2==0),
                                     p_state=p_state,p_rel=p_rel,state_trust=.82,rel_trust=.82,attack=attack))
    return rows


def locked_test(policy):
    rng=np.random.default_rng(SEED+99_999); rec=[]
    for sid,cfg in enumerate(scenario_grid()):
        for world in range(4): rec.append({**cfg,'scenario_id':sid,'world':world,**eval_world(rng,cfg,policy)})
    return pd.DataFrame(rec)


def summarize(df):
    cells=len(df)*14*16; repairs=int(df.repairs1.sum()+df.repairs2.sum())
    precision=df.true_repairs.sum()/max(1,repairs); recovery=df.true_repairs.sum()/max(1,df.corrupted_cells.sum())
    nonworse=(df.groupby('scenario_id').btbc_error.mean() <= df.groupby('scenario_id').raw_error.mean()+1e-12).mean()
    attack_recovery=df.attack_fixed_cells.sum()/max(1,df.attack_bad_cells.sum())
    return {
        'worlds':int(len(df)),'scenarios':int(df.scenario_id.nunique()),
        'raw_error_mean':float(df.raw_error.mean()),'btbc_error_mean':float(df.btbc_error.mean()),
        'relative_error_reduction':float((df.raw_error.mean()-df.btbc_error.mean())/max(1e-12,df.raw_error.mean())),
        'repair_precision':float(precision),'corruption_recovery_fraction':float(recovery),
        'false_correction_rate_per_cell':float(df.false_corrections.sum()/cells),
        'scenario_nonworse_fraction':float(nonworse),
        'stage2_repairs':int(df.repairs2.sum()),'stage1_repairs':int(df.repairs1.sum()),
        'attack_recovery_fraction':float(attack_recovery),
        'legitimate_change_damage_rate':float(df.legit_change_damage.sum()/max(1,df.legit_change_cells.sum())),
        'mean_ops_per_world':float(df.ops.mean()),
    }


def main():
    policy=Policy()
    df=locked_test(policy); summary=summarize(df)
    df.to_csv(OUT/'BTBC_v1_1_adversarial_locked_results.csv',index=False)
    (OUT/'BTBC_v1_1_summary.json').write_text(json.dumps(summary,indent=2))
    (OUT/'BTBC_v1_1_policy.json').write_text(json.dumps(asdict(policy),indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
