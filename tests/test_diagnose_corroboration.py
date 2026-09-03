from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "diagnose_corroboration.py"
spec = importlib.util.spec_from_file_location("diagnose_corroboration", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_route_all_is_unambiguously_permissive():
    assert mod.ROUTE_ALL["harm_weight"] == 0.0
    assert mod.ROUTE_ALL["threshold"] == -1.0


def test_oracle_relation_injection_adds_independent_columns():
    obs = np.array([[1, -1, 1, 1, -1, -1], [1, -1, -1, 1, -1, -1]], dtype=np.int8)
    st = np.full(obs.shape, 0.8)
    edges = [(0, 1), (1, 2), (3, 4), (4, 5)]
    obs_r = np.zeros((2, len(edges)), dtype=np.int8)
    rt = np.full(obs_r.shape, 0.8)
    mapping = {
        "fields": [["user", "a"], ["user", "b"]],
        "code_width": 3,
        "codebooks": {
            '["user","a"]': {"green": [1, -1, 1], "yellow": [1, -1, -1]},
            '["user","b"]': {"blue": [1, -1, -1]},
        },
    }
    scenario = {
        "ground_truth_fields": {"user.a": "green", "user.b": "blue"},
        "corrupted_fields": ["user.a"],
    }
    aobs, aobs_r, ast, art, aedges, meta = mod.inject_oracle_corroboration(
        obs, obs_r, st, rt, edges, mapping, scenario, witness_fields=1
    )
    assert np.array_equal(aobs, obs)
    assert np.array_equal(ast, st)
    assert len(aedges) > len(edges)
    assert aobs_r.shape[1] == len(aedges)
    assert art.shape == aobs_r.shape
    assert meta["added_edges"] == len(aedges) - len(edges)
    assert np.all(art[:, len(edges):] == 0.99)
