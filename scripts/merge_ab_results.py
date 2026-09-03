"""Merge BTBC A/B result JSON files without silently mixing incompatible runs.

The merger preserves each run's metadata and flattens scenario rows into one
analysis-friendly JSON/CSV bundle. By default it refuses to merge runs whose
scientific provenance differs (router, operating point, frozen sources,
scenario file, or model hash). Use --allow-mixed-provenance only for deliberate
cross-provenance inspection; such output is labeled non-poolable.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


PROVENANCE_KEYS = (
    "scenario_sha256",
    "model_sha256",
)
FILE_HASH_KEYS = (
    "btbc/frozen/BTBC_v1_1_adversarial_memory_integrity.py",
    "btbc/frozen/BTBC_v1_2_adaptive_router.py",
    "btbc/frozen/BTBC_v1_3_risk_calibrated_router.py",
    "btbc/frozen/BTBC_v1_4_risk_budget_router.py",
    "btbc/frozen/router.joblib",
    "btbc/frozen/operating.json",
    "btbc/frozen_v1_4_adapter.py",
    "btbc/llm_state_bridge.py",
)


def load_result(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("metadata"), dict):
        raise ValueError(f"{path}: missing metadata object")
    if not isinstance(obj.get("results"), list):
        raise ValueError(f"{path}: missing results list")
    return obj


def provenance_signature(obj: Mapping[str, Any]) -> Dict[str, Any]:
    md = obj.get("metadata") or {}
    hashes = md.get("file_hashes") or {}
    return {
        **{k: md.get(k) for k in PROVENANCE_KEYS},
        "scientific_label": md.get("scientific_label"),
        "file_hashes": {k: hashes.get(k) for k in FILE_HASH_KEYS},
    }


def condition_label(obj: Mapping[str, Any]) -> str:
    ab = obj.get("ablations") or {}
    active = sorted(k for k, v in ab.items() if bool(v))
    return "+".join(active) if active else "baseline"


def flatten_run(path: Path, obj: Mapping[str, Any], run_index: int) -> List[Dict[str, Any]]:
    md = obj.get("metadata") or {}
    seed = md.get("seed")
    condition = condition_label(obj)
    rows: List[Dict[str, Any]] = []
    for r in obj.get("results") or []:
        btbc = r.get("btbc") or {}
        metrics = btbc.get("metrics") or {}
        plain = r.get("plain") or {}
        llm = r.get("llm") or {}
        plain_score = llm.get("plain_score") or {}
        btbc_score = llm.get("btbc_score") or {}
        rows.append({
            "run_index": run_index,
            "source_file": str(path),
            "seed": seed,
            "condition": condition,
            "scenario_id": r.get("scenario_id"),
            "plain_final_memory_error": plain.get("final_memory_error"),
            "btbc_final_memory_error": metrics.get("final_memory_error"),
            "memory_error_delta": (
                None if plain.get("final_memory_error") is None or metrics.get("final_memory_error") is None
                else metrics.get("final_memory_error") - plain.get("final_memory_error")
            ),
            "true_repairs": metrics.get("true_repairs"),
            "false_corrections": metrics.get("false_corrections"),
            "recovered_corruptions": metrics.get("recovered_corruptions"),
            "recovered_corruption_fraction": metrics.get("recovered_corruption_fraction"),
            "legitimate_change_damage": metrics.get("legitimate_change_damage"),
            "quarantines": metrics.get("quarantines"),
            "escalations": metrics.get("escalations"),
            "repair_decisions": metrics.get("repair_decisions"),
            "plain_answer_exact": plain_score.get("exact_match"),
            "btbc_answer_exact": btbc_score.get("exact_match"),
            "repo_commit_sha": md.get("repo_commit_sha"),
            "scenario_sha256": md.get("scenario_sha256"),
            "model_sha256": md.get("model_sha256"),
        })
    return rows


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def expand_inputs(patterns: Sequence[str]) -> List[Path]:
    found: List[Path] = []
    for pattern in patterns:
        matches = [Path(p) for p in glob.glob(pattern)]
        if matches:
            found.extend(matches)
        else:
            p = Path(pattern)
            if p.exists():
                found.append(p)
    unique = sorted({p.resolve() for p in found})
    if not unique:
        raise SystemExit("No input JSON files matched")
    return unique


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inputs", nargs="+", help="Result JSON files or glob patterns")
    p.add_argument("--out", default="results/merged_ab_results.json")
    p.add_argument("--allow-mixed-provenance", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    paths = expand_inputs(args.inputs)
    loaded = [(p, load_result(p)) for p in paths]
    signatures = [provenance_signature(obj) for _, obj in loaded]
    reference = signatures[0]
    mismatches: List[Dict[str, Any]] = []
    for (path, _), sig in zip(loaded[1:], signatures[1:]):
        if sig != reference:
            mismatches.append({"file": str(path), "signature": sig})
    if mismatches and not args.allow_mixed_provenance:
        raise SystemExit(
            "Refusing to pool incompatible provenance. Re-run with "
            "--allow-mixed-provenance only for deliberate inspection.\n" +
            json.dumps(mismatches, indent=2, sort_keys=True)
        )

    rows: List[Dict[str, Any]] = []
    runs: List[Dict[str, Any]] = []
    for idx, (path, obj) in enumerate(loaded):
        md = dict(obj.get("metadata") or {})
        runs.append({
            "run_index": idx,
            "source_file": str(path),
            "condition": condition_label(obj),
            "metadata": md,
            "ablations": obj.get("ablations") or {},
        })
        rows.extend(flatten_run(path, obj, idx))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "poolable": not bool(mismatches),
        "mixed_provenance_allowed": bool(args.allow_mixed_provenance),
        "provenance_reference": reference,
        "provenance_mismatches": mismatches,
        "run_count": len(runs),
        "row_count": len(rows),
        "runs": runs,
        "rows": rows,
    }
    out.write_text(json.dumps(bundle, indent=2, sort_keys=True, default=str), encoding="utf-8")
    csv_path = out.with_suffix(".csv")
    write_csv(csv_path, rows)
    print(f"Merged {len(runs)} runs / {len(rows)} scenario rows")
    print(f"poolable={bundle['poolable']}")
    print(f"Wrote {out}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
