#!/usr/bin/env python3
"""Mixed-evidence proof test for BTBC history anchors.

Builds on the non-oracle bridge-v2 experiment, but requires independent source
families for a consensus anchor and evaluates a mixed suite containing both
real historical corroboration and coordinated false-consensus poison.
"""
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Mapping

from scripts.test_nonoracle_bridge_v2 import _files, _load_world, run_world, _row_score, _latest_active_id


def source_family(source: Any) -> str:
    s=str(source or '').strip().lower()
    if ':' in s:
        s=s.split(':',1)[0]
    if '/' in s:
        s=s.split('/',1)[0]
    return s


def derive_diverse_history_consensus(mapping: Mapping[str, Any], *, max_current_score=.45,
                                     min_witness_score=.65, min_source_families=2,
                                     min_consensus_share=.72, min_weight_margin=.45):
    rows=mapping.get('memory_rows') or {}
    fields=[tuple(x) for x in mapping.get('fields') or []]
    anchors={}
    for f_idx, field in enumerate(fields):
        latest_id=_latest_active_id(mapping,f_idx)
        latest=rows.get(latest_id) if latest_id else None
        if not latest: continue
        current_value=str(latest.get('value'))
        if _row_score(latest)>max_current_score: continue
        current_time=latest.get('valid_from')
        # Collapse repeated rows from the same provenance family to its strongest witness.
        fam_best={}
        for mid,row in rows.items():
            if str(mid)==latest_id: continue
            if str(row.get('entity'))!=str(field[0]) or str(row.get('attribute'))!=str(field[1]): continue
            if current_time is not None and row.get('valid_from') is not None and int(row.get('valid_from'))>int(current_time): continue
            score=_row_score(row)
            if score<min_witness_score: continue
            fam=source_family(row.get('source'))
            if not fam: continue
            key=(str(row.get('value')),fam)
            if key not in fam_best or score>_row_score(fam_best[key]): fam_best[key]=row
        if not fam_best: continue
        weight=defaultdict(float); supporters=defaultdict(list)
        for (value,_fam),row in fam_best.items():
            weight[value]+=_row_score(row); supporters[value].append(row)
        ranked=sorted(weight.items(),key=lambda kv:(-kv[1],kv[0]))
        best_value,best_weight=ranked[0]; second=ranked[1][1] if len(ranked)>1 else 0.0
        total=sum(weight.values()); share=best_weight/total if total else 0.0
        best_supporters=supporters[best_value]
        families={source_family(r.get('source')) for r in best_supporters}
        if best_value==current_value or len(families)<min_source_families: continue
        if share<min_consensus_share or best_weight-second<min_weight_margin: continue
        anchors[f_idx]={
          'field':[str(field[0]),str(field[1])], 'latest_memory_id':latest_id,
          'current_value':current_value,'current_score':_row_score(latest),
          'consensus_value':best_value,'consensus_weight':best_weight,
          'consensus_share':share,'weight_margin':best_weight-second,
          'supporter_count':len(best_supporters),'source_family_count':len(families),
          'supporters':[{'memory_id':str(r.get('memory_id')),'value':str(r.get('value')),
                         'source':str(r.get('source')),'source_family':source_family(r.get('source')),
                         'source_trust':float(r.get('source_trust',.5) or .5),
                         'confidence':float(r.get('confidence',.5) or .5),'score':_row_score(r),
                         'valid_from':r.get('valid_from')} for r in best_supporters]
        }
    return anchors


def main():
    p=argparse.ArgumentParser(); p.add_argument('--scenarios',required=True); p.add_argument('--limit',type=int,default=0); p.add_argument('--out',required=True)
    a=p.parse_args(); files=_files(Path(a.scenarios),a.limit)
    totals=defaultdict(lambda:defaultdict(int)); worlds=0; anchors=0; worlds_with=0
    import scripts.test_nonoracle_bridge_v2 as v2
    original=v2.derive_history_consensus
    v2.derive_history_consensus=derive_diverse_history_consensus
    try:
        details=[]
        for fp in files:
            sc=_load_world(fp); r=run_world(sc); worlds+=1; anchors+=int(r.get('anchor_count',0)); worlds_with+=int(r.get('anchor_count',0)>0)
            details.append({'file':fp.name,**r})
            for arm,m in r['arms'].items():
                for k,v in m.items():
                    if isinstance(v,(int,bool)): totals[arm][k]+=int(v)
        summary={'worlds':worlds,'worlds_with_anchors':worlds_with,'anchor_count':anchors,'arms':{k:dict(v) for k,v in totals.items()}}
        Path(a.out).parent.mkdir(parents=True,exist_ok=True); Path(a.out).write_text(json.dumps({'summary':summary,'worlds':details},indent=2,sort_keys=True)+'\n')
        print(json.dumps(summary,indent=2,sort_keys=True))
    finally:
        v2.derive_history_consensus=original

if __name__=='__main__': main()
