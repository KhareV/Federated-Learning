#!/usr/bin/env python3
"""V2-009 Section 41: the SINGLE guarded CALIBRATION session. Scores every eligible
CALIBRATION window with MODEL_V2_FINAL (model.eval() + torch.inference_mode() only -- no
gradient, no augmentation, no BatchNorm update, no dropout) and persists an immutable raw-
logit prediction table. Guarded by nhm.model_v2_calibration_guard's persistent ARMED ->
RUNNING -> COMPLETED state machine: a second invocation after COMPLETED raises
V2_CALIBRATION_ALREADY_CONSUMED before any data is touched. No temperature fit, no
threshold -- that happens afterward, from the frozen table only (Section 42).
"""

from __future__ import annotations

import csv
import json

import scripts._cal_v2_lib as lib
from nhm.hashing import hash_file
from nhm.model_v2_calibration_guard import (
    check_and_begin_session,
    complete_session,
    mark_partially_consumed,
)

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_009"
CONFIG_PATH = ROOT / "configs/model_v2/calibration_v2.yaml"


def _observed_preconditions() -> dict:
    return {
        "calibration_method_config_sha256": hash_file(CONFIG_PATH),
        "model_v2_final_checkpoint_sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
        "model_v2_final_manifest_sha256": hash_file(
            ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json"
        ),
        "model_v2_final_frozen_config_sha256": hash_file(
            ROOT / "configs/model_v2_final_frozen.yaml"
        ),
        "protocol_v3_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        ),
    }


def main() -> None:
    observed = _observed_preconditions()
    check_and_begin_session(ROOT, observed_preconditions=observed)

    try:
        population = lib.load_calibration_population_v2(ROOT)
        logits = lib.extract_frozen_logits_v2(population, ROOT)
        raw_probability = lib.raw_probability_from_logit(logits)

        rows = []
        for row, label, logit, prob in zip(
            population.rows, population.labels, logits, raw_probability, strict=True
        ):
            rows.append(
                {
                    "example_id": row["example_id"],
                    "participant_group_id": row["participant_group_id"],
                    "record_id": row["record_id"],
                    "label": int(label),
                    "raw_logit": format(float(logit), ".17g"),
                    "raw_probability": format(float(prob), ".17g"),
                    "model_id": "MODEL_V2_FINAL",
                    "checkpoint_sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
                }
            )

        if len(rows) != 1080:
            raise RuntimeError(f"CALIBRATION prediction row count {len(rows)} != 1080")

        predictions_path = OUT_DIR / "calibration_predictions.csv"
        with predictions_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    except Exception as exc:
        mark_partially_consumed(ROOT, failure_summary={"error": repr(exc)})
        raise

    completion_summary = {
        "calibration_rows": len(rows),
        "predictions_sha256": hash_file(predictions_path),
    }
    complete_session(ROOT, completion_summary=completion_summary)

    access_audit = {
        "guard_before": "ARMED",
        "guard_after": "COMPLETED",
        "session_count": 1,
        "calibration_rows": len(rows),
        "accessed_paths": list(population.accessed_paths),
        "TRAIN": 0, "VALIDATION": 0, "INTERNAL_TEST": 0, "INCART": 0, "NSTDB": 0, "BIDMC": 0,
        **completion_summary,
        "status": "PASS",
    }
    (OUT_DIR / "calibration_access_audit.json").write_text(
        json.dumps(access_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(access_audit, indent=2))


if __name__ == "__main__":
    main()
