#!/usr/bin/env python3
"""T008 / G4: audit AAMI_SVF_MAP_V1 for exhaustiveness and internal consistency, and write the
gate's declared evidence file (reports/labels/label_audit.json).

Requires reports/t008/annotation_symbol_census.csv and symbol_accounting.csv to already exist
(scripts/build_annotation_census_t008.py). Performs no acquisition, no window-building, no
split, no preprocessing.

Checks:
  - Every raw annotation occurrence (SOURCE scope, both datasets) is accounted for in exactly
    one of N/S/V/F/Q/UNMAPPABLE/NOT_A_BEAT (raw-count conservation).
  - Every symbol maps to exactly one class, identically across MITDB and INCART when the
    symbol occurs in both (dataset-independence of the shared mapper).
  - The YAML freeze manifest (manifests/labels/AAMI_SVF_MAP_V1.yaml) agrees exactly with the
    executable mapper (datasets.labels.AAMI_CLASSES).
  - INCART's seven documented pre-signal annotations are preserved, and INCART's
    post-signal count is exactly zero (reports/t007/incart_validation.json cross-check).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasets.labels import (  # noqa: E402
    AAMI_CLASSES,
    MAP_ID,
    SPEC_VERSION,
    TARGET_ID,
    map_annotation_symbol,
)

REPORT_DIR = ROOT / "reports/t008"
GATE_EVIDENCE_PATH = ROOT / "reports/labels/label_audit.json"
KNOWN_INCART_PRE_SIGNAL_RECORDS = {"I04", "I17", "I35", "I44", "I57", "I72", "I74"}


def _read_census_rows() -> list[dict[str, Any]]:
    with (REPORT_DIR / "annotation_symbol_census.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_accounting_rows() -> list[dict[str, Any]]:
    with (REPORT_DIR / "symbol_accounting.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _check_yaml_matches_mapper(errors: list[str]) -> None:
    manifest_path = ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if manifest["map_id"] != MAP_ID:
        errors.append(f"YAML map_id {manifest['map_id']!r} != executable MAP_ID {MAP_ID!r}")
    if manifest["target_id"] != TARGET_ID:
        errors.append(
            f"YAML target_id {manifest['target_id']!r} != executable TARGET_ID {TARGET_ID!r}"
        )
    if manifest["spec_version"] != SPEC_VERSION:
        errors.append(
            f"YAML spec_version {manifest['spec_version']!r} != "
            f"executable SPEC_VERSION {SPEC_VERSION!r}"
        )
    yaml_classes = {cls: tuple(symbols) for cls, symbols in manifest["aami_classes"].items()}
    if yaml_classes != dict(AAMI_CLASSES):
        errors.append(
            f"YAML aami_classes {yaml_classes} != executable AAMI_CLASSES {dict(AAMI_CLASSES)}"
        )


def _check_raw_count_conservation(
    census_rows: list[dict[str, Any]], errors: list[str]
) -> dict[str, int]:
    totals_by_dataset: dict[str, int] = {}
    for dataset_id in ("MITDB", "INCART"):
        source_total = sum(
            int(row["raw_count"])
            for row in census_rows
            if row["dataset_id"] == dataset_id and row["scope"] == "SOURCE"
        )
        totals_by_dataset[dataset_id] = source_total
        if source_total <= 0:
            errors.append(
                f"{dataset_id}: SOURCE scope raw annotation total is not positive ({source_total})"
            )
    return totals_by_dataset


def _check_single_classification_per_symbol(
    census_rows: list[dict[str, Any]], errors: list[str]
) -> None:
    seen: dict[str, tuple[str, str]] = {}
    for row in census_rows:
        symbol = row["symbol"]
        classification = (row["annotation_kind"], row["mapped_class"])
        if symbol in seen and seen[symbol] != classification:
            errors.append(
                f"symbol {symbol!r} classified inconsistently across rows: "
                f"{seen[symbol]} vs {classification}"
            )
        seen[symbol] = classification
        recomputed = map_annotation_symbol(symbol)
        expected = (recomputed.annotation_kind, recomputed.mapped_class)
        if classification != expected:
            errors.append(
                f"symbol {symbol!r} census classification {classification} != "
                f"live mapper {expected}"
            )


def _check_incart_pre_signal(
    accounting_rows: list[dict[str, Any]], errors: list[str]
) -> dict[str, int]:
    incart_source = [
        row for row in accounting_rows if row["dataset_id"] == "INCART" and row["scope"] == "SOURCE"
    ]
    pre_signal_total = sum(int(row["count_pre_signal"]) for row in incart_source)
    post_signal_total = sum(int(row["count_post_signal"]) for row in incart_source)
    if pre_signal_total != len(KNOWN_INCART_PRE_SIGNAL_RECORDS):
        errors.append(
            f"INCART pre_signal_total {pre_signal_total} != documented finding "
            f"{len(KNOWN_INCART_PRE_SIGNAL_RECORDS)} (reports/t007/incart_validation.json)"
        )
    if post_signal_total != 0:
        errors.append(f"INCART post_signal_total {post_signal_total} != 0")
    incart_validation_path = ROOT / "reports/t007/incart_validation.json"
    incart_validation = json.loads(incart_validation_path.read_text(encoding="utf-8"))
    documented_records = {row["record_id"] for row in incart_validation["known_source_anomalies"]}
    if documented_records != KNOWN_INCART_PRE_SIGNAL_RECORDS:
        errors.append(
            f"T007 known_source_anomalies records {sorted(documented_records)} != "
            f"T008's expected set {sorted(KNOWN_INCART_PRE_SIGNAL_RECORDS)}"
        )
    return {"pre_signal_total": pre_signal_total, "post_signal_total": post_signal_total}


def build_audit() -> dict[str, Any]:
    census_rows = _read_census_rows()
    accounting_rows = _read_accounting_rows()
    errors: list[str] = []

    _check_yaml_matches_mapper(errors)
    totals_by_dataset = _check_raw_count_conservation(census_rows, errors)
    _check_single_classification_per_symbol(census_rows, errors)
    incart_signal_totals = _check_incart_pre_signal(accounting_rows, errors)

    class_totals: dict[str, dict[str, int]] = {}
    unmappable_symbols: dict[str, list[str]] = {}
    for dataset_id in ("MITDB", "INCART"):
        source_rows = [
            row
            for row in census_rows
            if row["dataset_id"] == dataset_id and row["scope"] == "SOURCE"
        ]
        by_class: dict[str, int] = {}
        for row in source_rows:
            mapped_class = row["mapped_class"]
            by_class[mapped_class] = by_class.get(mapped_class, 0) + int(row["raw_count"])
        class_totals[dataset_id] = by_class
        unmappable_symbols[dataset_id] = sorted(
            row["symbol"] for row in source_rows if row["mapped_class"] == "UNMAPPABLE"
        )

    status = "PASS" if not errors else "FAIL"
    audit = {
        "map_id": MAP_ID,
        "target_id": TARGET_ID,
        "spec_version": SPEC_VERSION,
        "manifest_path": "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        "implementation_path": "datasets/labels.py",
        "freeze_id": "F04",
        "gate_id": "G4",
        "scope_datasets": ["MITDB", "INCART"],
        "excluded_datasets": ["NSTDB", "BIDMC", "WEARABLE_SIM_V1"],
        "source_scope_annotation_totals": totals_by_dataset,
        "mapped_class_totals_by_dataset": class_totals,
        "unmappable_symbols_by_dataset": unmappable_symbols,
        "incart_pre_signal_annotation_count": incart_signal_totals["pre_signal_total"],
        "incart_post_signal_annotation_count": incart_signal_totals["post_signal_total"],
        "incart_pre_signal_records": sorted(KNOWN_INCART_PRE_SIGNAL_RECORDS),
        "raw_count_conservation_checked": True,
        "single_classification_per_symbol_checked": True,
        "yaml_matches_executable_mapper_checked": True,
        "overall_status": status,
        "errors": errors,
    }
    return audit


def main() -> None:
    audit = build_audit()
    GATE_EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = GATE_EVIDENCE_PATH.with_suffix(f"{GATE_EVIDENCE_PATH.suffix}.tmp")
    temporary.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(GATE_EVIDENCE_PATH)
    if audit["overall_status"] != "PASS":
        raise RuntimeError(f"T008 label-map audit FAILED: {audit['errors']}")
    print(f"T008 label-map audit: {audit['overall_status']}")


if __name__ == "__main__":
    main()
