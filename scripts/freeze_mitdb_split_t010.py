#!/usr/bin/env python3
"""T010: create the MITDB_SPLIT_V1 freeze lock (F05) after the independent audit passes.

Requires reports/splits/split_audit.json and reports/splits/window_audit.json to already be
PASS (scripts/audit_split_leakage_t010.py and scripts/run_window_leakage_harness_t010.py).
Never re-derives or repairs the split -- only binds it, by hash, to T006 eligibility, the
frozen AAMI_SVF_MAP_V1 mapper, and the T009 split configuration. After writing the lock, it
calls evaluation.leakage_audit.verify_frozen_split to confirm the lock is self-consistent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasets.labels import MAP_ID as LABEL_MAP_ID  # noqa: E402
from datasets.mitdb import LEAD_POLICY_ID  # noqa: E402
from evaluation.leakage_audit import verify_frozen_split  # noqa: E402
from nhm.coverage import read_csv  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402

SPLIT_DIR = ROOT / "manifests/splits"
LOCK_PATH = SPLIT_DIR / "MITDB_SPLIT_V1.lock.json"
SPLIT_CSV = SPLIT_DIR / "MITDB_SPLIT_V1.csv"


def main() -> None:
    split_audit_path = ROOT / "reports/splits/split_audit.json"
    split_audit = json.loads(split_audit_path.read_text(encoding="utf-8"))
    if split_audit["overall_status"] != "PASS":
        raise RuntimeError(
            f"cannot freeze: split_audit.json overall_status={split_audit['overall_status']}"
        )
    if not split_audit["candidate_unchanged"]:
        raise RuntimeError("cannot freeze: candidate split hash changed during audit")

    window_audit_path = ROOT / "reports/splits/window_audit.json"
    window_audit = json.loads(window_audit_path.read_text(encoding="utf-8"))
    if window_audit["overall_status"] != "PASS":
        raise RuntimeError(
            f"cannot freeze: window_audit.json overall_status={window_audit['overall_status']}"
        )

    hash_before = hash_file(SPLIT_CSV)

    split_rows = read_csv(SPLIT_CSV)
    eligible_group_ids = {row["participant_group_id"] for row in split_rows}

    lock = {
        "freeze_id": "F05",
        "split_id": split_audit["split_id"],
        "status": "FROZEN",
        "split_sha256": hash_file(SPLIT_CSV),
        "split_yaml_sha256": hash_file(SPLIT_DIR / "MITDB_SPLIT_V1.yaml"),
        "groups_sha256": hash_file(SPLIT_DIR / "mitdb_groups.csv"),
        "strata_sha256": hash_file(SPLIT_DIR / "mitdb_patient_strata.csv"),
        "partition_roles_sha256": hash_file(SPLIT_DIR / "partition_roles_v1.yaml"),
        "label_map_id": LABEL_MAP_ID,
        "label_map_sha256": hash_file(ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml"),
        "lead_policy_id": LEAD_POLICY_ID,
        "eligible_manifest_sha256": hash_file(ROOT / "manifests/datasets/mitdb_mlii_records.csv"),
        "split_seed": 20260927,
        "patient_group_count": len(eligible_group_ids),
        "record_count": len(split_rows),
        "frozen_by_task": "T010",
        "audit_report_path": "reports/splits/split_audit.json",
        "window_harness_report_path": "reports/splits/window_audit.json",
        "post_freeze_change_rule": (
            "Any change to MITDB_SPLIT_V1.csv, participant grouping, partition assignment, "
            "split seed, or split algorithm after this freeze is a controlled scientific "
            "change (Class C, docs/CHANGE_CONTROL.md), not an ordinary refactor. It "
            "invalidates every dependent preprocessing cache, baseline, MODEL_V1 run, "
            "calibration, internal evaluation, and FL client manifest that exists at that "
            "point, and requires returning to T009 before any downstream model work resumes."
        ),
    }

    temporary = LOCK_PATH.with_suffix(f"{LOCK_PATH.suffix}.tmp")
    temporary.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(LOCK_PATH)

    hash_after = hash_file(SPLIT_CSV)
    if hash_before != hash_after:
        raise RuntimeError(
            f"SPLIT_HASH_MISMATCH: candidate changed while writing the lock "
            f"({hash_before} -> {hash_after})"
        )

    verification = verify_frozen_split(ROOT, LOCK_PATH)
    if verification["status"] != "PASS":
        raise RuntimeError(f"freeze lock failed self-verification: {verification}")

    print(f"T010 freeze lock: {lock['status']} (verified: {verification['status']})")


if __name__ == "__main__":
    main()
