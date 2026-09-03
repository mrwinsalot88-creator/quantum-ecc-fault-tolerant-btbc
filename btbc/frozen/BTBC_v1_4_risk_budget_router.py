#!/usr/bin/env python3
"""BTBC v1.4 — Explicit Risk-Budget Layer-0 Router

Original BTBC project research code. No third-party agent-memory implementation code is copied.
Uses scikit-learn RandomForestClassifier only as a generic probabilistic routing primitive.

Upgrade over v1.3
-----------------
v1.3 selected a risk-weighted score using a per-call harm guard.
v1.4 instead calibrates the router against an explicit *global false-correction budget*.
The validation policy chooses the highest-recovery operating point that stays below a
predeclared false-correction rate target. The threshold is then frozen before a fresh
locked test.

Runtime uses observable features only. Ground truth is used only to train/calibrate and
score synthetic experiments. This is classical structured-memory research code, not QEC.
"""
from __future__ import annotations
from pathlib import Path
import importlib.util, json, sys
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

OUT = Path(__file__).resolve().parent
V13_PATH = OUT / 'BTBC_v1_3_risk_calibrated_router.py'
SEED = 369_140026
TARGET_FALSE_CORRECTION_RATE = 0.0010  # 0.10% of memory cells

spec = importlib.util.spec_from_file_location('btbc_v13', V13_PATH)
v13 = importlib.util.module_from_spec(spec); sys.modules[spec.name] = v13; spec.loader.exec_module(v13)
v12 = v13.v12; v11 = v13.v11; FEATURES = v13.FEATURES


def fit_router():
    # Use two independent training worlds per scenario family to stabilize probability estimates.
    configs = v11.scenario_grid()
    train = v13.collect_rows(np.random.default_rng(SEED+1000), configs, worlds_each=1)
    clf = RandomForestClassifier(
        n_estimators=48, max_depth=9, min_samples_leaf=12, max_features='sqrt',
        class_weight={0:1.0, 1:2.25, 2:6.5}, random_state=SEED, n_jobs=1,
    )
    clf.fit(train[FEATURES].to_numpy(), train['class3'].to_numpy())
    return clf, train


def probs(clf, feat):
    p = clf.predict_proba(np.array([[feat[k] for k in FEATURES]]))[0]
    idx={int(c):i for i,c in enumerate(clf.classes_)}
    return (float(p[idx[1]]) if 1 in idx else 0.0,
            float(p[idx[2]]) if 2 in idx else 0.0)


def collect_validation_cache(clf, worlds_each=1):
    policy=v11.Policy(); rng=np.random.default_rng(SEED+2000)
    worlds=[]; rows=[]; wid=0
    for sid,cfg in enumerate(v11.scenario_grid()):
        for w in range(worlds_each):
            edges,truth,legit,rel_truth,obs,obs_r,st,rt,attack_cells,attack_rels=v11.make_world(rng,cfg)
            safe,actions,recovery,rec_actions,conf,rm,ctr=v12.get_branches(obs,obs_r,st,rt,edges,policy)
            cells=truth.size
            safe_err=int((safe!=truth).sum())
            safe_fc=int(((safe!=obs)&(obs==truth)&(safe!=truth)).sum())
            safe_changed=int((safe!=obs).sum())
            safe_tp=int(((safe!=obs)&(obs!=truth)&(safe==truth)).sum())
            worlds.append({'wid':wid,'sid':sid,'cells':cells,'safe_err':safe_err,'safe_fc':safe_fc,
                           'safe_changed':safe_changed,'safe_tp':safe_tp})
            for t,i in zip(*np.where(actions=='ESCALATE')):
                feat=v12.observable_features(obs,obs_r,st,rt,edges,conf,rm,int(t),int(i))
                pb,ph=probs(clf,feat)
                s=int(safe[t,i]); r=int(recovery[t,i]); o=int(obs[t,i]); y=int(truth[t,i])
                rows.append({
                    'wid':wid,'pb':pb,'ph':ph,
                    'err_delta':int(r!=y)-int(s!=y),
                    'fc_delta':int((r!=o) and (o==y) and (r!=y))-int((s!=o) and (o==y) and (s!=y)),
                    'changed_delta':int(r!=o)-int(s!=o),
                    'tp_delta':int((r!=o) and (o!=y) and (r==y))-int((s!=o) and (o!=y) and (s==y)),
                })
            wid+=1
    return pd.DataFrame(worlds), pd.DataFrame(rows)


def calibrate(clf):
    vw, vr = collect_validation_cache(clf, worlds_each=1)
    total_cells=int(vw.cells.sum())
    base_err=int(vw.safe_err.sum()); base_fc=int(vw.safe_fc.sum())
    base_changed=int(vw.safe_changed.sum()); base_tp=int(vw.safe_tp.sum())
    pb=vr.pb.to_numpy(); ph=vr.ph.to_numpy()
    ed=vr.err_delta.to_numpy(dtype=int); fd=vr.fc_delta.to_numpy(dtype=int)
    cd=vr.changed_delta.to_numpy(dtype=int); td=vr.tp_delta.to_numpy(dtype=int)
    candidates=[]
    for hw in (1.5,2.0,2.5,3.0,3.5,4.0,5.0,6.0,8.0,10.0,12.0):
        score=pb-hw*ph
        ths=np.unique(np.concatenate([np.quantile(score,np.linspace(0,1,81)),np.linspace(-.15,.70,86)]))
        for th in ths:
            m=score>=th
            err=base_err+int(ed[m].sum()); fc=base_fc+int(fd[m].sum())
            changed=base_changed+int(cd[m].sum()); tp=base_tp+int(td[m].sum())
            fcr=fc/total_cells
            if fcr <= TARGET_FALSE_CORRECTION_RATE:
                precision=tp/max(1,changed)
                candidates.append((err, fcr, -precision, int(m.sum()), hw, float(th), tp, fc, changed))
    if not candidates:
        raise RuntimeError('No validation operating point met the explicit risk budget')
    candidates.sort(); err,fcr,nprec,calls,hw,th,tp,fc,changed=candidates[0]
    return {
        'harm_weight':float(hw),'threshold':float(th),
        'target_false_correction_rate':TARGET_FALSE_CORRECTION_RATE,
        'validation_error_rate':err/total_cells,
        'validation_false_correction_rate':fcr,
        'validation_repair_precision':(-nprec),
        'validation_recovery_calls':int(calls),
        'validation_worlds':int(len(vw)), 'validation_escalated_cells':int(len(vr)),
    }, vw, vr


def btbc_v14(obs,obs_r,st,rt,edges,policy,router,operating):
    safe,actions,recovery,rec_actions,conf,rm,ctr=v12.get_branches(obs,obs_r,st,rt,edges,policy)
    out=safe.copy(); final_actions=actions.copy(); routed=blocked=0
    coords=list(zip(*np.where(actions=='ESCALATE')))
    if not coords:
        return out,final_actions,conf,rm,ctr,0,0,0.0
    feats=[v12.observable_features(obs,obs_r,st,rt,edges,conf,rm,int(t),int(i)) for t,i in coords]
    X=np.array([[f[k] for k in FEATURES] for f in feats])
    pp=router.predict_proba(X); idx={int(c):i for i,c in enumerate(router.classes_)}
    pb=pp[:,idx[1]] if 1 in idx else np.zeros(len(coords)); ph=pp[:,idx[2]] if 2 in idx else np.zeros(len(coords))
    scores=pb-operating['harm_weight']*ph
    route=scores>=operating['threshold']
    for (t,i),go in zip(coords,route):
        if go:
            routed+=1; out[t,i]=recovery[t,i]; final_actions[t,i]=rec_actions[t,i]
        else:
            blocked+=1; final_actions[t,i]='RISK_BUDGET_KEEP'
    return out,final_actions,conf,rm,ctr,routed,blocked,float(np.mean(scores))


def evaluate_world(rng,cfg,policy,router,operating):
    edges,truth,legit,rel_truth,obs,obs_r,st,rt,attack_cells,attack_rels=v11.make_world(rng,cfg)
    safe,actions,recovery,rec_actions,conf,rm,ctr=v12.get_branches(obs,obs_r,st,rt,edges,policy)
    adaptive,aa,_,_,_,routed,blocked,mean_score=btbc_v14(obs,obs_r,st,rt,edges,policy,router,operating)
    def err(x): return float(np.mean(x!=truth))
    def counts(x):
        ch=x!=obs; tp=ch&(obs!=truth)&(x==truth); fc=ch&(obs==truth)&(x!=truth)
        return ch,tp,fc
    ch,tp,fc=counts(adaptive); sch,stp,sfc=counts(safe); rch,rtp,rfc=counts(recovery)
    attack_bad=attack_cells&(obs!=truth); attack_fixed=attack_bad&(adaptive==truth)
    legit_damage=legit&(adaptive!=truth)
    return {
        'raw_error':err(obs),'safe_error':err(safe),'recovery_error':err(recovery),'adaptive_error':err(adaptive),
        'adaptive_delta':err(adaptive)-err(obs),'true_repairs':int(tp.sum()),'false_corrections':int(fc.sum()),
        'changed_cells':int(ch.sum()),'corrupted_cells':int((obs!=truth).sum()),
        'safe_true_repairs':int(stp.sum()),'safe_false_corrections':int(sfc.sum()),'safe_changed_cells':int(sch.sum()),
        'recovery_true_repairs':int(rtp.sum()),'recovery_false_corrections':int(rfc.sum()),'recovery_changed_cells':int(rch.sum()),
        'attack_bad_cells':int(attack_bad.sum()),'attack_fixed_cells':int(attack_fixed.sum()),
        'legit_change_cells':int(legit.sum()),'legit_change_damage':int(legit_damage.sum()),
        'router_recovery_calls':int(routed),'router_safe_blocks':int(blocked),'escalations':int((actions=='ESCALATE').sum()),
        'relation_mismatch':float(rm),'mean_confidence':float(np.mean(conf)),'mean_route_score':float(mean_score),
    }


def locked_test(router,operating):
    policy=v11.Policy(); rng=np.random.default_rng(SEED+99_999); rec=[]
    for sid,cfg in enumerate(v11.scenario_grid()):
        for world in range(2):
            rec.append({**cfg,'scenario_id':sid,'world':world,**evaluate_world(rng,cfg,policy,router,operating)})
    return pd.DataFrame(rec)


def summarize(df):
    cells=len(df)*14*16
    def red(col): return float((df.raw_error.mean()-df[col].mean())/df.raw_error.mean())
    def prec(tp,ch): return float(tp.sum()/max(1,ch.sum()))
    by=df.groupby('scenario_id').mean(numeric_only=True)
    return {
        'worlds':int(len(df)),'scenarios':int(df.scenario_id.nunique()),
        'raw_error_mean':float(df.raw_error.mean()),'safe_error_mean':float(df.safe_error.mean()),
        'full_recovery_error_mean':float(df.recovery_error.mean()),'adaptive_v14_error_mean':float(df.adaptive_error.mean()),
        'safe_relative_error_reduction':red('safe_error'),'full_recovery_relative_error_reduction':red('recovery_error'),
        'adaptive_v14_relative_error_reduction':red('adaptive_error'),
        'safe_repair_precision':prec(df.safe_true_repairs,df.safe_changed_cells),
        'full_recovery_repair_precision':prec(df.recovery_true_repairs,df.recovery_changed_cells),
        'adaptive_repair_precision':prec(df.true_repairs,df.changed_cells),
        'adaptive_corruption_recovery_fraction':float(df.true_repairs.sum()/max(1,df.corrupted_cells.sum())),
        'safe_false_correction_rate_per_cell':float(df.safe_false_corrections.sum()/cells),
        'full_recovery_false_correction_rate_per_cell':float(df.recovery_false_corrections.sum()/cells),
        'adaptive_false_correction_rate_per_cell':float(df.false_corrections.sum()/cells),
        'risk_budget_target':TARGET_FALSE_CORRECTION_RATE,
        'adaptive_budget_met_on_locked_test':bool(df.false_corrections.sum()/cells <= TARGET_FALSE_CORRECTION_RATE),
        'safe_scenario_nonworse_fraction':float((by.safe_error<=by.raw_error+1e-12).mean()),
        'full_recovery_scenario_nonworse_fraction':float((by.recovery_error<=by.raw_error+1e-12).mean()),
        'adaptive_scenario_nonworse_fraction':float((by.adaptive_error<=by.raw_error+1e-12).mean()),
        'router_recovery_fraction_of_escalations':float(df.router_recovery_calls.sum()/max(1,df.escalations.sum())),
        'attack_recovery_fraction':float(df.attack_fixed_cells.sum()/max(1,df.attack_bad_cells.sum())),
        'legitimate_change_damage_rate':float(df.legit_change_damage.sum()/max(1,df.legit_change_cells.sum())),
    }


def bootstrap(df,n=1500):
    rng=np.random.default_rng(SEED+777); arr=df[['adaptive_error','recovery_error','raw_error','safe_error']].to_numpy(); vals=[]
    for _ in range(n):
        s=arr[rng.integers(0,len(arr),len(arr))].mean(axis=0)
        vals.append([s[0]-s[2],s[0]-s[1],s[0]-s[3]])
    vals=np.asarray(vals)
    return {
        'adaptive_minus_raw_mean':float((df.adaptive_error-df.raw_error).mean()),
        'adaptive_minus_raw_ci95':[float(x) for x in np.quantile(vals[:,0],[.025,.975])],
        'adaptive_minus_full_recovery_mean':float((df.adaptive_error-df.recovery_error).mean()),
        'adaptive_minus_full_recovery_ci95':[float(x) for x in np.quantile(vals[:,1],[.025,.975])],
        'adaptive_minus_safe_mean':float((df.adaptive_error-df.safe_error).mean()),
        'adaptive_minus_safe_ci95':[float(x) for x in np.quantile(vals[:,2],[.025,.975])],
    }


def main():
    router,train=fit_router(); operating,vw,vr=calibrate(router)
    test=locked_test(router,operating); summary=summarize(test); boot=bootstrap(test)
    test.to_csv(OUT/'BTBC_v1_4_risk_budget_locked_results.csv',index=False)
    info={'features':FEATURES,**operating,'train_rows':int(len(train)),
          'feature_importances':{k:float(v) for k,v in zip(FEATURES,router.feature_importances_)},
          'base_policy':v11.Policy().__dict__}
    (OUT/'BTBC_v1_4_router.json').write_text(json.dumps(info,indent=2))
    (OUT/'BTBC_v1_4_summary.json').write_text(json.dumps({'summary':summary,'bootstrap':boot},indent=2))
    print(json.dumps({'operating':operating,'summary':summary,'bootstrap':boot},indent=2))

if __name__=='__main__': main()
