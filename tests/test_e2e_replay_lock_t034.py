"""T034 E2E_REPLAY_SOFTWARE_V1 lock: creation is reproducible, verification passes against
current repo state, tampering with any bound file is detected, and the selection ordering
rules (Section 45/46) reject reversed windows, duplicated timestamps, and missing windows."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from scripts.select_replay_windows_t034 import select, validate_selection
from scripts.verify_e2e_replay_t034 import verify

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1.lock.json"


def test_lock_file_exists_with_correct_status() -> None:
    assert LOCK_PATH.exists(), "run scripts/freeze_e2e_replay_t034.py"
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["lock_id"] == "E2E_REPLAY_SOFTWARE_V1"
    assert lock["status"] == "FROZEN_ENGINEERING_INTEGRATION"


def test_lock_never_claims_final_g21_closure() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["is_final_g21_lock"] is False
    assert lock["g21_status"] == "NON_PASS_PENDING_T030_REAL_WEARABLE"


def test_verify_passes_against_current_repository_state() -> None:
    result = verify()
    assert result["status"] == "PASS"
    assert result["bound_artifacts"] > 0


def test_verify_detects_tamper_on_any_bound_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    shadow_root = tmp_path / "repo"
    (shadow_root / "artifacts").mkdir(parents=True)
    (shadow_root / "artifacts/E2E_REPLAY_SOFTWARE_V1.lock.json").write_text(
        LOCK_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    for relative_path in lock["bound_artifacts"]:
        destination = shadow_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative_path, destination)
    for extra in (
        "artifacts/API_RUNTIME_V1.lock.json",
        "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
        "artifacts/DASHBOARD_UI_V1.lock.json",
    ):
        destination = shadow_root / extra
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / extra, destination)

    monkeypatch.setattr("scripts.verify_e2e_replay_t034.ROOT", shadow_root)

    tampered = shadow_root / "scripts/run_replay.py"
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="E2E_REPLAY_SOFTWARE_V1_TAMPER"):
        verify()


def _real_selection() -> dict:
    return select()


def test_validate_selection_passes_on_the_real_frozen_selection() -> None:
    validate_selection(_real_selection())


def test_validate_selection_rejects_reversed_windows() -> None:
    selection = _real_selection()
    windows = selection["windows"]
    windows[0], windows[1] = windows[1], windows[0]
    windows[0]["sequence_index"], windows[1]["sequence_index"] = (
        windows[1]["sequence_index"],
        windows[0]["sequence_index"],
    )
    with pytest.raises(RuntimeError, match="PUBLIC_ECG_REPLAY_V1_TIMESTAMPS_NOT_MONOTONIC"):
        validate_selection(selection)


def test_validate_selection_rejects_a_duplicated_timestamp() -> None:
    selection = _real_selection()
    selection["windows"][1]["prediction_timestamp_us"] = selection["windows"][0][
        "prediction_timestamp_us"
    ]
    with pytest.raises(RuntimeError, match="PUBLIC_ECG_REPLAY_V1_DUPLICATE_TIMESTAMP"):
        validate_selection(selection)


def test_validate_selection_rejects_a_missing_window() -> None:
    selection = _real_selection()
    selection["windows"] = selection["windows"][:-1]
    with pytest.raises(RuntimeError, match="PUBLIC_ECG_REPLAY_V1_WINDOW_COUNT_MISMATCH"):
        validate_selection(selection)


def test_validate_selection_rejects_a_broken_cadence() -> None:
    selection = _real_selection()
    selection["windows"][5]["prediction_timestamp_us"] += 1_000_000
    with pytest.raises(RuntimeError, match="PUBLIC_ECG_REPLAY_V1_CADENCE_VIOLATION"):
        validate_selection(selection)


def test_validate_selection_rejects_a_duplicate_window_id() -> None:
    selection = _real_selection()
    selection["windows"][3]["example_id"] = selection["windows"][2]["example_id"]
    with pytest.raises(RuntimeError, match="PUBLIC_ECG_REPLAY_V1_DUPLICATE_WINDOW_ID"):
        validate_selection(selection)


def test_frozen_selection_report_matches_a_fresh_recomputation() -> None:
    """The selection rule must be frozen/reproducible: a fresh run of select() reproduces the
    exact committed reports/t034/replay_selection.json."""
    committed = json.loads(
        (ROOT / "reports/t034/replay_selection.json").read_text(encoding="utf-8")
    )
    fresh = select()
    assert copy.deepcopy(committed) == fresh
