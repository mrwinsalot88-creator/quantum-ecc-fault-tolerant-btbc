#!/usr/bin/env python3
"""BTBC v1.3 — Risk-Calibrated Adaptive Layer-0 Router

Original BTBC project research code. No third-party agent-memory implementation code is copied.
Uses standard scikit-learn RandomForestClassifier as a generic routing primitive.

Upgrade over v1.2
-----------------
v1.2 learned a binary question: can RECOVERY help an ESCALATE case?
v1.3 learns three outcomes for each escalation:
  BENEFIT  - recovery fixes a value SAFE leaves wrong
  NEUTRAL  - recovery changes nothing important
  HARM     - recovery breaks a value SAFE had right

Layer 0 estimates all three probabilities and routes to RECOVERY only when
expected benefit exceeds expected harm by a validation-calibrated margin.
The route threshold is frozen before the locked test.

This is classical structured-memory research code, not quantum error correction.
"""
from __future__ import annotations
from pathlib import Path
import importlib.util, json, sys, zipfile
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

OUT = Path(__file__).resolve().parent
V12_PATH = OUT / 'BTBC_v1_2_adaptive_router.py'
SEED = 369_130026

spec = importlib.util.spec_from_file_location('btbc_v12', V12_PATH)
v12 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v12
spec.loader.exec_module(v12)
v11 = v12.v11
FEATURES = v12.FEATURES


def collect_rows(rng, configs, worlds_each):
    base = v12.collect_training_rows(rng, configs, worlds_each=worlds_each)
    # class: 0 neutral, 1 benefit, 2 harm
    cls = np.zeros(len(base), dtype=int)
    cls[base['target'].to_numpy(dtype=bool)] = 1
    cls[base['harmful'].to_numpy(dtype=bool)] = 2
    base = base.copy(); base['class3'] = cls
    return base


def train_router():
    configs = v11.scenario_grid()[::3]
    train = collect_rows(np.random.default_rng(SEED+1000), configs, worlds_each=1)
    val = collect_rows(np.random.default_rng(SEED+2000), configs, worlds_each=1)

    clf = RandomForestClassifier(
        n_estimators=40,
        max_depth=8,
        min_samples_leaf=10,
        max_features='sqrt',
        class_weight={0:1.0, 1:2.0, 2:5.0},
        random_state=SEED,
        n_jobs=1,
    )
    clf.fit(train[FEATURES].to_numpy(), train['class3'].to_numpy())
    proba = clf.predict_proba(val[FEATURES].to_numpy())
    # Defensive mapping in case a class is absent.
    idx = {int(c):i for i,c in enumerate(clf.classes_)}
    p_b = proba[:, idx.get(1,0)] if 1 in idx else np.zeros(len(val))
    p_h = proba[:, idx.get(2,0)] if 2 in idx else np.zeros(len(val))

    scored=[]
    # Explicitly search a risk/coverage frontier. Penalize harmful recovery heavily.
    for harm_weight in (2.0,3.0,4.0,5.0,6.0,8.0,10.0):
        score = p_b - harm_weight*p_h
        for th in np.linspace(-0.05,0.55,61):
            route = score >= th
            benefit = int((route & (val.class3.values==1)).sum())
            harm = int((route & (val.class3.values==2)).sum())
            calls = int(route.sum())
            # Net cell utility with a small review cost.
            utility = benefit - 7.5*harm - 0.005*calls
            harm_per_call = harm/max(1,calls)
            # prefer low-harm operating points; hard validation guard at 1.5%
            if harm_per_call <= 0.015:
                scored.append((utility, -harm_per_call, benefit, -calls, float(harm_weight), float(th), harm, calls))
    if not scored:
        raise RuntimeError('No validation operating point satisfied the harm guard')
    scored.sort(reverse=True)
    best=scored[0]
    _, neg_hpc, benefit, neg_calls, harm_weight, threshold, harm, calls = best
    return clf, {'harm_weight':harm_weight,'threshold':threshold,
                 'validation_utility':best[0], 'validation_benefit':benefit,
                 'validation_harm':harm,'validation_calls':calls,
                 'validation_harm_per_call':-neg_hpc,
                 'train_rows':len(train),'validation_rows':len(val)}, train, val


def route_probability(clf, feat):
    x=np.array([[feat[k] for k in FEATURES]])
    p=clf.predict_proba(x)[0]
    idx={int(c):i for i,c in enumerate(clf.classes_)}
    return float(p[idx[1]]) if 1 in idx else 0.0, float(p[idx[2]]) if 2 in idx else 0.0


def btbc_v13(obs,obs_r,st,rt,edges,policy,router,operating):
    safe,actions,recovery,rec_actions,conf,rm,ctr=v12.get_branches(obs,obs_r,st,rt,edges,policy)
    out=safe.copy(); final_actions=actions.copy(); routed=blocked=0
    scores=[]
    for t,i in zip(*np.where(actions=='ESCALATE')):
        feat=v12.observable_features(obs,obs_r,st,rt,edges,conf,rm,int(t),int(i))
        pb,ph=route_probability(router,feat)
        score=pb-operating['harm_weight']*ph
        scores.append(score)
        if score >= operating['threshold']:
            routed += 1
            out[t,i]=recovery[t,i]
            final_actions[t,i]=rec_actions[t,i]
        else:
            blocked += 1
            final_actions[t,i]='SAFE_KEEP'
    return out,final_actions,conf,rm,ctr,routed,blocked,(float(np.mean(scores)) if scores else 0.0)


def evaluate_world(rng,cfg,policy,router,operating):
    edges,truth,legit,rel_truth,obs,obs_r,st,rt,attack_cells,attack_rels=v11.make_world(rng,cfg)
    safe,actions,recovery,rec_actions,conf,rm,ctr=v12.get_branches(obs,obs_r,st,rt,edges,policy)
    adaptive,aa,_,_,_,routed,blocked,mean_route_score=btbc_v13(obs,obs_r,st,rt,edges,policy,router,operating)
    def err(x): return float(np.mean(x!=truth))
    def branch_counts(x):
        changed=x!=obs
        true_rep=changed&(obs!=truth)&(x==truth)
        false_corr=changed&(obs==truth)&(x!=truth)
        return changed,true_rep,false_corr
    changed,true_rep,false_corr=branch_counts(adaptive)
    safe_changed,safe_true,safe_false=branch_counts(safe)
    rec_changed,rec_true,rec_false=branch_counts(recovery)
    attack_bad=attack_cells&(obs!=truth); attack_fixed=attack_bad&(adaptive==truth)
    legit_damage=legit&(adaptive!=truth)
    return {
        'raw_error':err(obs),'safe_error':err(safe),'recovery_error':err(recovery),'adaptive_error':err(adaptive),
        'adaptive_delta':err(adaptive)-err(obs),
        'true_repairs':int(true_rep.sum()),'false_corrections':int(false_corr.sum()),'changed_cells':int(changed.sum()),
        'corrupted_cells':int((obs!=truth).sum()),
        'safe_true_repairs':int(safe_true.sum()),'safe_false_corrections':int(safe_false.sum()),'safe_changed_cells':int(safe_changed.sum()),
        'recovery_true_repairs':int(rec_true.sum()),'recovery_false_corrections':int(rec_false.sum()),'recovery_changed_cells':int(rec_changed.sum()),
        'attack_bad_cells':int(attack_bad.sum()),'attack_fixed_cells':int(attack_fixed.sum()),
        'legit_change_cells':int(legit.sum()),'legit_change_damage':int(legit_damage.sum()),
        'router_recovery_calls':int(routed),'router_safe_blocks':int(blocked),'escalations':int((actions=='ESCALATE').sum()),
        'relation_mismatch':float(rm),'mean_confidence':float(np.mean(conf)),'mean_route_score':mean_route_score,
    }


def locked_test(router,operating):
    policy=v11.Policy(); rng=np.random.default_rng(SEED+99_999); rec=[]
    for sid,cfg in enumerate(v11.scenario_grid()):
        for world in range(1):
            rec.append({**cfg,'scenario_id':sid,'world':world,**evaluate_world(rng,cfg,policy,router,operating)})
    return pd.DataFrame(rec)


def summarize(df):
    cells=len(df)*14*16
    def reduction(col): return float((df.raw_error.mean()-df[col].mean())/df.raw_error.mean())
    def precision(tp,changed): return float(tp.sum()/max(1,changed.sum()))
    by=df.groupby('scenario_id').mean(numeric_only=True)
    return {
        'worlds':int(len(df)),'scenarios':int(df.scenario_id.nunique()),
        'raw_error_mean':float(df.raw_error.mean()),'safe_error_mean':float(df.safe_error.mean()),
        'recovery_v11_error_mean':float(df.recovery_error.mean()),'adaptive_v13_error_mean':float(df.adaptive_error.mean()),
        'safe_relative_error_reduction':reduction('safe_error'),'recovery_v11_relative_error_reduction':reduction('recovery_error'),
        'adaptive_v13_relative_error_reduction':reduction('adaptive_error'),
        'safe_repair_precision':precision(df.safe_true_repairs,df.safe_changed_cells),
        'recovery_v11_repair_precision':precision(df.recovery_true_repairs,df.recovery_changed_cells),
        'adaptive_repair_precision':precision(df.true_repairs,df.changed_cells),
        'adaptive_corruption_recovery_fraction':float(df.true_repairs.sum()/max(1,df.corrupted_cells.sum())),
        'safe_false_correction_rate_per_cell':float(df.safe_false_corrections.sum()/cells),
        'recovery_v11_false_correction_rate_per_cell':float(df.recovery_false_corrections.sum()/cells),
        'adaptive_false_correction_rate_per_cell':float(df.false_corrections.sum()/cells),
        'safe_scenario_nonworse_fraction':float((by.safe_error<=by.raw_error+1e-12).mean()),
        'recovery_v11_scenario_nonworse_fraction':float((by.recovery_error<=by.raw_error+1e-12).mean()),
        'adaptive_scenario_nonworse_fraction':float((by.adaptive_error<=by.raw_error+1e-12).mean()),
        'router_recovery_fraction_of_escalations':float(df.router_recovery_calls.sum()/max(1,df.escalations.sum())),
        'attack_recovery_fraction':float(df.attack_fixed_cells.sum()/max(1,df.attack_bad_cells.sum())),
        'legitimate_change_damage_rate':float(df.legit_change_damage.sum()/max(1,df.legit_change_cells.sum())),
    }


def bootstrap_delta(df, n=3000):
    # paired bootstrap over worlds: v1.3 - full recovery error; and v1.3 - raw
    rng=np.random.default_rng(SEED+777)
    arr=df[['adaptive_error','recovery_error','raw_error']].to_numpy()
    vals=[]
    for _ in range(n):
        s=arr[rng.integers(0,len(arr),len(arr))].mean(axis=0)
        vals.append([s[0]-s[1], s[0]-s[2]])
    vals=np.asarray(vals)
    return {
        'adaptive_minus_recovery_mean':float((df.adaptive_error-df.recovery_error).mean()),
        'adaptive_minus_recovery_ci95':[float(x) for x in np.quantile(vals[:,0],[.025,.975])],
        'adaptive_minus_raw_mean':float((df.adaptive_error-df.raw_error).mean()),
        'adaptive_minus_raw_ci95':[float(x) for x in np.quantile(vals[:,1],[.025,.975])],
    }


def main():
    router,operating,train,val=train_router()
    test=locked_test(router,operating); summary=summarize(test); boot=bootstrap_delta(test)
    test.to_csv(OUT/'BTBC_v1_3_risk_calibrated_locked_results.csv',index=False)
    model_info={
        'features':FEATURES, **operating,
        'classes':{'0':'neutral','1':'benefit','2':'harm'},
        'feature_importances':{k:float(v) for k,v in zip(FEATURES,router.feature_importances_)},
        'base_policy':v11.Policy().__dict__,
    }
    (OUT/'BTBC_v1_3_router.json').write_text(json.dumps(model_info,indent=2))
    (OUT/'BTBC_v1_3_summary.json').write_text(json.dumps({'summary':summary,'bootstrap':boot},indent=2))
    print(json.dumps({'operating':operating,'summary':summary,'bootstrap':boot},indent=2))

if __name__=='__main__': main()
