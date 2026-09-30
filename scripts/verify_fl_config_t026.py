"""Verify the frozen F12/FL_CONFIG_V1 family."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from nhm.hashing import hash_file  # noqa: E402


def verify(root: Path = ROOT, lock_path: Path | None = None) -> dict[str, object]:
    path = lock_path or root / "artifacts/FL_CONFIG_V1.lock.json"
    lock = json.loads(path.read_text())
    paths = {
        "CLIENTS_IID_V1": "manifests/clients/CLIENTS_IID_V1.csv",
        "NONIID_LABEL_V1": "manifests/clients/NONIID_LABEL_V1.csv",
        "NONIID_QUANTITY_V1": "manifests/clients/NONIID_QUANTITY_V1.csv",
        "NONIID_FEATURE_V1": "manifests/clients/NONIID_FEATURE_V1.csv",
        "NONIID_COMBINED_V1": "manifests/clients/NONIID_COMBINED_V1.csv",
        "fl_iid_v1": "configs/fl_iid_v1.yaml",
        "fl_non_iid_v1": "configs/fl_non_iid_v1.yaml",
        "fl_feature_noise_v1": "configs/fl_feature_noise_v1.yaml",
        "FL_INIT_V1": "configs/fl_init_v1.yaml",
        "PREPROC_V1_lock": "manifests/preprocessing/PREPROC_V1.lock.json",
        "split": "manifests/splits/MITDB_SPLIT_V1.csv",
        "window_manifest": "manifests/windows/MITDB_WINDOWS_V1.csv",
        "aggregation": "federated/aggregation.py",
        "transport": "configs/fl_state_transport_v1.yaml",
        "non_iid_manifest_source": "federated/non_iid_manifest.py",
        "feature_noise_source": "federated/feature_noise.py",
        "non_iid_runner": "federated/non_iid_runner.py",
    }
    mismatches = [
        key
        for key, relative in paths.items()
        if lock["hashes"].get(key) != hash_file(root / relative)
    ]
    with (root / "manifests/freeze_registry_v1.csv").open(newline="") as handle:
        freezes = {row["freeze_id"]: row for row in csv.DictReader(handle)}
    if mismatches or lock["status"] != "FROZEN" or freezes["F12"]["current_status"] != "FROZEN":
        raise RuntimeError(f"FL_CONFIG_V1_VERIFY_FAILURE: mismatches={mismatches}")
    return {
        "status": "PASS",
        "freeze_id": "F12",
        "version_id": "FL_CONFIG_V1",
        "bound_artifacts": len(paths),
        "mismatches": [],
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
