# ruff: noqa: E501
"""Chart-to-table numerical consistency and graph-source completeness checks (used by the verifier and tests)."""

from __future__ import annotations

from typing import Any

import numpy as np


class ConsistencyError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}")
        self.code, self.detail = code, detail


def _col(table: dict[str, Any], name: str) -> list[Any]:
    i = table["columns"].index(name)
    return [r[i] for r in table["rows"]]


def _same(a: list[Any], b: list[Any]) -> bool:
    if len(a) != len(b):
        return False
    return all((x is None and y is None) or (x is not None and y is not None and abs(float(x) - float(y)) <= 1e-12) for x, y in zip(a, b, strict=True))


def assert_specs_have_data(specs: dict[str, dict[str, Any]], expected_ids: list[str]) -> None:
    if sorted(specs) != sorted(expected_ids):
        raise ConsistencyError("FIGURE_INVENTORY_MISMATCH", str(sorted(set(expected_ids) ^ set(specs))))
    for fid, spec in specs.items():
        if not spec["views"] or not spec["sources"]:
            raise ConsistencyError("MISSING_GRAPH_SOURCE", fid)
        for v in spec["views"]:
            has = {"lines": lambda v: any(s["x"] for s in v["series"]), "curves": lambda v: any(s["x"] for s in v["series"]), "bars": lambda v: any(s["values"] for s in v["series"]), "stacked": lambda v: any(s["values"] for s in v["series"]),
                   "heatmap": lambda v: bool(v["values"]), "confusion": lambda v: bool(v["matrices"]), "hist": lambda v: bool(v["panels"]), "intervals": lambda v: bool(v["rows"]), "diagram": lambda v: bool(v["nodes"]), "lineage": lambda v: bool(v["states"])}[v["kind"]](v)
            if not has:
                raise ConsistencyError("EMPTY_GRAPH_VIEW", f"{fid}/{v['id']}")


def check_chart_table(specs: dict[str, dict[str, Any]], tables: dict[str, dict[str, Any]]) -> dict[str, bool]:
    """Every checked chart series must equal the corresponding table column to 1e-12; raises on any mismatch."""
    t1, t3, t7 = tables["FL10_TAB01"], tables["FL10_TAB03"], tables["FL10_TAB07"]
    results: dict[str, bool] = {}

    def need(name: str, ok: bool) -> None:
        results[name] = ok
        if not ok:
            raise ConsistencyError("CHART_TABLE_MISMATCH", name)

    s4 = {s["name"]: s["y"] for s in specs["FL10_FIG04"]["views"][0]["series"]}
    need("FIG04.AUPRC", _same(s4["AUPRC"], _col(t1, "AUPRC")))
    need("FIG04.AUROC", _same(s4["AUROC"], _col(t1, "AUROC")))
    s6 = {s["name"]: s["y"] for s in specs["FL10_FIG06"]["views"][0]["series"]}
    need("FIG06.BCE", _same(s6["BCE (log loss)"], _col(t1, "BCE")))
    need("FIG06.Brier", _same(s6["Brier score"], _col(t1, "Brier")))
    s5 = {s["name"]: s["y"] for s in specs["FL10_FIG05"]["views"][0]["series"]}
    for label, col in (("F1", "F1"), ("Accuracy", "accuracy"), ("Balanced accuracy", "balanced_accuracy"), ("Sensitivity (recall)", "recall"), ("Specificity", "specificity"), ("Precision (PPV)", "precision")):
        need(f"FIG05.{col}", _same(s5[label], _col(t1, col)))
    need("FIG02.loss", _same(specs["FL10_FIG02"]["views"][0]["series"][0]["y"], _col(t7, "weighted_mean_training_loss")))
    clients = sorted(set(_col(t3, "client_id")))
    loss = {c: [r[t3["columns"].index("mean_training_loss")] for r in t3["rows"] if r[t3["columns"].index("client_id")] == c] for c in clients}
    for s, c in zip(specs["FL10_FIG03"]["views"][0]["series"], clients, strict=True):
        need(f"FIG03.{c}", _same(s["y"], loss[c]))
    w = specs["FL10_FIG13"]["views"][0]
    need("FIG13.weights_sum_to_one", all(abs(t - 1.0) < 1e-12 for t in w["total_check"]))
    for i, c in enumerate(clients):
        need(f"FIG13.{c}", _same(w["series"][i]["values"], [r[t3["columns"].index("aggregation_weight")] for r in t3["rows"] if r[t3["columns"].index("client_id")] == c]))
    v9 = specs["FL10_FIG09"]["views"][0]["matrices"]
    for m in v9:
        row = next(r for r in t1["rows"] if r[0] == m["label"])
        need(f"FIG09.{m['label']}", [m["TP"], m["FP"], m["TN"], m["FN"]] == [row[t1["columns"].index(k)] for k in ("TP", "FP", "TN", "FN")])
    t2 = tables["FL10_TAB02"]
    for r in specs["FL10_FIG16"]["views"][0]["rows"]:
        row = next(x for x in t2["rows"] if x[0] == r["label"])
        need(f"FIG16.{r['label']}", _same([r["point"], r["lo"], r["hi"]], [row[7], row[8], row[9]]))
    t5 = tables["FL10_TAB05"]
    for v in specs["FL10_FIG15"]["views"]:
        for s in v["series"]:
            col = t5["columns"].index(v["id"])
            rows = [r for r in t5["rows"] if r[0] == s["name"]]
            need(f"FIG15.{v['id']}.{s['name']}", _same(s["values"], [r[col] for r in rows]))
    summary_columns = {
        "AUPRC": "AUPRC", "AUROC": "AUROC", "F1": "F1",
        "Balanced acc.": "balanced_accuracy", "Sensitivity": "recall",
        "Specificity": "specificity", "BCE": "BCE",
        "Predicted +": "predicted_positives", "Predicted -": "predicted_negatives",
    }
    for v in specs["FL10_FIG20"]["views"]:
        for s in v["series"]:
            row = next(r for r in t1["rows"] if r[0] == s["name"])
            need(
                f"FIG20.{v['id']}.{s['name']}",
                _same(s["values"], [row[t1["columns"].index(summary_columns[c])]
                                    for c in v["categories"]]),
            )
    arr = np.array([[np.nan if x is None else x for x in row] for row in specs["FL10_FIG12"]["views"][0]["values"]], dtype=float)
    need("FIG12.shape", arr.shape == (8, 10))
    return results
