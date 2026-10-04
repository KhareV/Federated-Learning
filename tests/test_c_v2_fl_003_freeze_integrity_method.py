"""C-V2-FL-003-FREEZE-INTEGRITY method tests (provenance only): frozen finalizer restored
byte-identically, no self-exemption anywhere, successor differs only in the lazy communication
helper, V2-FL-003 method freeze byte-clean."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
FROZEN = "scripts/finalize_v2_fl_003_evidence.py"
SUCCESSOR = "scripts/finalize_v2_fl_003_evidence_v2.py"
FROZEN_SHA = "21c640c209577c999d17a30b961d0f74ef1d12e09a2f187e7e1ac30d1bf5ea75"
METHOD_COMMIT = "dd9d9df2303260d3b540c35fb382bb86212b96ef"


def _functions(path: str) -> dict[str, str]:
    tree = ast.parse((ROOT / path).read_text())
    return {n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}


def test_historical_finalizer_restored_byte_identically_to_the_method_commit() -> None:
    assert hash_file(ROOT / FROZEN) == FROZEN_SHA
    blob = subprocess.run(["git", "show", f"{METHOD_COMMIT}:{FROZEN}"], cwd=ROOT,
                          capture_output=True, check=True).stdout
    assert blob == (ROOT / FROZEN).read_bytes()
    freeze = json.loads((ROOT / "reports/model_v2/v2_fl_003/method_freeze.json").read_text())
    assert freeze["method_file_sha256"][FROZEN] == FROZEN_SHA


def test_no_self_exemption_logic_in_either_finalizer() -> None:
    for path in (FROZEN, SUCCESSOR):
        text = (ROOT / path).read_text()
        assert "AMENDMENT_ALLOWED" not in text and "unexpected" not in text, path


def test_v2_fl_003_method_freeze_is_byte_clean() -> None:
    freeze = json.loads((ROOT / "reports/model_v2/v2_fl_003/method_freeze.json").read_text())
    drift = [p for p, h in freeze["method_file_sha256"].items() if hash_file(ROOT / p) != h]
    assert len(freeze["method_file_sha256"]) == 36 and drift == []


def test_successor_changes_only_the_communication_extraction() -> None:
    frozen, successor = _functions(FROZEN), _functions(SUCCESSOR)
    for name in ("_patient_stats", "_runtime", "fedavg_paths", "selected_mu", "bootstrap",
                 "_csv", "_sh"):
        assert frozen[name] == successor[name], name  # scientific/evidence logic identical
    assert "_logical_bytes" in successor and "_logical_bytes" not in frozen
    text = (ROOT / SUCCESSOR).read_text()
    for forbidden in ("train_local", "run_fedprox", "torch", "AdamW", "restore_state"):
        assert forbidden not in text
    assert "SCIENTIFIC METHOD UNCHANGED" in text and "EVIDENCE-FINALIZATION CORRECTION ONLY" in text


def test_logical_bytes_helper_is_lazy_and_schema_aware() -> None:
    import scripts.finalize_v2_fl_003_evidence_v2 as successor

    assert successor._logical_bytes({"total_logical_payload_bytes": 7}) == 7
    assert successor._logical_bytes({"total_server_to_client_bytes": 3,
                                     "total_client_to_server_bytes": 4}) == 7
    # the historical eager default would have raised KeyError here:
    assert successor._logical_bytes({"total_logical_payload_bytes": 5,
                                     "unrelated": 1}) == 5
    with pytest.raises(KeyError):
        successor._logical_bytes({})


def test_corrective_method_binds_all_scientific_inputs() -> None:
    meta = json.loads((ROOT / "reports/model_v2/c_v2_fl_003_freeze_integrity/"
                       "correction_method.json").read_text())
    inputs = meta["inputs"]
    assert len(inputs["checkpoints"]) == 14 and len(inputs["result_json"]) == 7
    assert len(inputs["validation_prediction_tables"]) == 7 and len(inputs["round_logs"]) == 7
    for table in ("checkpoints", "result_json", "validation_prediction_tables", "round_logs"):
        for path, digest in inputs[table].items():
            assert hash_file(ROOT / path) == digest, path
    assert meta["historical_frozen_finalizer"]["restored_byte_identically"] is True
    assert meta["successor_finalizer"]["sha256"] == hash_file(ROOT / SUCCESSOR)
    assert meta["entry_sha"] == "87943640b86fcca2dd769690e5df2706c2f2a793"
