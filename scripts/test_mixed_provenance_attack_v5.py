#!/usr/bin/env python3
"""Mixed proof with provenance diversity and frozen BTBC relation semantics.

Fixes a bridge-only bug: anchor equality edges must encode the frozen relation
function, where relation(0,0)==0 rather than +1. Frozen BTBC/router/policy are
unchanged.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import scripts.test_nonoracle_bridge_v2 as v2
from scripts.test_mixed_provenance_attack_v4 import derive_diverse_history_consensus


def relation_semantic_augment(obs, obs_r, st, rt, edges, mapping, anchors, *, relation_trust_cap=.99):
    out_obs,out_r,out_st,out_rt,out_edges,meta = ORIGINAL_AUGMENT(
        obs,obs_r,st,rt,edges,mapping,anchors,relation_trust_cap=relation_trust_cap)
    base_rel=int(np.asarray(obs_r).shape[1]); width=int(mapping.get('code_width') or 0)
    fields=[tuple(x) for x in mapping.get('fields') or []]; codebooks=mapping.get('codebooks') or {}
    offset=0
    for info in meta.get('anchors',[]):
        f_idx=int(info['field_index']); field=fields[f_idx]
        fkey=v2._field_key(field); code=np.asarray(codebooks[fkey][str(info['consensus_value'])],dtype=np.int8)
        for bit in range(width):
            # Frozen relation(a,b): 0 if either endpoint is zero, otherwise
            # +1 for equal signs. A truth-matching target therefore expects
            # 0 for anchor bit 0 and +1 for anchor bit +/-1.
            out_r[:,base_rel+offset]=0 if int(code[bit])==0 else 1
            offset+=1
    return out_obs,out_r,out_st,out_rt,out_edges,meta

ORIGINAL_AUGMENT=v2.augment_with_history_anchors

def main():
    p=argparse.ArgumentParser(); p.add_argument('--scenarios',required=True); p.add_argument('--limit',type=int,default=0); p.add_argument('--out',required=True)
    a=p.parse_args(); files=v2._files(Path(a.scenarios),a.limit)
    old_derive=v2.derive_history_consensus; old_aug=v2.augment_with_history_anchors
    v2.derive_history_consensus=derive_diverse_history_consensus
    v2.augment_with_history_anchors=relation_semantic_augment
    try:
        rows=[v2.diagnose_world(v2._load_world(fp)) for fp in files]
        summary=v2.summarize(rows)
        Path(a.out).parent.mkdir(parents=True,exist_ok=True)
        Path(a.out).write_text(json.dumps({'summary':summary,'worlds':rows},indent=2,sort_keys=True)+'\n')
        print(json.dumps(summary,indent=2,sort_keys=True))
    finally:
        v2.derive_history_consensus=old_derive; v2.augment_with_history_anchors=old_aug
if __name__=='__main__': main()
