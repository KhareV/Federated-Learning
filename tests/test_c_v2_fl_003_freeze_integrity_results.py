"""C-V2-FL-003-FREEZE-INTEGRITY result tests: scientific outputs unchanged, independent
reconstruction identical, mu=0 re-verified, lifecycle-test drift control-only, V2-FL-002 pin scope,
fresh-process replays, byte-clean method freeze and the corrective attestation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/c_v2_fl_003_freeze_integrity"
FROZEN_SHA = "21c640c209577c999d17a30b961d0f74ef1d12e09a2f187e7e1ac30d1bf5ea75"


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def test_scientific_outputs_and_mu_are_unchanged() -> None:
    data = _j("scientific_freeze_verification.json")
    assert data["status"] == "PASS" and data["drifted_files"] == []
    assert data["FEDPROX_MU_V2_selected_mu"] == 0.1


def test_independent_reconstruction_reproduces_every_reported_artifact() -> None:
    data = _j("reconstruction/reconstruction_equality.json")
    assert data["status"] == "PASS" and data["all_identical"] is True
    assert set(data["files"]) == {
        "fedavg_vs_fedprox_comparison.json", "patient_level_comparison.json",
        "paired_bootstrap.json", "accounting_audit.json", "communication_compute.json",
        "heldout_firewall_audit.json", "chronology_audit.json", "selection_audit.json"}
    assert all(f["identical"] for f in data["files"].values())
    assert data["scientific_method_changed"] is False and data["training_changed"] is False
    selection = json.loads((ROOT / "reports/model_v2/v2_fl_003/selection/selection.json"
                            ).read_text())
    assert selection["ranking"] == [0.1, 0.001, 0.01] and selection["selected_mu"] == 0.1
    accounting = _j("reconstruction/accounting_audit.json")
    assert accounting["total_positive_mu_updates"] == 2800
    assert _j("reconstruction/heldout_firewall_audit.json")["INTERNAL_TEST_accessed"] is False


def test_mu_zero_reverified_exactly() -> None:
    data = _j("mu0_reverification.json")
    assert data["loss_delta"] == 0.0 and data["max_abs_gradient_delta"] == 0.0
    assert data["all_8_local_update_max_delta"] == 0.0 and data["exact_match"] is True
    assert data["aggregate_sha256"] == (
        "3f57e799f19a252a957061df7a5c36ee2002085e33569f370133ce09b170e71b")
    # the historical mu=0 evidence file was NOT overwritten
    assert json.loads((ROOT / "reports/model_v2/v2_fl_003/mu0_equivalence.json").read_text()
                      )["status"] == "PASS"


def test_lifecycle_test_drift_is_control_only_for_all_four_files() -> None:
    data = _j("lifecycle_test_drift_audit.json")
    assert data["status"] == "PASS" and data["blockers"] == []
    assert set(data["files"]) == {
        "tests/test_model_v2_control_plane.py", "tests/test_v2_fl_001_results.py",
        "tests/test_v2_fl_002_method.py", "tests/test_v2_fl_002_results.py"}
    assert data["changed_historical_test_files"] == 4
    for entry in data["files"].values():
        assert entry["classification"] == "FORWARD_LIFECYCLE_ONLY"
        assert entry["old_sha256"] != entry["entry_sha256"]
        assert entry["weakens_hashes_or_scientific_configuration_or_firewall_or_integrity"] is False


def test_v2_fl_002_pin_scope_only_the_audited_lifecycle_test_drifted() -> None:
    data = _j("historical_freeze_scope_audit.json")
    assert data["status"] == "PASS" and data["historical_freezes_rewritten"] is False
    v2 = data["audits"]["V2-FL-002"]
    assert v2["A_SCIENTIFIC_METHOD_FILES_drifted"] == []
    assert v2["B_LIFECYCLE_STATUS_ASSERTION_FILES_drifted"] == ["tests/test_v2_fl_002_method.py"]
    assert data["audits"]["V2-FL-001"]["drifted_files"] == []
    assert data["audits"]["V2-FL-003"]["drifted_files"] == []


def test_method_freeze_reconciliation_is_byte_clean_and_history_is_preserved() -> None:
    data = _j("method_freeze_reconciliation.json")
    assert data["final_method_freeze_status"] == "BYTE-CLEAN" and data["status"] == "PASS"
    assert data["historical_finalizer_sha256_now"] == FROZEN_SHA == hash_file(
        ROOT / "scripts/finalize_v2_fl_003_evidence.py")
    assert data["post_freeze_changed_method_files_originally_observed"] == [
        "scripts/finalize_v2_fl_003_evidence.py"]
    assert data["unexpected_changed_method_files_after_correction"] == []
    for key in ("scientific_method_impact", "training_impact", "selection_impact",
                "metrics_impact"):
        assert data[key] == "NONE"
    # the historical audit/criteria files are preserved unaltered (they still say what they said)
    historical = json.loads((ROOT / "reports/model_v2/v2_fl_003/method_immutability_audit.json"
                             ).read_text())
    assert "disclosed_amendment" in historical and historical["status"] == "PASS"


@pytest.mark.parametrize("n", [1, 2])
def test_fresh_process_replays_reproduce_all_seven_runs(n: int) -> None:
    data = json.loads((OUT / f"replay/replay_verification_c_run_{n}.json").read_text())
    assert data["status"] == "PASS" and len(data["runs"]) == 7
    assert data["selection_matches_lock"] and data["mu0_repeat_in_fresh_process"]["exact_match"]
    assert all(r["round_1_identical"] and r["validation_predictions_replayed_identically"]
               and r["best_checkpoint_sha_matches"] for r in data["runs"])


def test_corrective_attestation_and_firewall() -> None:
    path = OUT / "v2flg2_corrective_attestation.json"
    if not path.exists():  # transient: the attestation is written after the regression runs
        pytest.skip("attestation not yet written")
    data = json.loads(path.read_text())
    assert data["status"] == "PASS" and data["V2FLG2_remains"] == "PASS"
    assert all(v is True for v in data["criteria"].values())
    assert data["historical_v2flg2_criteria_preserved_unaltered"] is True
    assert not {"INTERNAL_TEST", "CALIBRATION", "INCART", "BIDMC"} & set(
        data["ledger_partitions_for_stage_V2_FL_003"])
    historical = json.loads((ROOT / "reports/model_v2/v2_fl_003/v2flg2_criteria.json"
                             ).read_text())
    assert historical["status"] == "PASS"
