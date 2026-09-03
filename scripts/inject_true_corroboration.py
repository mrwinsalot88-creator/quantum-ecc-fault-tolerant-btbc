#!/usr/bin/env python3
"""Inject benchmark-only true corroboration opportunities into generated worlds.

Ground truth is used here only to construct the held-out synthetic challenge. The
runtime BTBC controller never receives truth labels. For selected already-
corrupted fields, append 2-3 older high-trust observations from distinct source
families that agree with truth, then append a newest low-trust corrupted active
observation. This makes a real, non-oracle repair opportunity observable through
persisted history/provenance alone.
"""
from __future__ import annotations
import argparse, json, random, shutil
from pathlib import Path

VALUES=("amber","blue","green","ivory","orange","purple","red","yellow")

def wrong_value(rng, truth, preferred=None):
    if preferred is not None and str(preferred) != str(truth): return str(preferred)
    return rng.choice([v for v in VALUES if v != str(truth)])

def main():
    p=argparse.ArgumentParser(); p.add_argument('--src',required=True); p.add_argument('--out',required=True)
    p.add_argument('--seed',type=int,default=369963369); p.add_argument('--support-rate',type=float,default=.70)
    p.add_argument('--min-witnesses',type=int,default=2); p.add_argument('--max-witnesses',type=int,default=3)
    a=p.parse_args(); rng=random.Random(a.seed); src=Path(a.src); out=Path(a.out)
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    injected=[]; worlds=0
    for fp in sorted(src.glob('world_*.json')):
        obj=json.loads(fp.read_text()); sc=obj['scenarios'][0]; worlds+=1
        truth={str(k):str(v) for k,v in sc.get('ground_truth_fields',{}).items()}
        corrupted=set(map(str,sc.get('corrupted_fields',[]))); memories=sc['memories']
        by_field={}
        for r in memories:
            key=f"{r['entity']}.{r['attribute']}"; by_field.setdefault(key,[]).append(r)
        max_ts=max([int(r.get('valid_from') or r.get('created_at') or 0) for r in memories] or [0])
        for key in sorted(corrupted):
            if key not in truth or rng.random()>a.support_rate: continue
            entity,attr=key.split('.',1); rows=by_field.get(key,[])
            active=[r for r in rows if r.get('valid_to') is None]
            latest=max(active or rows,key=lambda r:int(r.get('valid_from') or r.get('created_at') or 0)) if rows else None
            bad=wrong_value(rng,truth[key],latest.get('value') if latest else None)
            base=max_ts+1000+len(injected)*20
            n=rng.randint(a.min_witnesses,a.max_witnesses)
            # close any prior active rows so the benchmark has exactly one newest active observation
            for r in rows:
                if r.get('valid_to') is None: r['valid_to']=base
            for j in range(n):
                ts=base+j
                memories.append({'memory_id':f"truecorr_{worlds:04d}_{len(injected):05d}_w{j}",
                  'session_id':sc['session_id'],'entity':entity,'attribute':attr,'value':truth[key],
                  'valid_from':ts,'valid_to':base+n+5,'source':f"independent_{chr(97+j)}:{rng.randrange(100000,999999)}",
                  'source_trust':round(rng.uniform(.92,.98),6),'confidence':round(rng.uniform(.92,.98),6),
                  'created_at':ts,'updated_at':ts,'status':'active'})
            ts=base+n+5
            memories.append({'memory_id':f"truecorr_{worlds:04d}_{len(injected):05d}_bad",
              'session_id':sc['session_id'],'entity':entity,'attribute':attr,'value':bad,
              'valid_from':ts,'valid_to':None,'source':f"current_low:{rng.randrange(100000,999999)}",
              'source_trust':.40,'confidence':.40,'created_at':ts,'updated_at':ts,'status':'active'})
            injected.append({'world':sc['id'],'field':key,'truth':truth[key],'active_corruption':bad,'witnesses':n})
        sc.setdefault('adversarial',{})['true_corroboration']=True
        (out/fp.name).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
    manifest={'worlds':worlds,'supported_corrupted_fields':len(injected),'seed':a.seed,'support_rate':a.support_rate,'injections':injected}
    (out/'true_corroboration_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='injections'},indent=2))
if __name__=='__main__': main()
