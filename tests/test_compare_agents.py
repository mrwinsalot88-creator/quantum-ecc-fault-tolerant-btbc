from __future__ import annotations

import json
from pathlib import Path

from btbc import memory_engine
from btbc.frozen_v1_4_adapter import derive_trusted_context_v1_4
from tests.compare_agents import field_metrics, load_scenarios, run_scenario


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "tests" / "scenarios.json"


def test_plain_and_btbc_seed_identically_and_plain_is_untouched(tmp_path):
    bundle = load_scenarios(SCENARIOS)
    scenario = bundle["scenarios"][0]
    sid = scenario["session_id"]
    plain = str(tmp_path / "plain.db")
    btbc = str(tmp_path / "btbc.db")
    memory_engine.seed_scenario(plain, scenario)
    memory_engine.seed_scenario(btbc, scenario)

    plain_before = memory_engine.snapshot_memories(plain, sid)
    btbc_before = memory_engine.snapshot_memories(btbc, sid)
    assert plain_before == btbc_before

    derive_trusted_context_v1_4(btbc, sid, limit=100)

    # The control arm must remain byte-for-byte equivalent at the row-value
    # level; all controller writes are confined to the BTBC arm.
    assert memory_engine.snapshot_memories(plain, sid) == plain_before


def test_metrics_count_repairs_and_damage_deterministically():
    scenario = {
        "ground_truth_fields": {"u.a": "right", "u.b": "new"},
        "corrupted_fields": ["u.a"],
        "legitimate_fields": ["u.b"],
    }
    pre = {"u.a": "wrong", "u.b": "new"}
    post = {"u.a": "right", "u.b": "old"}
    m = field_metrics(pre, post, scenario, [{"decision": "REPAIR"}, {"decision": "QUARANTINE"}])
    assert m["true_repairs"] == 1
    assert m["false_corrections"] == 1
    assert m["recovered_corruptions"] == 1
    assert m["recovered_corruption_fraction"] == 1.0
    assert m["legitimate_change_damage"] == 1
    assert m["final_memory_error"] == 1
    assert m["repair_decisions"] == 1
    assert m["quarantines"] == 1


def test_metrics_only_scenario_run_is_repeatable():
    bundle = load_scenarios(SCENARIOS)
    scenario = bundle["scenarios"][0]
    kwargs = {
        "system_prompt": bundle["system_prompt"],
        "ablations": {"no_relations": False, "no_temporal": False, "no_provenance": False},
        "llm": None,
    }
    a = run_scenario(scenario, **kwargs)
    b = run_scenario(scenario, **kwargs)

    assert a["plain"] == b["plain"]
    assert a["btbc"]["post_fields"] == b["btbc"]["post_fields"]
    assert a["btbc"]["metrics"] == b["btbc"]["metrics"]
    assert a["btbc"]["decisions"] == b["btbc"]["decisions"]
