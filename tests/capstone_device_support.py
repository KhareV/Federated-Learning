"""Shared helpers for the CAP-002 tests (cached replays, invariant checkers, AST scanner)."""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Sequence
from functools import cache
from itertools import pairwise
from typing import Any

from product.devices.replay import run_replay
from product.devices.scenarios import ScenarioSpec, load_scenarios
from simulation.types import ObservedRecord

TRUTH_MODULES = {"simulation.truth_v2013", "simulation.fl_cohort_truth_v1"}
TRUTH_NAMES = {"SimulationTruth", "get_truth"}


@cache
def scenario(scenario_id: str) -> ScenarioSpec:
    return load_scenarios()[scenario_id]


@cache
def replay(scenario_id: str) -> dict[str, Any]:
    return run_replay(scenario(scenario_id))


def drain(async_iterator: Any) -> list[Any]:
    async def collect() -> list[Any]:
        return [item async for item in async_iterator]

    return asyncio.run(collect())


def scan_source_for_truth(source: str) -> set[str]:
    """Names/modules of SimulationTruth-side code imported by a source text."""
    hits: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported = {a.name for a in node.names}
            if module in TRUTH_MODULES or imported & TRUTH_NAMES:
                hits.add(module)
            if module == "simulation" and imported & {"truth_v2013", "fl_cohort_truth_v1"}:
                hits.add(module)
        elif isinstance(node, ast.Import):
            hits |= {a.name for a in node.names if a.name in TRUTH_MODULES}
    return hits


def check_records_ordered(records: Sequence[ObservedRecord]) -> bool:
    return all(b.sample_index > a.sample_index and b.timestamp_us > a.timestamp_us
               for a, b in pairwise(records))


def check_only_observed_records(items: Sequence[object]) -> bool:
    return all(type(item) is ObservedRecord for item in items)


def check_no_delivery_in_outages(records: Sequence[ObservedRecord],
                                 outages: Sequence[tuple[int, int]]) -> bool:
    return not any(start <= r.sample_index < end for r in records for start, end in outages)
