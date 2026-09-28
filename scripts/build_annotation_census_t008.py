#!/usr/bin/env python3
"""T008: build the shared MIT-BIH/INCART annotation-symbol census.

Offline, deterministic, real-data only -- reads the already-acquired, hash-verified local
raw `.atr` annotation files via `datasets.mitdb.load_annotations` /
`datasets.incart.load_annotations` (T006/T007 scope). No download, no window-building, no
patient split, no preprocessing, no model training.

Maintains an explicit SOURCE vs CORE_CHANNEL_ELIGIBLE scope distinction:
  - MITDB SOURCE = all 48 records; CORE_CHANNEL_ELIGIBLE = the 46 in
    manifests/datasets/mitdb_mlii_records.csv (excludes 102/104, which lack exact MLII).
  - INCART SOURCE = CORE_CHANNEL_ELIGIBLE = all 75 records (manifests/datasets/incart_v1.yaml
    documents zero channel exclusions), reported at both scope labels for symmetry.

For every raw annotation, each occurrence is classified exactly once by
`datasets.labels.map_annotation_symbol` and by temporal position relative to the record's own
`sig_len` (PRE_SIGNAL / IN_SIGNAL / POST_SIGNAL), preserving (never dropping) the seven known
INCART pre-signal annotations documented in reports/t007/incart_validation.json.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasets import incart, mitdb  # noqa: E402
from datasets.labels import map_annotation_symbol  # noqa: E402

REPORT_DIR = ROOT / "reports/t008"

# The seven INCART records with a documented benign pre-signal (sample < 0) annotation --
# reports/t007/incart_validation.json::known_source_anomalies. Used only as a completeness
# cross-check here; the census computes temporal position independently from raw data.
KNOWN_INCART_PRE_SIGNAL_RECORDS = {"I04", "I17", "I35", "I44", "I57", "I72", "I74"}


def _temporal_status(sample: int, sig_len: int) -> str:
    if sample < 0:
        return "PRE_SIGNAL"
    if sample >= sig_len:
        return "POST_SIGNAL"
    return "IN_SIGNAL"


def _scoped_record_ids(dataset_id: str) -> dict[str, list[str]]:
    if dataset_id == "MITDB":
        source = mitdb.list_records()
        with (ROOT / "manifests/datasets/mitdb_mlii_records.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            core_eligible = [row["record_id"] for row in csv.DictReader(handle)]
        return {"SOURCE": source, "CORE_CHANNEL_ELIGIBLE": core_eligible}
    if dataset_id == "INCART":
        source = incart.list_records()
        return {"SOURCE": source, "CORE_CHANNEL_ELIGIBLE": list(source)}
    raise ValueError(f"UNKNOWN_DATASET_ID: {dataset_id!r}; T008 scope is MITDB/INCART only")


def _collect_symbol_accounting(
    dataset_id: str, loader: Any
) -> tuple[dict[tuple[str, str], dict[str, int]], set[str]]:
    """Per (record_id, symbol) raw occurrence counts split by temporal status, plus the set of
    record_ids with >=1 pre-signal annotation."""
    per_record_symbol: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {
            "count_total": 0, "count_in_signal": 0, "count_pre_signal": 0, "count_post_signal": 0,
        }
    )
    records_with_pre_signal: set[str] = set()

    for record_id in loader.list_records():
        header = loader.read_header(record_id)
        annotation = loader.load_annotations(record_id)
        for symbol, sample in zip(annotation.symbol, annotation.sample, strict=True):
            status = _temporal_status(int(sample), header.sig_len)
            key = (record_id, symbol)
            per_record_symbol[key]["count_total"] += 1
            per_record_symbol[key][f"count_{status.lower()}"] += 1
            if status == "PRE_SIGNAL":
                records_with_pre_signal.add(record_id)

    if dataset_id == "INCART":
        assert records_with_pre_signal == KNOWN_INCART_PRE_SIGNAL_RECORDS, (
            "INCART pre-signal record set changed since T007's documented finding: "
            f"expected {sorted(KNOWN_INCART_PRE_SIGNAL_RECORDS)}, "
            f"observed {sorted(records_with_pre_signal)}"
        )

    return per_record_symbol, records_with_pre_signal


def _dataset_census(dataset_id: str, loader: Any) -> dict[str, Any]:
    per_record_symbol, records_with_pre_signal = _collect_symbol_accounting(dataset_id, loader)
    scoped_record_ids = _scoped_record_ids(dataset_id)

    symbol_accounting_rows = []
    all_symbols = sorted({symbol for _, symbol in per_record_symbol})
    for scope, record_ids in scoped_record_ids.items():
        record_id_set = set(record_ids)
        for symbol in all_symbols:
            totals = {
                "count_total": 0,
                "count_in_signal": 0,
                "count_pre_signal": 0,
                "count_post_signal": 0,
            }
            containing = set()
            for (record_id, sym), counts in per_record_symbol.items():
                if sym != symbol or record_id not in record_id_set:
                    continue
                for field in totals:
                    totals[field] += counts[field]
                containing.add(record_id)
            if totals["count_total"] == 0:
                continue
            symbol_accounting_rows.append(
                {
                    "dataset_id": dataset_id,
                    "scope": scope,
                    "symbol": symbol,
                    **totals,
                    "records_containing": len(containing),
                }
            )

    symbol_census_rows = []
    for scope, record_ids in scoped_record_ids.items():
        record_id_set = set(record_ids)
        for symbol in all_symbols:
            raw_count = sum(
                counts["count_total"]
                for (record_id, sym), counts in per_record_symbol.items()
                if sym == symbol and record_id in record_id_set
            )
            if raw_count == 0:
                continue
            containing = {
                record_id
                for (record_id, sym) in per_record_symbol
                if sym == symbol and record_id in record_id_set
            }
            mapped = map_annotation_symbol(symbol)
            symbol_census_rows.append(
                {
                    "dataset_id": dataset_id,
                    "scope": scope,
                    "symbol": symbol,
                    "annotation_kind": mapped.annotation_kind,
                    "raw_count": raw_count,
                    "record_count_containing_symbol": len(containing),
                    "mapped_class": mapped.mapped_class,
                    "core_handling": mapped.core_handling,
                }
            )

    total_annotations_source = sum(
        counts["count_total"]
        for (record_id, _), counts in per_record_symbol.items()
        if record_id in set(scoped_record_ids["SOURCE"])
    )
    post_signal_total = sum(
        counts["count_post_signal"]
        for (record_id, _), counts in per_record_symbol.items()
        if record_id in set(scoped_record_ids["SOURCE"])
    )
    pre_signal_total = sum(
        counts["count_pre_signal"]
        for (record_id, _), counts in per_record_symbol.items()
        if record_id in set(scoped_record_ids["SOURCE"])
    )

    return {
        "symbol_census_rows": symbol_census_rows,
        "symbol_accounting_rows": symbol_accounting_rows,
        "total_annotations_source": total_annotations_source,
        "pre_signal_total": pre_signal_total,
        "post_signal_total": post_signal_total,
        "records_with_pre_signal": sorted(records_with_pre_signal),
        "scoped_record_ids": scoped_record_ids,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def build() -> dict[str, Any]:
    mitdb_result = _dataset_census("MITDB", mitdb)
    incart_result = _dataset_census("INCART", incart)

    census_fieldnames = [
        "dataset_id", "scope", "symbol", "annotation_kind", "raw_count",
        "record_count_containing_symbol", "mapped_class", "core_handling",
    ]
    accounting_fieldnames = [
        "dataset_id", "scope", "symbol", "count_total", "count_in_signal", "count_pre_signal",
        "count_post_signal", "records_containing",
    ]

    _write_csv(
        REPORT_DIR / "mitdb_annotation_symbol_census.csv",
        mitdb_result["symbol_census_rows"],
        census_fieldnames,
    )
    _write_csv(
        REPORT_DIR / "incart_annotation_symbol_census.csv",
        incart_result["symbol_census_rows"],
        census_fieldnames,
    )
    combined_rows = sorted(
        mitdb_result["symbol_census_rows"] + incart_result["symbol_census_rows"],
        key=lambda row: (row["dataset_id"], row["scope"], row["symbol"]),
    )
    _write_csv(REPORT_DIR / "annotation_symbol_census.csv", combined_rows, census_fieldnames)

    combined_accounting = sorted(
        mitdb_result["symbol_accounting_rows"] + incart_result["symbol_accounting_rows"],
        key=lambda row: (row["dataset_id"], row["scope"], row["symbol"]),
    )
    _write_csv(REPORT_DIR / "symbol_accounting.csv", combined_accounting, accounting_fieldnames)

    return {"MITDB": mitdb_result, "INCART": incart_result}


if __name__ == "__main__":
    summary = build()
    for dataset_id, result in summary.items():
        print(
            f"{dataset_id}: SOURCE annotations={result['total_annotations_source']} "
            f"pre_signal={result['pre_signal_total']} post_signal={result['post_signal_total']} "
            f"records_with_pre_signal={result['records_with_pre_signal']}"
        )
    print("T008 annotation census: generated")
