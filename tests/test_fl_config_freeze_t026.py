from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def test_f12_lock_binds_all_manifests_and_protocol() -> None:
    lock = json.loads((ROOT / "artifacts/FL_CONFIG_V1.lock.json").read_text())
    assert lock["status"] == "FROZEN"
    assert lock["frozen_before_T026_outcomes"] is True
    mapping = {
        "CLIENTS_IID_V1": "CLIENTS_IID_V1.csv",
        "NONIID_LABEL_V1": "NONIID_LABEL_V1.csv",
        "NONIID_QUANTITY_V1": "NONIID_QUANTITY_V1.csv",
        "NONIID_FEATURE_V1": "NONIID_FEATURE_V1.csv",
        "NONIID_COMBINED_V1": "NONIID_COMBINED_V1.csv",
    }
    for key, filename in mapping.items():
        assert lock["hashes"][key] == hash_file(ROOT / "manifests/clients" / filename)
    assert lock["shuffle_seed_namespace"] == "FL_IID_V1"
    assert lock["round_budget"] == {
        "clients": 8,
        "clients_per_round": 8,
        "rounds": 50,
        "local_epochs": 1,
        "batch_size": 64,
    }


def test_t025_artifacts_remain_exact() -> None:
    expected = {
        "configs/fl_iid_v1.yaml": (
            "529a43dab43b36c57ed65e2ba769d10eafefa79f21689fb3339dbe4d67e1cf89"
        ),
        "manifests/clients/CLIENTS_IID_V1.csv": (
            "80f38fa25c508f9b4e2a4fd49e29c4c8d0034443ec67f7c24bc0954912b6c32a"
        ),
        "reports/t025/fl_iid_rounds.csv": (
            "fde13b3aa5a54b4a7dffe6d0ca3bac85cf9fb07175b117beaa685268ced77e0d"
        ),
        "checkpoints/federated/FL_IID_V1_best.pt": (
            "7a2a7fc6bad6d713784cef114006b0e6d5a56e211ebc7d4e4a94fecdf3c85d10"
        ),
    }
    assert all(hash_file(ROOT / path) == digest for path, digest in expected.items())
