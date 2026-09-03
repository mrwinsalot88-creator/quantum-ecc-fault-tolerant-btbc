"""Deterministic A/B harness: plain SQLite memory vs frozen BTBC v1.4.

The memory-level metrics are primary. The optional GGUF stage is secondary and
uses identical prompts/decoding settings for both arms; only the memory context
differs. The harness uses disposable temporary DBs and never clears a user DB.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from btbc import memory_engine
from btbc.frozen_v1_4_adapter import derive_trusted_context_v1_4


REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN_FILES = [
    "btbc/frozen/BTBC_v1_1_adversarial_memory_integrity.py",
    "btbc/frozen/BTBC_v1_2_adaptive_router.py",
    "btbc/frozen/BTBC_v1_3_risk_calibrated_router.py",
    "btbc/frozen/BTBC_v1_4_risk_budget_router.py",
    "btbc/frozen/router.joblib",
    "btbc/frozen/operating.json",
    "btbc/frozen_v1_4_adapter.py",
    "btbc/llm_state_bridge.py",
]


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def repo_sha() -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def package_versions() -> Dict[str, str]:
    names = ["numpy", "pandas", "scipy", "scikit-learn", "joblib", "pytest", "llama-cpp-python"]
    out: Dict[str, str] = {}
    for name in names:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = "not-installed"
    return out


def normalize_answer(text: str) -> str:
    return " ".join(str(text).strip().lower().split())


def score_answer(answer: str, expected: Sequence[str]) -> Dict[str, Any]:
    norm = normalize_answer(answer)
    ex = [normalize_answer(x) for x in expected]
    exact = norm in ex
    contains = any(x and x in norm for x in ex)
    return {"exact_match": bool(exact), "contains_expected": bool(contains)}


def field_metrics(
    pre: Mapping[str, str],
    post: Mapping[str, str],
    scenario: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    truth = {str(k): str(v) for k, v in scenario.get("ground_truth_fields", {}).items()}
    corrupted = set(map(str, scenario.get("corrupted_fields", [])))
    legitimate = set(map(str, scenario.get("legitimate_fields", [])))

    true_repairs = 0
    false_corrections = 0
    legitimate_change_damage = 0
    final_errors = 0
    changed_fields: List[str] = []

    for field, expected in truth.items():
        before = pre.get(field)
        after = post.get(field)
        if before != after:
            changed_fields.append(field)
        if before != expected and after == expected:
            true_repairs += 1
        if before == expected and after != expected:
            false_corrections += 1
        if field in legitimate and before == expected and after != expected:
            legitimate_change_damage += 1
        if after != expected:
            final_errors += 1

    corrupted_recovered = sum(1 for f in corrupted if pre.get(f) != truth.get(f) and post.get(f) == truth.get(f))
    corrupted_present = sum(1 for f in corrupted if pre.get(f) != truth.get(f))
    recovered_fraction = (corrupted_recovered / corrupted_present) if corrupted_present else None

    quarantines = sum(1 for d in decisions if str(d.get("decision")) == "QUARANTINE")
    escalations = sum(1 for d in decisions if str(d.get("decision")) == "ESCALATE")
    repairs = sum(1 for d in decisions if str(d.get("decision")) == "REPAIR")

    return {
        "true_repairs": true_repairs,
        "false_corrections": false_corrections,
        "recovered_corruptions": corrupted_recovered,
        "recovered_corruption_fraction": recovered_fraction,
        "legitimate_change_damage": legitimate_change_damage,
        "quarantines": quarantines,
        "escalations": escalations,
        "repair_decisions": repairs,
        "final_memory_error": final_errors,
        "changed_fields": sorted(changed_fields),
    }


def load_scenarios(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("scenarios"), list):
        raise ValueError("scenario file must contain an object with a 'scenarios' list")
    return obj


def run_scenario(
    scenario: Mapping[str, Any],
    *,
    system_prompt: str,
    ablations: Mapping[str, bool],
    llm: Any = None,
    max_tokens: int = 128,
) -> Dict[str, Any]:
    sid = str(scenario["session_id"])
    with tempfile.TemporaryDirectory(prefix="btbc_ab_") as td:
        plain_db = str(Path(td) / "plain.db")
        btbc_db = str(Path(td) / "btbc.db")
        memory_engine.seed_scenario(plain_db, scenario)
        memory_engine.seed_scenario(btbc_db, scenario)

        plain_before = memory_engine.active_field_values(plain_db, sid)
        btbc_before = memory_engine.active_field_values(btbc_db, sid)
        if plain_before != btbc_before:
            raise RuntimeError("A/B seed mismatch before controller execution")

        plain_context = memory_engine.memory_context(plain_db, sid)
        adapter_result = derive_trusted_context_v1_4(
            btbc_db,
            sid,
            limit=max(100, len(scenario.get("memories", [])) + 10),
            ablations=dict(ablations),
        )
        btbc_after = memory_engine.active_field_values(btbc_db, sid)
        # Use the post-controller DB as the actual agent context. This prevents
        # historical bridge slices from being repeated in the prompt.
        btbc_context = memory_engine.memory_context(btbc_db, sid)
        decisions = list(adapter_result.get("decisions") or [])

        metrics = field_metrics(btbc_before, btbc_after, scenario, decisions)
        truth = {str(k): str(v) for k, v in scenario.get("ground_truth_fields", {}).items()}
        plain_final_error = sum(1 for k, v in truth.items() if plain_before.get(k) != v)

        result: Dict[str, Any] = {
            "scenario_id": scenario.get("id"),
            "description": scenario.get("description"),
            "session_id": sid,
            "ground_truth_fields": truth,
            "plain": {
                "pre_fields": plain_before,
                "post_fields": dict(plain_before),
                "memory_context": plain_context,
                "final_memory_error": plain_final_error,
            },
            "btbc": {
                "pre_fields": btbc_before,
                "post_fields": btbc_after,
                "memory_context": btbc_context,
                "metrics": metrics,
                "decisions": decisions,
                "adapter_metrics": adapter_result.get("metrics"),
                "router_hash": adapter_result.get("router_hash"),
                "operating_hash": adapter_result.get("operating_hash"),
                "adapter_hash": adapter_result.get("adapter_hash"),
                "frozen_dir_hash": adapter_result.get("frozen_dir_hash"),
            },
        }

        query = scenario.get("query") or {}
        if llm is not None and query.get("user_message"):
            expected = list(query.get("expected_answers") or [])
            plain_answer = llm.chat(
                system_prompt=system_prompt,
                memory_context=plain_context,
                user_message=str(query["user_message"]),
                max_tokens=max_tokens,
                temperature=0.0,
            )
            btbc_answer = llm.chat(
                system_prompt=system_prompt,
                memory_context=btbc_context,
                user_message=str(query["user_message"]),
                max_tokens=max_tokens,
                temperature=0.0,
            )
            result["llm"] = {
                "user_message": query["user_message"],
                "expected_answers": expected,
                "plain_answer": plain_answer,
                "plain_score": score_answer(plain_answer, expected),
                "btbc_answer": btbc_answer,
                "btbc_score": score_answer(btbc_answer, expected),
            }
        return result


def write_summary_csv(path: Path, results: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "scenario_id", "plain_final_memory_error", "btbc_final_memory_error",
        "true_repairs", "false_corrections", "recovered_corruptions",
        "recovered_corruption_fraction", "legitimate_change_damage",
        "quarantines", "escalations", "repair_decisions",
        "plain_answer_exact", "btbc_answer_exact",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            m = r["btbc"]["metrics"]
            llm = r.get("llm") or {}
            w.writerow({
                "scenario_id": r.get("scenario_id"),
                "plain_final_memory_error": r["plain"].get("final_memory_error"),
                "btbc_final_memory_error": m.get("final_memory_error"),
                "true_repairs": m.get("true_repairs"),
                "false_corrections": m.get("false_corrections"),
                "recovered_corruptions": m.get("recovered_corruptions"),
                "recovered_corruption_fraction": m.get("recovered_corruption_fraction"),
                "legitimate_change_damage": m.get("legitimate_change_damage"),
                "quarantines": m.get("quarantines"),
                "escalations": m.get("escalations"),
                "repair_decisions": m.get("repair_decisions"),
                "plain_answer_exact": (llm.get("plain_score") or {}).get("exact_match"),
                "btbc_answer_exact": (llm.get("btbc_score") or {}).get("exact_match"),
            })


def build_metadata(args: argparse.Namespace, scenario_path: Path) -> Dict[str, Any]:
    model_path = Path(args.model).resolve() if args.model else None
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_commit_sha": repo_sha(),
        "python": sys.version,
        "platform": platform.platform(),
        "packages": package_versions(),
        "seed": int(args.seed),
        "args": vars(args),
        "scenario_sha256": sha256_file(scenario_path),
        "model_sha256": sha256_file(model_path) if model_path else None,
        "file_hashes": {rel: sha256_file(REPO_ROOT / rel) for rel in FROZEN_FILES},
        "scientific_label": "frozen BTBC v1.4 operating through llm_state_bridge",
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenarios", default="tests/scenarios.json")
    p.add_argument("--model", default=os.environ.get("BTBC_MODEL_PATH", "model/model.gguf"))
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default="results/results.json")
    p.add_argument("--n-gpu-layers", type=int, default=int(os.environ.get("BTBC_N_GPU_LAYERS", "0")))
    p.add_argument("--n-ctx", type=int, default=4096)
    p.add_argument("--max-tokens", type=int, default=128)
    p.add_argument("--only-metrics", action="store_true")
    p.add_argument("--no-relations", action="store_true")
    p.add_argument("--no-temporal", action="store_true")
    p.add_argument("--no-provenance", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    scenario_path = (REPO_ROOT / args.scenarios).resolve() if not Path(args.scenarios).is_absolute() else Path(args.scenarios)
    bundle = load_scenarios(scenario_path)
    ablations = {
        "no_relations": bool(args.no_relations),
        "no_temporal": bool(args.no_temporal),
        "no_provenance": bool(args.no_provenance),
    }

    llm = None
    if not args.only_metrics:
        model_path = Path(args.model)
        if not model_path.is_absolute():
            model_path = REPO_ROOT / model_path
        if not model_path.exists():
            raise SystemExit(
                f"Model file not found: {model_path}. Supply --model or use --only-metrics."
            )
        from btbc.local_llm import LocalLLM
        llm = LocalLLM(
            str(model_path), n_gpu_layers=args.n_gpu_layers, n_ctx=args.n_ctx, seed=args.seed
        )

    results = [
        run_scenario(
            s,
            system_prompt=str(bundle.get("system_prompt") or "Use the supplied memory."),
            ablations=ablations,
            llm=llm,
            max_tokens=args.max_tokens,
        )
        for s in bundle["scenarios"]
    ]

    output = {
        "metadata": build_metadata(args, scenario_path),
        "ablations": ablations,
        "results": results,
    }
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True, default=str), encoding="utf-8")
    write_summary_csv(out_path.with_suffix(".csv"), results)
    print(f"Wrote {out_path}")
    print(f"Wrote {out_path.with_suffix('.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
