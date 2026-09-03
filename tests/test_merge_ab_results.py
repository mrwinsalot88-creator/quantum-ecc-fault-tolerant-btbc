from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import merge_ab_results as merge


def _bundle(seed=0, *, model_hash=None, scenario_hash="scenario", router_hash="router", condition=None):
    return {
        "metadata": {
            "seed": seed,
            "repo_commit_sha": "commit",
            "scenario_sha256": scenario_hash,
            "model_sha256": model_hash,
            "scientific_label": "frozen BTBC v1.4 operating through llm_state_bridge",
            "file_hashes": {
                "btbc/frozen/BTBC_v1_1_adversarial_memory_integrity.py": "v11",
                "btbc/frozen/BTBC_v1_2_adaptive_router.py": "v12",
                "btbc/frozen/BTBC_v1_3_risk_calibrated_router.py": "v13",
                "btbc/frozen/BTBC_v1_4_risk_budget_router.py": "v14",
                "btbc/frozen/router.joblib": router_hash,
                "btbc/frozen/operating.json": "operating",
                "btbc/frozen_v1_4_adapter.py": "adapter",
                "btbc/llm_state_bridge.py": "bridge",
            },
        },
        "ablations": condition or {"no_relations": False, "no_temporal": False, "no_provenance": False},
        "results": [
            {
                "scenario_id": "s1",
                "plain": {"final_memory_error": 1},
                "btbc": {
                    "metrics": {
                        "final_memory_error": 0,
                        "true_repairs": 1,
                        "false_corrections": 0,
                        "recovered_corruptions": 1,
                        "recovered_corruption_fraction": 1.0,
                        "legitimate_change_damage": 0,
                        "quarantines": 0,
                        "escalations": 0,
                        "repair_decisions": 1,
                    }
                },
            }
        ],
    }


def test_merge_same_provenance(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_bundle(seed=0)), encoding="utf-8")
    b.write_text(json.dumps(_bundle(seed=1)), encoding="utf-8")
    out = tmp_path / "merged.json"

    assert merge.main([str(a), str(b), "--out", str(out)]) == 0
    obj = json.loads(out.read_text(encoding="utf-8"))
    assert obj["poolable"] is True
    assert obj["run_count"] == 2
    assert obj["row_count"] == 2
    assert {r["seed"] for r in obj["rows"]} == {0, 1}
    assert all(r["memory_error_delta"] == -1 for r in obj["rows"])
    assert out.with_suffix(".csv").exists()


def test_rejects_mixed_provenance(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_bundle(router_hash="router-a")), encoding="utf-8")
    b.write_text(json.dumps(_bundle(router_hash="router-b")), encoding="utf-8")

    with pytest.raises(SystemExit, match="Refusing to pool incompatible provenance"):
        merge.main([str(a), str(b), "--out", str(tmp_path / "x.json")])


def test_can_label_deliberate_mixed_provenance(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_bundle(scenario_hash="a")), encoding="utf-8")
    b.write_text(json.dumps(_bundle(scenario_hash="b")), encoding="utf-8")
    out = tmp_path / "mixed.json"

    assert merge.main([
        str(a), str(b), "--out", str(out), "--allow-mixed-provenance"
    ]) == 0
    obj = json.loads(out.read_text(encoding="utf-8"))
    assert obj["poolable"] is False
    assert obj["mixed_provenance_allowed"] is True
    assert len(obj["provenance_mismatches"]) == 1
