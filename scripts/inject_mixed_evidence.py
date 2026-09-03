#!/usr/bin/env python3
"""Inject mixed provenance evidence for the BTBC proof test.

For selected fields, add either:
  * genuine corroboration from two distinct source families that agrees with truth, or
  * coordinated false corroboration from several source IDs belonging to one
    underlying source family (``colluder``), all agreeing on the same wrong value.

The active/latest value is made low-score so the history-anchor path is eligible.
Ground truth is used only to construct the synthetic challenge and later evaluate it.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

VALUES = ("amber", "blue", "green", "ivory", "orange", "purple", "red", "yellow")


def other(rng: random.Random, truth: str) -> str:
    return rng.choice([v for v in VALUES if v != truth])


def add_row(memories, *, sc, entity, attr, value, source, trust, confidence, ts, mid, valid_to):
    memories.append({
        "memory_id": mid,
        "session_id": sc["session_id"],
        "entity": entity,
        "attribute": attr,
        "value": value,
        "valid_from": ts,
        "valid_to": valid_to,
        "source": source,
        "source_trust": trust,
        "confidence": confidence,
        "created_at": ts,
        "updated_at": ts,
        "status": "active",
    })


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=369369)
    p.add_argument("--genuine-rate", type=float, default=0.22)
    p.add_argument("--collusion-rate", type=float, default=0.22)
    a = p.parse_args()

    rng = random.Random(a.seed)
    src, out = Path(a.src), Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    genuine = 0
    colluded = 0
    worlds = 0
    details = []

    for fp in sorted(src.glob("world_*.json")):
        obj = json.loads(fp.read_text())
        sc = obj["scenarios"][0]
        worlds += 1
        truth = {str(k): str(v) for k, v in sc.get("ground_truth_fields", {}).items()}
        corrupted = set(map(str, sc.get("corrupted_fields", [])))
        legitimate = set(map(str, sc.get("legitimate_fields", [])))
        memories = sc["memories"]
        max_ts = max(int(r.get("valid_from") or r.get("created_at") or 0) for r in memories)
        by_field = {}
        for r in memories:
            key = f"{r['entity']}.{r['attribute']}"
            by_field.setdefault(key, []).append(r)

        for key, tval in truth.items():
            if key in legitimate:
                continue
            rows = by_field.get(key, [])
            if not rows:
                continue
            roll = rng.random()
            mode = None
            if key in corrupted and roll < a.genuine_rate:
                mode = "genuine"
            elif key not in corrupted and roll < a.collusion_rate:
                mode = "collusion"
            if mode is None:
                continue

            entity, attr = key.split(".", 1)
            base = max_ts + 1000 + (genuine + colluded) * 20

            if mode == "genuine":
                # Two genuinely distinct provenance families independently support truth.
                for j, fam in enumerate(("archive", "verified_import")):
                    ts = base + j
                    add_row(
                        memories, sc=sc, entity=entity, attr=attr, value=tval,
                        source=f"{fam}:{rng.randrange(100000,999999)}",
                        trust=round(rng.uniform(.92, .99), 6),
                        confidence=round(rng.uniform(.92, .99), 6), ts=ts,
                        mid=f"mix_{worlds:04d}_{genuine:05d}_g{j}", valid_to=base + 5,
                    )
                latest_val = other(rng, tval)
                genuine += 1
                details.append({"world": sc["id"], "field": key, "mode": mode, "truth": tval})
            else:
                wrong = other(rng, tval)
                # Several different IDs, but one underlying provenance family. A diversity
                # gate should collapse these to one family rather than count each ID.
                n = rng.randint(3, 4)
                for j in range(n):
                    ts = base + j
                    add_row(
                        memories, sc=sc, entity=entity, attr=attr, value=wrong,
                        source=f"colluder:{rng.randrange(100000,999999)}",
                        trust=round(rng.uniform(.94, .99), 6),
                        confidence=round(rng.uniform(.94, .99), 6), ts=ts,
                        mid=f"mix_{worlds:04d}_{colluded:05d}_c{j}", valid_to=base + n + 5,
                    )
                latest_val = tval
                colluded += 1
                details.append({"world": sc["id"], "field": key, "mode": mode, "truth": tval, "false_consensus": wrong})

            # Make latest active state low-score, so eligible evidence must decide whether
            # to challenge it. For genuine cases this active value is wrong; for collusion
            # cases it is correct.
            ts = base + 10
            add_row(
                memories, sc=sc, entity=entity, attr=attr, value=latest_val,
                source=f"current:{rng.randrange(100000,999999)}", trust=.40,
                confidence=.40, ts=ts,
                mid=f"mix_{worlds:04d}_{genuine+colluded:05d}_latest", valid_to=None,
            )

        sc.setdefault("adversarial", {})["mixed_provenance"] = True
        (out / fp.name).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

    manifest = {
        "worlds": worlds,
        "seed": a.seed,
        "genuine_rate": a.genuine_rate,
        "collusion_rate": a.collusion_rate,
        "genuine_fields": genuine,
        "colluded_fields": colluded,
        "cases": details,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "cases"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
