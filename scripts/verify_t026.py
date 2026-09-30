"""Verify frozen T026 non-IID results without retraining."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from nhm.hashing import hash_file  # noqa: E402
from scripts.verify_fl_config_t026 import verify as verify_f12  # noqa: E402


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify(root: Path = ROOT) -> dict[str, object]:
    verify_f12(root)
    expected_round0 = "c368b6cfaaa8a52b60b48e92332ca9fa694e94cf7b655c7c83f4e63bf747d5aa"
    for condition in ("label", "quantity", "feature", "combined"):
        rounds = rows(root / f"reports/t026/{condition}_rounds.csv")
        clients = rows(root / f"reports/t026/{condition}_client_rounds.csv")
        result = json.loads((root / f"reports/t026/{condition}_result.json").read_text())
        if (
            len(rounds) != 51
            or len(clients) != 400
            or rounds[0]["global_state_sha256"] != expected_round0
            or any(row["client_count"] != "8" for row in rounds[1:])
            or any(row["status"] != "PASS" for row in clients)
            or result["status"] != "PASS"
            or not result["finite"]
            or result["logical_payload_bytes"] != 43_491_200
        ):
            raise RuntimeError(f"T026_RESULT_VERIFY_FAILURE: {condition}")
    reproducibility = json.loads((root / "reports/t026/reproducibility.json").read_text())
    report = json.loads((root / "reports/fl_non_iid.json").read_text())
    hashes = json.loads((root / "reports/t026/artifact_hashes.json").read_text())
    mismatches = [path for path, digest in hashes.items() if hash_file(root / path) != digest]
    if reproducibility["status"] != "PASS" or report["status"] != "PASS" or mismatches:
        raise RuntimeError(f"T026_EVIDENCE_VERIFY_FAILURE: {mismatches}")
    return {
        "status": "PASS",
        "conditions": 4,
        "rounds_per_condition": 50,
        "client_updates": 1600,
        "round_0_sha256": expected_round0,
        "F12": "FROZEN",
        "reproducibility": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
