from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL_SCHEMA = ROOT / "contracts/LABEL_SCHEMA_V1.md"


def _text() -> str:
    return LABEL_SCHEMA.read_text(encoding="utf-8")


def test_target_and_mapping_identifiers_present() -> None:
    text = _text()
    assert "AAMI_SVF_WINDOW_V1" in text
    assert "AAMI_SVF_MAP_V1" in text


def test_target_semantics_are_exact() -> None:
    text = _text()
    assert "SVF_CONTAINING_WINDOW" in text
    assert "N_ONLY_WINDOW" in text
    assert "RECHECK_SENSOR" in text


def test_window_and_cadence_are_locked() -> None:
    text = _text()
    assert "10-second ECG window" in text
    assert "5 seconds" in text
    assert "[t - 10 seconds, t]" in text


def test_exclusion_wording_is_present() -> None:
    text = _text().casefold()
    for term in ("unknown", "unmappable", "paced", "fewer than 5 mappable beats", "unusable"):
        assert term in text


def test_exact_aami_svf_map_v1_table_is_present() -> None:
    text = _text()
    expected_rows = [
        "N, L, R, e, j -> N",
        "A, a, J, S    -> S",
        "V, E          -> V",
        "F             -> F",
        "/, f, Q       -> Q / excluded",
    ]
    for row in expected_rows:
        assert row in text


def test_claim_boundary_excludes_diagnosis() -> None:
    text = _text().casefold()
    assert "disease probability" in text
    assert "diagnosis of arrhythmia" in text
    assert "future forecast" in text
    assert "beat-classifier output" in text


def test_mapping_change_requires_change_control() -> None:
    text = _text().casefold()
    assert "change-control event" in text or "change control" in text
    assert "class c" in text
