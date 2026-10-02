"""C-V2-003-PROVENANCE tests: confirms the frozen V2-003 scientific artifacts are unchanged,
the method-freeze commit is a real ancestor of the result commit, and the registry CSVs still
parse correctly despite their CRLF convention. Read-only -- no model fit, no recomputation.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
METHOD_FREEZE_SHA = "d07a561c92d9a5e5401b074e682784fe727075d4"
RESULT_SHA = "52013e3dae2bc763cf9462f252d2b91598403e7c"


def test_method_freeze_is_ancestor_of_result() -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", METHOD_FREEZE_SHA, RESULT_SHA],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0


def test_feature_audit_lock_unchanged() -> None:
    lock_path = ROOT / "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json"
    expected = "a6876430dcad040b7008a69200fb4a36d735ad9a58d834c46d66d5543609623b"
    assert hash_file(lock_path) == expected


def test_best_reduced_rf_unchanged() -> None:
    lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json").read_text()
    )
    assert lock["best_reduced_rf"]["selected_variant"] == "RR"
    assert lock["best_reduced_rf"]["AUPRC"] == 0.713140103147974


def test_minimal_adequate_subset_unchanged() -> None:
    lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json").read_text()
    )
    assert lock["minimal_adequate_feature_subset"]["selected_variant"] == "RR"
    assert lock["minimal_adequate_feature_subset"]["selected_feature_count"] == 9


def test_baseline_v1_lock_unchanged() -> None:
    lock_path = ROOT / "manifests/baselines/BASELINE_V1.lock.json"
    expected = "38f94cb210fe8872f5a195dee606740bf0d6ae3a93be576c88eb60a88f2021c5"
    assert hash_file(lock_path) == expected


def test_model_v1_cv_reference_lock_unchanged() -> None:
    lock_path = ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"
    expected = "87dc828fcc0c9a6747ca1b228e027d8303542c8fc23981056a4cf5808a3e4139"
    assert hash_file(lock_path) == expected


def test_oof_predictions_unchanged() -> None:
    oof_path = ROOT / "reports/model_v2/v2_003/oof_predictions.csv"
    recorded = json.loads((ROOT / "reports/model_v2/v2_003/artifact_hashes.json").read_text())
    key = "reports/model_v2/v2_003/oof_predictions.csv"
    assert hash_file(oof_path) == recorded["artifacts"][key]


def test_registries_still_parse_despite_crlf_convention() -> None:
    import csv

    for path in [
        ROOT / "manifests/model_v2/task_registry_v1.csv",
        ROOT / "manifests/model_v2/gate_registry_v1.csv",
        ROOT / "manifests/model_v2/component_registry_v1.csv",
    ]:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        header_len = len(rows[0])
        assert all(len(row) == header_len for row in rows[1:])


def test_v2_003_and_v2g2_still_pass() -> None:
    import csv

    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row["status"] for row in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}
    assert tasks["V2-003"] == "PASS"
    assert gates["V2G2"] == "PASS"
    assert tasks["V2-004"] == "NOT_STARTED"
