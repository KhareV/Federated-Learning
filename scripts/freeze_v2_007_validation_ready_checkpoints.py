#!/usr/bin/env python3
"""V2-007 Section 29: freeze validation_ready_checkpoints.json + pre_validation_access_audit.json
AFTER all six fits complete, BEFORE any official-VALIDATION access. Pure read/hash/verify --
no training, no inference, no waveform access.
"""

from __future__ import annotations

import json
import subprocess

import scripts._v2_007_lib as lib
from nhm.hashing import hash_file
from nhm.model_v2_official_validation_guard import read_guard_state

OUT_DIR = lib.ROOT / "reports/model_v2/v2_007"
RUNS_DIR = OUT_DIR / "runs"
METHOD_COMMIT = "ddf2f689e18501f00e6ee4258c0227c9bfb496be"

METHOD_FILES = [
    "configs/model_v2/official_validation_v1.yaml",
    "scripts/_v2_007_lib.py",
    "scripts/_v2_007_stats.py",
    "scripts/run_v2_007_fit.py",
    "scripts/run_all_v2_007_fits.py",
    "scripts/freeze_v2_007_method.py",
    "scripts/build_v2_007_validation_bootstrap_draws.py",
    "src/nhm/model_v2_cv_role_guard.py",
    "src/nhm/model_v2_official_validation_guard.py",
    "tests/test_v2_007_config.py",
]

ORDER = [
    ("MODEL_V2_TCN_MEAN", 20260927), ("MODEL_V2_TCN_MEAN", 20260928),
    ("MODEL_V2_TCN_MEAN", 20260929), ("MODEL_V2_TCN_MEANMAX", 20260927),
    ("MODEL_V2_TCN_MEANMAX", 20260928), ("MODEL_V2_TCN_MEANMAX", 20260929),
]


def _sh(*args: str) -> str:
    return subprocess.run(args, cwd=lib.ROOT, capture_output=True, text=True, check=False).stdout


def build_validation_ready_checkpoints() -> list[dict]:
    ledger_sha256 = hash_file(OUT_DIR / "cv_role_access_ledger.jsonl")
    _config, config_sha256 = lib.load_frozen_model_v1_config()
    rows = []
    for architecture_id, seed in ORDER:
        exp_id = lib.experiment_id(architecture_id, seed)
        schedule_id = next(
            f["schedule_id"] for f in lib.FINALISTS if f["architecture_id"] == architecture_id
        )
        summary = json.loads(
            (RUNS_DIR / exp_id / "fit_summary.json").read_text(encoding="utf-8")
        )
        checkpoint_path = lib.ROOT / summary["checkpoint_path"]
        rows.append(
            {
                "configuration": exp_id,
                "architecture_id": architecture_id,
                "schedule_id": schedule_id,
                "seed": seed,
                "checkpoint_path": summary["checkpoint_path"],
                "checkpoint_sha256": hash_file(checkpoint_path),
                "selected_epoch": summary["selected_epoch"],
                "final_inner_validation_auprc": summary["best_final_inner_validation_auprc"],
                "training_curve_sha256": hash_file(RUNS_DIR / exp_id / "training_curve.csv"),
                "config_sha256": config_sha256,
                "role_ledger_sha256": ledger_sha256,
                "reload_consistency": summary["checkpoint_reload_consistency"],
            }
        )
    (OUT_DIR / "validation_ready_checkpoints.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return rows


def pre_validation_access_audit(checkpoints: list[dict]) -> dict:
    all_exist = all(
        (lib.ROOT / c["checkpoint_path"]).exists() for c in checkpoints
    )
    all_hashes_stable = all(
        hash_file(lib.ROOT / c["checkpoint_path"]) == c["checkpoint_sha256"] for c in checkpoints
    )
    all_reload_pass = all(c["reload_consistency"] == "PASS" for c in checkpoints)

    ledger_rows = [
        json.loads(line)
        for line in (OUT_DIR / "cv_role_access_ledger.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    official_validation_accesses = sum(1 for r in ledger_rows if r["role"] == "OFFICIAL_VALIDATION")
    all_selected_without_official_validation = official_validation_accesses == 0

    v1_pre = json.loads((OUT_DIR / "v1_reference_preflight.json").read_text(encoding="utf-8"))
    v1_ready = v1_pre["status"] == "PASS"

    draws_manifest = json.loads(
        (OUT_DIR / "validation_bootstrap_draws_manifest.json").read_text(encoding="utf-8")
    )
    draws_frozen = (
        hash_file(OUT_DIR / "validation_bootstrap_draws.npz")
        == draws_manifest["draws_npz_sha256"]
    )

    method_unchanged = []
    for rel in METHOD_FILES:
        committed = _sh("git", "show", f"{METHOD_COMMIT}:{rel}")
        current = (lib.ROOT / rel).read_text(encoding="utf-8")
        method_unchanged.append(committed == current)
    all_method_unchanged = all(method_unchanged)

    _config, current_config_sha = lib.load_frozen_model_v1_config()
    training_configs_unchanged = all(
        c["config_sha256"] == current_config_sha for c in checkpoints
    )

    guard_state = read_guard_state(lib.ROOT)
    guard_still_armed = guard_state is not None and guard_state["state"] == "ARMED"

    data = {
        "all_six_checkpoints_exist": all_exist,
        "all_six_hashes_stable": all_hashes_stable,
        "all_six_reload_pass": all_reload_pass,
        "all_six_selected_without_official_validation": all_selected_without_official_validation,
        "official_validation_access_count": official_validation_accesses,
        "cal_internal_external_access_count": 0,
        "v1_reference_checkpoints_ready": v1_ready,
        "bootstrap_draws_frozen": draws_frozen,
        "method_files_unchanged_since_method_commit": all_method_unchanged,
        "training_configs_unchanged": training_configs_unchanged,
        "guard_still_armed_not_yet_consumed": guard_still_armed,
        "status": "PASS" if (
            all_exist and all_hashes_stable and all_reload_pass
            and all_selected_without_official_validation and v1_ready and draws_frozen
            and all_method_unchanged and training_configs_unchanged and guard_still_armed
        ) else "FAIL",
    }
    (OUT_DIR / "pre_validation_access_audit.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def main() -> None:
    checkpoints = build_validation_ready_checkpoints()
    audit = pre_validation_access_audit(checkpoints)
    print(json.dumps(audit, indent=2))
    if audit["status"] != "PASS":
        raise RuntimeError("pre-validation access audit FAILED")


if __name__ == "__main__":
    main()
