from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
P = REPO_ROOT / "scripts" / "probe_corroboration.py"
spec = importlib.util.spec_from_file_location("probe_corroboration", P)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_augment_relations_supports_candidate_only_at_target_time():
    obs = np.array([[1, 1, -1, 1], [-1, 1, -1, 1]], dtype=np.int8)
    obs_r = np.zeros((2, 0), dtype=np.int8)
    rt = np.zeros((2, 0), dtype=float)
    mapping = {"code_width": 2}
    new_r, new_rt, edges, meta = mod._augment_relations(
        obs, obs_r, rt, [], mapping, [(1, 0, 1)], anchors_per_target=1
    )
    assert meta["added_edges"] == 1
    assert len(edges) == 1
    i, j = edges[0]
    assert new_r[0, 0] == mod._rel(int(obs[0, i]), int(obs[0, j]))
    assert new_r[1, 0] == mod._rel(1, int(obs[1, j]))
    assert new_rt[1, 0] == 0.995


def test_summary_is_additive():
    row = {
        "baseline_escalations": 3,
        "baseline_recovery_candidate_cells": 0,
        "synthetic_edges_added": 6,
        "repair2_conversions": 2,
        "correct_final_truth_bit_conversions": 1,
    }
    s = mod.summarize([row, row])
    assert s["worlds"] == 2
    assert s["worlds_with_escalations"] == 2
    assert s["baseline_escalations"] == 6
    assert s["repair2_conversions"] == 4
    assert s["correct_final_truth_bit_conversions"] == 2
