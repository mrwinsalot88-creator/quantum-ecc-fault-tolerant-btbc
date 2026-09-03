#!/usr/bin/env python3
"""Non-oracle BTBC bridge-v2 experiment using historical consensus anchors.

This is the first follow-up after the oracle corroboration diagnostic. It does
NOT use scenario ground truth to construct evidence. Ground truth is used only
for evaluation after the controller has run.

Bridge-v2 prototype idea
------------------------
For a field whose latest active observation has low trust/confidence, inspect
older observations of that same field. If at least two sufficiently trusted
historical observations strongly agree on a different categorical value, add
an auxiliary anchor codeword representing that observed consensus. Connect the
current field bits to the anchor bits with explicit +1 equality relations.
Those anchors are derived entirely from persisted memory history and provenance,
not from corruption labels or ground truth.

Frozen v1.x source, router.joblib, and operating.json remain untouched.

The experiment also reports a deliberately simple ``consensus_only`` baseline
that directly substitutes the same consensus value. This is essential: if a
plain trust-weighted consensus rule performs as well as or better than frozen
BTBC given exactly the same evidence, we should not claim the BTBC controller
adds value.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from collections import defaultdict
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
from btbc.llm_state_bridge import decode_v14_out_to_records, encode_sqlite_to_v14_state
import btbc.frozen.v1_4 as frozen_v14_module

REPO_ROOT = Path(__file__).resolve().parents[1]


def _field_key(field: Sequence[str]) -> str:
    return json.dumps([str(field[0]), str(field[1])], separators=(",", ":"))


def _row_score(row: Mapping[str, Any]) -> float:
    return float(row.get("source_trust", 0.5) or 0.5) * float(row.get("confidence", 0.5) or 0.5)


def _load_world(path: Path) -> Mapping[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    scenarios = obj.get("scenarios", []) if isinstance(obj, dict) else []
    if len(scenarios) != 1:
        raise ValueError(f"{path}: expected exactly one scenario")
    return scenarios[0]


def _files(path: Path, limit: int) -> List[Path]:
    files = [path] if path.is_file() else sorted(p for p in path.glob("*.json") if p.name != "manifest.json")
    return files if limit == 0 else files[:limit]


def _latest_active_id(mapping: Mapping[str, Any], field_index: int) -> Optional[str]:
    active = mapping.get("active_memory_ids") or []
    for t in range(len(active) - 1, -1, -1):
        if field_index < len(active[t]) and active[t][field_index] is not None:
            return str(active[t][field_index])
    return None


def derive_history_consensus(
    mapping: Mapping[str, Any],
    *,
    max_current_score: float = 0.45,
    min_witness_score: float = 0.65,
    min_supporters: int = 2,
    min_consensus_share: float = 0.72,
    min_weight_margin: float = 0.45,
) -> Dict[int, Dict[str, Any]]:
    """Derive non-oracle per-field consensus anchors from persisted history.

    No scenario labels or ground truth are accepted by this function. It only
    sees the bridge mapping created from the database.
    """
    rows = mapping.get("memory_rows") or {}
    fields = [tuple(x) for x in mapping.get("fields") or []]
    anchors: Dict[int, Dict[str, Any]] = {}

    for f_idx, field in enumerate(fields):
        latest_id = _latest_active_id(mapping, f_idx)
        latest = rows.get(latest_id) if latest_id else None
        if not latest:
            continue
        current_value = str(latest.get("value"))
        current_score = _row_score(latest)
        if current_score > float(max_current_score):
            continue

        current_time = latest.get("valid_from")
        candidates: List[Mapping[str, Any]] = []
        for mid, row in rows.items():
            if str(mid) == latest_id:
                continue
            if str(row.get("entity")) != str(field[0]) or str(row.get("attribute")) != str(field[1]):
                continue
            if current_time is not None and row.get("valid_from") is not None:
                if int(row.get("valid_from")) > int(current_time):
                    continue
            score = _row_score(row)
            if score < float(min_witness_score):
                continue
            candidates.append(row)

        if not candidates:
            continue

        weight_by_value: Dict[str, float] = defaultdict(float)
        supporters_by_value: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
        for row in candidates:
            value = str(row.get("value"))
            score = _row_score(row)
            weight_by_value[value] += score
            supporters_by_value[value].append(row)

        ranked = sorted(weight_by_value.items(), key=lambda kv: (-kv[1], kv[0]))
        best_value, best_weight = ranked[0]
        second_weight = ranked[1][1] if len(ranked) > 1 else 0.0
        total_weight = sum(weight_by_value.values())
        share = best_weight / total_weight if total_weight else 0.0
        supporters = supporters_by_value[best_value]

        if best_value == current_value:
            continue
        if len(supporters) < int(min_supporters):
            continue
        if share < float(min_consensus_share):
            continue
        if (best_weight - second_weight) < float(min_weight_margin):
            continue

        anchors[f_idx] = {
            "field": [str(field[0]), str(field[1])],
            "latest_memory_id": latest_id,
            "current_value": current_value,
            "current_score": current_score,
            "consensus_value": best_value,
            "consensus_weight": best_weight,
            "consensus_share": share,
            "weight_margin": best_weight - second_weight,
            "supporter_count": len(supporters),
            "supporters": [
                {
                    "memory_id": str(r.get("memory_id")),
                    "value": str(r.get("value")),
                    "source": str(r.get("source")),
                    "source_trust": float(r.get("source_trust", 0.5) or 0.5),
                    "confidence": float(r.get("confidence", 0.5) or 0.5),
                    "score": _row_score(r),
                    "valid_from": r.get("valid_from"),
                }
                for r in supporters
            ],
        }
    return anchors


def augment_with_history_anchors(
    obs: np.ndarray,
    obs_r: np.ndarray,
    st: np.ndarray,
    rt: np.ndarray,
    edges: Sequence[Tuple[int, int]],
    mapping: Mapping[str, Any],
    anchors: Mapping[int, Mapping[str, Any]],
    *,
    relation_trust_cap: float = 0.99,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[Tuple[int, int]], Dict[str, Any]]:
    """Append auxiliary anchor nodes and equality-relation observations."""
    obs = np.asarray(obs, dtype=np.int8)
    obs_r = np.asarray(obs_r, dtype=np.int8)
    st = np.asarray(st, dtype=float)
    rt = np.asarray(rt, dtype=float)
    width = int(mapping.get("code_width") or 0)
    fields = [tuple(x) for x in mapping.get("fields") or []]
    codebooks = mapping.get("codebooks") or {}
    original_n = obs.shape[1]

    extra_obs_cols: List[np.ndarray] = []
    extra_st_cols: List[np.ndarray] = []
    new_edges = [tuple(map(int, e)) for e in edges]
    extra_rel_cols: List[np.ndarray] = []
    extra_rt_cols: List[np.ndarray] = []
    meta: List[Dict[str, Any]] = []

    anchor_base_by_field: Dict[int, int] = {}
    for f_idx in sorted(anchors):
        if f_idx >= len(fields):
            continue
        field = fields[f_idx]
        fkey = _field_key(field)
        consensus_value = str(anchors[f_idx]["consensus_value"])
        codebook = codebooks.get(fkey) or {}
        if consensus_value not in codebook:
            continue
        code = np.asarray(codebook[consensus_value], dtype=np.int8)
        if code.size != width:
            continue
        base = original_n + len(extra_obs_cols)
        anchor_base_by_field[f_idx] = base
        supporter_scores = [float(x["score"]) for x in anchors[f_idx].get("supporters", [])]
        anchor_trust = min(float(relation_trust_cap), max(0.05, float(np.mean(supporter_scores)))) if supporter_scores else 0.5
        for bit in range(width):
            extra_obs_cols.append(np.full(obs.shape[0], int(code[bit]), dtype=np.int8))
            extra_st_cols.append(np.full(obs.shape[0], anchor_trust, dtype=float))
        for bit in range(width):
            target_node = f_idx * width + bit
            anchor_node = base + bit
            new_edges.append((target_node, anchor_node))
            # Explicit equality observation: current field is expected to agree
            # with the independent historical-consensus anchor.
            extra_rel_cols.append(np.ones(obs.shape[0], dtype=np.int8))
            extra_rt_cols.append(np.full(obs.shape[0], anchor_trust, dtype=float))
        meta.append({
            **dict(anchors[f_idx]),
            "field_index": int(f_idx),
            "anchor_node_start": int(base),
            "anchor_trust": float(anchor_trust),
            "added_nodes": int(width),
            "added_edges": int(width),
        })

    if extra_obs_cols:
        obs2 = np.column_stack([obs, *extra_obs_cols]).astype(np.int8)
        st2 = np.column_stack([st, *extra_st_cols]).astype(float)
    else:
        obs2, st2 = obs.copy(), st.copy()
    if extra_rel_cols:
        obs_r2 = np.column_stack([obs_r, *extra_rel_cols]).astype(np.int8)
        rt2 = np.column_stack([rt, *extra_rt_cols]).astype(float)
    else:
        obs_r2, rt2 = obs_r.copy(), rt.copy()

    return obs2, obs_r2, st2, rt2, new_edges, {
        "original_n": int(original_n),
        "anchor_count": len(meta),
        "added_nodes": int(obs2.shape[1] - original_n),
        "added_edges": int(len(new_edges) - len(edges)),
        "anchors": meta,
    }


def _field_values_from_out(out: np.ndarray, mapping: Mapping[str, Any], original_n: int) -> Dict[str, Optional[str]]:
    sliced = np.asarray(out)[:, :original_n]
    records = decode_v14_out_to_records(sliced, mapping)
    vals: Dict[str, Optional[str]] = {}
    for r in records:
        vals[f"{r.get('entity')}.{r.get('attribute')}"] = r.get("value")
    return vals


def _evaluate(final_fields: Mapping[str, Any], scenario: Mapping[str, Any], pre_fields: Mapping[str, Any]) -> Dict[str, Any]:
    truth = {str(k): str(v) for k, v in scenario.get("ground_truth_fields", {}).items()}
    corrupted = set(str(x) for x in scenario.get("corrupted_fields", []))
    legitimate = set(str(x) for x in scenario.get("legitimate_fields", []))
    final = {str(k): None if v is None else str(v) for k, v in final_fields.items()}
    pre = {str(k): None if v is None else str(v) for k, v in pre_fields.items()}

    final_errors = sorted(k for k, v in truth.items() if final.get(k) != v)
    pre_errors = sorted(k for k, v in truth.items() if pre.get(k) != v)
    repaired = sorted(k for k in corrupted if pre.get(k) != truth.get(k) and final.get(k) == truth.get(k))
    false_corrections = sorted(k for k, v in truth.items() if pre.get(k) == v and final.get(k) != v)
    legit_damage = sorted(k for k in legitimate if pre.get(k) == truth.get(k) and final.get(k) != truth.get(k))
    changed = sorted(k for k in truth if final.get(k) != pre.get(k))
    return {
        "pre_error_count": len(pre_errors),
        "final_error_count": len(final_errors),
        "error_delta": len(pre_errors) - len(final_errors),
        "repaired_corrupted_fields": repaired,
        "true_repairs": len(repaired),
        "false_corrected_fields": false_corrections,
        "false_corrections": len(false_corrections),
        "legitimate_damaged_fields": legit_damage,
        "legitimate_change_damage": len(legit_damage),
        "changed_fields": changed,
        "changed_field_count": len(changed),
        "final_error_fields": final_errors,
    }


def _consensus_only_fields(pre_fields: Mapping[str, Any], anchors: Mapping[int, Mapping[str, Any]], mapping: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(pre_fields)
    fields = [tuple(x) for x in mapping.get("fields") or []]
    for f_idx, info in anchors.items():
        if f_idx >= len(fields):
            continue
        field = fields[f_idx]
        out[f"{field[0]}.{field[1]}"] = info["consensus_value"]
    return out


def diagnose_world(scenario: Mapping[str, Any]) -> Dict[str, Any]:
    sid = str(scenario["session_id"])
    with tempfile.TemporaryDirectory(prefix="btbc_bridge_v2_") as td:
        db = str(Path(td) / "world.db")
        memory_engine.seed_scenario(db, scenario)
        pre_fields = memory_engine.active_field_values(db, sid)
        obs, obs_r, st, rt, edges, mapping = encode_sqlite_to_v14_state(db, sid, limit=500)
        original_n = int(obs.shape[1])

        anchors = derive_history_consensus(mapping)
        aug_obs, aug_obs_r, aug_st, aug_rt, aug_edges, aug_meta = augment_with_history_anchors(
            obs, obs_r, st, rt, edges, mapping, anchors
        )

        router = joblib.load(FROZEN_ROUTER_PATH)
        policy = _load_policy()
        btbc_v14 = _load_frozen_v14_function()
        locked = json.loads(Path(FROZEN_OPERATING_PATH).read_text(encoding="utf-8"))

        # Existing bridge, unchanged.
        base_safe, base_actions, base_recovery, base_rec_actions, *_ = frozen_v14_module.v12.get_branches(
            obs, obs_r, st, rt, edges, policy
        )
        base_result = btbc_v14(obs, obs_r, st, rt, edges, policy, router, locked)
        base_out, base_final_actions, *_base_rest, base_routed, base_blocked, base_mean_score = base_result
        base_fields = _field_values_from_out(np.asarray(base_out), mapping, original_n)

        # Non-oracle bridge-v2 prototype.
        v2_safe, v2_actions, v2_recovery, v2_rec_actions, *_ = frozen_v14_module.v12.get_branches(
            aug_obs, aug_obs_r, aug_st, aug_rt, aug_edges, policy
        )
        v2_result = btbc_v14(aug_obs, aug_obs_r, aug_st, aug_rt, aug_edges, policy, router, locked)
        v2_out, v2_final_actions, *_v2_rest, v2_routed, v2_blocked, v2_mean_score = v2_result
        v2_fields = _field_values_from_out(np.asarray(v2_out), mapping, original_n)

        consensus_fields = _consensus_only_fields(pre_fields, anchors, mapping)

        return {
            "scenario_id": scenario.get("id"),
            "world_seed": scenario.get("world_seed"),
            "anchor_count": len(anchors),
            "anchor_fields": [
                f"{info['field'][0]}.{info['field'][1]}" for _, info in sorted(anchors.items())
            ],
            "anchor_details": aug_meta["anchors"],
            "plain": _evaluate(pre_fields, scenario, pre_fields),
            "consensus_only": _evaluate(consensus_fields, scenario, pre_fields),
            "btbc_v1_bridge": {
                **_evaluate(base_fields, scenario, pre_fields),
                "pre_gate_candidate_cells": int(np.sum(np.asarray(base_recovery) != np.asarray(base_safe))),
                "escalated_cells": int(np.sum(np.asarray(base_actions).astype(str) == "ESCALATE")),
                "stage2_repairs": int(np.sum(np.asarray(base_rec_actions).astype(str) == "REPAIR2")),
                "routed": int(base_routed),
                "blocked": int(base_blocked),
                "mean_score": float(base_mean_score),
            },
            "btbc_v2_history_anchor": {
                **_evaluate(v2_fields, scenario, pre_fields),
                "pre_gate_candidate_cells": int(np.sum(np.asarray(v2_recovery) != np.asarray(v2_safe))),
                "escalated_cells": int(np.sum(np.asarray(v2_actions).astype(str) == "ESCALATE")),
                "stage2_repairs": int(np.sum(np.asarray(v2_rec_actions).astype(str) == "REPAIR2")),
                "routed": int(v2_routed),
                "blocked": int(v2_blocked),
                "mean_score": float(v2_mean_score),
                "added_nodes": int(aug_meta["added_nodes"]),
                "added_edges": int(aug_meta["added_edges"]),
            },
        }


def summarize(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    arms = ["plain", "consensus_only", "btbc_v1_bridge", "btbc_v2_history_anchor"]
    out: Dict[str, Any] = {
        "worlds": len(rows),
        "worlds_with_anchors": sum(int(r.get("anchor_count", 0) > 0) for r in rows),
        "anchor_count": sum(int(r.get("anchor_count", 0)) for r in rows),
        "arms": {},
    }
    for arm in arms:
        agg: Dict[str, Any] = {
            "pre_error_count": 0,
            "final_error_count": 0,
            "error_delta": 0,
            "true_repairs": 0,
            "false_corrections": 0,
            "legitimate_change_damage": 0,
            "changed_field_count": 0,
            "worlds_improved": 0,
            "worlds_tied": 0,
            "worlds_worsened": 0,
        }
        for r in rows:
            a = r[arm]
            for k in ["pre_error_count", "final_error_count", "error_delta", "true_repairs", "false_corrections", "legitimate_change_damage", "changed_field_count"]:
                agg[k] += int(a.get(k, 0))
            d = int(a.get("error_delta", 0))
            agg["worlds_improved"] += int(d > 0)
            agg["worlds_tied"] += int(d == 0)
            agg["worlds_worsened"] += int(d < 0)
        if arm.startswith("btbc_"):
            for k in ["pre_gate_candidate_cells", "escalated_cells", "stage2_repairs", "routed", "blocked"]:
                agg[k] = sum(int(r[arm].get(k, 0)) for r in rows)
        out["arms"][arm] = agg
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenarios", required=True, help="Generated-world JSON file or directory")
    p.add_argument("--limit", type=int, default=200, help="0 means all worlds")
    p.add_argument("--out", default="results/bridge_v2/nonoracle_summary.json")
    args = p.parse_args(argv)

    src = Path(args.scenarios)
    if not src.is_absolute():
        src = REPO_ROOT / src
    files = _files(src, args.limit)
    if not files:
        raise SystemExit(f"No scenario files found under {src}")
    rows = [diagnose_world(_load_world(f)) for f in files]
    bundle = {
        "scientific_label": "non-oracle bridge-v2 history-consensus anchor experiment",
        "construction_guardrail": "Ground truth/corruption labels are never passed to derive_history_consensus or augment_with_history_anchors; labels are used only by _evaluate after controller output.",
        "summary": summarize(rows),
        "worlds": rows,
    }
    out = Path(args.out)
    if not out.is_absolute():
        out = REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(bundle["summary"], indent=2, sort_keys=True))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
