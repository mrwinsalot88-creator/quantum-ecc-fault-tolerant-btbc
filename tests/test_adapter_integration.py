"""Strict integration tests for the frozen v1.4 adapter.

These tests are skipped if btbc/frozen/ or required artifacts are missing. They
verify numeric equality between a direct call to btbc_v14 and the adapter, and
check round-trip identity and a targeted repair scenario with redundant evidence.
"""
import os
import json
import pytest
import importlib
import joblib
import numpy as np
from btbc import llm_state_bridge as bridge
from btbc import frozen_v1_4_adapter as adapter
from datetime import datetime
import sqlite3

FROZEN_DIR = os.path.join(os.path.dirname(adapter.__file__), "frozen")
ROUTER_PATH = os.path.join(FROZEN_DIR, "router.joblib")
OPERATING_PATH = os.path.join(FROZEN_DIR, "operating.json")

skip_condition = not (os.path.isdir(FROZEN_DIR) and os.path.exists(ROUTER_PATH) and os.path.exists(OPERATING_PATH))

@pytest.mark.skipif(skip_condition, reason="Frozen v1.x sources or artifacts missing under btbc/frozen/")
def test_bridge_round_trip(tmp_path):
    db = str(tmp_path / "rt.db")
    # Create a minimal memories table
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE memories (
        memory_id TEXT PRIMARY KEY,
        session_id TEXT,
        entity TEXT,
        attribute TEXT,
        value TEXT,
        valid_from INTEGER,
        valid_to INTEGER,
        source TEXT,
        source_trust REAL,
        confidence REAL,
        created_at INTEGER,
        updated_at INTEGER,
        status TEXT
    )
    """)
    conn.commit()
    conn.close()

    # insert deterministic records
    now = int(datetime.utcnow().timestamp())
    r1 = {"memory_id": "m1", "session_id": "srt", "entity": "user", "attribute": "favorite_color", "value": "blue", "valid_from": now - 1000, "source": "user", "source_trust": 1.0, "confidence": 1.0, "created_at": now - 1000}
    r2 = {"memory_id": "m2", "session_id": "srt", "entity": "user", "attribute": "age", "value": "30", "valid_from": now - 1000, "source": "user", "source_trust": 1.0, "confidence": 1.0, "created_at": now - 1000}
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    for r in (r1, r2):
        cur.execute("INSERT INTO memories (memory_id, session_id, entity, attribute, value, valid_from, source, source_trust, confidence, created_at, updated_at, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r["memory_id"], r["session_id"], r["entity"], r["attribute"], r["value"], r["valid_from"], r["source"], r["source_trust"], r["confidence"], r["created_at"], r["created_at"], "active"))
    conn.commit()
    conn.close()

    # bridge round-trip
    ok = bridge.bridge_round_trip_ok(db, "srt", limit=100)
    assert ok is True

@pytest.mark.skipif(skip_condition, reason="Frozen v1.x sources or artifacts missing under btbc/frozen/")
def test_adapter_matches_direct_v14(tmp_path):
    db = str(tmp_path / "id.db")
    # prepare DB and insert a record
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE memories (
        memory_id TEXT PRIMARY KEY,
        session_id TEXT,
        entity TEXT,
        attribute TEXT,
        value TEXT,
        valid_from INTEGER,
        valid_to INTEGER,
        source TEXT,
        source_trust REAL,
        confidence REAL,
        created_at INTEGER,
        updated_at INTEGER,
        status TEXT
    )
    """)
    conn.commit()
    now = int(datetime.utcnow().timestamp())
    cur.execute("INSERT INTO memories (memory_id, session_id, entity, attribute, value, valid_from, source, source_trust, confidence, created_at, updated_at, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("m1", "sid", "user", "favorite_color", "blue", now - 1000, "user", 1.0, 1.0, now - 1000, now - 1000, "active"))
    conn.commit()
    conn.close()

    # encode via bridge
    obs, obs_r, st, rt, edges, mapping = bridge.encode_sqlite_to_v14_state(db, "sid", limit=100)

    # direct v1.4 call
    v14mod = importlib.import_module("btbc.frozen.v1_4")
    v14 = getattr(v14mod, "btbc_v14")
    router = joblib.load(ROUTER_PATH)
    with open(OPERATING_PATH, "r") as f:
        operating = json.load(f)
    v11 = importlib.import_module("btbc.frozen.v1_1")
    policy = v11.Policy()

    out_direct, actions_direct, conf, rm, ctr, routed, blocked, mean_score = v14(obs, obs_r, st, rt, edges, policy, router, operating)

    # adapter call
    res = adapter.derive_trusted_context_v1_4(db, "sid", limit=100)

    out_adapter = res["out_array"]
    actions_adapter = res["actions_array"]

    assert isinstance(out_adapter, np.ndarray)
    assert isinstance(actions_adapter, np.ndarray)

    assert np.array_equal(np.asarray(out_direct), out_adapter)
    assert np.array_equal(np.asarray(actions_direct), actions_adapter)

@pytest.mark.skipif(skip_condition, reason="Frozen v1.x sources or artifacts missing under btbc/frozen/")
def test_redundant_evidence_preserves_truth_and_applies_decision_correctly(tmp_path):
    """Scenario:
    - g1: trusted historical record favorite_color=green
    - g2: second supporting evidence (temporal or relational) for green
    - c1: low-trust injected corrupted record favorite_color=yellow
    - u1: unrelated record name=Alice

    Expectations:
    - The frozen decision for c1 is either REPAIR (if permitted) or a non-REPAIR abstention/quarantine action.
    - If decision == REPAIR, the adapter must update c1.value to the repaired value exactly (green).
    - If decision != REPAIR, the adapter must not silently rewrite the DB value for c1.
    - u1 must remain unchanged.
    """
    db = str(tmp_path / "redundant.db")
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE memories (
        memory_id TEXT PRIMARY KEY,
        session_id TEXT,
        entity TEXT,
        attribute TEXT,
        value TEXT,
        valid_from INTEGER,
        valid_to INTEGER,
        source TEXT,
        source_trust REAL,
        confidence REAL,
        created_at INTEGER,
        updated_at INTEGER,
        status TEXT,
        controller_decision TEXT,
        controller_reason TEXT
    )
    """)
    # relationships table for explicit relational support
    cur.execute("""
    CREATE TABLE relationships (
        rel_id TEXT PRIMARY KEY,
        from_memory_id TEXT,
        to_memory_id TEXT,
        relation_type TEXT,
        provenance TEXT,
        trust REAL,
        created_at INTEGER
    )
    """)
    conn.commit()

    now = int(datetime.utcnow().timestamp())
    # trusted historical record g1
    g1 = ("g1", "rep2", "user", "favorite_color", "green", now - 2000, None, "user_input", 1.0, 1.0, now - 2000, now - 2000, "active", None, None)
    # second supporting evidence g2 (could be another source with high trust)
    g2 = ("g2", "rep2", "user", "favorite_color", "green", now - 1500, None, "observed", 0.9, 1.0, now - 1500, now - 1500, "active", None, None)
    # corrupted injected low-trust c1
    c1 = ("c1", "rep2", "user", "favorite_color", "yellow", now - 1000, None, "malicious", 0.1, 1.0, now - 1000, now - 1000, "active", None, None)
    # unrelated
    u1 = ("u1", "rep2", "user", "name", "Alice", now - 2000, None, "user_input", 1.0, 1.0, now - 2000, now - 2000, "active", None, None)

    for row in (g1, g2, c1, u1):
        cur.execute("INSERT INTO memories (memory_id, session_id, entity, attribute, value, valid_from, valid_to, source, source_trust, confidence, created_at, updated_at, status, controller_decision, controller_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
    conn.commit()
    # add explicit relationship linking g1 <-> g2 to strengthen relational evidence
    rel_id = "r1"
    cur.execute("INSERT INTO relationships (rel_id, from_memory_id, to_memory_id, relation_type, provenance, trust, created_at) VALUES (?,?,?,?,?,?,?)", (rel_id, "g1", "g2", "support", "synth", 0.9, now - 1500))
    conn.commit()
    conn.close()

    # Sanity: ensure bridge can encode
    obs, obs_r, st, rt, edges, mapping = bridge.encode_sqlite_to_v14_state(db, "rep2", limit=100)
    assert mapping is not None

    # run adapter
    res = adapter.derive_trusted_context_v1_4(db, "rep2", limit=100)

    # find decision for c1
    decisions = res.get("decisions", [])
    c1_dec = next((d for d in decisions if d.get("memory_id") == "c1"), None)
    assert c1_dec is not None, "No decision produced for corrupted memory c1"

    decision = c1_dec.get("decision")

    # Decision correctness: must be one of accepted decisions
    assert decision in {"REPAIR", "QUARANTINE", "ESCALATE", "RISK_BUDGET_KEEP", "KEEP"}

    # DB application correctness
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT value, controller_decision FROM memories WHERE memory_id = ?", ("c1",))
    c1_row = cur.fetchone()
    cur.execute("SELECT value, controller_decision FROM memories WHERE memory_id = ?", ("u1",))
    u1_row = cur.fetchone()
    cur.execute("SELECT value, controller_decision FROM memories WHERE memory_id = ?", ("g1",))
    g1_row = cur.fetchone()
    conn.close()

    # unrelated unchanged
    assert u1_row[0] == "Alice"

    if decision == "REPAIR":
        # adapter must have updated c1 to ground truth (green)
        assert c1_row[0] == "green"
    else:
        # adapter should not silently have rewritten the corrupted row
        assert c1_row[0] == "yellow"

    # ground truth evidence must still be present and unchanged
    assert g1_row[0] == "green"

