from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from capstone_persistence.store import CapstoneSqliteStore
from studio.hardware_demo import (
    FEATURES,
    HardwareDemoService,
    _local_train,
    _model,
    _state,
    assign_labels_and_split,
    build_windows,
    canonical_digest,
)


def populated(tmp_path, *, owner: str = "user-a", seconds: int = 30):
    store = CapstoneSqliteStore(tmp_path / "product.sqlite3")
    with store._lock, store._connection:
        store._connection.execute("""CREATE TABLE hardware_sessions (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, collection TEXT NOT NULL,
            started_at TEXT NOT NULL, stopped_at TEXT, status TEXT NOT NULL,
            mark TEXT, last_received_at TEXT, record_count INTEGER NOT NULL DEFAULT 0)""")
        store._connection.execute("""CREATE TABLE hardware_trace (
            session_id TEXT NOT NULL, ordinal INTEGER NOT NULL, document_id TEXT NOT NULL,
            ingested_at TEXT NOT NULL, ecg INTEGER NOT NULL, bpm INTEGER, spo2 INTEGER,
            collection TEXT, PRIMARY KEY(session_id, document_id))""")
        start = datetime(2026, 10, 15, tzinfo=UTC)
        count = seconds * 20
        store._connection.execute(
            "INSERT INTO hardware_sessions VALUES (?,?,?,?,?,?,?,?,?)",
            ("HW-RECORDED-A", owner, "nhm_integration_test", start.isoformat(), (start + timedelta(seconds=seconds)).isoformat(), "STOPPED", None, None, count),
        )
        for i in range(count):
            stamp = start + timedelta(milliseconds=50 * i)
            store._connection.execute(
                "INSERT INTO hardware_trace VALUES (?,?,?,?,?,?,?,?)",
                ("HW-RECORDED-A", i + 1, f"doc-{i:05d}", stamp.isoformat(), 1800 + (i * 37) % 500, 70 + i % 7, 96 + i % 3, "nhm_integration_test"),
            )
    return store, HardwareDemoService(store, tmp_path / "runs")


def test_recorded_values_build_deterministic_features_and_ablation_changes_digest(tmp_path):
    store, service = populated(tmp_path)
    records = service._records("user-a", ["HW-RECORDED-A"])
    windows, excluded = build_windows(records)
    assert len(windows) == 30 and not excluded and len(windows[0]["features"]) == len(FEATURES)
    before = canonical_digest({w["window_id"]: w["features"] for w in windows})
    altered = [dict(row) for row in records]
    altered[0]["ecg"] += 500
    changed, _ = build_windows(altered)
    after = canonical_digest({w["window_id"]: w["features"] for w in changed})
    assert before != after and windows[0]["features"] != changed[0]["features"]
    train_a, hold_a = assign_labels_and_split(windows, 77)
    train_again, hold_again = assign_labels_and_split(windows, 77)
    train_b, hold_b = assign_labels_and_split(windows, 78)
    labels_for = lambda rows: {w["window_id"]: w["label"] for w in rows}
    assert labels_for(train_a + hold_a) == labels_for(train_again + hold_again)
    assert labels_for(train_a + hold_a) != labels_for(train_b + hold_b)
    # The changed recorded value reaches the loss/gradient computation, not only metadata.
    state = _state(_model(91))
    x_before = np.asarray([windows[0]["features"], windows[1]["features"]], dtype=np.float32)
    x_after = np.asarray([changed[0]["features"], changed[1]["features"]], dtype=np.float32)
    labels = np.asarray([0, 1], dtype=np.int64)
    trained_before, diag_before = _local_train(state, x_before, labels, algorithm="FEDAVG", seed=12)
    trained_after, diag_after = _local_train(state, x_after, labels, algorithm="FEDAVG", seed=12)
    assert diag_before["final_loss"] != diag_after["final_loss"]
    assert any(not np.array_equal(trained_before[key], trained_after[key]) for key in trained_before)
    store.close()


def test_mu_zero_is_exactly_equivalent_to_fedavg_and_nonzero_records_penalty():
    state = _state(_model(44))
    x = np.linspace(-1, 1, 4 * len(FEATURES), dtype=np.float32).reshape(4, len(FEATURES))
    y = np.asarray([0, 1, 0, 1], dtype=np.int64)
    avg, avg_diag = _local_train(state, x, y, algorithm="FEDAVG", seed=9)
    zero, zero_diag = _local_train(state, x, y, algorithm="FEDPROX", seed=9, mu=0.0)
    prox, prox_diag = _local_train(state, x, y, algorithm="FEDPROX", seed=9, mu=0.1)
    assert all(np.array_equal(avg[key], zero[key]) for key in avg)
    assert avg_diag["final_loss"] == zero_diag["final_loss"]
    assert prox_diag["final_proximal_penalty"] > 0
    assert all(np.isfinite(value).all() for value in prox.values())


@pytest.mark.parametrize("algorithm", ["FEDAVG", "FEDPROX"])
def test_genuine_three_round_training_uses_eight_clients_and_persists_provenance(tmp_path, algorithm):
    store, service = populated(tmp_path)
    result = service.run("user-a", session_ids=["HW-RECORDED-A"], rounds=3, algorithm=algorithm, secagg_mode="PLAIN", label_seed=77)
    assert result["status"] == "COMPLETED" and len(result["rounds"]) == 3
    assert result["dataset"]["training_windows"] + result["dataset"]["holdout_windows"] == 30
    assert len(result["dataset"]["clients"]) == 8
    assigned = [window_id for client in result["dataset"]["clients"].values() for window_id in client["window_ids"]]
    assert len(assigned) == len(set(assigned)) == result["dataset"]["training_windows"]
    assert all(row["accepted_updates"] == 8 and row["optimizer_steps"] == 16 for row in result["rounds"])
    assert len(set(result["state_progression"].values())) == 4
    assert result["dataset"]["label_assignment"]["status"] == "SYNTHETIC_ASSIGNED_FOR_DEMO"
    assert service.get("user-a", result["run_id"])["snapshot_sha256"] == result["snapshot_sha256"]
    with pytest.raises(PermissionError):
        service.get("user-b", result["run_id"])
    store.close()


def test_round_one_secagg_shadow_executes_actual_protected_comparison(tmp_path):
    pytest.importorskip("flwr")
    store, service = populated(tmp_path)
    result = service.run("user-a", session_ids=["HW-RECORDED-A"], rounds=3, algorithm="FEDPROX", secagg_mode="SECAGG_SHADOW", label_seed=88)
    shadow = result["secagg_shadow"]
    assert shadow["status"] == "PASS" and shadow["round"] == 1
    assert shadow["plain_clear_update_count"] == 8
    assert shadow["protected_clear_update_count"] == 0
    assert shadow["authoritative_aggregation"] == "PLAIN"
    store.close()


def test_active_foreign_and_too_short_sessions_fail_closed(tmp_path):
    store, service = populated(tmp_path, seconds=10)
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA"):
        service.run("user-a", session_ids=["HW-RECORDED-A"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=1)
    with pytest.raises(PermissionError):
        service.run("user-b", session_ids=["HW-RECORDED-A"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=1)
    store.close()
