# ruff: noqa: E501
"""The live-aware figure/table builders must reproduce the delivered FL10 figures/tables for a completed 10-round bundle, and must never invent data for a partial one."""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path

from fl10 import charts, tables
from fl10.bundle import build_bundle
from fl10.consistency import check_chart_table
from studio import specs as studio_specs
from studio import tables as studio_tables
from studio.recorded import from_fl10_bundle

ROOT = Path(__file__).resolve().parents[1]
ADDITIVE_VIEW_KEYS = {"pending", "current_round", "planned_rounds"}


@cache
def fl10_bundle():
    return build_bundle(ROOT / "reports/fl10/runs/modeA", ROOT / "reports/fl10/eval/modeA")


def strip(view: dict) -> dict:
    out = {k: v for k, v in view.items() if k not in ADDITIVE_VIEW_KEYS}
    if view.get("id") == "pair":
        out["id"] = "r3_r10"
    for key in ("x_label",):    # deliberate wording: the reused cohort is a DIAGNOSTIC holdout, not an independent one; the optimizer-step label does not assume 2 steps/round
        if isinstance(out.get(key), str):
            out[key] = out[key].replace("Diagnostic holdout participant", "Independent holdout participant").replace("; 2 steps per round", "")
    return out


def test_completed_bundle_figures_equal_delivered_fl10_figures():
    b = fl10_bundle()
    reference = charts.build_specs(b)
    live = studio_specs.build_specs(from_fl10_bundle(b))
    assert sorted(live) == sorted(reference)
    for fid, spec in reference.items():
        mine = live[fid]
        assert mine["title"] == spec["title"].replace("independent holdout", "reused diagnostic holdout"), fid
        assert [strip(v) for v in mine["views"]] == [strip(v) for v in spec["views"]], fid


def test_completed_bundle_tables_equal_delivered_fl10_tables():
    b = fl10_bundle()
    reference = tables.build_tables(b)
    live = studio_tables.build_tables(from_fl10_bundle(b))
    assert sorted(live) == sorted(reference)
    for tid, table in reference.items():
        assert live[tid]["columns"] == table["columns"], tid
        assert live[tid]["title"] == table["title"].replace("independent evaluation", "diagnostic evaluation"), tid
        if tid == "FL10_TAB12":
            continue   # check wording is generalized; statuses are asserted below
        if tid == "FL10_TAB10":   # deliberate wording (this run / diagnostic holdout); same four evidence lanes in the same order
            assert [r[0][:2] for r in live[tid]["rows"]] == [r[0][:2] for r in table["rows"]]
            continue
        assert live[tid]["rows"] == table["rows"], tid
    assert all(row[1] == "PASS" for row in live["FL10_TAB12"]["rows"])


def test_chart_table_consistency_holds_for_the_live_builders():
    sb = from_fl10_bundle(fl10_bundle())
    specs, tabs = studio_specs.build_specs(sb), studio_tables.build_tables(sb)
    assert len(check_chart_table(specs, tabs)) >= 60


def partial(rounds_evaluated: list[int], rounds_committed: int):
    sb = copy.deepcopy(from_fl10_bundle(fl10_bundle()))
    keep = {f"R{r:02d}" for r in rounds_evaluated}
    ev = sb["evaluation"]
    ev["states"] = {k: v for k, v in ev["states"].items() if k in keep}
    ev["status"] = {f"R{r:02d}": ("COMPLETED" if f"R{r:02d}" in keep else "QUEUED") for r in range(rounds_committed + 1)}
    ev["paired"] = None
    sb["rounds"] = [r for r in sb["rounds"] if r["round"] <= rounds_committed]
    sb["client_rounds"] = [r for r in sb["client_rounds"] if r["round"] <= rounds_committed]
    sb["batches"] = [r for r in sb["batches"] if r["round"] <= rounds_committed]
    sb["state_progression"] = {k: v for k, v in sb["state_progression"].items() if int(k) <= rounds_committed}
    return sb


def test_partial_run_has_gaps_not_invented_points():
    sb = partial([0, 1, 2], 4)       # four rounds committed, only R00-R02 evaluated
    sb["run"] = {**sb["run"], "status": "RUNNING"}
    specs = studio_specs.build_specs(sb)
    auprc = next(s for s in specs["FL10_FIG04"]["views"][0]["series"] if s["name"] == "AUPRC")["y"]
    assert len(auprc) == 11 and all(v is not None for v in auprc[:3]) and all(v is None for v in auprc[3:])
    pending = {m["state"]: m["status"] for m in specs["FL10_FIG04"]["views"][0]["pending"]}
    assert pending["R03"] == "QUEUED" and pending["R10"] == "NOT_SUBMITTED" and "R02" not in pending
    loss = specs["FL10_FIG02"]["views"][0]["series"][0]["y"]
    assert all(v is not None for v in loss[:4]) and all(v is None for v in loss[4:])
    assert [s["name"].split()[0] for s in specs["FL10_FIG07"]["views"][0]["series"]] == ["R00", "R01", "R02"]
    assert specs["FL10_FIG16"]["availability"] in ("PENDING", "PARTIAL") and specs["FL10_FIG16"]["views"][0]["rows"] == []
    tabs = studio_tables.build_tables(sb)
    assert [r[0] for r in tabs["FL10_TAB01"]["rows"]] == ["R00", "R01", "R02"]
    assert tabs["FL10_TAB02"]["rows"] == [] and {row[1] for row in tabs["FL10_TAB12"]["rows"]} >= {"PENDING"}
    assert len(tabs["FL10_TAB03"]["rows"]) == 8 * 4


def test_nothing_evaluated_yet_is_pending_everywhere():
    sb = partial([], 0)
    specs = studio_specs.build_specs(sb)
    assert specs["FL10_FIG04"]["availability"] == "PENDING"
    assert all(v is None for v in specs["FL10_FIG04"]["views"][0]["series"][0]["y"])
    assert studio_tables.build_tables(sb)["FL10_TAB01"]["rows"] == []


def test_three_round_run_uses_the_r0_to_r3_comparison():
    sb = partial([0, 1, 2, 3], 3)
    sb["planned_rounds"] = sb["run_length"] = 3
    for key in [k for k in list(sb["evaluation"]["states"]) if int(k[1:]) > 3]:
        del sb["evaluation"]["states"][key]
    sb["evaluation"]["status"] = {f"R{r:02d}": "COMPLETED" for r in range(4)}
    specs = studio_specs.build_specs(sb)
    assert specs["FL10_FIG04"]["views"][0]["series"][0]["x"] == [0, 1, 2, 3]
    assert specs["FL10_FIG16"]["title"] == "Paired R3 minus R0 effects"
    assert [s["name"] for s in specs["FL10_FIG15"]["views"][0]["series"]] == ["R00", "R03"]
    assert json.dumps(specs)  # fully serializable
