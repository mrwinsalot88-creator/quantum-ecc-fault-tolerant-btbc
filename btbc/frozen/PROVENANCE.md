# BTBC v1.4 frozen-source provenance

The original BTBC v1.1-v1.4 research source files in this directory are copied unchanged from the project's research artifacts.

`router.joblib` is a deterministic reconstruction produced by the exact v1.4 `fit_router()` implementation. The source itself fixes `SEED = 369_140026`; the regeneration script does not replace that seed.

`operating.json` is produced by the exact v1.4 `calibrate(router)` implementation and must match the archived locked operating point:

```json
{
  "harm_weight": 4.0,
  "threshold": 0.04447377462482015,
  "target_false_correction_rate": 0.001,
  "validation_error_rate": 0.18369708994708994,
  "validation_false_correction_rate": 0.000992063492063492,
  "validation_repair_precision": 0.9657768651608487,
  "validation_recovery_calls": 1541,
  "validation_worlds": 135,
  "validation_escalated_cells": 4252
}
```

The binary router was not an original archived binary artifact. It is regenerated from the frozen source, and the regeneration script fails if the calibrated operating point differs from the archived values.
