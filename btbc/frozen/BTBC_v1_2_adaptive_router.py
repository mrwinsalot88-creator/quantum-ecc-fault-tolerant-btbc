#!/usr/bin/env python3
"""BTBC v1.2 — Learned SAFE/RECOVERY Layer-0 Router

Original BTBC project code. No third-party memory-system source code is copied.
Uses standard scikit-learn DecisionTreeClassifier only as the learned routing primitive.

Purpose
-------
BTBC v1.1 made Layer 9 more aggressive by adding a second-stage reviewer. That
improved recovery but introduced more false corrections. v1.2 adds a learned
Layer-0 gate that decides, for each ESCALATE cell, whether to remain in SAFE
mode (keep/quarantine) or allow RECOVERY mode (invoke the v1.1 reviewer).

Training/calibration uses synthetic worlds with truth labels. The locked test
uses fresh random seeds and a frozen router. Runtime routing uses only observable
features; ground truth is never supplied to the decoder/router.

This is classical structured-memory research code, not quantum error correction.
"""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import importlib.util, json, sys
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, export_text

OUT = Path(__file__).resolve().parent
BASE_PATH = OUT / 'BTBC_v1_1_adversarial_memory_integrity.py'
SEED = 369_120026

spec = importlib.util.spec_from_file_location('btbc_v11', BASE_PATH)
v11 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v11
spec.loader.exec_module(v11)

FEATURES = [
    'confidence','state_trust','global_relation_mismatch','local_relation_mismatch',
    'local_relation_trust','temporal_disagreement','neighbor_agreement','rel_support_margin'
]


def observable_features(obs, obs_r, state_trust, rel_trust, edges, conf, rm, t, i):
    inc = v11.incident_lists(obs.shape[1], edges)[i]
    mism=[]; trusts=[]; supports=np.zeros(3,float)
    for k,j in inc:
        trusts.append(float(rel_trust[t,k]))
        pred=v11.relation(int(obs[t,i]), int(obs[t,j]))
        mism.append(float(pred != int(obs_r[t,k])))
        w=float(rel_trust[t,k])
        for qi,cand in enumerate((-1,0,1)):
            supports[qi] += w * (v11.relation(cand,int(obs[t,j])) == int(obs_r[t,k]))
    if len(supports):
        sr=np.sort(supports)
        support_margin=float(sr[-1]-sr[-2]) if len(sr)>1 else 0.0
    else: support_margin=0.0
    neigh=[]
    if t>0: neigh.append(int(obs[t-1,i]))
    if t+1<obs.shape[0]: neigh.append(int(obs[t+1,i]))
    if len(neigh)==2: neighbor_agreement=float(neigh[0]==neigh[1])
    elif len(neigh)==1: neighbor_agreement=0.5
    else: neighbor_agreement=0.0
    return {
        'confidence':float(conf[t,i]),
        'state_trust':float(state_trust[t,i]),
        'global_relation_mismatch':float(rm),
        'local_relation_mismatch':float(np.mean(mism)) if mism else 0.0,
        'local_relation_trust':float(np.mean(trusts)) if trusts else 0.0,
        'temporal_disagreement':float(v11.temporal_disagreement(obs,t,i)),
        'neighbor_agreement':neighbor_agreement,
        'rel_support_margin':support_margin,
    }


def get_branches(obs,obs_r,st,rt,edges,policy):
    ctr=v11.Counters(); rm=v11.global_relation_mismatch(obs,obs_r,edges)
    proposed,conf=v11.decode_candidate(obs,obs_r,st,rt,edges,policy.passes,ctr)
    safe,actions=v11.stage1_route(obs,proposed,conf,st,rm,policy,ctr)
    recovery,rec_actions=v11.second_stage_review(obs,obs_r,st,rt,edges,safe,actions,policy,ctr)
    return safe,actions,recovery,rec_actions,conf,rm,ctr


def collect_training_rows(rng, configs, worlds_each=1):
    policy=v11.Policy(); rows=[]
    for sid,cfg in enumerate(configs):
        for w in range(worlds_each):
            edges,truth,legit,rel_truth,obs,obs_r,st,rt,attack_cells,attack_rels=v11.make_world(rng,cfg)
            safe,actions,recovery,rec_actions,conf,rm,ctr=get_branches(obs,obs_r,st,rt,edges,policy)
            for t,i in zip(*np.where(actions=='ESCALATE')):
                feat=observable_features(obs,obs_r,st,rt,edges,conf,rm,int(t),int(i))
                safe_ok = int(safe[t,i] == truth[t,i])
                rec_ok = int(recovery[t,i] == truth[t,i])
                rec_changed = int(recovery[t,i] != safe[t,i])
                # Positive only when RECOVERY fixes something SAFE leaves wrong.
                # Negative includes harmful recovery and no-benefit review.
                target = int(rec_ok > safe_ok)
                harmful = int(rec_ok < safe_ok)
                rows.append({**feat,'target':target,'harmful':harmful,'rec_changed':rec_changed,
                             'sid':sid,'world':w})
    return pd.DataFrame(rows)


def train_router():
    configs=v11.scenario_grid()
    rng=np.random.default_rng(SEED+1000)
    # Separate calibration and validation worlds/seeds.
    train=collect_training_rows(rng,configs,worlds_each=1)
    vrng=np.random.default_rng(SEED+2000)
    val=collect_training_rows(vrng,configs,worlds_each=1)
    X=train[FEATURES].to_numpy(); y=train.target.to_numpy()
    clf=DecisionTreeClassifier(max_depth=5,min_samples_leaf=24,class_weight={0:1.0,1:2.3},random_state=SEED)
    clf.fit(X,y)
    # Threshold chosen on validation to reward useful recovery and punish harmful routing.
    p=clf.predict_proba(val[FEATURES].to_numpy())[:,1]
    thresholds=np.linspace(.15,.85,29)
    scored=[]
    for th in thresholds:
        route=p>=th
        benefit=int((route & (val.target.values==1)).sum())
        harm=int((route & (val.harmful.values==1)).sum())
        calls=int(route.sum())
        # utility: fixes - 6*new harms - small review cost
        utility=benefit - 6.0*harm - 0.015*calls
        scored.append((utility,float(th),benefit,harm,calls))
    scored.sort(reverse=True)
    return clf,scored[0],train,val


def btbc_v12(obs,obs_r,st,rt,edges,policy,router,threshold):
    safe,actions,recovery,rec_actions,conf,rm,ctr=get_branches(obs,obs_r,st,rt,edges,policy)
    out=safe.copy(); final_actions=actions.copy(); routed=0; blocked=0
    for t,i in zip(*np.where(actions=='ESCALATE')):
        feat=observable_features(obs,obs_r,st,rt,edges,conf,rm,int(t),int(i))
        x=np.array([[feat[k] for k in FEATURES]])
        prob=float(router.predict_proba(x)[0,1])
        if prob>=threshold:
            routed+=1
            out[t,i]=recovery[t,i]
            final_actions[t,i]=rec_actions[t,i]
        else:
            blocked+=1
            final_actions[t,i]='SAFE_KEEP'
    return out,final_actions,conf,rm,ctr,routed,blocked


def evaluate_world(rng,cfg,policy,router,threshold):
    edges,truth,legit,rel_truth,obs,obs_r,st,rt,attack_cells,attack_rels=v11.make_world(rng,cfg)
    safe,actions,recovery,rec_actions,conf,rm,ctr=get_branches(obs,obs_r,st,rt,edges,policy)
    adaptive,aa,_,_,_,routed,blocked=btbc_v12(obs,obs_r,st,rt,edges,policy,router,threshold)
    def err(x): return float(np.mean(x!=truth))
    changed=adaptive!=obs
    true_rep=changed&(obs!=truth)&(adaptive==truth)
    false_corr=changed&(obs==truth)&(adaptive!=truth)
    safe_changed=safe!=obs
    rec_changed=recovery!=obs
    safe_true=safe_changed&(obs!=truth)&(safe==truth)
    rec_true=rec_changed&(obs!=truth)&(recovery==truth)
    safe_false=safe_changed&(obs==truth)&(safe!=truth)
    rec_false=rec_changed&(obs==truth)&(recovery!=truth)
    attack_bad=attack_cells&(obs!=truth)
    attack_fixed=attack_bad&(adaptive==truth)
    legit_damage=legit&(adaptive!=truth)
    return {
        'raw_error':err(obs),'safe_error':err(safe),'recovery_error':err(recovery),'adaptive_error':err(adaptive),
        'adaptive_delta':err(adaptive)-err(obs),
        'true_repairs':int(true_rep.sum()),'false_corrections':int(false_corr.sum()),
        'changed_cells':int(changed.sum()),'corrupted_cells':int((obs!=truth).sum()),
        'safe_true_repairs':int(safe_true.sum()),'safe_false_corrections':int(safe_false.sum()),'safe_changed_cells':int(safe_changed.sum()),
        'recovery_true_repairs':int(rec_true.sum()),'recovery_false_corrections':int(rec_false.sum()),'recovery_changed_cells':int(rec_changed.sum()),
        'attack_bad_cells':int(attack_bad.sum()),'attack_fixed_cells':int(attack_fixed.sum()),
        'legit_change_cells':int(legit.sum()),'legit_change_damage':int(legit_damage.sum()),
        'router_recovery_calls':int(routed),'router_safe_blocks':int(blocked),
        'escalations':int((actions=='ESCALATE').sum()),'relation_mismatch':float(rm),
        'mean_confidence':float(np.mean(conf)),
    }


def locked_test(router,threshold):
    policy=v11.Policy(); rng=np.random.default_rng(SEED+99_999); rec=[]
    for sid,cfg in enumerate(v11.scenario_grid()):
        for world in range(4):
            rec.append({**cfg,'scenario_id':sid,'world':world,
                        **evaluate_world(rng,cfg,policy,router,threshold)})
    return pd.DataFrame(rec)


def summarize(df):
    cells=len(df)*14*16
    def reduction(col): return float((df.raw_error.mean()-df[col].mean())/df.raw_error.mean())
    repairs=int(df.changed_cells.sum())
    precision=float(df.true_repairs.sum()/max(1,repairs))
    safe_precision=float(df.safe_true_repairs.sum()/max(1,df.safe_changed_cells.sum()))
    rec_precision=float(df.recovery_true_repairs.sum()/max(1,df.recovery_changed_cells.sum()))
    nonworse=float((df.groupby('scenario_id').adaptive_error.mean() <=
                    df.groupby('scenario_id').raw_error.mean()+1e-12).mean())
    safe_nonworse=float((df.groupby('scenario_id').safe_error.mean() <= df.groupby('scenario_id').raw_error.mean()+1e-12).mean())
    rec_nonworse=float((df.groupby('scenario_id').recovery_error.mean() <= df.groupby('scenario_id').raw_error.mean()+1e-12).mean())
    return {
        'worlds':int(len(df)),'scenarios':int(df.scenario_id.nunique()),
        'raw_error_mean':float(df.raw_error.mean()),
        'safe_error_mean':float(df.safe_error.mean()),
        'recovery_v11_error_mean':float(df.recovery_error.mean()),
        'adaptive_v12_error_mean':float(df.adaptive_error.mean()),
        'safe_relative_error_reduction':reduction('safe_error'),
        'recovery_v11_relative_error_reduction':reduction('recovery_error'),
        'adaptive_v12_relative_error_reduction':reduction('adaptive_error'),
        'safe_repair_precision':safe_precision,
        'recovery_v11_repair_precision':rec_precision,
        'adaptive_repair_precision':precision,
        'adaptive_corruption_recovery_fraction':float(df.true_repairs.sum()/max(1,df.corrupted_cells.sum())),
        'safe_false_correction_rate_per_cell':float(df.safe_false_corrections.sum()/cells),
        'recovery_v11_false_correction_rate_per_cell':float(df.recovery_false_corrections.sum()/cells),
        'adaptive_false_correction_rate_per_cell':float(df.false_corrections.sum()/cells),
        'safe_scenario_nonworse_fraction':safe_nonworse,
        'recovery_v11_scenario_nonworse_fraction':rec_nonworse,
        'adaptive_scenario_nonworse_fraction':nonworse,
        'router_recovery_fraction_of_escalations':float(df.router_recovery_calls.sum()/max(1,df.escalations.sum())),
        'attack_recovery_fraction':float(df.attack_fixed_cells.sum()/max(1,df.attack_bad_cells.sum())),
        'legitimate_change_damage_rate':float(df.legit_change_damage.sum()/max(1,df.legit_change_cells.sum())),
    }


def main():
    router,best,train,val=train_router(); utility,threshold,benefit,harm,calls=best
    test=locked_test(router,threshold); summary=summarize(test)
    test.to_csv(OUT/'BTBC_v1_2_adaptive_locked_results.csv',index=False)
    (OUT/'BTBC_v1_2_summary.json').write_text(json.dumps(summary,indent=2))
    model_info={
        'features':FEATURES,'threshold':threshold,'validation_utility':utility,
        'validation_beneficial_routes':benefit,'validation_harmful_routes':harm,
        'validation_recovery_calls':calls,'train_escalated_cells':int(len(train)),
        'validation_escalated_cells':int(len(val)),
        'tree':export_text(router,feature_names=FEATURES),
        'base_policy':asdict(v11.Policy()),
    }
    (OUT/'BTBC_v1_2_router.json').write_text(json.dumps(model_info,indent=2))
    print('ROUTER threshold',threshold,'validation utility',utility,'benefit',benefit,'harm',harm,'calls',calls)
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
