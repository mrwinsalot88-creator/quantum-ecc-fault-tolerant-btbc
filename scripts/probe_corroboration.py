#!/usr/bin/env python3
"""Test-only causal probe for independent relational corroboration.

This is NOT an efficacy benchmark. It deliberately injects synthetic high-trust
relation observations supporting frozen v1.1's own proposed value at cells that
stage 1 escalates. The purpose is mechanistic: determine whether lack of an
independent relation family is what makes the frozen recovery branch return
REVIEW_KEEP behind llm_state_bridge.

Frozen v1.x source, router.joblib, and operating.json are never modified.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from btbc import memory_engine
from btbc.llm_state_bridge import encode_sqlite_to_v14_state
import btbc.frozen.v1_4 as frozen_v14
from btbc.frozen_v1_4_adapter import _load_policy

REPO_ROOT = Path(__file__).resolve().parents[1]


def _rel(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return 1 if a == b else -1


def _scenario(path: Path) -> Mapping[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    xs = obj.get("scenarios") if isinstance(obj, dict) else None
    if not isinstance(xs, list) or len(xs) != 1:
        raise ValueError(f"{path}: expected exactly one scenario")
    return xs[0]


def _files(path: Path, limit: int) -> List[Path]:
    fs = [path] if path.is_file() else sorted(p for p in path.glob("*.json") if p.name != "manifest.json")
    if limit > 0:
        fs = fs[:limit]
    if not fs:
        raise SystemExit(f"No world JSON files found under {path}")
    return fs


def _candidate_truth_label(mapping: Mapping[str, Any], scenario: Mapping[str, Any], t: int, i: int, cand: int) -> Optional[bool]:
    width = int(mapping["code_width"])
    fidx = i // width
    fields = mapping["fields"]
    if fidx >= len(fields):
        return None
    entity, attribute = fields[fidx]
    gt = scenario.get("ground_truth_fields", {}).get(f"{entity}.{attribute}")
    if gt is None:
        return None
    fkey = json.dumps([str(entity), str(attribute)], separators=(",", ":"))
    code = mapping.get("codebooks", {}).get(fkey, {}).get(str(gt))
    if code is None:
        return None
    bit = i - fidx * width
    return int(code[bit]) == int(cand)


def _augment_relations(
    obs: np.ndarray,
    obs_r: np.ndarray,
    rt: np.ndarray,
    edges: Sequence[Tuple[int, int]],
    mapping: Mapping[str, Any],
    targets: Sequence[Tuple[int, int, int]],
    *,
    anchors_per_target: int = 8,
    trust: float = 0.995,
) -> Tuple[np.ndarray, np.ndarray, List[Tuple[int, int]], Dict[str, Any]]:
    """Add high-trust edges whose target-time relation supports proposed candidate.

    At non-target times each injected edge simply records the ordinary observed
    relation. At the target timestamp alone it records the relation implied by
    the proposed candidate. This creates an explicit independent relation-family
    signal without altering state observations or temporal history.
    """
    obs = np.asarray(obs, dtype=np.int8)
    old_edges = [tuple(map(int, e)) for e in edges]
    width = int(mapping["code_width"])
    existing = set(tuple(sorted(e)) for e in old_edges)
    specs: Dict[Tuple[int, int], Dict[int, int]] = {}
    selected: Dict[str, List[Tuple[int, int]]] = {}

    for t, i, cand in targets:
        field_i = i // width
        anchors = [j for j in range(obs.shape[1]) if j // width != field_i and int(obs[t, j]) != 0]
        # Deterministic spread across other fields/bits.
        chosen: List[int] = []
        for j in anchors:
            e = tuple(sorted((int(i), int(j))))
            if i == j or e in existing or e in specs:
                continue
            chosen.append(j)
            if len(chosen) >= anchors_per_target:
                break
        key = f"{t}:{i}"
        selected[key] = []
        for j in chosen:
            e = tuple(sorted((int(i), int(j))))
            specs.setdefault(e, {})[int(t)] = _rel(int(cand), int(obs[t, j]))
            selected[key].append(e)

    new_edges = old_edges + sorted(specs)
    T = obs.shape[0]
    E0 = len(old_edges)
    E1 = len(new_edges)
    new_obs_r = np.zeros((T, E1), dtype=np.int8)
    new_rt = np.full((T, E1), 0.5, dtype=float)
    if E0:
        new_obs_r[:, :E0] = np.asarray(obs_r, dtype=np.int8)
        new_rt[:, :E0] = np.asarray(rt, dtype=float)
    for k, e in enumerate(new_edges[E0:], start=E0):
        i, j = e
        overrides = specs[e]
        for t in range(T):
            new_obs_r[t, k] = np.int8(overrides.get(t, _rel(int(obs[t, i]), int(obs[t, j]))))
            new_rt[t, k] = float(trust)
    return new_obs_r, new_rt, new_edges, {"selected_edges": selected, "added_edges": len(specs)}


def probe_world(scenario: Mapping[str, Any], anchors_per_target: int = 8) -> Dict[str, Any]:
    sid = str(scenario["session_id"])
    with tempfile.TemporaryDirectory(prefix="btbc_probe_") as td:
        db = str(Path(td) / "w.db")
        memory_engine.seed_scenario(db, scenario)
        obs, obs_r, st, rt, edges, mapping = encode_sqlite_to_v14_state(db, sid, limit=max(100, len(scenario.get("memories", [])) + 10))
        policy = _load_policy()
        v12 = frozen_v14.v12
        v11 = v12.v11

        proposed, conf = v11.decode_candidate(obs, obs_r, st, rt, edges, policy.passes, v11.Counters())
        safe, actions, recovery, rec_actions, _conf, rm, _ctr = v12.get_branches(obs, obs_r, st, rt, edges, policy)
        coords = [(int(t), int(i)) for t, i in zip(*np.where(np.asarray(actions).astype(str) == "ESCALATE"))]
        targets = [(t, i, int(proposed[t, i])) for t, i in coords]

        target_rows = []
        for t, i, cand in targets:
            target_rows.append({
                "t": t,
                "i": i,
                "observed": int(obs[t, i]),
                "candidate": cand,
                "candidate_differs": bool(cand != int(obs[t, i])),
                "candidate_matches_final_truth_bit": _candidate_truth_label(mapping, scenario, t, i, cand),
                "baseline_recovery_action": str(rec_actions[t, i]),
                "baseline_recovery_changed": bool(int(recovery[t, i]) != int(safe[t, i])),
            })

        aug_obs_r, aug_rt, aug_edges, aug_meta = _augment_relations(
            obs, obs_r, rt, edges, mapping, targets, anchors_per_target=anchors_per_target
        )
        aug_safe, aug_actions, aug_recovery, aug_rec_actions, _c2, aug_rm, _ctr2 = v12.get_branches(
            obs, aug_obs_r, st, aug_rt, aug_edges, policy
        )

        conversions = 0
        correct_bit_conversions = 0
        for row in target_rows:
            t, i = row["t"], row["i"]
            row["aug_stage1_action"] = str(aug_actions[t, i])
            row["aug_recovery_action"] = str(aug_rec_actions[t, i])
            row["aug_recovery_changed"] = bool(int(aug_recovery[t, i]) != int(aug_safe[t, i]))
            if row["aug_recovery_action"] == "REPAIR2":
                conversions += 1
                if row["candidate_matches_final_truth_bit"] is True:
                    correct_bit_conversions += 1

        return {
            "scenario_id": scenario.get("id"),
            "session_id": sid,
            "baseline_relation_mismatch": float(rm),
            "augmented_relation_mismatch": float(aug_rm),
            "baseline_escalations": len(coords),
            "baseline_recovery_candidate_cells": int(np.sum(np.asarray(recovery) != np.asarray(safe))),
            "synthetic_edges_added": int(aug_meta["added_edges"]),
            "repair2_conversions": int(conversions),
            "correct_final_truth_bit_conversions": int(correct_bit_conversions),
            "targets": target_rows,
            "probe_note": "Synthetic relation evidence supports frozen proposed candidates; diagnostic only, not an efficacy result.",
        }


def summarize(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return {
        "worlds": len(rows),
        "worlds_with_escalations": sum(int(r["baseline_escalations"] > 0) for r in rows),
        "baseline_escalations": sum(int(r["baseline_escalations"]) for r in rows),
        "baseline_recovery_candidate_cells": sum(int(r["baseline_recovery_candidate_cells"]) for r in rows),
        "synthetic_edges_added": sum(int(r["synthetic_edges_added"]) for r in rows),
        "repair2_conversions": sum(int(r["repair2_conversions"]) for r in rows),
        "correct_final_truth_bit_conversions": sum(int(r["correct_final_truth_bit_conversions"]) for r in rows),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--anchors-per-target", type=int, default=8)
    ap.add_argument("--out", default="results/debug/corroboration_probe.json")
    args = ap.parse_args(argv)
    src = Path(args.scenarios)
    if not src.is_absolute(): src = REPO_ROOT / src
    fs = _files(src, args.limit)
    rows = [probe_world(_scenario(p), anchors_per_target=args.anchors_per_target) for p in fs]
    bundle = {
        "scientific_label": "synthetic corroboration causal probe; not efficacy evidence",
        "summary": summarize(rows),
        "worlds": rows,
    }
    out = Path(args.out)
    if not out.is_absolute(): out = REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(bundle["summary"], indent=2, sort_keys=True))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
