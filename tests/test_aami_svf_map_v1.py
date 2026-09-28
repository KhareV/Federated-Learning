"""Exhaustive AAMI_SVF_MAP_V1 mapper tests -- every allowlisted symbol, paced/unknown/unmapped
beats, non-beat markers, dataset-independence, and consistency with the YAML freeze manifest
and contracts/LABEL_SCHEMA_V1.md."""

from pathlib import Path

import pytest
import wfdb.io.annotation as wfdb_ann
import yaml

from datasets.labels import (
    AAMI_CLASSES,
    BEAT_SYMBOLS,
    MAP_ID,
    NON_BEAT_SYMBOLS,
    NOT_A_BEAT,
    SPEC_VERSION,
    TARGET_ID,
    UNMAPPABLE,
    classify_annotation_kind,
    map_annotation_symbol,
)

ROOT = Path(__file__).resolve().parents[1]

ALLOWLISTED_BEAT_TO_CLASS = {
    "N": "N", "L": "N", "R": "N", "e": "N", "j": "N",
    "A": "S", "a": "S", "J": "S", "S": "S",
    "V": "V", "E": "V",
    "F": "F",
    "/": "Q", "f": "Q", "Q": "Q",
}


@pytest.mark.parametrize("symbol,expected_class", sorted(ALLOWLISTED_BEAT_TO_CLASS.items()))
def test_every_allowlisted_symbol_maps_to_its_frozen_class(
    symbol: str, expected_class: str
) -> None:
    mapped = map_annotation_symbol(symbol)
    assert mapped.annotation_kind == "BEAT"
    assert mapped.mapped_class == expected_class
    assert mapped.map_id == MAP_ID


def test_paced_beat_maps_to_q_and_is_excluded() -> None:
    mapped = map_annotation_symbol("/")
    assert mapped.mapped_class == "Q"
    assert mapped.core_handling == "EXCLUDE_Q"


def test_unclassifiable_beat_symbol_q_maps_to_q_and_is_excluded() -> None:
    mapped = map_annotation_symbol("Q")
    assert mapped.mapped_class == "Q"
    assert mapped.core_handling == "EXCLUDE_Q"


def test_learning_symbol_is_a_real_unlisted_beat_and_is_unmappable() -> None:
    """'?' (WFDB "Learning") is a beat per is_qrs but is not in the AAMI allowlist -- must be
    UNMAPPABLE, never coerced to the nearest class."""
    mapped = map_annotation_symbol("?")
    assert mapped.annotation_kind == "BEAT"
    assert mapped.mapped_class == UNMAPPABLE
    assert mapped.core_handling == "EXCLUDE_UNMAPPABLE"


@pytest.mark.parametrize("symbol", ["!", "B", "n", "r"])
def test_real_unlisted_beat_symbols_observed_in_source_data_are_unmappable(symbol: str) -> None:
    """'!' (MIT-BIH: Ventricular flutter wave) and 'B'/'n' (INCART: bundle branch block /
    supraventricular escape beat) are real beat symbols actually present in the acquired T006/
    T007 raw data (see reports/t008/annotation_symbol_census.csv) but are not in the frozen
    AAMI allowlist. 'r' (R-on-T PVC) is in the WFDB standard vocabulary for completeness."""
    mapped = map_annotation_symbol(symbol)
    assert mapped.annotation_kind == "BEAT"
    assert mapped.mapped_class == UNMAPPABLE


@pytest.mark.parametrize("symbol", ["~", "+", '"', "|", "[", "]", "x"])
def test_real_non_beat_markers_observed_in_source_data_are_not_a_beat(symbol: str) -> None:
    """All seven are real non-beat annotation markers actually present in the acquired T006/
    T007 MIT-BIH raw data (see reports/t008/annotation_symbol_census.csv)."""
    mapped = map_annotation_symbol(symbol)
    assert mapped.annotation_kind == "NON_BEAT"
    assert mapped.mapped_class == NOT_A_BEAT
    assert mapped.core_handling == "IGNORE_NON_BEAT"


def test_unrecognized_symbol_raises_instead_of_guessing() -> None:
    with pytest.raises(ValueError, match="UNRECOGNIZED_WFDB_ANNOTATION_SYMBOL"):
        classify_annotation_kind("%")


def test_mapper_is_dataset_independent() -> None:
    """The same symbol maps identically no matter which dataset it came from -- the function
    itself never takes a dataset argument, so this is true by construction; assert it anyway
    for the symbols both MIT-BIH and INCART actually share."""
    shared_symbols = ["N", "A", "F", "Q", "R", "S", "V", "j"]
    for symbol in shared_symbols:
        first = map_annotation_symbol(symbol)
        second = map_annotation_symbol(symbol)
        assert first == second


def test_every_allowlisted_symbol_classifies_as_beat() -> None:
    for symbols in AAMI_CLASSES.values():
        for symbol in symbols:
            assert symbol in BEAT_SYMBOLS


def test_beat_and_non_beat_symbol_sets_are_disjoint() -> None:
    assert BEAT_SYMBOLS.isdisjoint(NON_BEAT_SYMBOLS)


def test_beat_non_beat_tables_match_wfdb_is_qrs_table() -> None:
    """Cross-check the hardcoded BEAT_SYMBOLS/NON_BEAT_SYMBOLS tables against the live
    wfdb==4.3.1 authoritative source (wfdb.io.annotation.is_qrs / ann_label_table) so a
    library upgrade that silently changes this table is caught, not silently inherited."""
    live_beat = set()
    live_non_beat = set()
    for _, row in wfdb_ann.ann_label_table.iterrows():
        symbol = row["symbol"]
        is_beat = wfdb_ann.is_qrs[row["label_store"]]
        (live_beat if is_beat else live_non_beat).add(symbol)
    assert live_beat == BEAT_SYMBOLS
    assert live_non_beat == NON_BEAT_SYMBOLS


def test_yaml_manifest_matches_executable_mapper() -> None:
    manifest_path = ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["map_id"] == MAP_ID
    assert manifest["target_id"] == TARGET_ID
    assert manifest["spec_version"] == SPEC_VERSION
    assert manifest["implementation_module"] == "datasets/labels.py"
    yaml_classes = {cls: tuple(symbols) for cls, symbols in manifest["aami_classes"].items()}
    assert yaml_classes == dict(AAMI_CLASSES)


def test_label_schema_contract_table_matches_executable_mapper() -> None:
    contract = (ROOT / "contracts/LABEL_SCHEMA_V1.md").read_text(encoding="utf-8")
    assert "N, L, R, e, j -> N" in contract
    assert "A, a, J, S    -> S" in contract
    assert "V, E          -> V" in contract
    assert "F             -> F" in contract
    assert "/, f, Q       -> Q / excluded" in contract


def test_mapping_tables_are_immutable() -> None:
    with pytest.raises(TypeError):
        AAMI_CLASSES["N"] = ("N",)  # type: ignore[index]
