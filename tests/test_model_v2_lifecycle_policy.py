"""Enforcement of MODEL_V2_LIFECYCLE_TEST_POLICY_V1: one mutable current-lifecycle test, no future
NOT_STARTED hard-codes in historical tests, no broad exemption of scientific files."""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "configs/model_v2/lifecycle_test_policy_v1.yaml").read_text())
CURRENT = POLICY["current_lifecycle_test"]
LIVE_NOT_STARTED = re.compile(
    r'(tasks|gates|rows|row)\[[^\]]*\](\["status"\])?\s*==\s*"NOT_STARTED"|'
    r'row\["status"\]\s*==\s*"NOT_STARTED"')


def _v2_tests() -> list[str]:
    paths: set[str] = set()
    for pattern in POLICY["v2_lineage_test_globs"]:
        paths |= {str(Path(p).relative_to(ROOT)) for p in glob.glob(str(ROOT / pattern))}
    return sorted(paths)


def test_policy_identity_and_single_mutable_lifecycle_test() -> None:
    assert POLICY["policy_id"] == "MODEL_V2_LIFECYCLE_TEST_POLICY_V1"
    assert CURRENT == "tests/test_model_v2_current_lifecycle.py" and (ROOT / CURRENT).exists()
    assert CURRENT in POLICY["classified_lifecycle_control_files"]
    assert set(POLICY["rules"]) == {"A", "B", "C", "D", "E", "F"}


def test_historical_v2_tests_do_not_hard_code_future_not_started() -> None:
    offenders = {}
    for path in _v2_tests():
        if path == CURRENT or path.endswith("test_model_v2_lifecycle_policy.py"):
            continue
        hits = [n for n, line in enumerate((ROOT / path).read_text().splitlines(), start=1)
                if LIVE_NOT_STARTED.search(line) and not line.lstrip().startswith("#")]
        if hits:
            offenders[path] = hits
    assert offenders == {}, offenders


def test_current_lifecycle_test_is_exact_not_broad() -> None:
    text = (ROOT / CURRENT).read_text()
    assert "EXPECTED_TASKS" in text and "EXPECTED_GATES" in text
    assert "assert actual == EXPECTED_TASKS" in text and "assert actual == EXPECTED_GATES" in text
    assert 'in {"NOT_STARTED"' not in text and 'in {"PASS"' not in text


def test_no_scientific_method_freeze_binds_the_mutable_lifecycle_test() -> None:
    for freeze in glob.glob(str(ROOT / "reports/model_v2/v2_fl_00[4-9]*/method_freeze.json")) + \
            glob.glob(str(ROOT / "reports/model_v2/v2_fl_004/*method*.json")):
        text = Path(freeze).read_text()
        assert "test_model_v2_current_lifecycle" not in text, freeze
    for lock in glob.glob(str(ROOT / "manifests/model_v2/*SECAGG*.lock.json")) + glob.glob(
            str(ROOT / "artifacts/SECAGG_*_V2*.lock.json")):
        assert "test_model_v2_current_lifecycle" not in Path(lock).read_text(), lock


def test_historical_freeze_drift_is_confined_to_classified_lifecycle_test_files() -> None:
    classified = set(POLICY["classified_lifecycle_control_files"])
    for phase in ("v2_fl_001", "v2_fl_002", "v2_fl_003", "v2_fl_eval_001"):
        freeze = json.loads((ROOT / f"reports/model_v2/{phase}/method_freeze.json").read_text())
        pins = freeze["method_file_sha256"]
        drift = [p for p, h in pins.items() if hash_file(ROOT / p) != h]
        scientific = [p for p in drift if not p.startswith("tests/")]
        assert scientific == [], (phase, scientific)  # no scientific-method file drifted
        assert set(drift) <= classified, (phase, sorted(set(drift) - classified))
