#!/usr/bin/env python3
"""T035-REPRO offline dataset-provenance materialization.

scripts/acquire_{mitdb,bidmc,incart,nstdb}.py are network-dependent (they fetch the official
RECORDS/SHA256SUMS.txt from physionet.org on every invocation, even when every local byte
already matches, to remain independently authoritative). In this sandboxed environment,
outbound network access to physionet.org is unreliable/extremely slow (observed: >15 minutes,
sometimes failing to complete at all). This script reproduces the SAME verification step
(local file bytes hash-match the dataset's own checksum authority) entirely offline, using
ONLY repository-TRACKED inputs:
  - data/raw/<dataset>/<version>/SHA256SUMS.txt (explicitly carved out of .gitignore as
    trackable provenance -- the exact same file the acquire script would have fetched and
    wrote locally after the original T006/T007 network acquisition).
  - the ORIGINAL acquisition's own tracked records list (reports/t006/acquisition_metadata.
    json, reports/t007/{bidmc,incart,nstdb}_acquisition_metadata.json) -- committed historical
    evidence from when network acquisition genuinely succeeded.

It verifies every file named in the tracked SHA256SUMS.txt against its local bytes (hash_file,
the same primitive scripts/acquire_*.py and datasets/physionet.py use) and then writes the
RECORDS file datasets.*.list_records() requires, using the historical tracked record list.
No bytes are invented; nothing is downloaded; every verified hash is the project's own
previously-fetched, committed checksum authority.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]

DATASETS = {
    "mitdb": {
        "raw_root": ROOT / "data/raw/mitdb/1.0.0",
        "metadata_path": ROOT / "reports/t006/acquisition_metadata.json",
    },
    "bidmc": {
        "raw_root": ROOT / "data/raw/bidmc/1.0.0",
        "metadata_path": ROOT / "reports/t007/bidmc_acquisition_metadata.json",
    },
    "incartdb": {
        "raw_root": ROOT / "data/raw/incartdb/1.0.0",
        "metadata_path": ROOT / "reports/t007/incart_acquisition_metadata.json",
    },
    "nstdb": {
        "raw_root": ROOT / "data/raw/nstdb/1.0.0",
        "metadata_path": ROOT / "reports/t007/nstdb_acquisition_metadata.json",
    },
}


def _parse_sha256_manifest(text: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts
        hashes[name] = digest
    return hashes


def main() -> None:
    report: dict[str, dict] = {}
    overall_status = "PASS"

    for dataset_id, paths in DATASETS.items():
        raw_root: Path = paths["raw_root"]
        metadata_path: Path = paths["metadata_path"]
        sums_path = raw_root / "SHA256SUMS.txt"

        if not sums_path.exists():
            report[dataset_id] = {"status": "FAIL", "reason": "TRACKED_SHA256SUMS_MISSING"}
            overall_status = "FAIL"
            continue
        if not metadata_path.exists():
            report[dataset_id] = {"status": "FAIL", "reason": "TRACKED_METADATA_MISSING"}
            overall_status = "FAIL"
            continue

        expected_hashes = _parse_sha256_manifest(sums_path.read_text(encoding="utf-8"))
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        records: list[str] = metadata["records"]

        mismatches: list[str] = []
        missing: list[str] = []
        verified = 0
        for filename, expected_digest in expected_hashes.items():
            local_file = raw_root / filename
            if not local_file.exists():
                missing.append(filename)
                continue
            if hash_file(local_file) != expected_digest:
                mismatches.append(filename)
                continue
            verified += 1

        status = "PASS" if not mismatches and not missing else "FAIL"
        if status != "PASS":
            overall_status = "FAIL"

        if status == "PASS":
            (raw_root / "RECORDS").write_text("\n".join(records) + "\n", encoding="utf-8")

        report[dataset_id] = {
            "status": status,
            "files_in_tracked_sha256sums": len(expected_hashes),
            "files_verified": verified,
            "files_missing": missing,
            "files_hash_mismatch": mismatches,
            "record_count": len(records),
            "records_file_written": status == "PASS",
            "checksum_authority": str(sums_path.relative_to(ROOT)),
            "record_list_source": str(metadata_path.relative_to(ROOT)),
        }

    output = {
        "checkpoint": "T035",
        "method": (
            "offline verification against repository-TRACKED SHA256SUMS.txt + tracked "
            "historical acquisition metadata; no network access used (physionet.org fetch "
            "was unreliable/very slow in this sandbox -- see reports/t035/"
            "clean_checkout_audit.json)"
        ),
        "datasets": report,
        "status": overall_status,
    }
    out_path = ROOT / "reports/t035/raw_provenance_materialization.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    if overall_status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
