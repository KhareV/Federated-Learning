from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.verify_t027 import verify

ROOT = Path(__file__).resolve().parents[1]


def test_t027_verifier() -> None:
    assert verify()["status"] == "PASS"


def test_all_candidates_and_conditions_complete() -> None:
    for stem in ("mu_0p001", "mu_0p01", "mu_0p1"):
        rows = list(csv.DictReader((ROOT / f"reports/t027/candidates/{stem}_rounds.csv").open()))
        clients = list(
            csv.DictReader((ROOT / f"reports/t027/candidates/{stem}_client_rounds.csv").open())
        )
        assert len(rows) == 51
        assert len(clients) == 400
    report = json.loads((ROOT / "reports/fedprox.json").read_text())
    assert [row["condition"] for row in report["comparisons"]] == [
        "IID",
        "LABEL",
        "QUANTITY",
        "FEATURE",
        "COMBINED",
    ]
    assert all(row["selected_mu"] == 0.01 for row in report["comparisons"])


def test_scope_and_matching() -> None:
    scope = json.loads((ROOT / "reports/t027/scope_audit.json").read_text())
    assert scope["TRAIN_access"] is True and scope["VALIDATION_access"] is True
    for key in (
        "CALIBRATION_access",
        "INTERNAL_TEST_access",
        "CAL_V1_applied",
        "SecAgg_plus",
        "differential_privacy",
        "hardware",
    ):
        assert scope[key] is False
    matched = json.loads((ROOT / "reports/t027/matched_variable_audit.json").read_text())
    assert all(
        all(value is True for value in audit.values()) for audit in matched["conditions"].values()
    )


def test_mu_lock_and_replay() -> None:
    lock = json.loads((ROOT / "artifacts/FEDPROX_MU_V1.lock.json").read_text())
    assert lock["selected_mu"] == 0.01
    assert lock["selected_before_cross_condition_runs"] is True
    replay = json.loads((ROOT / "reports/t027/reproducibility.json").read_text())
    assert replay["selected_mu_identical"] is True
    assert all(row["status"] == "PASS" for row in replay["round1_replay"].values())
    assert all(row["status"] == "PASS" for row in replay["checkpoint_prediction_replay"].values())
