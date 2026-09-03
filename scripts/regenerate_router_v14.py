"""Regenerate the frozen BTBC v1.4 router deterministically.

This script requires the exact unchanged research sources under btbc/frozen/.
It uses the source-defined SEED and exact fit_router()/calibrate() signatures.
It writes router.joblib and operating.json only after verifying the calibrated
operating point matches the archived locked v1.4 values.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIR = ROOT / "btbc" / "frozen"
ROUTER_OUT = FROZEN_DIR / "router.joblib"
OPERATING_OUT = FROZEN_DIR / "operating.json"

EXPECTED = {
    "harm_weight": 4.0,
    "threshold": 0.04447377462482015,
    "target_false_correction_rate": 0.001,
    "validation_error_rate": 0.18369708994708994,
    "validation_false_correction_rate": 0.000992063492063492,
    "validation_repair_precision": 0.9657768651608487,
    "validation_recovery_calls": 1541,
    "validation_worlds": 135,
    "validation_escalated_cells": 4252,
}


def main() -> None:
    mod = importlib.import_module("btbc.frozen.BTBC_v1_4_risk_budget_router")
    router, _train = mod.fit_router()
    operating, _vw, _vr = mod.calibrate(router)

    if operating != EXPECTED:
        raise RuntimeError(
            "Regenerated operating point does not match archived frozen v1.4 values.\n"
            f"expected={json.dumps(EXPECTED, sort_keys=True)}\n"
            f"actual={json.dumps(operating, sort_keys=True)}"
        )

    joblib.dump(router, ROUTER_OUT)
    OPERATING_OUT.write_text(json.dumps(operating, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {ROUTER_OUT}")
    print(f"Wrote {OPERATING_OUT}")
    print(f"Source SEED={mod.SEED}")


if __name__ == "__main__":
    main()
