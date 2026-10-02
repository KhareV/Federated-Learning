#!/usr/bin/env python3
"""C-V2-001-VERIFY Section 2: deterministic, exhaustive chunked full-pytest verifier.

Collects the complete test-node set, partitions it into deterministic chunks, executes every
chunk exactly once, and proves union(executed) == collected, zero duplicate executions, zero
missing nodes, and zero failed chunks. This is run IN ADDITION TO a plain `pytest -q`
invocation (which already completed successfully) purely to give node-level mechanical proof.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/cv2_001_verify"
CHUNK_SIZE = 300


def collect_node_ids() -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT,
        env={"PYTHONPATH": "src:."},
        capture_output=True,
        text=True,
        check=True,
    )
    node_ids = sorted(
        line.strip()
        for line in result.stdout.splitlines()
        if "::" in line and not line.startswith(" ")
    )
    return node_ids


def run_chunk(index: int, node_ids: list[str]) -> dict:
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *node_ids],
        cwd=ROOT,
        env={"PYTHONPATH": "src:."},
        capture_output=True,
        text=True,
        check=False,
    )
    duration = time.monotonic() - start

    def _is_summary(line: str) -> bool:
        return " passed" in line or " failed" in line or " error" in line

    summary_line = next(
        (line for line in reversed(result.stdout.splitlines()) if _is_summary(line)), ""
    )
    return {
        "chunk_index": index,
        "node_count": len(node_ids),
        "exit_code": result.returncode,
        "duration_seconds": round(duration, 3),
        "summary_line": summary_line.strip(),
    }


def main() -> None:
    collected = collect_node_ids()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pytest_collection.txt").write_text("\n".join(collected) + "\n", encoding="utf-8")

    chunks = [collected[i : i + CHUNK_SIZE] for i in range(0, len(collected), CHUNK_SIZE)]
    chunk_results = []
    executed_nodes: list[str] = []
    for index, chunk in enumerate(chunks):
        result = run_chunk(index, chunk)
        chunk_results.append(result)
        executed_nodes.extend(chunk)
        print(json.dumps(result))

    union_executed = set(executed_nodes)
    collected_set = set(collected)

    proof = {
        "checkpoint": "C-V2-001-VERIFY",
        "method": "deterministic_exhaustive_chunking",
        "chunk_size": CHUNK_SIZE,
        "total_collected": len(collected),
        "total_chunks": len(chunks),
        "chunk_results": chunk_results,
        "total_executed_node_instances": len(executed_nodes),
        "union_executed_equals_collected": union_executed == collected_set,
        "duplicate_executions": len(executed_nodes) - len(union_executed),
        "missing_nodes": sorted(collected_set - union_executed),
        "extra_nodes": sorted(union_executed - collected_set),
        "failed_chunks": [c["chunk_index"] for c in chunk_results if c["exit_code"] != 0],
        "all_exit_codes_zero": all(c["exit_code"] == 0 for c in chunk_results),
    }
    proof["status"] = (
        "PASS"
        if proof["union_executed_equals_collected"]
        and proof["duplicate_executions"] == 0
        and not proof["missing_nodes"]
        and not proof["failed_chunks"]
        and proof["all_exit_codes_zero"]
        else "FAIL"
    )

    (OUT / "pytest_chunks.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in proof.items() if k != "chunk_results"}, indent=2))
    if proof["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
