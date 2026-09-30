from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.verify_t025 import verify

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_iid_result_verifies() -> None:
    assert verify()["status"] == "PASS"


def test_round_and_client_logs_are_complete_and_exact() -> None:
    with (ROOT / "reports/t025/fl_iid_rounds.csv").open(newline="") as handle:
        rounds = list(csv.DictReader(handle))
    with (ROOT / "reports/t025/fl_iid_client_rounds.csv").open(newline="") as handle:
        clients = list(csv.DictReader(handle))
    assert [int(row["round"]) for row in rounds] == list(range(51))
    assert len(clients) == 400
    assert all(
        int(row["num_examples"])
        == int(row["positive_examples"]) + int(row["negative_examples"])
        for row in clients
    )
    assert all(int(row["local_epoch"]) == 1 for row in clients)
    assert all(row["optimizer"] == "AdamW" for row in clients)


def test_scope_and_canonical_f12_status() -> None:
    scope = json.loads((ROOT / "reports/t025/scope_audit.json").read_text())
    assert scope["TRAIN_access"] is True and scope["VALIDATION_access"] is True
    for key in (
        "CALIBRATION_access",
        "INTERNAL_TEST_access",
        "INCART_access",
        "NSTDB_access",
        "BIDMC_access",
        "WEARABLE_V1_access",
        "FedProx",
        "SecAgg_plus",
        "differential_privacy",
        "non_IID",
        "hardware",
        "CAL_V1_transferred",
        "central_checkpoint_warm_start",
    ):
        assert scope[key] is False
    lock = json.loads((ROOT / "artifacts/FL_IID_V1.lock.json").read_text())
    assert lock["canonical_F12_status"] == "NOT_FROZEN"
