"""Generate independent randomized BTBC memory-integrity benchmark worlds.

Each output file is directly consumable by tests/compare_agents.py: it contains
one scenario inside the normal {"scenarios": [...]} wrapper. A manifest records
the generator configuration and SHA-256 of every world for reproducibility.

This is experimental bridge-benchmark infrastructure. It does not modify the
frozen BTBC v1.x implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SYSTEM_PROMPT = (
    "Answer using the supplied memory. If the memory does not support an answer, "
    "say you do not know."
)
GENERATOR_VERSION = 1
VALUES = ("amber", "blue", "green", "ivory", "orange", "purple", "red", "yellow")
SOURCES = ("user", "profile", "import", "session_note", "trusted_sync")
ATTRIBUTES = (
    "favorite_color", "home_state", "favorite_food", "preferred_drink",
    "pet_name", "preferred_language", "work_city", "favorite_season",
    "music_genre", "shoe_brand", "vacation_style", "coffee_order",
    "hobby", "vehicle_color", "favorite_number", "preferred_store",
    "morning_drink", "weekend_activity", "favorite_snack", "desk_location",
)


@dataclass(frozen=True)
class GeneratorConfig:
    num_worlds: int = 200
    min_fields: int = 5
    max_fields: int = 20
    temporal_depth: int = 5
    corruption_rate: float = 0.10
    high_trust_corruption_fraction: float = 0.20
    relationship_density: float = 0.15
    duplicate_conflict_rate: float = 0.10
    burstiness: float = 0.20
    legitimate_change_rate: float = 0.10
    provenance_noise: float = 0.25
    master_seed: int = 369


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _clip(x: float, lo: float = 0.01, hi: float = 0.995) -> float:
    return max(lo, min(hi, float(x)))


def _other_value(rng: random.Random, current: str) -> str:
    choices = [v for v in VALUES if v != current]
    return rng.choice(choices)


def _source(rng: random.Random, provenance_noise: float, *, corrupt: bool = False) -> str:
    if corrupt:
        base = "injected_fault"
    else:
        base = rng.choice(SOURCES)
    if rng.random() < provenance_noise:
        return f"{base}:{rng.randrange(1, 10_000):04d}"
    return base


def _active_fields(memories: Sequence[Mapping[str, Any]]) -> Dict[str, str]:
    by_field: Dict[str, List[Mapping[str, Any]]] = {}
    times = [int(r.get("valid_from") or r.get("created_at") or 0) for r in memories]
    now = max(times) if times else 0
    for r in memories:
        vf = int(r.get("valid_from") or r.get("created_at") or 0)
        vt = r.get("valid_to")
        if vf <= now and (vt is None or now < int(vt)) and str(r.get("status") or "active") != "deleted":
            key = f"{r['entity']}.{r['attribute']}"
            by_field.setdefault(key, []).append(r)
    out: Dict[str, str] = {}
    for key, rows in by_field.items():
        winner = max(rows, key=lambda r: (
            int(r.get("valid_from") or 0),
            int(r.get("created_at") or 0),
            str(r["memory_id"]),
        ))
        out[key] = str(winner["value"])
    return out


def _memory_row(
    *, world: int, field_index: int, event_index: int, session_id: str,
    attribute: str, value: str, timestamp: int, source: str,
    source_trust: float, confidence: float, valid_to: Optional[int] = None,
    suffix: str = "obs",
) -> Dict[str, Any]:
    return {
        "memory_id": f"w{world:04d}_f{field_index:03d}_{suffix}{event_index:02d}",
        "session_id": session_id,
        "entity": "user",
        "attribute": attribute,
        "value": value,
        "valid_from": int(timestamp),
        "valid_to": None if valid_to is None else int(valid_to),
        "source": source,
        "source_trust": round(_clip(source_trust), 6),
        "confidence": round(_clip(confidence), 6),
        "created_at": int(timestamp),
        "updated_at": int(timestamp),
        "status": "active",
    }


def generate_world(world_index: int, cfg: GeneratorConfig) -> Dict[str, Any]:
    """Generate one deterministic, independent paired A/B world."""
    world_seed = cfg.master_seed + world_index * 1_000_003
    rng = random.Random(world_seed)
    k = rng.randint(cfg.min_fields, cfg.max_fields)
    if k > len(ATTRIBUTES):
        raise ValueError(f"max_fields cannot exceed {len(ATTRIBUTES)}")
    attributes = rng.sample(list(ATTRIBUTES), k)
    session_id = f"generated_{world_index:04d}"
    times = [100 * (i + 1) for i in range(cfg.temporal_depth)]
    if len(times) < 3:
        raise ValueError("temporal_depth must be >= 3")

    legitimate_indices = {i for i in range(k) if rng.random() < cfg.legitimate_change_rate}
    corruption_candidates = [i for i in range(k) if i not in legitimate_indices]
    corrupted_indices = {i for i in corruption_candidates if rng.random() < cfg.corruption_rate}
    if cfg.corruption_rate > 0 and corruption_candidates and not corrupted_indices:
        corrupted_indices.add(rng.choice(corruption_candidates))

    # Burstiness adds a correlated cluster of final-window corruptions while
    # preserving independent world seeds as the unit of statistical analysis.
    burst_triggered = bool(corruption_candidates and rng.random() < cfg.burstiness)
    if burst_triggered:
        extra_n = min(len(corruption_candidates), max(1, int(math.ceil(k * cfg.corruption_rate))))
        corrupted_indices.update(rng.sample(corruption_candidates, extra_n))

    memories: List[Dict[str, Any]] = []
    truth: Dict[str, str] = {}
    corrupted_fields: List[str] = []
    legitimate_fields: List[str] = []
    anchor_memory: Dict[int, str] = {}
    injections: List[Dict[str, Any]] = []

    for i, attr in enumerate(attributes):
        key = f"user.{attr}"
        initial = rng.choice(VALUES)
        current_truth = initial
        event_no = 0

        first = _memory_row(
            world=world_index, field_index=i, event_index=event_no,
            session_id=session_id, attribute=attr, value=initial,
            timestamp=times[0], source=_source(rng, cfg.provenance_noise),
            source_trust=rng.uniform(0.88, 0.995), confidence=rng.uniform(0.90, 0.995),
        )
        memories.append(first)
        anchor_memory[i] = first["memory_id"]
        event_no += 1

        # Add trusted temporal support for many fields. The support rate is
        # intentionally high enough for no-temporal ablations to have a chance
        # to differ, without forcing a repair outcome.
        for t in times[1:-1]:
            if i in legitimate_indices and t == times[-2]:
                new_value = _other_value(rng, current_truth)
                memories.append(_memory_row(
                    world=world_index, field_index=i, event_index=event_no,
                    session_id=session_id, attribute=attr, value=new_value,
                    timestamp=t, source=_source(rng, cfg.provenance_noise),
                    source_trust=rng.uniform(0.92, 0.995), confidence=rng.uniform(0.94, 0.995),
                    suffix="legit",
                ))
                anchor_memory[i] = memories[-1]["memory_id"]
                current_truth = new_value
                legitimate_fields.append(key)
                event_no += 1
            elif rng.random() < 0.65:
                memories.append(_memory_row(
                    world=world_index, field_index=i, event_index=event_no,
                    session_id=session_id, attribute=attr, value=current_truth,
                    timestamp=t, source=_source(rng, cfg.provenance_noise),
                    source_trust=rng.uniform(0.82, 0.995), confidence=rng.uniform(0.86, 0.995),
                    suffix="support",
                ))
                anchor_memory[i] = memories[-1]["memory_id"]
                event_no += 1

        truth[key] = current_truth

        if i in corrupted_indices:
            wrong = _other_value(rng, current_truth)
            high_trust = rng.random() < cfg.high_trust_corruption_fraction
            trust = rng.uniform(0.65, 0.95) if high_trust else rng.uniform(0.05, 0.25)
            conf = rng.uniform(0.65, 0.95) if high_trust else rng.uniform(0.08, 0.35)
            corrupt_ts = times[-1]
            row = _memory_row(
                world=world_index, field_index=i, event_index=event_no,
                session_id=session_id, attribute=attr, value=wrong,
                timestamp=corrupt_ts, source=_source(rng, cfg.provenance_noise, corrupt=True),
                source_trust=trust, confidence=conf, suffix="fault",
            )
            # When duplicate conflict is selected, create a trusted truth row at
            # the same logical time, then make the fault one creation tick later
            # so the plain active-memory rule deterministically sees the fault.
            if rng.random() < cfg.duplicate_conflict_rate:
                good = _memory_row(
                    world=world_index, field_index=i, event_index=event_no,
                    session_id=session_id, attribute=attr, value=current_truth,
                    timestamp=corrupt_ts, source=_source(rng, cfg.provenance_noise),
                    source_trust=rng.uniform(0.90, 0.995), confidence=rng.uniform(0.92, 0.995),
                    suffix="conflict_good",
                )
                memories.append(good)
                anchor_memory[i] = good["memory_id"]
                event_no += 1
                row = _memory_row(
                    world=world_index, field_index=i, event_index=event_no,
                    session_id=session_id, attribute=attr, value=wrong,
                    timestamp=corrupt_ts, source=_source(rng, cfg.provenance_noise, corrupt=True),
                    source_trust=trust, confidence=conf, suffix="conflict_fault",
                )
                row["created_at"] = corrupt_ts + 1
                row["updated_at"] = corrupt_ts + 1
            memories.append(row)
            corrupted_fields.append(key)
            injections.append({
                "field": key,
                "memory_id": row["memory_id"],
                "kind": "corruption",
                "wrong_value": wrong,
                "ground_truth": current_truth,
                "source_trust": row["source_trust"],
                "confidence": row["confidence"],
                "high_trust": high_trust,
            })
        elif i not in legitimate_indices and rng.random() < 0.40:
            # A final trusted support observation makes some clean fields recent,
            # guarding against a benchmark where only corrupt fields have late data.
            memories.append(_memory_row(
                world=world_index, field_index=i, event_index=event_no,
                session_id=session_id, attribute=attr, value=current_truth,
                timestamp=times[-1], source=_source(rng, cfg.provenance_noise),
                source_trust=rng.uniform(0.88, 0.995), confidence=rng.uniform(0.90, 0.995),
                suffix="final_support",
            ))
            anchor_memory[i] = memories[-1]["memory_id"]

    relationships: List[Dict[str, Any]] = []
    for i in range(k):
        for j in range(i + 1, k):
            if rng.random() >= cfg.relationship_density:
                continue
            relationships.append({
                "from_memory_id": anchor_memory[i],
                "to_memory_id": anchor_memory[j],
                "relation_type": "generated_association",
                "provenance": _source(rng, cfg.provenance_noise),
                "trust": round(rng.uniform(0.75, 0.98), 6),
                "created_at": times[-2],
                # Intentionally no scalar relation_value override. With the
                # current categorical bridge a single +/-1 cannot represent all
                # per-bit cross-field codeword relations faithfully. These links
                # therefore test relational topology, not independent semantic
                # contradiction evidence.
                "relation_value": None,
                "observed_relation": None,
            })

    pre = _active_fields(memories)
    expected_corrupted = sorted(k for k, v in truth.items() if pre.get(k) != v)
    # Keep labels tied to actual seeded DB semantics rather than generator intent.
    corrupted_fields = expected_corrupted

    scenario = {
        "id": f"generated_world_{world_index:04d}",
        "session_id": session_id,
        "description": (
            f"Generated memory world {world_index} with {k} fields, "
            f"{len(corrupted_fields)} active corruptions, "
            f"{len(legitimate_fields)} legitimate changes, and "
            f"{len(relationships)} relational links."
        ),
        "world_seed": world_seed,
        "memories": memories,
        "relationships": relationships,
        "ground_truth_fields": truth,
        "corrupted_fields": corrupted_fields,
        "legitimate_fields": sorted(set(legitimate_fields)),
        "injections": injections,
        "generation": {
            "burst_triggered": burst_triggered,
            "field_count": k,
            "temporal_depth": cfg.temporal_depth,
            "relationship_count": len(relationships),
        },
        "query": {},
    }
    return scenario


def generate_suite(cfg: GeneratorConfig) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    config_dict = asdict(cfg)
    config_hash = _sha_obj({"generator_version": GENERATOR_VERSION, "config": config_dict})
    suite_id = f"btbc-generated-v{GENERATOR_VERSION}-{config_hash[:16]}"
    worlds = [generate_world(i, cfg) for i in range(cfg.num_worlds)]
    manifest = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "suite_id": suite_id,
        "config_sha256": config_hash,
        "config": config_dict,
        "world_count": len(worlds),
        "relation_evidence_note": (
            "Explicit generated links exercise relational topology. Under the current "
            "categorical bridge they do not encode independent per-bit semantic relation evidence."
        ),
    }
    return worlds, manifest


def write_suite(out_dir: Path, cfg: GeneratorConfig, *, clean: bool = False) -> Dict[str, Any]:
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    worlds, manifest = generate_suite(cfg)
    files = []
    for i, scenario in enumerate(worlds):
        obj = {
            "schema_version": 2,
            "system_prompt": SYSTEM_PROMPT,
            "generator": {
                "suite_id": manifest["suite_id"],
                "config_sha256": manifest["config_sha256"],
                "world_index": i,
                "world_seed": scenario["world_seed"],
            },
            "scenarios": [scenario],
        }
        path = out_dir / f"world_{i:04d}.json"
        text = json.dumps(obj, indent=2, sort_keys=True)
        path.write_text(text + "\n", encoding="utf-8")
        files.append({
            "world_index": i,
            "world_seed": scenario["world_seed"],
            "path": path.name,
            "sha256": hashlib.sha256((text + "\n").encode("utf-8")).hexdigest(),
            "corrupted_fields": len(scenario["corrupted_fields"]),
            "legitimate_fields": len(scenario["legitimate_fields"]),
            "relationships": len(scenario["relationships"]),
        })
    manifest = dict(manifest)
    manifest["files"] = files
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _rate(value: str) -> float:
    x = float(value)
    if not 0.0 <= x <= 1.0:
        raise argparse.ArgumentTypeError("rate must be between 0 and 1")
    return x


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--num-worlds", type=int, default=200)
    p.add_argument("--min-fields", type=int, default=5)
    p.add_argument("--max-fields", type=int, default=20)
    p.add_argument("--temporal-depth", type=int, default=5)
    p.add_argument("--corruption-rate", type=_rate, default=0.10)
    p.add_argument("--high-trust-corruption-fraction", type=_rate, default=0.20)
    p.add_argument("--relationship-density", type=_rate, default=0.15)
    p.add_argument("--duplicate-conflict-rate", type=_rate, default=0.10)
    p.add_argument("--burstiness", type=_rate, default=0.20)
    p.add_argument("--legitimate-change-rate", type=_rate, default=0.10)
    p.add_argument("--provenance-noise", type=_rate, default=0.25)
    p.add_argument("--seed", type=int, default=369, dest="master_seed")
    p.add_argument("--out-dir", default="results/generated_worlds")
    p.add_argument("--clean", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.num_worlds < 1:
        raise SystemExit("--num-worlds must be >= 1")
    if args.min_fields < 1 or args.max_fields < args.min_fields:
        raise SystemExit("require 1 <= min-fields <= max-fields")
    if args.max_fields > len(ATTRIBUTES):
        raise SystemExit(f"--max-fields cannot exceed {len(ATTRIBUTES)}")
    if args.temporal_depth < 3:
        raise SystemExit("--temporal-depth must be >= 3")
    cfg = GeneratorConfig(**{k: getattr(args, k) for k in GeneratorConfig.__dataclass_fields__})
    manifest = write_suite(Path(args.out_dir), cfg, clean=bool(args.clean))
    print(f"Generated {manifest['world_count']} worlds in {args.out_dir}")
    print(f"suite_id={manifest['suite_id']}")
    print(f"config_sha256={manifest['config_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
