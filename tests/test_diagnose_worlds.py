from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "diagnose_worlds.py"
spec = importlib.util.spec_from_file_location("diagnose_worlds", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def _scenario():
    return {
        "id": "diag_temporal",
        "session_id": "s_diag",
        "memories": [
            {"memory_id":"g1","session_id":"s_diag","entity":"user","attribute":"favorite_color","value":"green","valid_from":100,"source":"user","source_trust":0.99,"confidence":0.99,"created_at":100,"updated_at":100,"status":"active"},
            {"memory_id":"g2","session_id":"s_diag","entity":"user","attribute":"favorite_color","value":"green","valid_from":200,"source":"user","source_trust":0.99,"confidence":0.99,"created_at":200,"updated_at":200,"status":"active"},
            {"memory_id":"bad1","session_id":"s_diag","entity":"user","attribute":"favorite_color","value":"yellow","valid_from":300,"source":"fault","source_trust":0.10,"confidence":0.20,"created_at":300,"updated_at":300,"status":"active"},
        ],
        "relationships": [],
        "ground_truth_fields": {"user.favorite_color": "green"},
        "corrupted_fields": ["user.favorite_color"],
        "legitimate_fields": [],
    }


def test_debug_profiles_are_actually_more_permissive_than_threshold_one():
    assert mod.DEBUG_PROFILES["route_all_escalations"]["threshold"] < 0
    assert mod.DEBUG_PROFILES["route_all_escalations"]["harm_weight"] == 0.0


def test_diagnose_scenario_reports_pre_gate_and_all_profiles():
    row = mod.diagnose_scenario(_scenario(), include_cell_trace=False)
    assert row["scenario_id"] == "diag_temporal"
    assert "pre_gate" in row
    assert "recovery_candidate_cells" in row["pre_gate"]
    assert set(row["runs"]) == {"locked", *mod.DEBUG_PROFILES.keys()}
    assert row["runs"]["route_all_escalations"]["blocked"] == 0
    assert row["runs"]["route_all_escalations"]["routed"] == row["pre_gate"]["escalated_cells"]


def test_summary_counts_worlds_and_candidates():
    row = mod.diagnose_scenario(_scenario(), include_cell_trace=False)
    summary = mod.summarize([row, row])
    assert summary["worlds"] == 2
    assert summary["pre_gate_candidate_cells"] == 2 * row["pre_gate"]["recovery_candidate_cells"]
    assert summary["profiles"]["locked"]["routed"] == 2 * row["runs"]["locked"]["routed"]
