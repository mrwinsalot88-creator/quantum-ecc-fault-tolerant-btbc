#!/usr/bin/env python3
"""Diagnose where frozen BTBC v1.4 becomes inert behind llm_state_bridge.

This script does not modify frozen source, retrain the router, recalibrate the
locked operating point, or mutate a persistent user database. Each scenario is
seeded into a disposable SQLite DB, encoded by the existing bridge, and then
run through the exact frozen v1.4 function under the locked operating point and
several explicitly-labeled debug-only permissive operating points.

It also calls the frozen v1.2 branch builder directly so we can distinguish:
  A) recovery candidates exist before v1.4 and are blocked by routing, versus
  B) the bridge/state representation never creates useful recovery candidates.
"""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import joblib
import numpy as np

from btbc import memory_engine
from btbc.frozen_v1_4_adapter import (
    FROZEN_OPERATING_PATH,
    FROZEN_ROUTER_PATH,
    _load_frozen_v14_function,
    _load_policy,
)
from btbc.llm_state_bridge import (
    decode_v14_actions,
    decode_v14_out_to_records,
    encode_sqlite_to_v14_state,
)
import btbc.frozen.v1_4 as frozen_v14_module


REPO_ROOT = Path(__file__).resolve().parents[1]

# IMPORTANT: v1.4 routes recovery when score >= threshold. Therefore threshold
# 1.0 is *more restrictive*, not more permissive. These debug profiles lower
# the threshold instead. target_false_correction_rate is metadata only at
# runtime; frozen btbc_v14 reads harm_weight and threshold.
DEBUG_PROFILES: Dict[str, Dict[str, float]] = {
    "route_all_escalations": {
        "harm_weight": 0.0,
        "threshold": -1.0,
        "target_false_correction_rate": 1.0,
    },
    "low_harm": {
        "harm_weight": 0.5,
        "threshold": -0.05,
        "target_false_correction_rate": 0.20,
    },
    "moderate": {
        "harm_weight": 1.0,
        "threshold": 0.0,
        "target_false_correction_rate": 0.10,
    },
}


def _action_counts(actions: np.ndarray) -> Dict[str, int]:
    arr = np.asarray(actions).astype(str)
    if arr.size == 0:
        return {}
    vals, counts = np.unique(arr, return_counts=True)
    return {str(v): int(c) for v, c in zip(vals, counts)}


def _changed_cells(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.sum(np.asarray(a) != np.asarray(b)))


def _load_one_scenario_file(path: Path) -> Tuple[str, Mapping[str, Any]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    scenarios = obj.get("scenarios") if isinstance(obj, dict) else None
    if not isinstance(scenarios, list) or len(scenarios) != 1:
        raise ValueError(f"{path}: expected exactly one scenario in 'scenarios'")
    return str(obj.get("system_prompt") or "Use the supplied memory."), scenarios[0]


def _iter_scenario_files(path: Path, limit: Optional[int]) -> List[Path]:
    if path.is_file():
        files = [path]
    else:
        files = sorted(p for p in path.glob("*.json") if p.name != "manifest.json")
    if limit is not None:
        files = files[: int(limit)]
    if not files:
        raise SystemExit(f"No scenario JSON files found under {path}")
    return files


def _cell_trace(
    actions: np.ndarray,
    out: np.ndarray,
    mapping: Mapping[str, Any],
    *,
    include_keep: bool = False,
) -> List[Dict[str, Any]]:
    actions = np.asarray(actions).astype(str)
    out = np.asarray(out)
    times = list(mapping.get("time_axis") or [])
    fields = list(mapping.get("fields") or [])
    width = int(mapping.get("code_width") or 1)
    active_ids = list(mapping.get("active_memory_ids") or [])
    codebooks = mapping.get("codebooks") or {}
    rows = mapping.get("memory_rows") or {}

    trace: List[Dict[str, Any]] = []
    for t in range(actions.shape[0]):
        for i in range(actions.shape[1]):
            action = str(actions[t, i])
            if not include_keep and action == "KEEP":
                continue
            f_idx = i // width
            if f_idx >= len(fields):
                continue
            field = fields[f_idx]
            fkey = json.dumps([str(field[0]), str(field[1])], separators=(",", ":"))
            start = f_idx * width
            stop = start + width
            mid = None
            if t < len(active_ids) and f_idx < len(active_ids[t]):
                mid = active_ids[t][f_idx]
            row = rows.get(mid) if mid else None
            vector = out[t, start:stop]
            decoded_value = None
            decode_distance = None
            best: List[Tuple[int, str]] = []
            for value, code in (codebooks.get(fkey) or {}).items():
                c = np.asarray(code, dtype=np.int8)
                known = vector != 0
                dist = int(np.sum(c[known] != vector[known])) if np.any(known) else int(vector.size)
                best.append((dist, str(value)))
            if best:
                best.sort(key=lambda x: (x[0], x[1]))
                decode_distance, decoded_value = best[0]
            trace.append({
                "t_index": int(t),
                "timestamp": times[t] if t < len(times) else None,
                "cell_index": int(i),
                "field_index": int(f_idx),
                "memory_id": mid,
                "entity": str(field[0]),
                "attribute": str(field[1]),
                "input_value": None if row is None else row.get("value"),
                "action": action,
                "decoded_value": decoded_value,
                "decode_distance": decode_distance,
                "output_cell": int(out[t, i]),
            })
    return trace


def diagnose_scenario(
    scenario: Mapping[str, Any],
    *,
    ablations: Optional[Mapping[str, bool]] = None,
    include_cell_trace: bool = True,
) -> Dict[str, Any]:
    sid = str(scenario["session_id"])
    with tempfile.TemporaryDirectory(prefix="btbc_diag_") as td:
        db = str(Path(td) / "world.db")
        memory_engine.seed_scenario(db, scenario)
        obs, obs_r, st, rt, edges, mapping = encode_sqlite_to_v14_state(
            db,
            sid,
            limit=max(100, len(scenario.get("memories", [])) + 10),
            ablations=dict(ablations or {}),
        )

        btbc_v14 = _load_frozen_v14_function()
        policy = _load_policy()
        router = joblib.load(FROZEN_ROUTER_PATH)
        locked = json.loads(Path(FROZEN_OPERATING_PATH).read_text(encoding="utf-8"))

        # Direct frozen pre-gate branches. This is diagnostic-only observation;
        # no source code or parameters are changed.
        safe, stage1_actions, recovery, recovery_actions, conf, rm, ctr = frozen_v14_module.v12.get_branches(
            obs, obs_r, st, rt, edges, policy
        )

        profiles: Dict[str, Dict[str, Any]] = {"locked": dict(locked), **DEBUG_PROFILES}
        runs: Dict[str, Any] = {}
        for name, operating in profiles.items():
            result = btbc_v14(obs, obs_r, st, rt, edges, policy, router, operating)
            out, actions, _conf, _rm, _ctr, routed, blocked, mean_score = result
            out_arr = np.asarray(out)
            actions_arr = np.asarray(actions)
            decoded_actions = decode_v14_actions(actions_arr, out_arr, mapping)
            decoded_records = decode_v14_out_to_records(out_arr, mapping)
            runs[name] = {
                "operating": operating,
                "routed": int(routed),
                "blocked": int(blocked),
                "mean_score": float(mean_score),
                "action_counts": _action_counts(actions_arr),
                "changed_from_observed_cells": _changed_cells(out_arr, obs),
                "changed_from_safe_cells": _changed_cells(out_arr, safe),
                "decoded_actions": decoded_actions,
                "decoded_records": decoded_records,
                "cell_trace": _cell_trace(actions_arr, out_arr, mapping) if include_cell_trace else [],
            }

        truth = {str(k): str(v) for k, v in scenario.get("ground_truth_fields", {}).items()}
        pre_fields = memory_engine.active_field_values(db, sid)
        return {
            "scenario_id": scenario.get("id"),
            "session_id": sid,
            "ground_truth_fields": truth,
            "pre_fields": pre_fields,
            "bridge_shape": {
                "T": int(obs.shape[0]),
                "N": int(obs.shape[1]),
                "E": int(len(edges)),
                "code_width": int(mapping.get("code_width") or 0),
            },
            "pre_gate": {
                "stage1_action_counts": _action_counts(stage1_actions),
                "recovery_action_counts": _action_counts(recovery_actions),
                "safe_changed_from_observed_cells": _changed_cells(safe, obs),
                "recovery_changed_from_safe_cells": _changed_cells(recovery, safe),
                "recovery_changed_from_observed_cells": _changed_cells(recovery, obs),
                "escalated_cells": int(np.sum(np.asarray(stage1_actions).astype(str) == "ESCALATE")),
                "recovery_candidate_cells": int(np.sum(np.asarray(recovery) != np.asarray(safe))),
                "relation_mismatch": float(rm),
                "mean_confidence": float(np.mean(conf)) if np.asarray(conf).size else None,
                "ctr": ctr,
            },
            "runs": runs,
        }


def summarize(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "worlds": len(rows),
        "worlds_with_pre_gate_candidates": 0,
        "pre_gate_candidate_cells": 0,
        "pre_gate_escalated_cells": 0,
        "profiles": {},
    }
    for row in rows:
        pg = row["pre_gate"]
        c = int(pg["recovery_candidate_cells"])
        out["pre_gate_candidate_cells"] += c
        out["pre_gate_escalated_cells"] += int(pg["escalated_cells"])
        if c:
            out["worlds_with_pre_gate_candidates"] += 1
        for name, run in row["runs"].items():
            p = out["profiles"].setdefault(name, {
                "routed": 0,
                "blocked": 0,
                "changed_from_observed_cells": 0,
                "worlds_with_any_change": 0,
                "action_counts": {},
            })
            p["routed"] += int(run["routed"])
            p["blocked"] += int(run["blocked"])
            changed = int(run["changed_from_observed_cells"])
            p["changed_from_observed_cells"] += changed
            if changed:
                p["worlds_with_any_change"] += 1
            for action, count in run["action_counts"].items():
                p["action_counts"][action] = int(p["action_counts"].get(action, 0)) + int(count)
    return out


def write_summary_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profiles = ["locked", *DEBUG_PROFILES.keys()]
    fields = [
        "scenario_id", "T", "N", "E", "pre_gate_candidates", "pre_gate_escalations",
    ]
    for p in profiles:
        fields += [f"{p}_routed", f"{p}_blocked", f"{p}_changed_cells"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            rec: Dict[str, Any] = {
                "scenario_id": row.get("scenario_id"),
                "T": row["bridge_shape"]["T"],
                "N": row["bridge_shape"]["N"],
                "E": row["bridge_shape"]["E"],
                "pre_gate_candidates": row["pre_gate"]["recovery_candidate_cells"],
                "pre_gate_escalations": row["pre_gate"]["escalated_cells"],
            }
            for p in profiles:
                run = row["runs"][p]
                rec[f"{p}_routed"] = run["routed"]
                rec[f"{p}_blocked"] = run["blocked"]
                rec[f"{p}_changed_cells"] = run["changed_from_observed_cells"]
            w.writerow(rec)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenarios", required=True, help="One world JSON file or directory of world_*.json files")
    p.add_argument("--limit", type=int, default=20, help="Maximum worlds to diagnose; use 0 for all")
    p.add_argument("--out-dir", default="results/debug")
    p.add_argument("--no-cell-trace", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    path = Path(args.scenarios)
    if not path.is_absolute():
        path = REPO_ROOT / path
    limit = None if args.limit == 0 else int(args.limit)
    files = _iter_scenario_files(path, limit)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for src in files:
        _system_prompt, scenario = _load_one_scenario_file(src)
        row = diagnose_scenario(scenario, include_cell_trace=not args.no_cell_trace)
        row["source_file"] = str(src)
        rows.append(row)
        (out_dir / f"{row['scenario_id']}.json").write_text(
            json.dumps(row, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )

    summary = summarize(rows)
    bundle = {
        "scientific_label": "diagnostic only: frozen BTBC v1.4 through llm_state_bridge",
        "note": "Debug operating profiles are not validated operating points and must not be used as efficacy claims.",
        "profiles": {"locked": json.loads(Path(FROZEN_OPERATING_PATH).read_text(encoding="utf-8")), **DEBUG_PROFILES},
        "summary": summary,
        "worlds": rows,
    }
    (out_dir / "diagnostic_summary.json").write_text(
        json.dumps(bundle, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    write_summary_csv(out_dir / "diagnostic_summary.csv", rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"Wrote diagnostics to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
