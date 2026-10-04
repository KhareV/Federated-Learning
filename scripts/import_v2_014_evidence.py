#!/usr/bin/env python3
"""V2-014 explicit, automated evidence importer (the ONLY path by which externally generated
clean-clone evidence enters the development repository). It verifies every file hash recorded in
the external evidence_manifest.json first, refuses a non-PASS package, and copies verbatim.

Usage: python -m scripts.import_v2_014_evidence <external_evidence_dir> <clone1|clone2>
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "reports/model_v2/v2_014"


def main() -> None:
    source, label = Path(sys.argv[1]), sys.argv[2]
    if label not in ("clone1", "clone2"):
        sys.exit("label must be clone1 or clone2")
    manifest = json.loads((source / "evidence_manifest.json").read_text())
    bad = [n for n, d in manifest["files"].items()
           if not (source / n).exists() or hash_file(source / n) != d]
    repro = json.loads((source / "reproducibility_manifest.json").read_text())
    expected_mode = "full" if label == "clone1" else "final"
    if bad or repro["result"] != "PASS" or repro["mode"] != expected_mode:
        sys.exit(f"REFUSED: hash mismatches={bad} result={repro['result']} mode={repro['mode']}")
    target = DEST / label
    if target.exists():
        sys.exit("destination already exists; evidence is append-only")
    shutil.copytree(source, target)
    imported = {n: hash_file(target / n) for n in manifest["files"]}
    if imported != manifest["files"]:
        shutil.rmtree(target)
        sys.exit("REFUSED: copy altered content")
    record = {"source_label": label, "clone_target_sha": repro["clone_target_sha"],
              "files": len(imported), "evidence_manifest_sha256": hash_file(
                  target / "evidence_manifest.json"), "verified_before_copy": True}
    (DEST / f"import_{label}.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    if label == "clone1":
        (DEST / "method_commit.txt").write_text(repro["clone_target_sha"] + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
