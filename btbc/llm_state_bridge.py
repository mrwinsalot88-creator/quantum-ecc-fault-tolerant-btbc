"""BTBC local-agent LLM <-> frozen v1.4 state bridge.

This module is NEW adapter code. It does not modify or reimplement the frozen
BTBC v1.1-v1.4 decoder/router. Its only job is to translate persistent LLM
memory records into the numeric arrays consumed by the frozen implementation
and decode repaired arrays back into memory records.

Frozen v1.x expects:
    obs   : int8 state matrix, shape (T, N), values in {-1, 0, +1}
    obs_r : int8 relation matrix, shape (T, E), values in {-1, 0, +1}
    st    : float state-trust matrix, shape (T, N)
    rt    : float relation-trust matrix, shape (T, E)
    edges : sequence of integer (i, j) node pairs

Arbitrary LLM memory values are categorical strings, so they cannot be placed
into a single ternary cell reversibly. This bridge therefore represents each
(entity, attribute) field as a fixed-width deterministic codeword over {-1,+1};
0 is reserved for an unknown / absent value. The text value itself remains in
SQLite and in the mapping. Decoding selects the nearest known codeword for that
field (Hamming distance), with deterministic lexical tie-breaking.

This representation is an experimental interface layer. Any measured result
must be described as "frozen BTBC v1.4 operating through llm_state_bridge", not
as evidence that this categorical encoding is part of the original v1.4 model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import hashlib
import json
import sqlite3

import numpy as np

UNKNOWN = np.int8(0)
NEG = np.int8(-1)
POS = np.int8(1)
DEFAULT_CODE_WIDTH = 12


@dataclass(frozen=True)
class MemoryRow:
    memory_id: str
    session_id: str
    entity: str
    attribute: str
    value: str
    valid_from: int
    valid_to: Optional[int]
    source: Optional[str]
    source_trust: float
    confidence: float
    created_at: int
    updated_at: int
    status: str

    @property
    def field(self) -> Tuple[str, str]:
        return (self.entity, self.attribute)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _load_memories(db_path: str, session_id: str, limit: int) -> List[MemoryRow]:
    conn = sqlite3.connect(db_path)
    try:
        if not _has_table(conn, "memories"):
            raise RuntimeError("SQLite database has no 'memories' table")
        cols = _table_columns(conn, "memories")
        required = {"memory_id", "session_id", "entity", "attribute", "value"}
        missing = required - cols
        if missing:
            raise RuntimeError(f"memories table missing required columns: {sorted(missing)}")

        def c(name: str, default_sql: str) -> str:
            return name if name in cols else f"{default_sql} AS {name}"

        sql = f"""
        SELECT memory_id, session_id, entity, attribute, value,
               {c('valid_from','0')}, {c('valid_to','NULL')},
               {c('source','NULL')}, {c('source_trust','0.5')},
               {c('confidence','1.0')}, {c('created_at','0')},
               {c('updated_at','0')}, {c('status',"'active'")}
        FROM memories
        WHERE session_id = ?
        ORDER BY COALESCE(valid_from, created_at, 0), created_at, memory_id
        LIMIT ?
        """
        rows = conn.execute(sql, (session_id, int(limit))).fetchall()
    finally:
        conn.close()

    out: List[MemoryRow] = []
    for r in rows:
        vf = int(r[5] if r[5] is not None else (r[10] or 0))
        out.append(
            MemoryRow(
                memory_id=str(r[0]), session_id=str(r[1]), entity=str(r[2]),
                attribute=str(r[3]), value=str(r[4]), valid_from=vf,
                valid_to=None if r[6] is None else int(r[6]), source=r[7],
                source_trust=float(0.5 if r[8] is None else r[8]),
                confidence=float(1.0 if r[9] is None else r[9]),
                created_at=int(r[10] or 0), updated_at=int(r[11] or 0),
                status=str(r[12] or "active"),
            )
        )
    return out


def _stable_codeword(field: Tuple[str, str], value: str, width: int) -> np.ndarray:
    """Deterministically map a categorical value to {-1,+1}^width."""
    if width < 3:
        raise ValueError("code_width must be >= 3")
    seed = json.dumps([field[0], field[1], value], ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    bits: List[int] = []
    counter = 0
    material = digest
    while len(bits) < width:
        for byte in material:
            for shift in range(8):
                bits.append((byte >> shift) & 1)
                if len(bits) == width:
                    break
            if len(bits) == width:
                break
        counter += 1
        material = hashlib.sha256(digest + counter.to_bytes(4, "big")).digest()
    return np.asarray([POS if b else NEG for b in bits], dtype=np.int8)


def _active_row(rows: Sequence[MemoryRow], t: int) -> Optional[MemoryRow]:
    eligible = [r for r in rows if r.valid_from <= t and (r.valid_to is None or t < r.valid_to)]
    if not eligible:
        return None
    return max(eligible, key=lambda r: (r.valid_from, r.created_at, r.memory_id))


def _relation(a: int, b: int) -> np.int8:
    if a == 0 or b == 0:
        return UNKNOWN
    return POS if a == b else NEG


def _load_explicit_relationships(db_path: str, memory_to_field: Mapping[str, Tuple[str, str]]) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    try:
        if not _has_table(conn, "relationships"):
            return []
        cols = _table_columns(conn, "relationships")
        if not {"from_memory_id", "to_memory_id"}.issubset(cols):
            return []
        select = ["from_memory_id", "to_memory_id"]
        for optional in ("relation_type", "provenance", "trust", "created_at", "relation_value", "observed_relation"):
            select.append(optional if optional in cols else f"NULL AS {optional}")
        rows = conn.execute(f"SELECT {', '.join(select)} FROM relationships").fetchall()
    finally:
        conn.close()

    out = []
    for r in rows:
        a, b = str(r[0]), str(r[1])
        if a not in memory_to_field or b not in memory_to_field:
            continue
        out.append({
            "from_memory_id": a,
            "to_memory_id": b,
            "from_field": memory_to_field[a],
            "to_field": memory_to_field[b],
            "relation_type": r[2],
            "provenance": r[3],
            "trust": float(0.5 if r[4] is None else r[4]),
            "created_at": int(r[5] or 0),
            "relation_value": r[6] if r[6] is not None else r[7],
        })
    return out


def encode_sqlite_to_v14_state(
    db_path: str,
    session_id: str,
    limit: int = 500,
    *,
    code_width: int = DEFAULT_CODE_WIDTH,
    ablations: Optional[Mapping[str, bool]] = None,
    config_path: Optional[str] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[Tuple[int, int]], Dict[str, Any]]:
    """Encode one session into the exact numeric container types used by frozen v1.x.

    Returns (obs, obs_r, st, rt, edges, mapping).
    """
    del config_path  # reserved for future bridge-only configuration
    ab = dict(ablations or {})
    rows = _load_memories(db_path, session_id, limit)
    if not rows:
        raise RuntimeError(f"No memories found for session_id={session_id!r}")

    fields = sorted({r.field for r in rows})
    field_index = {f: idx for idx, f in enumerate(fields)}
    field_rows: Dict[Tuple[str, str], List[MemoryRow]] = {f: [] for f in fields}
    memory_to_field: Dict[str, Tuple[str, str]] = {}
    for r in rows:
        field_rows[r.field].append(r)
        memory_to_field[r.memory_id] = r.field
    for f in fields:
        field_rows[f].sort(key=lambda r: (r.valid_from, r.created_at, r.memory_id))

    # Every event boundary becomes a temporal observation. Include valid_to boundaries
    # so legitimate changes/expiration are represented explicitly.
    times = sorted({r.valid_from for r in rows} | {r.valid_to for r in rows if r.valid_to is not None})
    if not times:
        times = [0]

    T = len(times)
    N = len(fields) * int(code_width)
    obs = np.zeros((T, N), dtype=np.int8)
    st = np.full((T, N), 0.5, dtype=float)

    codebooks: Dict[str, Dict[str, List[int]]] = {}
    field_slices: Dict[str, Tuple[int, int]] = {}
    active_memory_ids: List[List[Optional[str]]] = [[None] * len(fields) for _ in range(T)]

    for f_idx, field in enumerate(fields):
        start = f_idx * code_width
        stop = start + code_width
        fkey = json.dumps(list(field), separators=(",", ":"))
        field_slices[fkey] = (start, stop)
        values = sorted({r.value for r in field_rows[field]})
        codebooks[fkey] = {v: _stable_codeword(field, v, code_width).astype(int).tolist() for v in values}

        for t_idx, timestamp in enumerate(times):
            r = _active_row(field_rows[field], int(timestamp))
            if r is None:
                continue
            active_memory_ids[t_idx][f_idx] = r.memory_id
            obs[t_idx, start:stop] = np.asarray(codebooks[fkey][r.value], dtype=np.int8)
            trust = 0.5 if ab.get("no_provenance") else float(np.clip(r.source_trust * r.confidence, 0.05, 0.995))
            st[t_idx, start:stop] = trust

    edges_set: set[Tuple[int, int]] = set()
    edge_meta: Dict[Tuple[int, int], Dict[str, Any]] = {}

    # Internal codeword edges make each field a local relational structure.
    if not ab.get("no_relations"):
        for f_idx in range(len(fields)):
            start = f_idx * code_width
            for j in range(code_width):
                a = start + j
                b = start + ((j + 1) % code_width)
                e = tuple(sorted((a, b)))
                edges_set.add(e)
                edge_meta.setdefault(e, {"kind": "internal", "trust": None, "relation_value": None})

        # Explicit DB relationships connect corresponding codeword positions.
        for rel in _load_explicit_relationships(db_path, memory_to_field):
            fa, fb = rel["from_field"], rel["to_field"]
            if fa == fb or fa not in field_index or fb not in field_index:
                continue
            a0 = field_index[fa] * code_width
            b0 = field_index[fb] * code_width
            for j in range(code_width):
                e = tuple(sorted((a0 + j, b0 + j)))
                edges_set.add(e)
                edge_meta[e] = {
                    "kind": "explicit",
                    "trust": float(np.clip(rel["trust"], 0.05, 0.995)),
                    "relation_value": rel.get("relation_value"),
                    "relation_type": rel.get("relation_type"),
                }

    edges = sorted(edges_set)
    E = len(edges)
    obs_r = np.zeros((T, E), dtype=np.int8)
    rt = np.full((T, E), 0.5, dtype=float)

    for t in range(T):
        for k, (i, j) in enumerate(edges):
            meta = edge_meta[(i, j)]
            override = meta.get("relation_value")
            if override is not None:
                try:
                    rv = int(override)
                    obs_r[t, k] = np.int8(max(-1, min(1, rv)))
                except (TypeError, ValueError):
                    obs_r[t, k] = _relation(int(obs[t, i]), int(obs[t, j]))
            else:
                obs_r[t, k] = _relation(int(obs[t, i]), int(obs[t, j]))
            if ab.get("no_provenance"):
                rt[t, k] = 0.5
            elif meta.get("trust") is not None:
                rt[t, k] = meta["trust"]
            else:
                rt[t, k] = float(np.clip((st[t, i] + st[t, j]) / 2.0, 0.05, 0.995))

    if ab.get("no_temporal") and T > 1:
        # Neutralize temporal history while preserving API shape: repeat latest state.
        obs[:] = obs[-1]
        st[:] = st[-1]
        obs_r[:] = obs_r[-1]
        rt[:] = rt[-1]

    mapping: Dict[str, Any] = {
        "version": 1,
        "session_id": session_id,
        "code_width": int(code_width),
        "time_axis": [int(t) for t in times],
        "fields": [list(f) for f in fields],
        "field_slices": {k: list(v) for k, v in field_slices.items()},
        "codebooks": codebooks,
        "active_memory_ids": active_memory_ids,
        "memory_rows": {r.memory_id: {
            "memory_id": r.memory_id, "session_id": r.session_id, "entity": r.entity,
            "attribute": r.attribute, "value": r.value, "valid_from": r.valid_from,
            "valid_to": r.valid_to, "source": r.source, "source_trust": r.source_trust,
            "confidence": r.confidence, "created_at": r.created_at,
            "updated_at": r.updated_at, "status": r.status,
        } for r in rows},
        "edges": [list(e) for e in edges],
        "bridge_note": "categorical text encoded as deterministic {-1,+1} codewords; 0 reserved for unknown",
    }
    return obs, obs_r, st, rt, edges, mapping


def _field_key(field: Sequence[str]) -> str:
    return json.dumps([str(field[0]), str(field[1])], separators=(",", ":"))


def _nearest_value(vector: np.ndarray, codebook: Mapping[str, Sequence[int]]) -> Tuple[Optional[str], int]:
    if np.all(vector == 0):
        return None, int(vector.size)
    candidates: List[Tuple[int, str]] = []
    for value, code in codebook.items():
        c = np.asarray(code, dtype=np.int8)
        # Unknown output cells do not vote against a codeword.
        mask = vector != 0
        distance = int(np.sum(c[mask] != vector[mask])) if np.any(mask) else int(vector.size)
        candidates.append((distance, str(value)))
    if not candidates:
        return None, int(vector.size)
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][1], candidates[0][0]


def decode_v14_out_to_records(out_array: np.ndarray, mapping: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Decode a frozen output matrix into deterministic temporal field records."""
    out = np.asarray(out_array, dtype=np.int8)
    fields = [tuple(f) for f in mapping["fields"]]
    width = int(mapping["code_width"])
    time_axis = list(mapping["time_axis"])
    active_ids = mapping["active_memory_ids"]
    codebooks = mapping["codebooks"]
    if out.shape != (len(time_axis), len(fields) * width):
        raise RuntimeError(f"Unexpected output shape {out.shape}; expected {(len(time_axis), len(fields) * width)}")

    decoded: List[Dict[str, Any]] = []
    for t_idx, timestamp in enumerate(time_axis):
        for f_idx, field in enumerate(fields):
            start = f_idx * width
            vec = out[t_idx, start:start + width]
            fkey = _field_key(field)
            value, distance = _nearest_value(vec, codebooks[fkey])
            memory_id = active_ids[t_idx][f_idx]
            if memory_id is None and value is None:
                continue
            base = dict(mapping.get("memory_rows", {}).get(memory_id, {})) if memory_id else {}
            base.update({
                "memory_id": memory_id,
                "session_id": mapping["session_id"],
                "entity": field[0],
                "attribute": field[1],
                "value": value,
                "time_index": t_idx,
                "timestamp": int(timestamp),
                "decode_distance": int(distance),
                "state_vector": vec.astype(int).tolist(),
            })
            decoded.append(base)
    return decoded


def decode_v14_actions(final_actions: np.ndarray, out_array: np.ndarray, mapping: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Aggregate per-cell frozen actions into per-memory/per-time decisions."""
    actions = np.asarray(final_actions, dtype=object)
    out = np.asarray(out_array, dtype=np.int8)
    if actions.shape != out.shape:
        raise RuntimeError(f"actions shape {actions.shape} does not match output shape {out.shape}")
    fields = [tuple(f) for f in mapping["fields"]]
    width = int(mapping["code_width"])
    time_axis = mapping["time_axis"]
    active_ids = mapping["active_memory_ids"]
    decoded_lookup = {(r["time_index"], r["entity"], r["attribute"]): r for r in decode_v14_out_to_records(out, mapping)}

    result: List[Dict[str, Any]] = []
    for t_idx, timestamp in enumerate(time_axis):
        for f_idx, field in enumerate(fields):
            memory_id = active_ids[t_idx][f_idx]
            if memory_id is None:
                continue
            start = f_idx * width
            cell_actions = [str(x) for x in actions[t_idx, start:start + width].tolist()]
            non_keep = [a for a in cell_actions if a != "KEEP"]
            if any(a.startswith("REPAIR") for a in non_keep):
                decision = "REPAIR"
            elif any(a == "QUARANTINE" for a in non_keep):
                decision = "QUARANTINE"
            elif any(a == "ESCALATE" for a in non_keep):
                decision = "ESCALATE"
            elif any(a == "RISK_BUDGET_KEEP" for a in non_keep):
                decision = "RISK_BUDGET_KEEP"
            else:
                decision = "KEEP"
            decoded = decoded_lookup.get((t_idx, field[0], field[1]), {})
            result.append({
                "memory_id": memory_id,
                "time_index": t_idx,
                "timestamp": int(timestamp),
                "entity": field[0],
                "attribute": field[1],
                "decision": decision,
                "cell_actions": cell_actions,
                "decoded_value": decoded.get("value"),
                "decode_distance": decoded.get("decode_distance"),
            })
    return result


def bridge_round_trip_ok(db_path: str, session_id: str, limit: int = 500, code_width: int = DEFAULT_CODE_WIDTH) -> bool:
    """Smoke-check that encoding followed by decoding reproduces active values."""
    obs, _obs_r, _st, _rt, _edges, mapping = encode_sqlite_to_v14_state(
        db_path, session_id, limit=limit, code_width=code_width
    )
    decoded = decode_v14_out_to_records(obs, mapping)
    by_id: Dict[str, str] = {}
    for row in decoded:
        mid = row.get("memory_id")
        if mid is not None:
            by_id[str(mid)] = str(row.get("value"))
    for mid, original in mapping["memory_rows"].items():
        # A record that is never active (for example immediately superseded at the same
        # timestamp) is intentionally absent from the state grid and is not asserted.
        if mid in by_id and by_id[mid] != str(original["value"]):
            return False
    return True
