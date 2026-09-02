"""Thin adapter that calls frozen v1.4 using the supplied llm_state_bridge encoder/decoder.

This module does NOT implement any encoding heuristics. It relies entirely on
btbc.llm_state_bridge to produce the numeric arrays and mapping expected by
frozen BTBC v1.x. It calls the exact frozen API:

    out, final_actions, conf, rm, ctr, routed, blocked, mean_score = btbc_v14(obs, obs_r, st, rt, edges, policy, router, operating)

and then decodes final_actions via the bridge and writes deterministic updates
back to the SQLite `memories` table. Failures are loud and immediate.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import importlib
import os
import json
import hashlib
import time
import sqlite3

import joblib
import numpy as np

from btbc.llm_state_bridge import (
    encode_sqlite_to_v14_state,
    decode_v14_out_to_records,
    decode_v14_actions,
)

FROZEN_DIR = os.path.join(os.path.dirname(__file__), "frozen")
FROZEN_ROUTER_PATH = os.path.join(FROZEN_DIR, "router.joblib")
FROZEN_OPERATING_PATH = os.path.join(FROZEN_DIR, "operating.json")
FROZEN_V14_MODULE = "btbc.frozen.v1_4"
FROZEN_V14_FN = "btbc_v14"
FROZEN_V11_MODULE = "btbc.frozen.v1_1"


def _hash_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                c = f.read(8192)
                if not c:
                    break
                h.update(c)
        return h.hexdigest()
    except Exception:
        return None


def _hash_dir(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        if not os.path.isdir(path):
            return None
        for root, dirs, files in os.walk(path):
            dirs.sort()
            files.sort()
            for fname in files:
                full = os.path.join(root, fname)
                if not os.path.isfile(full):
                    continue
                with open(full, "rb") as f:
                    while True:
                        c = f.read(8192)
                        if not c:
                            break
                        h.update(c)
        return h.hexdigest()
    except Exception:
        return None


def _load_frozen_v14_function():
    try:
        mod = importlib.import_module(FROZEN_V14_MODULE)
    except Exception as e:
        raise RuntimeError(f"Frozen v1.4 module {FROZEN_V14_MODULE} not importable: {e}")
    if not hasattr(mod, FROZEN_V14_FN):
        raise RuntimeError(f"Frozen v1.4 module must expose function '{FROZEN_V14_FN}'")
    return getattr(mod, FROZEN_V14_FN)


def _load_policy():
    # Prefer the Policy class exposed by frozen v1.1 sources
    try:
        v11 = importlib.import_module(FROZEN_V11_MODULE)
        if hasattr(v11, "Policy"):
            return v11.Policy()
    except Exception:
        pass
    # As a fallback, return None to let frozen code decide — but per spec we should fail fast.
    raise RuntimeError(f"Policy class not found in {FROZEN_V11_MODULE}. Place v1.1 sources under btbc/frozen/ with a Policy class.")


def derive_trusted_context_v1_4(db_path: str, session_id: str, limit: int = 500, ablations: Optional[Dict[str, bool]] = None, config_path: str = "btbc/v1_4_config.json") -> Dict[str, Any]:
    """Run frozen v1.4 via the provided bridge and apply deterministic DB updates.

    Returns a dict with keys:
      - memory_context: decoded text lines (string)
      - decisions: list of per-memory decision dicts (from decode_v14_actions)
      - metrics: dict from frozen run
      - out_array: numpy ndarray returned by frozen v1.4 (numeric state)
      - actions_array: numpy ndarray of actions returned by frozen v1.4
      - frozen_hashes: dict with frozen_dir_hash, router_hash, operating_hash, adapter_hash
    
    This function fails loudly on any mismatch in mapping or DB application.
    """
    if ablations is None:
        ablations = {}

    if not os.path.isdir(FROZEN_DIR):
        raise RuntimeError("btbc/frozen/ directory not found. Place frozen v1.1..v1.4 source and artifacts there.")
    if not os.path.exists(FROZEN_ROUTER_PATH):
        raise RuntimeError(f"Frozen router artifact not found at {FROZEN_ROUTER_PATH}. Add trained router.joblib for v1.4.")
    if not os.path.exists(FROZEN_OPERATING_PATH):
        raise RuntimeError(f"Frozen operating config not found at {FROZEN_OPERATING_PATH}. Add operating.json for v1.4.")

    # 1) Encode via bridge
    enc = encode_sqlite_to_v14_state(db_path, session_id, limit=limit, ablations=ablations, config_path=config_path)
    if not isinstance(enc, tuple) or len(enc) != 6:
        raise RuntimeError("Bridge encoder must return (obs, obs_r, st, rt, edges, mapping)")
    obs, obs_r, st, rt, edges, mapping = enc

    # 2) Load frozen function and artifacts
    btbc_v14 = _load_frozen_v14_function()
    router = joblib.load(FROZEN_ROUTER_PATH)
    with open(FROZEN_OPERATING_PATH, "r") as f:
        operating = json.load(f)

    # 3) Policy
    policy = _load_policy()

    # 4) Call exact API
    result = btbc_v14(obs, obs_r, st, rt, edges, policy, router, operating)
    # Expecting 8-tuple
    if not isinstance(result, tuple) or len(result) != 8:
        raise RuntimeError("Frozen v1.4 must return 8-tuple: out, final_actions, conf, rm, ctr, routed, blocked, mean_score")
    out, final_actions, conf, rm, ctr, routed, blocked, mean_score = result

    out_arr = np.asarray(out)
    actions_arr = np.asarray(final_actions)

    # 5) Decode decisions with bridge helper
    decisions = decode_v14_actions(actions_arr, out_arr, mapping)

    # 6) Apply deterministic updates to SQLite. Fail loudly on mismatches.
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # ensure memories table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'")
        if cur.fetchone() is None:
            raise RuntimeError("SQLite DB has no 'memories' table to apply decisions")

        applied = []
        now = int(time.time())
        for d in decisions:
            mid = d.get("memory_id")
            if not mid:
                raise RuntimeError(f"Decision missing memory_id: {d}")
            # ensure record exists
            cur.execute("SELECT COUNT(1) FROM memories WHERE memory_id = ?", (mid,))
            if cur.fetchone()[0] == 0:
                raise RuntimeError(f"Decision targets unknown memory_id {mid}")
            decision = d.get("decision")
            reason = d.get("cell_actions") or d.get("decoded_value") or f"v1_4:{decision}"
            # If decision is REPAIR and decoded_value present, update value too
            if decision == "REPAIR" and d.get("decoded_value") is not None:
                cur.execute("UPDATE memories SET value = ?, controller_decision = ?, controller_reason = ?, updated_at = ? WHERE memory_id = ?", (d.get("decoded_value"), decision, json.dumps(reason), now, mid))
            else:
                cur.execute("UPDATE memories SET controller_decision = ?, controller_reason = ?, updated_at = ? WHERE memory_id = ?", (decision, json.dumps(reason), now, mid))
            applied.append({"memory_id": mid, "decision": decision, "reason": reason})
        conn.commit()
    finally:
        conn.close()

    # 7) Decode out to human-readable records for memory_context
    decoded_records = decode_v14_out_to_records(out_arr, mapping)
    memory_context_lines = [f"{r.get('entity')}.{r.get('attribute')} = {r.get('value')}" for r in decoded_records]
    memory_context = "\n".join(memory_context_lines)

    metrics = {
        "conf": conf,
        "rm": rm,
        "ctr": ctr,
        "routed": int(routed),
        "blocked": int(blocked),
        "mean_score": float(mean_score) if mean_score is not None else None,
        "applied_decisions": len(decisions),
    }

    frozen_dir_hash = _hash_dir(FROZEN_DIR)
    router_hash = _hash_file(FROZEN_ROUTER_PATH)
    operating_hash = _hash_file(FROZEN_OPERATING_PATH)
    adapter_hash = _hash_file(os.path.abspath(__file__))

    return {
        "memory_context": memory_context,
        "decisions": decisions,
        "metrics": metrics,
        "out_array": out_arr,
        "actions_array": actions_arr,
        "frozen_dir_hash": frozen_dir_hash,
        "router_hash": router_hash,
        "operating_hash": operating_hash,
        "adapter_hash": adapter_hash,
    }
