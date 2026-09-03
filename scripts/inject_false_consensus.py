#!/usr/bin/env python3
"""Inject adversarial historical false consensus into generated worlds.

The active/latest value remains ground truth, but 3-4 distinct high-trust historical
sources agree on the same wrong value. This is designed to test whether
history-consensus anchoring mistakes coordinated provenance for independent truth.
"""
from __future__ import annotations
import argparse, json, random, shutil
from pathlib import Path

VALUES=("amber","blue","green","ivory","orange","purple","red","yellow")

def other(rng, truth):
    return rng.choice([v for v in VALUES if v != truth])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--src', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--seed', type=int, default=369963)
    p.add_argument('--attack-rate', type=float, default=0.50)
    p.add_argument('--min-colluders', type=int, default=3)
    p.add_argument('--max-colluders', type=int, default=4)
    a=p.parse_args(); rng=random.Random(a.seed)
    src=Path(a.src); out=Path(a.out)
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    attacked=0; worlds=0; attacked_fields=[]
    for fp in sorted(src.glob('world_*.json')):
        obj=json.loads(fp.read_text())
        sc=obj['scenarios'][0]; worlds+=1
        truth={str(k):str(v) for k,v in sc.get('ground_truth_fields',{}).items()}
        corrupted=set(map(str,sc.get('corrupted_fields',[])))
        legitimate=set(map(str,sc.get('legitimate_fields',[])))
        memories=sc['memories']
        max_ts=max(int(r.get('valid_from') or r.get('created_at') or 0) for r in memories)
        by_field={}
        for r in memories:
            key=f"{r['entity']}.{r['attribute']}"; by_field.setdefault(key,[]).append(r)
        for key,tval in truth.items():
            if key in corrupted or key in legitimate or rng.random()>a.attack_rate: continue
            rows=by_field.get(key,[])
            if not rows: continue
            entity,attr=key.split('.',1)
            wrong=other(rng,tval)
            # Poison the historical record with distinct-looking, trusted sources.
            n=rng.randint(a.min_colluders,a.max_colluders)
            base=max_ts+1000+attacked*20
            for j in range(n):
                ts=base+j
                memories.append({
                    'memory_id':f"adv_{worlds:04d}_{attacked:05d}_c{j}",
                    'session_id':sc['session_id'],'entity':entity,'attribute':attr,
                    'value':wrong,'valid_from':ts,'valid_to':base+n+10,
                    'source':f"colluder_{j}:{rng.randrange(100000,999999)}",
                    'source_trust':round(rng.uniform(.94,.99),6),
                    'confidence':round(rng.uniform(.94,.99),6),
                    'created_at':ts,'updated_at':ts,'status':'active'})
            # Keep the active state correct but deliberately low-score, so the
            # historical-consensus detector is eligible to challenge it.
            ts=base+n+10
            memories.append({
                'memory_id':f"adv_{worlds:04d}_{attacked:05d}_truth",
                'session_id':sc['session_id'],'entity':entity,'attribute':attr,
                'value':tval,'valid_from':ts,'valid_to':None,
                'source':f"current_truth:{rng.randrange(100000,999999)}",
                'source_trust':.40,'confidence':.40,
                'created_at':ts,'updated_at':ts,'status':'active'})
            attacked+=1; attacked_fields.append({'world':sc['id'],'field':key,'truth':tval,'false_consensus':wrong,'colluders':n})
        sc['description'] += f" Adversarial false-consensus injection applied; cumulative attacked fields={attacked}."
        sc.setdefault('adversarial',{})['false_consensus']=True
        fp_out=out/fp.name; fp_out.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
    manifest={'worlds':worlds,'attacked_fields':attacked,'seed':a.seed,'attack_rate':a.attack_rate,'min_colluders':a.min_colluders,'max_colluders':a.max_colluders,'attacks':attacked_fields}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='attacks'},indent=2))
if __name__=='__main__': main()
