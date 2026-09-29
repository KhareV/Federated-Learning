"""PREPROC_V1_RESAMPLER_V1 identity: ratio derivation, coefficient invariants, coefficient
regeneration, config consistency, and the forbidden-convenience-API static audit."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from preprocessing.resample import COEFFICIENT_DIR, load_resampler_spec
from scripts.design_resampler_t011 import CONVERSIONS, _reduced_ratio, design_coefficients

ROOT = Path(__file__).resolve().parents[1]

RESAMPLER_IDS = ["MITDB_360_TO_250_V1", "INCART_257_TO_250_V1"]
EXPECTED_RATIOS = {
    "MITDB_360_TO_250_V1": {"input_rate_hz": 360, "output_rate_hz": 250, "up": 25, "down": 36},
    "INCART_257_TO_250_V1": {
        "input_rate_hz": 257, "output_rate_hz": 250, "up": 250, "down": 257,
    },
}
EXPECTED_NUM_TAPS = {"MITDB_360_TO_250_V1": 721, "INCART_257_TO_250_V1": 5141}


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_ratio_is_exact_reduced_fraction(resampler_id: str) -> None:
    expected = EXPECTED_RATIOS[resampler_id]
    divisor = math.gcd(expected["input_rate_hz"], expected["output_rate_hz"])
    up = expected["output_rate_hz"] // divisor
    down = expected["input_rate_hz"] // divisor
    assert up == expected["up"]
    assert down == expected["down"]
    assert math.gcd(up, down) == 1


def test_360_to_250_ratio_is_25_over_36() -> None:
    spec = load_resampler_spec("MITDB_360_TO_250_V1")
    assert (spec.up, spec.down) == (25, 36)


def test_257_to_250_ratio_is_250_over_257() -> None:
    spec = load_resampler_spec("INCART_257_TO_250_V1")
    assert (spec.up, spec.down) == (250, 257)


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_coefficient_tap_count(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    assert spec.num_taps == EXPECTED_NUM_TAPS[resampler_id]
    assert spec.num_taps % 2 == 1


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_coefficients_finite_and_float64(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    assert spec.coefficients.dtype == np.float64
    assert np.all(np.isfinite(spec.coefficients))


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_coefficients_are_symmetric_linear_phase(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    assert np.array_equal(spec.coefficients, spec.coefficients[::-1])


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_coefficient_dc_gain_equals_up(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    assert spec.coefficients.sum() == pytest.approx(spec.up, abs=1e-9)


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_coefficient_hash_matches_manifest(resampler_id: str) -> None:
    manifest = json.loads((COEFFICIENT_DIR / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["conversions"][resampler_id]
    spec = load_resampler_spec(resampler_id)
    assert spec.coefficient_sha256 == entry["coefficient_sha256"]


def test_coefficient_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "coefficients"
    shutil.copytree(COEFFICIENT_DIR, workspace)
    array_path = workspace / "MITDB_360_TO_250_V1.npy"
    array = np.load(array_path)
    array[0] += 1.0
    np.save(array_path, array)
    with pytest.raises(ValueError, match="COEFFICIENT_HASH_MISMATCH"):
        load_resampler_spec("MITDB_360_TO_250_V1", coefficient_dir=workspace)


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_group_delay_matches_expected_10_output_samples_40ms(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    assert spec.group_delay_output_samples == 10
    assert spec.group_delay_seconds == pytest.approx(0.040, abs=1e-12)


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_startup_transient_span_matches_expected_20_samples(resampler_id: str) -> None:
    manifest = json.loads((COEFFICIENT_DIR / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["conversions"][resampler_id]
    assert entry["startup_transient_output_span"] == 20
    # verify independently from first principles: (num_taps - 1) // down
    assert (entry["num_taps"] - 1) // entry["down"] == 20
    assert (entry["num_taps"] - 1) % entry["down"] == 0


def test_coefficient_regeneration_is_bit_identical() -> None:
    """Recomputing coefficients via the pure design function must reproduce the committed
    array bytes exactly -- the design script itself only adds file I/O around this call."""
    for resampler_id, rates in CONVERSIONS.items():
        up, down = _reduced_ratio(rates["input_rate_hz"], rates["output_rate_hz"])
        regenerated = design_coefficients(up, down)
        committed = np.load(COEFFICIENT_DIR / f"{resampler_id}.npy")
        assert np.array_equal(regenerated, committed), f"{resampler_id}: regeneration mismatch"
        assert regenerated.tobytes() == committed.tobytes()


def test_config_preproc_v1_agrees_with_coefficient_manifest() -> None:
    config = yaml.safe_load((ROOT / "configs/preproc_v1.yaml").read_text(encoding="utf-8"))
    manifest = json.loads((COEFFICIENT_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert config["preproc_id"] == manifest["preproc_id"]
    assert config["resampler"]["resampler_id"] == manifest["resampler_id"]
    assert config["resampler"]["status"] == "PASS"
    for resampler_id in RESAMPLER_IDS:
        config_entry = config["resampler"]["conversions"][resampler_id]
        manifest_entry = manifest["conversions"][resampler_id]
        assert config_entry["up"] == manifest_entry["up"]
        assert config_entry["down"] == manifest_entry["down"]
        assert config_entry["num_taps"] == manifest_entry["num_taps"]
        assert config_entry["coefficient_sha256"] == manifest_entry["coefficient_sha256"]
    # ecg_filter/ppg_filter/gap_policy were DEFERRED_T012 as of T011; T012 has since
    # validated them (tests/test_ecg_filter.py, tests/test_ppg_filter.py,
    # tests/test_gap_policy_v1.py) -- only windowing/quality remain deferred to T013.
    assert config["ecg_filter"]["status"] == "PASS"
    assert config["ppg_filter"]["status"] == "PASS"
    assert config["gap_policy"]["status"] == "PASS"
    assert config["windowing"]["status"] == "DEFERRED_T013"
    assert config["quality"]["status"] == "DEFERRED_T013"
    assert config["status"] == "DRAFT_UNTIL_G6"


# ---------------------------------------------------------------------------------------
# Forbidden convenience-API static audit (Section 37)
# ---------------------------------------------------------------------------------------

FORBIDDEN_CALLS = (
    "signal.resample(",
    "signal.resample_poly(",
    "resample_poly(",
    ".filtfilt(",
    "sosfiltfilt(",
)


def test_production_resampler_module_never_calls_forbidden_convenience_apis() -> None:
    source = (ROOT / "preprocessing/resample.py").read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_CALLS:
        assert forbidden not in source, f"forbidden convenience API found: {forbidden}"


def test_production_resampler_module_does_not_import_test_reference() -> None:
    source = (ROOT / "preprocessing/resample.py").read_text(encoding="utf-8")
    assert "resampler_reference" not in source
