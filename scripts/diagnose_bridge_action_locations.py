#!/usr/bin/env python3
"""Locate where bridge-v2 recovery decisions occur.

Diagnostic only. Reports proposed/final REPAIR2 actions and output changes split
between original memory nodes vs auxiliary anchors and latest vs historical time.
"""
from __future__ import annotations
import argparse, json, tempfile
from collections import Counter
from pathlib import Path
import joblib, numpy as np
from btbc import memory_engine
from btbc.frozen_v1_4_adapter import FROZEN_OPERATING_PATH,FROZEN_ROUTER_PATH,_load_frozen_v14_function,_load_policy
from btbc.llm_state_bridge import encode_sqlite_to_v14_state
import btbc.frozen.v1_4 as frozen
import scripts.test_nonoracle_bridge_v2 as v2
from scripts.test_mixed_provenance_attack_v4 import derive_diverse_history_consensus
from scripts.test_mixed_provenance_attack_v5 import relation_semantic_augment

def diagnose(sc):
    sid=str(sc['session_id'])
    with tempfile.TemporaryDirectory(prefix='btbc_loc_') as td:
        db=str(Path(td)/'w.db'); memory_engine.seed_scenario(db,sc)
        obs,obs_r,st,rt,edges,mapping=encode_sqlite_to_v14_state(db,sid,limit=500)
        n=int(obs.shape[1]); anchors=derive_diverse_history_consensus(mapping)
        aug_obs,aug_r,aug_st,aug_rt,aug_edges,meta=relation_semantic_augment(obs,obs_r,st,rt,edges,mapping,anchors)
        policy=_load_policy(); router=joblib.load(FROZEN_ROUTER_PATH); operating=json.loads(Path(FROZEN_OPERATING_PATH).read_text())
        safe,actions,recovery,rec_actions,*_=frozen.v12.get_branches(aug_obs,aug_r,aug_st,aug_rt,aug_edges,policy)
        out,final_actions,*rest=frozen.btbc_v14(aug_obs,aug_r,aug_st,aug_rt,aug_edges,policy,router,operating)
        T=aug_obs.shape[0]; latest=T-1
        proposed=np.asarray(rec_actions).astype(str)=='REPAIR2'; final=np.asarray(final_actions).astype(str)=='REPAIR2'
        changed=np.asarray(out)!=np.asarray(aug_obs); from_safe=np.asarray(out)!=np.asarray(safe)
        candidate=np.asarray(recovery)!=np.asarray(safe)
        def split(mask):
            return {'total':int(mask.sum()),'original':int(mask[:,:n].sum()),'anchor':int(mask[:,n:].sum()),
                    'latest_original':int(mask[latest,:n].sum()),'historical_original':int(mask[:latest,:n].sum()),
                    'latest_anchor':int(mask[latest,n:].sum()),'historical_anchor':int(mask[:latest,n:].sum())}
        return {'scenario_id':sc.get('id'),'anchors':len(anchors),'original_n':n,'added_n':int(aug_obs.shape[1]-n),
                'candidate_recovery_vs_safe':split(candidate),'proposed_repair2':split(proposed),'final_repair2':split(final),
                'output_changed_vs_obs':split(changed),'output_changed_vs_safe':split(from_safe)}

def add(dst,src):
    for group,v in src.items():
        if not isinstance(v,dict): continue
        for k,x in v.items(): dst[group][k]+=int(x)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--scenarios',required=True); p.add_argument('--limit',type=int,default=20); p.add_argument('--out',required=True)
    a=p.parse_args(); files=v2._files(Path(a.scenarios),a.limit)
    rows=[]; agg={k:Counter() for k in ['candidate_recovery_vs_safe','proposed_repair2','final_repair2','output_changed_vs_obs','output_changed_vs_safe']}
    for fp in files:
        r=diagnose(v2._load_world(fp)); rows.append(r); add(agg,r)
    summary={'worlds':len(rows),'worlds_with_anchors':sum(r['anchors']>0 for r in rows),'anchors':sum(r['anchors'] for r in rows),
             **{k:dict(v) for k,v in agg.items()}}
    Path(a.out).parent.mkdir(parents=True,exist_ok=True); Path(a.out).write_text(json.dumps({'summary':summary,'worlds':rows},indent=2,sort_keys=True)+'\n')
    print(json.dumps(summary,indent=2,sort_keys=True))
if __name__=='__main__': main()
