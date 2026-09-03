from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "generate_worlds.py"
spec = importlib.util.spec_from_file_location("generate_worlds", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def test_generate_world_is_deterministic():
    cfg = mod.GeneratorConfig(num_worlds=3, min_fields=5, max_fields=8, master_seed=369)
    a = mod.generate_world(1, cfg)
    b = mod.generate_world(1, cfg)
    assert canonical(a) == canonical(b)


def test_different_world_seeds_change_world():
    cfg = mod.GeneratorConfig(num_worlds=3, min_fields=5, max_fields=8, master_seed=369)
    a = mod.generate_world(0, cfg)
    b = mod.generate_world(1, cfg)
    assert a["world_seed"] != b["world_seed"]
    assert canonical(a) != canonical(b)


def test_ground_truth_and_corruption_labels_match_seeded_active_state():
    cfg = mod.GeneratorConfig(
        num_worlds=5,
        min_fields=6,
        max_fields=8,
        temporal_depth=5,
        corruption_rate=0.25,
        legitimate_change_rate=0.20,
        master_seed=123,
    )
    for i in range(5):
        world = mod.generate_world(i, cfg)
        active = mod._active_fields(world["memories"])
        truth = world["ground_truth_fields"]
        actual_corrupt = sorted(k for k, v in truth.items() if active.get(k) != v)
        assert world["corrupted_fields"] == actual_corrupt
        assert set(world["legitimate_fields"]).isdisjoint(world["corrupted_fields"])
        assert set(truth) == set(active)


def test_write_suite_emits_manifest_and_one_scenario_per_file(tmp_path):
    cfg = mod.GeneratorConfig(num_worlds=4, min_fields=5, max_fields=5, master_seed=77)
    manifest = mod.write_suite(tmp_path, cfg)
    assert manifest["world_count"] == 4
    assert len(manifest["files"]) == 4
    for i in range(4):
        obj = json.loads((tmp_path / f"world_{i:04d}.json").read_text())
        assert len(obj["scenarios"]) == 1
        assert obj["generator"]["suite_id"] == manifest["suite_id"]
    saved = json.loads((tmp_path / "manifest.json").read_text())
    assert saved["config_sha256"] == manifest["config_sha256"]


def test_generated_relationships_do_not_fake_scalar_relation_evidence():
    cfg = mod.GeneratorConfig(
        num_worlds=1,
        min_fields=8,
        max_fields=8,
        relationship_density=1.0,
        master_seed=11,
    )
    world = mod.generate_world(0, cfg)
    assert world["relationships"]
    assert all(r["relation_value"] is None for r in world["relationships"])
    assert all(r["observed_relation"] is None for r in world["relationships"])
