#!/usr/bin/env python3
"""V2-007 Section 30/31/32: the SINGLE locked official-VALIDATION prediction session.

Scores all 6 frozen V2 finalist checkpoints plus all 3 historical MODEL_V1 reference
checkpoints against the official-VALIDATION partition, in ONE guarded session. model.eval() +
torch.inference_mode() only -- no gradient, no augmentation, no BatchNorm update, no dropout,
no calibration, no threshold. The official-VALIDATION window source is read exactly once via
scripts._v2_007_lib.load_official_validation_population (gated by both the CV-role firewall's
OFFICIAL_VALIDATION rule, requiring checkpoint_finalized=True, and the partition firewall),
then every fixed checkpoint is scored against that same in-memory population. Guarded by
nhm.model_v2_official_validation_guard's persistent ARMED -> RUNNING -> COMPLETED state
machine: a second invocation after COMPLETED raises MODEL_V2_VALIDATION_ALREADY_CONSUMED
before any data is touched.
"""

from __future__ import annotations

import csv
import json

import scripts._v2_007_lib as lib
from nhm.hashing import hash_file
from nhm.model_v2_official_validation_guard import (
    check_and_begin_session,
    complete_session,
    mark_partially_consumed,
)

OUT_DIR = lib.ROOT / "reports/model_v2/v2_007"
RUNS_DIR = OUT_DIR / "runs"

ORDER = [
    ("MODEL_V2_TCN_MEAN", 20260927), ("MODEL_V2_TCN_MEAN", 20260928),
    ("MODEL_V2_TCN_MEAN", 20260929), ("MODEL_V2_TCN_MEANMAX", 20260927),
    ("MODEL_V2_TCN_MEANMAX", 20260928), ("MODEL_V2_TCN_MEANMAX", 20260929),
]
V1_SEEDS = (20260927, 20260928, 20260929)


def _observed_preconditions() -> dict:
    return {
        "official_validation_config_sha256": hash_file(
            lib.ROOT / "configs/model_v2/official_validation_v1.yaml"
        ),
        "bootstrap_draws_sha256": hash_file(OUT_DIR / "validation_bootstrap_draws.npz"),
        "shortlist_lock_sha256": hash_file(
            lib.ROOT / "manifests/model_v2/MODEL_V2_FINALIST_SHORTLIST_V1.lock.json"
        ),
        "protocol_v3_lock_sha256": hash_file(
            lib.ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        ),
        "final_inner_manifest_sha256": hash_file(lib.FINAL_INNER_CSV),
    }


def _verify_checkpoint_hashes_before_access() -> dict:
    """Independent safety check (beyond the guard's own precondition dict): every V2
    checkpoint hash must match validation_ready_checkpoints.json, every V1 reference
    checkpoint hash must match the frozen expected value. Raises before any waveform data is
    touched if anything differs."""
    v2_rows = json.loads(
        (OUT_DIR / "validation_ready_checkpoints.json").read_text(encoding="utf-8")
    )
    v2_mismatches = [
        row["configuration"]
        for row in v2_rows
        if hash_file(lib.ROOT / row["checkpoint_path"]) != row["checkpoint_sha256"]
    ]
    v1_pre = json.loads((OUT_DIR / "v1_reference_preflight.json").read_text(encoding="utf-8"))
    v1_mismatches = [
        seed for seed, info in v1_pre["checkpoints"].items()
        if hash_file(lib.ROOT / info["path"]) != info["expected_sha256"]
    ]
    if v2_mismatches or v1_mismatches:
        raise RuntimeError(
            f"checkpoint hash mismatch before official-VALIDATION access: "
            f"v2={v2_mismatches} v1={v1_mismatches}"
        )
    return {"v2_rows": v2_rows, "v1_checkpoints": v1_pre["checkpoints"]}


def main() -> None:
    pre = _verify_checkpoint_hashes_before_access()
    observed = _observed_preconditions()

    check_and_begin_session(lib.ROOT, observed_preconditions=observed)

    config, _config_sha = lib.load_frozen_model_v1_config()
    groups = lib.official_validation_groups()

    try:
        population, example_meta = lib.load_official_validation_population(
            architecture_id="V2-007_OFFICIAL_VALIDATION_SESSION",
            schedule_id="ALL_6_FINALIST_CONFIGS_PLUS_3_V1_REFERENCE",
            seed=0,
            participant_group_ids=groups,
            checkpoint_finalized=True,
            access_purpose=(
                "single locked official-VALIDATION scoring session: 6 V2 finalist "
                "checkpoints + 3 historical MODEL_V1 reference checkpoints"
            ),
        )

        label_by_example = dict(
            zip(population.example_ids, population.labels.tolist(), strict=True)
        )

        v2_rows = []
        for row in pre["v2_rows"]:
            architecture_id = row["architecture_id"]
            checkpoint_path = lib.ROOT / row["checkpoint_path"]
            model = lib.load_v2_checkpoint(architecture_id, checkpoint_path)
            raw_logits, raw_probs, example_ids, group_ids = lib.score_checkpoint(
                model, population, seed=row["seed"], config=config
            )
            for example_id, group_id, logit, prob in zip(
                example_ids, group_ids, raw_logits, raw_probs, strict=True
            ):
                meta = example_meta[example_id]
                v2_rows.append(
                    {
                        "example_id": example_id,
                        "participant_group_id": group_id,
                        "record_id": meta["record_id"],
                        "configuration_id": row["configuration"],
                        "architecture_id": architecture_id,
                        "schedule_id": row["schedule_id"],
                        "seed": row["seed"],
                        "label": label_by_example[example_id],
                        "raw_logit": float(logit),
                        "raw_probability": float(prob),
                        "checkpoint_sha256": row["checkpoint_sha256"],
                        "selected_epoch": row["selected_epoch"],
                    }
                )
        v2_rows.sort(key=lambda r: (r["configuration_id"], r["example_id"]))

        v1_rows = []
        for seed in V1_SEEDS:
            info = pre["v1_checkpoints"][str(seed)]
            model = lib.load_v1_checkpoint(seed)
            raw_logits, raw_probs, example_ids, group_ids = lib.score_checkpoint(
                model, population, seed=seed, config=config
            )
            for example_id, group_id, logit, prob in zip(
                example_ids, group_ids, raw_logits, raw_probs, strict=True
            ):
                meta = example_meta[example_id]
                v1_rows.append(
                    {
                        "example_id": example_id,
                        "participant_group_id": group_id,
                        "record_id": meta["record_id"],
                        "model_id": "MODEL_V1",
                        "architecture_id": "MODEL_V1",
                        "seed": seed,
                        "label": label_by_example[example_id],
                        "raw_logit": float(logit),
                        "raw_probability": float(prob),
                        "checkpoint_sha256": info["expected_sha256"],
                    }
                )
        v1_rows.sort(key=lambda r: (r["seed"], r["example_id"]))

        if len(v2_rows) != 2 * 3 * 2880:
            raise RuntimeError(f"V2 prediction row count {len(v2_rows)} != 17280")
        if len(v1_rows) != 3 * 2880:
            raise RuntimeError(f"V1 prediction row count {len(v1_rows)} != 8640")

        v2_path = OUT_DIR / "official_validation_predictions.csv"
        with v2_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(v2_rows[0].keys()))
            writer.writeheader()
            writer.writerows(v2_rows)

        v1_path = OUT_DIR / "v1_reference_validation_predictions.csv"
        with v1_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(v1_rows[0].keys()))
            writer.writeheader()
            writer.writerows(v1_rows)

    except Exception as exc:
        mark_partially_consumed(lib.ROOT, failure_summary={"error": repr(exc)})
        raise

    completion_summary = {
        "v2_prediction_rows": len(v2_rows),
        "v1_prediction_rows": len(v1_rows),
        "v2_predictions_sha256": hash_file(v2_path),
        "v1_predictions_sha256": hash_file(v1_path),
    }
    complete_session(lib.ROOT, completion_summary=completion_summary)

    access_audit = {
        "guard_before": "ARMED",
        "guard_after": "COMPLETED",
        "session_count": 1,
        "v2_configurations_scored": len(pre["v2_rows"]),
        "v1_checkpoints_scored": len(V1_SEEDS),
        **completion_summary,
        "status": "PASS",
    }
    (OUT_DIR / "official_validation_access_audit.json").write_text(
        json.dumps(access_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(access_audit, indent=2))


if __name__ == "__main__":
    main()
