#!/usr/bin/env python3
"""Synthetic independent-relation probe for the BTBC categorical bridge.

Diagnostic only. Frozen v1.x source, router.joblib, and operating.json are not
modified. The probe seeds a disposable DB, uses llm_state_bridge normally, then
adds *oracle-labeled synthetic relation observations* in-memory for currently
corrupted fields. Those observations are deliberately independent of the
observed target codeword: they are computed from the scenario ground truth and
other witness fields. This is NOT a deployable algorithm and must never be
reported as benchmark efficacy. Its purpose is causal localization: can the
unchanged frozen decoder/reviewer produce repair candidates when independent
relational evidence is actually present?
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import joblib
import numpy as np

from btbc import memory_engine
from btbc.frozen_v1_4_adapter import (
    FROZEN_OPERATING_PATH,
    FROZEN_ROUTER_PATH,
    _load_frozen_v14_function,
    _load_policy,
)
from btbc.llm_state_bridge import decode_v14_out_to_records, encode_sqlite_to_v14_state
import btbc.frozen.v1_4 as frozen_v14_module

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTE_ALL = {"harm_weight": 0.0, "threshold": -1.0, "target_false_correction_rate": 1.0}


def _field_key(field: Sequence[str]) -> str:
    return json.dumps([str(field[0]), str(field[1])], separators=(",", ":"))


def _load_world(path: Path) -> Mapping[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    scenarios = obj.get("scenarios", [])
    if len(scenarios) != 1:
        raise ValueError(f"{path}: expected exactly one scenario")
    return scenarios[0]


def _files(path: Path, limit: int) -> List[Path]:
    fs = [path] if path.is_file() else sorted(p for p in path.glob("*.json") if p.name != "manifest.json")
    return fs if limit == 0 else fs[:limit]


def _relation(a: int, b: int) -> np.int8:
    if a == 0 or b == 0:
        return np.int8(0)
    return np.int8(1 if a == b else -1)


def inject_oracle_corroboration(
    obs: np.ndarray,
    obs_r: np.ndarray,
    st: np.ndarray,
    rt: np.ndarray,
    edges: Sequence[Tuple[int, int]],
    mapping: Mapping[str, Any],
    scenario: Mapping[str, Any],
    *,
    witness_fields: int = 3,
    relation_trust: float = 0.99,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[Tuple[int, int]], Dict[str, Any]]:
    """Return copies with synthetic truth-derived relation observations appended.

    Each target bit is connected to up to ``witness_fields`` nodes belonging to
    other fields. The observed relation is what the relation *would* be if the
    target bit held its ground-truth codeword. This gives the frozen relational
    evidence family an independent signal while leaving state observations and
    provenance untouched.
    """
    obs = np.asarray(obs).copy(); obs_r = np.asarray(obs_r).copy()
    st = np.asarray(st).copy(); rt = np.asarray(rt).copy()
    new_edges = [tuple(map(int, e)) for e in edges]
    existing = {tuple(sorted(e)) for e in new_edges}
    fields = [tuple(x) for x in mapping.get("fields", [])]
    width = int(mapping.get("code_width") or 0)
    codebooks = mapping.get("codebooks") or {}
    truth = {str(k): str(v) for k, v in scenario.get("ground_truth_fields", {}).items()}
    corrupted = set(str(x) for x in scenario.get("corrupted_fields", []))
    appended_rel_cols: List[np.ndarray] = []
    appended_trust_cols: List[np.ndarray] = []
    added_meta: List[Dict[str, Any]] = []

    for f_idx, field in enumerate(fields):
        name = f"{field[0]}.{field[1]}"
        if name not in corrupted or name not in truth:
            continue
        fkey = _field_key(field)
        gt_value = truth[name]
        if gt_value not in (codebooks.get(fkey) or {}):
            continue
        gt_code = np.asarray(codebooks[fkey][gt_value], dtype=np.int8)
        witnesses = [idx for idx in range(len(fields)) if idx != f_idx][:max(0, int(witness_fields))]
        if not witnesses:
            continue
        for bit in range(width):
            target_node = f_idx * width + bit
            for rank, w_idx in enumerate(witnesses):
                # Shift witness bit by rank so multiple witnesses are not exact
                # copies of a single local position.
                witness_bit = (bit + rank) % width
                witness_node = w_idx * width + witness_bit
                edge = tuple(sorted((target_node, witness_node)))
                if edge in existing:
                    continue
                existing.add(edge); new_edges.append(edge)
                rel_col = np.zeros(obs.shape[0], dtype=np.int8)
                for t in range(obs.shape[0]):
                    rel_col[t] = _relation(int(gt_code[bit]), int(obs[t, witness_node]))
                appended_rel_cols.append(rel_col)
                appended_trust_cols.append(np.full(obs.shape[0], float(relation_trust), dtype=float))
                added_meta.append({
                    "target_field": name,
                    "target_bit": bit,
                    "witness_field": f"{fields[w_idx][0]}.{fields[w_idx][1]}",
                    "witness_bit": witness_bit,
                    "edge": list(edge),
                    "trust": float(relation_trust),
                })

    if appended_rel_cols:
        obs_r = np.column_stack([obs_r, *appended_rel_cols])
        rt = np.column_stack([rt, *appended_trust_cols])
    return obs, obs_r, st, rt, new_edges, {
        "added_edges": len(added_meta),
        "edge_meta": added_meta,
        "targets": sorted(corrupted),
    }


def _final_field_values(out: np.ndarray, mapping: Mapping[str, Any]) -> Dict[str, Optional[str]]:
    recs = decode_v14_out_to_records(np.asarray(out), mapping)
    vals: Dict[str, Optional[str]] = {}
    for r in recs:
        vals[f"{r.get('entity')}.{r.get('attribute')}"] = r.get("value")
    return vals


def _run_state(obs, obs_r, st, rt, edges, mapping, scenario, router, policy, btbc_v14, operating):
    safe, actions, recovery, rec_actions, conf, rm, ctr = frozen_v14_module.v12.get_branches(
        obs, obs_r, st, rt, edges, policy
    )
    out, final_actions, *_rest, routed, blocked, mean_score = btbc_v14(
        obs, obs_r, st, rt, edges, policy, router, operating
    )
    out = np.asarray(out); final_actions = np.asarray(final_actions).astype(str)
    truth = {str(k): str(v) for k, v in scenario.get("ground_truth_fields", {}).items()}
    corrupted = set(str(x) for x in scenario.get("corrupted_fields", []))
    final_vals = _final_field_values(out, mapping)
    repaired_fields = sorted(k for k in corrupted if final_vals.get(k) == truth.get(k))
    return {
        "pre_gate_candidate_cells": int(np.sum(np.asarray(recovery) != np.asarray(safe))),
        "escalated_cells": int(np.sum(np.asarray(actions).astype(str) == "ESCALATE")),
        "stage1_repairs": int(np.sum(np.asarray(actions).astype(str) == "REPAIR1")),
        "stage2_repairs": int(np.sum(np.asarray(rec_actions).astype(str) == "REPAIR2")),
        "routed": int(routed), "blocked": int(blocked),
        "mean_score": float(mean_score),
        "changed_cells": int(np.sum(out != obs)),
        "action_counts": {str(v): int(c) for v, c in zip(*np.unique(final_actions, return_counts=True))},
        "repaired_corrupted_fields": repaired_fields,
        "repaired_corrupted_field_count": len(repaired_fields),
        "final_fields": final_vals,
        "relation_mismatch": float(rm),
        "mean_confidence": float(np.mean(conf)),
    }


def diagnose_world(scenario: Mapping[str, Any], *, witness_fields: int = 3) -> Dict[str, Any]:
    sid = str(scenario["session_id"])
    with tempfile.TemporaryDirectory(prefix="btbc_corrob_") as td:
        db = str(Path(td) / "world.db")
        memory_engine.seed_scenario(db, scenario)
        obs, obs_r, st, rt, edges, mapping = encode_sqlite_to_v14_state(db, sid, limit=500)
        router = joblib.load(FROZEN_ROUTER_PATH); policy = _load_policy(); btbc_v14 = _load_frozen_v14_function()
        locked = json.loads(Path(FROZEN_OPERATING_PATH).read_text(encoding="utf-8"))
        aug = inject_oracle_corroboration(obs, obs_r, st, rt, edges, mapping, scenario, witness_fields=witness_fields)
        aobs, aobs_r, ast, art, aedges, meta = aug
        return {
            "scenario_id": scenario.get("id"),
            "corrupted_fields": list(scenario.get("corrupted_fields", [])),
            "baseline_locked": _run_state(obs, obs_r, st, rt, edges, mapping, scenario, router, policy, btbc_v14, locked),
            "baseline_route_all": _run_state(obs, obs_r, st, rt, edges, mapping, scenario, router, policy, btbc_v14, ROUTE_ALL),
            "corroborated_locked": _run_state(aobs, aobs_r, ast, art, aedges, mapping, scenario, router, policy, btbc_v14, locked),
            "corroborated_route_all": _run_state(aobs, aobs_r, ast, art, aedges, mapping, scenario, router, policy, btbc_v14, ROUTE_ALL),
            "corroboration": meta,
        }


def summarize(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    arms = ["baseline_locked", "baseline_route_all", "corroborated_locked", "corroborated_route_all"]
    out: Dict[str, Any] = {"worlds": len(rows), "arms": {}}
    for arm in arms:
        out["arms"][arm] = {
            "pre_gate_candidate_cells": sum(int(r[arm]["pre_gate_candidate_cells"]) for r in rows),
            "escalated_cells": sum(int(r[arm]["escalated_cells"]) for r in rows),
            "stage1_repairs": sum(int(r[arm]["stage1_repairs"]) for r in rows),
            "stage2_repairs": sum(int(r[arm]["stage2_repairs"]) for r in rows),
            "routed": sum(int(r[arm]["routed"]) for r in rows),
            "blocked": sum(int(r[arm]["blocked"]) for r in rows),
            "changed_cells": sum(int(r[arm]["changed_cells"]) for r in rows),
            "repaired_corrupted_fields": sum(int(r[arm]["repaired_corrupted_field_count"]) for r in rows),
            "worlds_with_pre_gate_candidates": sum(bool(r[arm]["pre_gate_candidate_cells"]) for r in rows),
            "worlds_with_repaired_corrupted_fields": sum(bool(r[arm]["repaired_corrupted_field_count"]) for r in rows),
        }
    out["added_edges"] = sum(int(r["corroboration"]["added_edges"]) for r in rows)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenarios", required=True)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--witness-fields", type=int, default=3)
    p.add_argument("--out", default="results/corroboration/summary.json")
    args = p.parse_args(argv)
    src = Path(args.scenarios); src = src if src.is_absolute() else REPO_ROOT / src
    fs = _files(src, args.limit)
    rows = [diagnose_world(_load_world(f), witness_fields=args.witness_fields) for f in fs]
    bundle = {
        "scientific_label": "oracle synthetic corroboration diagnostic only",
        "warning": "Ground truth is used to construct relation observations. This is causal diagnosis, not an efficacy benchmark.",
        "summary": summarize(rows),
        "worlds": rows,
    }
    out = Path(args.out); out = out if out.is_absolute() else REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(bundle["summary"], indent=2, sort_keys=True))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
