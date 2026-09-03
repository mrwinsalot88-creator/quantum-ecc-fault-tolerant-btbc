from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "test_nonoracle_bridge_v2.py"
spec = importlib.util.spec_from_file_location("test_nonoracle_bridge_v2_script", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def _mapping():
    return {
        "fields": [["user", "favorite_color"]],
        "code_width": 4,
        "active_memory_ids": [["m1"], ["m2"], ["m3"]],
        "memory_rows": {
            "m1": {"memory_id":"m1","entity":"user","attribute":"favorite_color","value":"green","valid_from":100,"source":"a","source_trust":0.95,"confidence":0.95},
            "m2": {"memory_id":"m2","entity":"user","attribute":"favorite_color","value":"green","valid_from":200,"source":"b","source_trust":0.92,"confidence":0.96},
            "m3": {"memory_id":"m3","entity":"user","attribute":"favorite_color","value":"yellow","valid_from":300,"source":"c","source_trust":0.10,"confidence":0.20},
        },
        "codebooks": {
            '["user","favorite_color"]': {
                "green": [1, 1, -1, 1],
                "yellow": [-1, 1, 1, -1],
            }
        },
    }


def test_history_consensus_does_not_need_ground_truth():
    anchors = mod.derive_history_consensus(_mapping())
    assert 0 in anchors
    assert anchors[0]["consensus_value"] == "green"
    assert anchors[0]["current_value"] == "yellow"
    assert anchors[0]["supporter_count"] == 2


def test_high_trust_current_value_is_not_overridden():
    m = _mapping()
    m["memory_rows"]["m3"]["source_trust"] = 0.95
    m["memory_rows"]["m3"]["confidence"] = 0.95
    assert mod.derive_history_consensus(m) == {}


def test_weak_or_split_history_does_not_create_anchor():
    m = _mapping()
    m["memory_rows"]["m2"]["value"] = "yellow"
    assert mod.derive_history_consensus(m) == {}


def test_augmentation_adds_constant_anchor_nodes_and_equality_edges():
    import numpy as np

    m = _mapping()
    anchors = mod.derive_history_consensus(m)
    obs = np.asarray([[1,1,-1,1],[1,1,-1,1],[-1,1,1,-1]], dtype=np.int8)
    st = np.ones_like(obs, dtype=float) * 0.9
    obs_r = np.zeros((3,0), dtype=np.int8)
    rt = np.zeros((3,0), dtype=float)
    obs2, obs_r2, st2, rt2, edges2, meta = mod.augment_with_history_anchors(obs, obs_r, st, rt, [], m, anchors)
    assert obs2.shape == (3, 8)
    assert obs_r2.shape == (3, 4)
    assert st2.shape == (3, 8)
    assert rt2.shape == (3, 4)
    assert len(edges2) == 4
    assert meta["anchor_count"] == 1
    assert np.all(obs_r2 == 1)
    assert np.all(obs2[:, 4:] == np.asarray([1,1,-1,1], dtype=np.int8))
