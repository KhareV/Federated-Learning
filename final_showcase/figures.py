# ruff: noqa: E501
"""Reusable figure / comparison / metric-table system. Every number plotted or tabulated comes from ``research.bundle()``; nothing is typed in here.

Exports per figure: SVG, 300-dpi PNG, JSON provenance (sources, hashes, caption). Per table: CSV, JSON, Markdown. All outputs are hashed in a manifest."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from final_showcase import LANE_LABEL, research

OUT = Path("reports/final_showcase/publication")
PALETTE = {"V1": "#8a8f98", "V2": "#1f6fb2", "FedAvg": "#1f6fb2", "FedProx": "#d98324", "central": "#2f2f2f", "synthetic": "#7a3fa0"}
CONDITION_LABEL = {"iid": "IID", "label": "Label skew", "feature": "Feature skew", "quantity": "Quantity skew", "combined": "Combined"}
plt.rcParams.update({"svg.hashsalt": "nhm-final-showcase", "svg.fonttype": "none", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ResearchMetricTable:
    table_id: str
    title: str
    caption: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    sources: tuple[str, ...]
    lane: str

    def csv_bytes(self) -> bytes:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(self.columns)
        w.writerows([["" if v is None else v for v in row] for row in self.rows])
        return buf.getvalue().encode()

    def json_bytes(self) -> bytes:
        body = {"table_id": self.table_id, "title": self.title, "caption": self.caption, "lane": self.lane, "columns": list(self.columns), "rows": [list(r) for r in self.rows], "sources": list(self.sources),
                "undefined_policy": "null = not defined / not available (never zero)"}
        return (json.dumps(body, indent=1, sort_keys=True) + "\n").encode()

    def markdown_bytes(self) -> bytes:
        def cell(v: Any) -> str:
            return "UNDEFINED" if v is None else (f"{v:.4f}" if isinstance(v, float) else str(v))
        lines = [f"**{self.title}**", "", "| " + " | ".join(self.columns) + " |", "|" + "---|" * len(self.columns)]
        lines += ["| " + " | ".join(cell(v) for v in r) + " |" for r in self.rows]
        return ("\n".join(lines) + f"\n\n*{self.caption}*\n").encode()


@dataclass(frozen=True)
class ResearchComparison:
    """A named difference between two frozen quantities with the uncertainty status stated explicitly."""
    comparison_id: str
    left: str
    right: str
    rows: tuple[dict[str, Any], ...]
    uncertainty: str
    caveat: str


@dataclass(frozen=True)
class ResearchFigure:
    figure_id: str
    title: str
    caption: str
    lane: str
    sources: tuple[str, ...]
    draw: Callable[[dict[str, Any]], plt.Figure] = field(repr=False)


def _pt(b: dict[str, Any], dataset: str, model_id: str) -> dict[str, Any]:
    return next(m for m in b["models"] if m["dataset"] == dataset and m["model_id"] == model_id)


def _err(m: dict[str, Any], metric: str = "AUPRC") -> tuple[float, float]:
    ci = m["ci_95"][metric]
    return m["point"][metric] - ci["lower"], ci["upper"] - m["point"][metric]


def _footer(fig: plt.Figure, text: str) -> None:
    fig.text(0.01, 0.005, text, fontsize=6.5, color="#555", ha="left", va="bottom")


# ------------------------------------------------------------------ figures
def fig_architecture(b: dict[str, Any]) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    for i in range(8):
        y = 5.4 - i * 0.62
        ax.add_patch(plt.Rectangle((0.2, y - 0.22), 2.6, 0.44, fc="#e8f1fa", ec=PALETTE["V2"]))
        ax.text(1.5, y, f"Client {i}: local data stays here", ha="center", va="center", fontsize=7)
        ax.annotate("", xy=(4.6, 3.0), xytext=(2.8, y), arrowprops={"arrowstyle": "->", "color": "#888", "lw": 0.7})
    ax.add_patch(plt.Rectangle((4.6, 2.4), 2.2, 1.2, fc="#fdf2e4", ec=PALETTE["FedProx"]))
    ax.text(5.7, 3.0, "Coordinator\nweighted FedAvg\n(updates only)", ha="center", va="center", fontsize=8)
    ax.annotate("", xy=(8.0, 3.0), xytext=(6.8, 3.0), arrowprops={"arrowstyle": "->", "color": "#333", "lw": 1.2})
    ax.add_patch(plt.Rectangle((8.0, 2.45), 1.8, 1.1, fc="#eef7ee", ec="#2f7d32"))
    ax.text(8.9, 3.0, "New global\nstate\n→ broadcast", ha="center", va="center", fontsize=8)
    ax.text(5.0, 0.35, "Raw windows, labels and signals never leave a client; only model updates and digests cross the boundary.", ha="center", fontsize=8)
    ax.set_title("Federated learning architecture and data locality", fontsize=10)
    return fig


def fig_convergence(b: dict[str, Any]) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), sharey=True)
    for ax, algo in zip(axes, ("FedAvg", "FedProx"), strict=True):
        for cond in research.CONDITIONS:
            log = b["round_logs"][f"{algo}|{cond}"]
            xs = [s["round"] for s in log["series"]]
            ax.plot(xs, [s["validation_AUPRC"] for s in log["series"]], lw=1.2, label=CONDITION_LABEL[cond])
        ax.set_title(f"V2 {algo}", fontsize=9)
        ax.set_xlabel("Communication round")
    axes[0].set_ylabel("Development-validation AUPRC")
    axes[1].legend(fontsize=7, frameon=False)
    fig.suptitle("Scientific convergence of V2 federated training (development-validation split; not test evidence)", fontsize=9)
    return fig


def fig_heterogeneity(b: dict[str, Any]) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    for ax, dataset in zip(axes, ("INTERNAL_TEST", "INCART"), strict=True):
        ms = [_pt(b, dataset, f"V2_FEDAVG_{c.upper()}") for c in research.CONDITIONS]
        ys = [m["point"]["AUPRC"] for m in ms]
        errs = [list(e) for e in zip(*[_err(m) for m in ms], strict=True)]
        ax.errorbar(range(5), ys, yerr=errs, fmt="o", color=PALETTE["V2"], capsize=3)
        ax.set_xticks(range(5), [CONDITION_LABEL[c] for c in research.CONDITIONS], rotation=25, fontsize=7)
        ax.set_title(f"{dataset} (V2 FedAvg)", fontsize=9)
        ax.set_ylabel("AUPRC (nominal 95% patient-cluster CI)")
    fig.suptitle("Effect of controlled data heterogeneity", fontsize=10)
    return fig


def fig_fedavg_fedprox(b: dict[str, Any]) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    for ax, dataset in zip(axes, ("INTERNAL_TEST", "INCART"), strict=True):
        for k, (algo, key) in enumerate((("FedAvg", "FEDAVG"), ("FedProx", "FEDPROX"))):
            ms = [_pt(b, dataset, f"V2_{key}_{c.upper()}") for c in research.CONDITIONS]
            errs = [list(e) for e in zip(*[_err(m) for m in ms], strict=True)]
            ax.errorbar([i + (k - 0.5) * 0.2 for i in range(5)], [m["point"]["AUPRC"] for m in ms], yerr=errs, fmt="o", color=PALETTE[algo], capsize=2, label=algo)
        ax.set_xticks(range(5), [CONDITION_LABEL[c] for c in research.CONDITIONS], rotation=25, fontsize=7)
        ax.set_title(dataset, fontsize=9)
    axes[0].set_ylabel("AUPRC")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("FedAvg vs FedProx (V2; mu = 0.1)", fontsize=10)
    return fig


def fig_performance(b: dict[str, Any]) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    hist = b["historical_centralized"]
    for ax, (dataset, key) in zip(axes, (("INTERNAL_TEST", "internal_test"), ("INCART", "incart")), strict=True):
        items = [("V1 FedAvg IID", _pt(b, dataset, "V1_FEDAVG_IID"), PALETTE["V1"]), ("V2 FedAvg IID", _pt(b, dataset, "V2_FEDAVG_IID"), PALETTE["V2"])]
        for i, (name, m, color) in enumerate(items):
            ax.errorbar([i], [m["point"]["AUPRC"]], yerr=[[_err(m)[0]], [_err(m)[1]]], fmt="o", color=color, capsize=3, label=name)
        ax.scatter([2], [hist[f"MODEL_V2_FINAL_{key}"]["AUPRC"]], marker="D", color=PALETTE["central"], label="V2 centralized (historical frozen ref.)")
        ax.scatter([3], [hist[f"MODEL_V1_{key}"]["AUPRC"]], marker="D", color="#aaa", label="V1 centralized (historical frozen ref.)")
        ax.set_xticks(range(4), ["V1 FL", "V2 FL", "V2 central", "V1 central"], fontsize=7)
        ax.set_title(dataset, fontsize=9)
    axes[0].set_ylabel("AUPRC")
    axes[1].legend(fontsize=6.5, frameon=False, loc="lower right")
    fig.suptitle("Scientific performance, with historical centralized references (no paired interval for diamonds)", fontsize=9)
    return fig


def fig_synthetic(b: dict[str, Any]) -> plt.Figure:
    s = b["synthetic"]
    keys = list(s["states"])
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9))
    for metric, color in (("AUPRC", PALETTE["synthetic"]), ("AUROC", "#2a8f8f")):
        ys = [s["states"][k]["pooled"][metric] for k in keys]
        errs = [[s["states"][k]["pooled"][metric] - s["states"][k]["uncertainty"][metric]["lower"] for k in keys], [s["states"][k]["uncertainty"][metric]["upper"] - s["states"][k]["pooled"][metric] for k in keys]]
        axes[0].errorbar(range(4), ys, yerr=errs, marker="o", color=color, capsize=3, label=metric)
    axes[0].set_xticks(range(4), ["R0", "R1", "R2", "R3 cand."])
    axes[0].set_title("Holdout metrics by round (nominal CI, 8 clusters)", fontsize=8)
    axes[0].legend(frameon=False, fontsize=7)
    for k, color in zip(keys, ("#bbb", "#999", "#666", PALETTE["synthetic"]), strict=True):
        c = s["states"][k]["curves"]
        axes[1].plot([p[0] for p in c["roc"]], [p[1] for p in c["roc"]], color=color, lw=1, label=k.replace("_", " "))
        axes[2].plot([p[0] for p in c["pr"]], [p[1] for p in c["pr"]], color=color, lw=1)
    axes[1].plot([0, 1], [0, 1], ":", color="#aaa")
    axes[1].set_xlabel("False-positive rate")
    axes[1].set_ylabel("True-positive rate")
    axes[1].legend(fontsize=6, frameon=False)
    axes[2].set_xlabel("Recall")
    axes[2].set_ylabel("Precision")
    fig.suptitle(LANE_LABEL, fontsize=8, color="#7a3fa0")
    return fig


FIGURES: tuple[ResearchFigure, ...] = (
    ResearchFigure("FIG1_ARCHITECTURE", "FL architecture and data locality", "Eight clients keep raw data local; the coordinator receives updates only, aggregates by weighted FedAvg and broadcasts the new global state.", "B", ("reports/model_v2/v2_fl_004/client_data_locality_audit.json",), fig_architecture),
    ResearchFigure("FIG2_CONVERGENCE", "Scientific convergence", "Development-validation AUPRC per communication round for each controlled heterogeneity condition, from the frozen round logs.", "B", ("reports/model_v2/v2_fl_001/round_log.csv", "reports/model_v2/v2_fl_002/*_round_log.csv", "reports/model_v2/v2_fl_003/**/round_log.csv"), fig_convergence),
    ResearchFigure("FIG3_HETEROGENEITY", "Heterogeneity effect", "V2 FedAvg AUPRC under IID, label, feature, quantity and combined heterogeneity on the two frozen evaluation datasets.", "B", ("reports/model_v2/v2_fl_eval_001/internal_test_statistics.json", "reports/model_v2/v2_fl_eval_001/incart_statistics.json"), fig_heterogeneity),
    ResearchFigure("FIG4_FEDAVG_FEDPROX", "FedAvg vs FedProx", "Paired point estimates with nominal 95% patient-cluster intervals; no significance test was computed.", "B", ("reports/model_v2/v2_fl_eval_001/internal_test_statistics.json", "reports/model_v2/v2_fl_eval_001/incart_statistics.json"), fig_fedavg_fedprox),
    ResearchFigure("FIG5_PERFORMANCE", "Scientific performance incl. historical centralized reference", "Federated V1/V2 (with intervals) against the historical frozen centralized references (no interval available).", "B+H", ("reports/model_v2/v2_fl_eval_001/historical_frozen_centralized_references.json", "reports/model_v2/v2_fl_eval_001/internal_test_statistics.json", "reports/model_v2/v2_fl_eval_001/incart_statistics.json"), fig_performance),
    ResearchFigure("FIG6_SYNTHETIC", "Live sandbox federation: independent synthetic evaluation", "Rounds 0-3 of the sandbox federation on the frozen independent synthetic holdout. Threshold-free metrics rise; the fixed 0.5 operating point does not separate classes.", "C", (research.SYNTH,), fig_synthetic),
)


def tables(b: dict[str, Any]) -> list[ResearchMetricTable]:
    cols = ("model_id", "generation", "algorithm", "condition", "mu", "dataset", "AUPRC", "AUPRC_ci_lower", "AUPRC_ci_upper", "AUROC", "pooled_F1", "precision", "sensitivity", "specificity", "patient_macro_F1", "BCE", "accuracy")
    t1 = tuple((m["model_id"], m["generation"], m["algorithm"], m["condition"], m["mu"], m["dataset"], m["point"]["AUPRC"], m["ci_95"]["AUPRC"]["lower"], m["ci_95"]["AUPRC"]["upper"], m["point"]["AUROC"], m["point"]["pooled_F1"], m["point"]["precision"],
                m["point"]["sensitivity"], m["point"]["specificity"], m["point"]["patient_macro_F1"], m["point"]["BCE"], m["point"]["accuracy"]) for m in b["models"])
    comp = b["comparability"]["rows"]
    t2 = tuple((r["dataset"], r["centralized_V2_AUPRC"], r["federated_V2_FedAvg_IID_AUPRC"], r["AUPRC_difference_federated_minus_centralized"], r["centralized_V2_AUROC"], r["federated_V2_FedAvg_IID_AUROC"], r["AUROC_difference_federated_minus_centralized"]) for r in comp)
    s = b["synthetic"]["states"]
    m3 = ("AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "TP", "FP", "TN", "FN", "BCE")
    t3 = tuple((k, *[v["pooled"][m] for m in m3], v["participant_macro_F1"]) for k, v in s.items())
    t4 = tuple((k, cid, p["windows"], p["positives"], p["AUPRC"], p["AUROC"], p["F1"], p["recall"], p["specificity"], p["TP"], p["FP"], p["TN"], p["FN"]) for k, v in s.items() for cid, p in v["per_participant"].items())
    tag = LANE_LABEL
    return [
        ResearchMetricTable("TAB1_ALL_MODELS", "All 20 federated models on both frozen evaluation datasets", "Frozen one-shot FL evaluation (V2-FL-EVAL-001); AUPRC intervals are nominal 95% patient-cluster percentile intervals; no p-values.", cols, t1, ("reports/model_v2/v2_fl_eval_001/*_statistics.json",), "B"),
        ResearchMetricTable("TAB2_MAIN_COMPARISON", "Historical centralized V2 vs federated V2 (FedAvg, IID)", "Point values from frozen artifacts; differences are simple subtractions with no paired interval. Descriptive only.", ("dataset", "centralized_AUPRC", "federated_AUPRC", "AUPRC_difference", "centralized_AUROC", "federated_AUROC", "AUROC_difference"), t2, ("reports/model_v2/v2_fl_eval_001/historical_frozen_centralized_references.json",), "B+H"),
        ResearchMetricTable("TAB3_SYNTHETIC_GLOBAL", "Synthetic holdout: global states round 0 to 3", f"{tag}. Raw sigmoid threshold 0.5, no calibration. Blank = undefined.", ("state", *m3, "participant_macro_F1"), t3, (research.SYNTH,), "C"),
        ResearchMetricTable("TAB4_SYNTHETIC_PER_CLIENT", "Synthetic holdout: per held-out participant", f"{tag}. One row per state and holdout participant (mirrors site conditions).", ("state", "holdout_id", "windows", "positives", "AUPRC", "AUROC", "F1", "recall", "specificity", "TP", "FP", "TN", "FN"), t4, (research.SYNTH,), "C"),
    ]


def export_all(out: Path = OUT) -> dict[str, Any]:
    b = research.bundle()
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"schema_version": "NHM_FINAL_SHOWCASE_EXPORT_MANIFEST_V1", "bundle_schema": b["schema_version"], "figures": {}, "tables": {}}
    for fig in FIGURES:
        f = fig.draw(b)
        _footer(f, f"{fig.figure_id} · lane {fig.lane} · derived from frozen artifacts · not a clinical claim")
        files = {}
        for ext, kw in (("svg", {}), ("png", {"dpi": 300})):
            path = out / "figures" / f"{fig.figure_id}.{ext}"
            f.savefig(path, bbox_inches="tight", metadata={"Date": None, "Creator": "nhm"} if ext == "svg" else {"Software": ""}, **kw)
            files[ext] = {"path": str(path), "sha256": _sha(path.read_bytes())}
        plt.close(f)
        prov = {"figure_id": fig.figure_id, "title": fig.title, "caption": fig.caption, "lane": fig.lane, "sources": list(fig.sources), "bundle_schema": b["schema_version"]}
        pp = out / "figures" / f"{fig.figure_id}.provenance.json"
        pp.write_bytes((json.dumps(prov, indent=1, sort_keys=True) + "\n").encode())
        files["provenance"] = {"path": str(pp), "sha256": _sha(pp.read_bytes())}
        manifest["figures"][fig.figure_id] = files
    for t in tables(b):
        files = {}
        for ext, data in (("csv", t.csv_bytes()), ("json", t.json_bytes()), ("md", t.markdown_bytes())):
            path = out / "tables" / f"{t.table_id}.{ext}"
            path.write_bytes(data)
            files[ext] = {"path": str(path), "sha256": _sha(data)}
        manifest["tables"][t.table_id] = files
    (out / "export_manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    m = export_all()
    print(json.dumps({"figures": list(m["figures"]), "tables": list(m["tables"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
