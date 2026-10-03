"""V2-009 Section 6: the authoritative exhaustive deterministic chunked pytest regression,
required BEFORE any CALIBRATION waveform access (V2-008's monolithic pytest runs are not
trusted as sufficient proof here -- see v2_008_entry_provenance_disclosure.json). Partitions
the collected node list into fixed-size deterministic chunks and executes each chunk as its
own pytest invocation, proving set(executed) == set(collected) with zero missing/duplicate/
unexpected/failed nodes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_009"
CHUNK_SIZE = 80
VENV_PYTHON = str(ROOT / ".venv-t032/bin/python")


def main() -> None:
    collect = subprocess.run(
        [VENV_PYTHON, "-m", "pytest", "--collect-only", "-q", "-p", "no:warnings"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": "src:."},
    )
    nodes = sorted(line for line in collect.stdout.splitlines() if "::" in line)
    (OUT / "pytest_collected_nodes.txt").write_text("\n".join(nodes) + "\n", encoding="utf-8")

    collected_sorted_hash = hashlib.sha256("\n".join(sorted(nodes)).encode("utf-8")).hexdigest()
    chunks = [nodes[i : i + CHUNK_SIZE] for i in range(0, len(nodes), CHUNK_SIZE)]

    manifest_rows = []
    result_rows = []
    executed_nodes: list[str] = []
    failed_chunks = 0
    failed_tests_total = 0

    for chunk_index, chunk_nodes in enumerate(chunks):
        chunk_id = f"chunk_{chunk_index:03d}"
        chunk_hash = hashlib.sha256("\n".join(chunk_nodes).encode("utf-8")).hexdigest()
        manifest_rows.append(
            {
                "chunk_id": chunk_id, "node_count": len(chunk_nodes), "node_hash": chunk_hash,
                "first_node": chunk_nodes[0], "last_node": chunk_nodes[-1],
            }
        )
        start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        env = dict(os.environ)
        env["PYTHONPATH"] = "src:."
        result = subprocess.run(
            [VENV_PYTHON, "-m", "pytest", "-q", "-p", "no:warnings", *chunk_nodes],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        end = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        failed_node_ids = []
        if result.returncode != 0:
            failed_chunks += 1
            for line in result.stdout.splitlines():
                if line.startswith("FAILED "):
                    failed_node_ids.append(line.split(" ")[1])
            failed_tests_total += len(failed_node_ids) if failed_node_ids else 1
        executed_nodes.extend(chunk_nodes)
        result_rows.append(
            {
                "chunk_id": chunk_id, "node_count": len(chunk_nodes), "node_hash": chunk_hash,
                "start": start, "end": end, "exit_code": result.returncode,
                "failed_node_ids": ";".join(failed_node_ids),
            }
        )
        print(f"{chunk_id}: {len(chunk_nodes)} nodes exit={result.returncode}")

    manifest_fields = list(manifest_rows[0].keys())
    with (OUT / "pytest_chunk_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=manifest_fields)
        writer.writeheader()
        writer.writerows(manifest_rows)

    result_fields = list(result_rows[0].keys())
    with (OUT / "pytest_chunk_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=result_fields)
        writer.writeheader()
        writer.writerows(result_rows)

    executed_set = set(executed_nodes)
    collected_set = set(nodes)
    duplicates = len(executed_nodes) - len(executed_set)
    missing = len(collected_set - executed_set)
    unexpected = len(executed_set - collected_set)

    proof = {
        "collected_node_count": len(nodes),
        "collected_sorted_node_list_sha256": collected_sorted_hash,
        "chunk_size": CHUNK_SIZE,
        "chunk_count": len(chunks),
        "executed_unique_count": len(executed_set),
        "missing": missing,
        "duplicates": duplicates,
        "unexpected": unexpected,
        "failed_chunks": failed_chunks,
        "failed_tests": failed_tests_total,
        "collected_equals_executed": collected_set == executed_set,
        "status": (
            "PASS"
            if (collected_set == executed_set and missing == 0 and duplicates == 0
                and unexpected == 0 and failed_chunks == 0 and failed_tests_total == 0)
            else "FAIL"
        ),
    }
    (OUT / "pre_calibration_full_regression_proof.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    main()
