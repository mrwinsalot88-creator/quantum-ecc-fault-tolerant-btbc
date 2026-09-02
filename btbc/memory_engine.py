"""Deterministic SQLite helpers for the BTBC local-agent A/B harness.

This module is harness-only code. It does not alter the frozen BTBC v1.x
implementation. The helpers intentionally operate on disposable experiment
DBs; callers should not point them at production or long-lived databases.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import os
import sqlite3


def init_db(path: str, *, reset: bool = False) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if reset and p.exists():
        p.unlink()
    conn = sqlite3.connect(str(p))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                entity TEXT NOT NULL,
                attribute TEXT NOT NULL,
                value TEXT NOT NULL,
                valid_from INTEGER,
                valid_to INTEGER,
                source TEXT,
                source_trust REAL,
                confidence REAL,
                created_at INTEGER,
                updated_at INTEGER,
                status TEXT DEFAULT 'active',
                controller_decision TEXT,
                controller_reason TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS relationships (
                from_memory_id TEXT NOT NULL,
                to_memory_id TEXT NOT NULL,
                relation_type TEXT,
                provenance TEXT,
                trust REAL,
                created_at INTEGER,
                relation_value INTEGER,
                observed_relation INTEGER
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def clear_db(path: str) -> None:
    init_db(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM relationships")
        conn.execute("DELETE FROM memories")
        conn.commit()
    finally:
        conn.close()


def insert_memory(path: str, row: Mapping[str, Any]) -> None:
    required = ("memory_id", "session_id", "entity", "attribute", "value")
    missing = [k for k in required if k not in row]
    if missing:
        raise ValueError(f"memory row missing required fields: {missing}")
    cols = [
        "memory_id", "session_id", "entity", "attribute", "value",
        "valid_from", "valid_to", "source", "source_trust", "confidence",
        "created_at", "updated_at", "status",
    ]
    defaults = {
        "valid_from": 0, "valid_to": None, "source": "scenario",
        "source_trust": 0.5, "confidence": 1.0, "created_at": 0,
        "updated_at": 0, "status": "active",
    }
    vals = [row.get(c, defaults.get(c)) for c in cols]
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            f"INSERT INTO memories ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            vals,
        )
        conn.commit()
    finally:
        conn.close()


def insert_relationship(path: str, row: Mapping[str, Any]) -> None:
    if "from_memory_id" not in row or "to_memory_id" not in row:
        raise ValueError("relationship requires from_memory_id and to_memory_id")
    cols = [
        "from_memory_id", "to_memory_id", "relation_type", "provenance",
        "trust", "created_at", "relation_value", "observed_relation",
    ]
    defaults = {
        "relation_type": None, "provenance": "scenario", "trust": 0.5,
        "created_at": 0, "relation_value": None, "observed_relation": None,
    }
    vals = [row.get(c, defaults.get(c)) for c in cols]
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            f"INSERT INTO relationships ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            vals,
        )
        conn.commit()
    finally:
        conn.close()


def seed_scenario(path: str, scenario: Mapping[str, Any]) -> None:
    """Reset and seed one disposable scenario database."""
    init_db(path, reset=True)
    for row in scenario.get("memories", []):
        insert_memory(path, row)
    for row in scenario.get("relationships", []):
        insert_relationship(path, row)


def snapshot_memories(path: str, session_id: str) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM memories WHERE session_id=? "
            "ORDER BY COALESCE(valid_from, created_at, 0), created_at, memory_id",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def active_memories(path: str, session_id: str) -> List[Dict[str, Any]]:
    """Return one deterministic active row per (entity, attribute).

    The latest eligible row wins using the same ordering idea as the bridge:
    valid_from, created_at, memory_id. Rows with an explicit valid_to are
    considered active only if no later event boundary has passed them.
    """
    rows = snapshot_memories(path, session_id)
    if not rows:
        return []
    boundaries = [int(r.get("valid_from") or r.get("created_at") or 0) for r in rows]
    t = max(boundaries) if boundaries else 0
    by_field: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in rows:
        vf = int(r.get("valid_from") or r.get("created_at") or 0)
        vt = r.get("valid_to")
        if vf <= t and (vt is None or t < int(vt)) and str(r.get("status") or "active") != "deleted":
            by_field.setdefault((str(r["entity"]), str(r["attribute"])), []).append(r)
    out: List[Dict[str, Any]] = []
    for field in sorted(by_field):
        candidates = by_field[field]
        out.append(max(candidates, key=lambda r: (
            int(r.get("valid_from") or 0), int(r.get("created_at") or 0), str(r["memory_id"])
        )))
    return out


def memory_context(path: str, session_id: str) -> str:
    return "\n".join(
        f"{r['entity']}.{r['attribute']} = {r['value']}" for r in active_memories(path, session_id)
    )


def active_field_values(path: str, session_id: str) -> Dict[str, str]:
    return {
        f"{r['entity']}.{r['attribute']}": str(r["value"])
        for r in active_memories(path, session_id)
    }
