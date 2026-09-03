"""Run BTBC memory-only A/B experiments over generated scenario worlds.

The runner combines world_*.json files into one deterministic scenario bundle,
then runs the existing compare_agents.py harness once per requested condition.
Each world remains an independent paired row inside the result. The existing
strict merger is then used on each condition output, preserving the current
result schema without pretending repeated CLI seeds are independent samples.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPARE = REPO_ROOT / "tests" / "compare_agents.py"
MERGER = REPO_ROOT / "scripts" / "merge_ab_results.py"

CONDITIONS = {
    "baseline": [],
    "no_relations": ["--no-relations"],
    "no_temporal": ["--no-temporal"],
    "no_provenance": ["--no-provenance"],
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_worlds(scenarios_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    paths = sorted(scenarios_dir.glob("world_*.json"))
    if not paths:
        raise SystemExit(f"No world_*.json files found in {scenarios_dir}")
    scenarios: List[Dict[str, Any]] = []
    suite_ids = set()
    config_hashes = set()
    system_prompts = set()
    seen_ids = set()
    file_rows = []
    for p in paths:
        obj = json.loads(p.read_text(encoding="utf-8"))
        rows = obj.get("scenarios")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError(f"{p}: expected exactly one scenario")
        scenario = rows[0]
        sid = str(scenario.get("id"))
        if sid in seen_ids:
            raise ValueError(f"duplicate scenario id: {sid}")
        seen_ids.add(sid)
        scenarios.append(scenario)
        gen = obj.get("generator") or {}
        if gen.get("suite_id"):
            suite_ids.add(str(gen["suite_id"]))
        if gen.get("config_sha256"):
            config_hashes.add(str(gen["config_sha256"]))
        system_prompts.add(str(obj.get("system_prompt") or "Use the supplied memory."))
        file_rows.append({"path": p.name, "sha256": sha256_file(p), "scenario_id": sid})
    if len(suite_ids) > 1:
        raise ValueError(f"mixed suite ids in {scenarios_dir}: {sorted(suite_ids)}")
    if len(config_hashes) > 1:
        raise ValueError(f"mixed generator configs in {scenarios_dir}: {sorted(config_hashes)}")
    if len(system_prompts) > 1:
        raise ValueError("generated worlds contain different system prompts")
    meta = {
        "suite_id": next(iter(suite_ids), None),
        "config_sha256": next(iter(config_hashes), None),
        "world_count": len(scenarios),
        "files": file_rows,
        "system_prompt": next(iter(system_prompts)),
    }
    return scenarios, meta


def write_combined_bundle(scenarios_dir: Path, out_path: Path) -> Dict[str, Any]:
    scenarios, meta = load_worlds(scenarios_dir)
    bundle = {
        "schema_version": 2,
        "system_prompt": meta["system_prompt"],
        "generator": {
            "suite_id": meta["suite_id"],
            "config_sha256": meta["config_sha256"],
            "world_count": meta["world_count"],
        },
        "scenarios": scenarios,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    meta["combined_bundle"] = str(out_path)
    meta["combined_sha256"] = sha256_file(out_path)
    return meta


def run_cmd(cmd: Sequence[str], *, cwd: Path = REPO_ROOT) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(list(cmd), cwd=str(cwd), check=True)


def run_condition(
    condition: str,
    suite_path: Path,
    out_dir: Path,
    *,
    python: str,
    seed: int,
) -> Path:
    flags = CONDITIONS[condition]
    out = out_dir / f"{condition}.json"
    cmd = [
        python, str(COMPARE),
        "--only-metrics",
        "--scenarios", str(suite_path),
        "--seed", str(seed),
        "--out", str(out),
        *flags,
    ]
    run_cmd(cmd)
    merged = out_dir / f"{condition}_merged.json"
    run_cmd([python, str(MERGER), str(out), "--out", str(merged)])
    return merged


def summarize_merged(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    rows = list(obj.get("rows") or [])
    plain = sum(int(r.get("plain_final_memory_error") or 0) for r in rows)
    btbc = sum(int(r.get("btbc_final_memory_error") or 0) for r in rows)
    repairs = sum(int(r.get("true_repairs") or 0) for r in rows)
    false = sum(int(r.get("false_corrections") or 0) for r in rows)
    legit = sum(int(r.get("legitimate_change_damage") or 0) for r in rows)
    deltas = [
        int(r.get("plain_final_memory_error") or 0) - int(r.get("btbc_final_memory_error") or 0)
        for r in rows
    ]
    improved = sum(1 for d in deltas if d > 0)
    tied = sum(1 for d in deltas if d == 0)
    worsened = sum(1 for d in deltas if d < 0)
    return {
        "worlds": len(rows),
        "plain_final_errors": plain,
        "btbc_final_errors": btbc,
        "net_error_reduction": plain - btbc,
        "true_repairs": repairs,
        "false_corrections": false,
        "legitimate_change_damage": legit,
        "worlds_improved": improved,
        "worlds_tied": tied,
        "worlds_worsened": worsened,
        "poolable": bool(obj.get("poolable")),
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenarios-dir", default="results/generated_worlds")
    p.add_argument("--out-dir", default="results/generated_ab")
    p.add_argument(
        "--conditions",
        default="baseline,no_relations,no_temporal,no_provenance",
        help="comma-separated subset of: " + ",".join(CONDITIONS),
    )
    p.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    p.add_argument("--seed", type=int, default=0, help="recorded harness seed; worlds carry their own independent seeds")
    p.add_argument("--python", default=sys.executable)
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    selected = [x.strip() for x in args.conditions.split(",") if x.strip()]
    unknown = [x for x in selected if x not in CONDITIONS]
    if unknown:
        raise SystemExit(f"unknown conditions: {unknown}")
    if not selected:
        raise SystemExit("no conditions selected")
    scenarios_dir = Path(args.scenarios_dir)
    if not scenarios_dir.is_absolute():
        scenarios_dir = REPO_ROOT / scenarios_dir
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    suite_path = out_dir / "generated_suite.json"
    suite_meta = write_combined_bundle(scenarios_dir, suite_path)
    print(
        f"Prepared {suite_meta['world_count']} independent worlds; "
        f"suite_id={suite_meta['suite_id']} sha256={suite_meta['combined_sha256']}"
    )

    results: Dict[str, Path] = {}
    max_workers = max(1, min(int(args.workers), len(selected)))
    if max_workers == 1:
        for condition in selected:
            results[condition] = run_condition(
                condition, suite_path, out_dir, python=args.python, seed=args.seed
            )
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {
                ex.submit(
                    run_condition, condition, suite_path, out_dir,
                    python=args.python, seed=args.seed,
                ): condition
                for condition in selected
            }
            for fut in concurrent.futures.as_completed(futs):
                condition = futs[fut]
                results[condition] = fut.result()

    summary = {
        "suite": suite_meta,
        "conditions": {name: summarize_merged(results[name]) for name in selected},
        "note": (
            "Each generated world is the independent paired unit. The compare_agents --seed "
            "value is provenance only in memory-only mode and must not be counted as another sample."
        ),
    }
    summary_path = out_dir / "experiment_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nExperiment summary")
    for name in selected:
        print(name, json.dumps(summary["conditions"][name], sort_keys=True))
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
