# ruff: noqa: E501
"""Exports for the 20 figures and 12 tables: SVG, 300-dpi PNG, source-data CSV and JSON provenance per figure; CSV/JSON/Markdown per table; one hash manifest.
Drawing consumes ONLY the chart specs from fl10.charts (the same specs the app renders)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from final_showcase.figures import ResearchMetricTable
from fl10.charts import build_specs
from fl10.tables import build_tables

plt.rcParams.update({"svg.hashsalt": "nhm-fl10", "svg.fonttype": "none", "font.size": 8, "axes.spines.top": False, "axes.spines.right": False})
PALETTE = ["#1f6fb2", "#d98324", "#2f7d32", "#7a3fa0", "#c0392b", "#2a8f8f", "#8a6d3b", "#555555", "#e377c2", "#17becf", "#bcbd22"]
EXPORT_VIEWS = {"FL10_FIG05": ["all"], "FL10_FIG09": ["r3_r10"], "FL10_FIG10": ["r3_r10"]}   # other figures export every view; CSV always contains ALL views
UNDEFINED_NOTE = "Gaps = UNDEFINED or NOT CAPTURED (never zero)."


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _nan(values: list[Any]) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in values], dtype=float)


def _panels(spec: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    chosen = EXPORT_VIEWS.get(spec["id"])
    panels: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for view in spec["views"]:
        if chosen is not None and view["id"] not in chosen:
            continue
        if view["kind"] == "confusion":
            panels += [(view, m) for m in view["matrices"]]
        elif view["kind"] == "hist":
            panels += [(view, h) for h in view["panels"]]
        else:
            panels.append((view, None))
    return panels


def _draw(ax: Any, view: dict[str, Any], sub: dict[str, Any] | None) -> None:
    kind = view["kind"]
    if kind in ("lines", "curves"):
        n = 0
        for i, s in enumerate(view["series"]):
            if not s.get("default", True):
                continue
            ax.plot(s["x"], _nan(s["y"]), marker="o" if kind == "lines" else None, ms=3, lw=1.2, ls="--" if s.get("dashed") else "-", color=PALETTE[i % len(PALETTE)], label=s["name"], drawstyle="steps-post" if kind == "curves" and view["id"] == "pr" else "default")
            n += 1
        if view.get("diagonal"):
            ax.plot([0, 1], [0, 1], ":", color="#aaa")
        if view.get("hline") is not None:
            ax.axhline(view["hline"], ls="--", color="#999", lw=0.8, label=view.get("hline_label"))
        ax.set_xlabel(view["x_label"])
        ax.set_ylabel(view["y_label"])
        ax.legend(fontsize=6, frameon=False)
    elif kind == "bars":
        cats, series = view["categories"], view["series"]
        width = 0.8 / max(1, len(series))
        x = np.arange(len(cats))
        for i, s in enumerate(series):
            vals = _nan(s["values"])
            ax.bar(x + i * width, np.nan_to_num(vals), width, color=PALETTE[i % len(PALETTE)], label=s["name"])
            for j, v in enumerate(vals):
                if np.isnan(v):
                    ax.text(x[j] + i * width, 0, "U", ha="center", va="bottom", fontsize=5, color="#c0392b")
        ax.set_xticks(x + width * (len(series) - 1) / 2, cats, rotation=60 if len(cats) > 8 else 0, fontsize=5, ha="right" if len(cats) > 8 else "center")
        ax.set_xlabel(view["x_label"])
        ax.set_ylabel(view["y_label"])
        ax.legend(fontsize=6, frameon=False)
    elif kind == "stacked":
        bottom = np.zeros(len(view["categories"]))
        for i, s in enumerate(view["series"]):
            vals = np.array(s["values"], dtype=float)
            ax.bar(view["categories"], vals, bottom=bottom, color=PALETTE[i % len(PALETTE)], label=s["name"])
            bottom += vals
        ax.set_xlabel(view["x_label"])
        ax.set_ylabel(view["y_label"])
        ax.legend(fontsize=5, frameon=False, ncol=2)
    elif kind == "heatmap":
        data = np.ma.masked_invalid(np.array([[np.nan if v is None else v for v in row] for row in view["values"]], dtype=float))
        im = ax.imshow(data, aspect="auto", cmap="viridis")
        ax.set_xticks(range(len(view["cols"])), view["cols"], fontsize=6)
        ax.set_yticks(range(len(view["rows"])), view["rows"], fontsize=6)
        for r in range(data.shape[0]):
            for c in range(data.shape[1]):
                ax.text(c, r, "NC" if data.mask[r, c] else f"{data[r, c]:.3g}", ha="center", va="center", fontsize=4.5, color="white")
        ax.figure.colorbar(im, ax=ax, label=view["value_label"], fraction=0.04)
    elif kind == "hist":
        assert sub is not None
        edges = np.array(sub["edges"])
        centers = (edges[:-1] + edges[1:]) / 2
        w = edges[1] - edges[0]
        ax.bar(centers, sub["negative"], w * 0.95, alpha=0.6, color=PALETTE[0], label="actual negative")
        ax.bar(centers, sub["positive"], w * 0.95, alpha=0.6, color=PALETTE[1], label="actual positive")
        ax.axvline(view["threshold"], color="k", ls="--", lw=1, label="threshold 0.5")
        ax.set_title(sub["name"], fontsize=8)
        ax.set_xlabel("Predicted probability (sigmoid of raw logit)")
        ax.set_ylabel("Windows")
        ax.legend(fontsize=6, frameon=False)
    elif kind == "confusion":
        assert sub is not None
        m = np.array([[sub["TP"], sub["FN"]], [sub["FP"], sub["TN"]]], dtype=float)
        ax.imshow(m, cmap="Blues")
        for r in range(2):
            for c in range(2):
                total = m[r].sum()
                ax.text(c, r, f"{int(m[r, c])}\n({m[r, c] / total:.1%} of row)" if total else f"{int(m[r, c])}", ha="center", va="center", fontsize=8, color="black")
        ax.set_xticks([0, 1], ["pred +", "pred -"])
        ax.set_yticks([0, 1], ["actual +", "actual -"])
        ax.set_title(f"{sub['label']}  (N={sub['n']}; TP {sub['TP']} FP {sub['FP']} TN {sub['TN']} FN {sub['FN']})", fontsize=6)
    elif kind == "intervals":
        rows = view["rows"]
        y = np.arange(len(rows))
        pts = _nan([r["point"] for r in rows])
        lo, hi = _nan([r["lo"] for r in rows]), _nan([r["hi"] for r in rows])
        ax.errorbar(pts, y, xerr=[np.nan_to_num(pts - lo), np.nan_to_num(hi - pts)], fmt="o", capsize=3, color=PALETTE[0])
        ax.axvline(0, color="k", lw=0.8)
        ax.set_yticks(y, [r["label"] for r in rows], fontsize=6)
        ax.set_xlabel(view["x_label"] + " (nominal 95% paired participant-cluster interval)")
    elif kind == "diagram":
        ax.axis("off")
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        for i, n in enumerate(view["nodes"]):
            y = 9.2 - i * 1.0
            ax.add_patch(plt.Rectangle((0.1, y - 0.35), 3.4, 0.7, fc="#e8f1fa", ec=PALETTE[0]))
            ax.text(1.8, y, n["label"], ha="center", va="center", fontsize=6)
            ax.annotate("", xy=(4.6, 5), xytext=(3.5, y), arrowprops={"arrowstyle": "->", "color": "#888", "lw": 0.6})
        ax.text(1.8, 9.9, view["monitoring"], ha="center", fontsize=6, color=PALETTE[3])
        for i, stage in enumerate(view["stages"]):
            ax.add_patch(plt.Rectangle((4.6, 8.4 - i * 1.8), 5.2, 1.1, fc="#fdf2e4", ec=PALETTE[1]))
            ax.text(7.2, 8.95 - i * 1.8, stage, ha="center", va="center", fontsize=7)
    elif kind == "lineage":
        ax.axis("off")
        ax.set_xlim(0, 10)
        ax.set_ylim(0, len(view["states"]))
        for i, s in enumerate(view["states"]):
            y = len(view["states"]) - 1 - i + 0.5
            ref = {True: "= frozen reference", False: "DIFFERS from frozen reference", None: ""}[s["equals_frozen_reference"]]
            ax.text(0.1, y, f"{s['state']}  sha256 {s['sha256'][:20]}...  prev {(s['previous'] or 'FL_INIT_V2')[:12]}...  accepted {s['accepted_updates']}  {s['status']} {ref}", fontsize=5.5, va="center")
            if i:
                ax.annotate("", xy=(0.05, y + 0.45), xytext=(0.05, y + 0.05), arrowprops={"arrowstyle": "<-", "lw": 0.5})
    if kind in ("lines", "curves", "bars", "heatmap", "stacked") and view.get("label"):
        ax.set_title(view["label"], fontsize=8)


def flatten(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """ALL views, all points: the source data behind the figure."""
    rows: list[dict[str, Any]] = []
    for v in spec["views"]:
        base = {"figure": spec["id"], "view": v["id"]}
        if v["kind"] in ("lines", "curves"):
            for s in v["series"]:
                for x, y in zip(s["x"], s["y"], strict=True):
                    rows.append({**base, "series": s["name"], "x": x, "y": "" if y is None else y})
        elif v["kind"] in ("bars", "stacked"):
            for s in v["series"]:
                for c, val in zip(v["categories"], s["values"], strict=True):
                    rows.append({**base, "series": s["name"], "category": c, "value": "" if val is None else val})
        elif v["kind"] == "heatmap":
            for r, row in zip(v["rows"], v["values"], strict=True):
                for c, val in zip(v["cols"], row, strict=True):
                    rows.append({**base, "row": r, "col": c, "value": "" if val is None else val})
        elif v["kind"] == "confusion":
            rows += [{**base, "state": m["label"], "TP": m["TP"], "FP": m["FP"], "TN": m["TN"], "FN": m["FN"], "n": m["n"]} for m in v["matrices"]]
        elif v["kind"] == "hist":
            for p in v["panels"]:
                for i in range(len(p["positive"])):
                    rows.append({**base, "state": p["name"], "bin_lower": p["edges"][i], "bin_upper": p["edges"][i + 1], "positive": p["positive"][i], "negative": p["negative"][i]})
        elif v["kind"] == "intervals":
            rows += [{**base, "metric": r["label"], "point": "" if r["point"] is None else r["point"], "lower": "" if r["lo"] is None else r["lo"], "upper": "" if r["hi"] is None else r["hi"], "valid_replicates": r["valid"], "invalid_replicates": r["invalid"]} for r in v["rows"]]
        elif v["kind"] == "lineage":
            rows += [{**base, **s} for s in v["states"]]
        elif v["kind"] == "diagram":
            rows += [{**base, "node": n["id"], "label": n["label"]} for n in v["nodes"]] + [{**base, "node": f"stage{i}", "label": s} for i, s in enumerate(v["stages"])]
    return rows


def render(spec: dict[str, Any], b: dict[str, Any]) -> plt.Figure:
    panels = _panels(spec)
    cols = min(3, len(panels)) if len(panels) > 1 else 1
    rows = int(np.ceil(len(panels) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(5.2 * cols, 3.6 * rows + 0.5), squeeze=False)
    for ax in axes.ravel()[len(panels):]:
        ax.axis("off")
    for ax, (view, sub) in zip(axes.ravel(), panels, strict=False):
        _draw(ax, view, sub)
    fig.suptitle(f"{spec['id']} - {spec['title']}", fontsize=9)
    fig.text(0.01, 0.003, f"{b['synthetic_label']} | run {b['run_id']} (mode {b['mode']}) | {UNDEFINED_NOTE}", fontsize=5.5, color="#7a3fa0", ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    return fig


def export_all(b: dict[str, Any], out: Path) -> dict[str, Any]:
    specs = build_specs(b)
    tables = build_tables(b)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"schema_version": "NHM_FL10_EXPORT_MANIFEST_V1", "run_id": b["run_id"], "mode": b["mode"], "bundle_schema": b["schema_version"], "protocol_sha256": b["protocol"]["sha256"],
                                "source_hashes": {**b["run_files"], **b["evaluation_files"]}, "figures": {}, "tables": {}}
    for fid, spec in specs.items():
        fig = render(spec, b)
        files: dict[str, Any] = {}
        for ext, kw in (("svg", {}), ("png", {"dpi": 300})):
            path = out / "figures" / f"{fid}.{ext}"
            fig.savefig(path, bbox_inches="tight", metadata={"Date": None, "Creator": "nhm-fl10"} if ext == "svg" else {"Software": ""}, **kw)
            files[ext] = {"path": str(path), "sha256": _sha(path.read_bytes())}
        plt.close(fig)
        rows = flatten(spec)
        cols = list(dict.fromkeys(k for r in rows for k in r))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        cpath = out / "figures" / f"{fid}.csv"
        cpath.write_bytes(buf.getvalue().encode())
        files["csv"] = {"path": str(cpath), "sha256": _sha(cpath.read_bytes()), "rows": len(rows)}
        prov = {"figure_id": fid, "title": spec["title"], "caption": spec["caption"], "synthetic_label": b["synthetic_label"], "sources": spec["sources"], "source_hashes": manifest["source_hashes"], "run_id": b["run_id"], "mode": b["mode"],
                "threshold": "raw sigmoid >= 0.5 where applicable", "views": [v["id"] for v in spec["views"]], "exported_views": EXPORT_VIEWS.get(fid, "all"), "spec_sha256": _sha(json.dumps(spec, sort_keys=True, default=str).encode()),
                "evaluation_cohort": "16 independent synthetic participants" if spec["group"] in ("evaluation",) else None, "training_vs_evaluation": "evaluation" if spec["group"] == "evaluation" else "training/federation" if spec["group"] in ("evolution", "federation", "diagnostics") else spec["group"]}
        ppath = out / "figures" / f"{fid}.provenance.json"
        ppath.write_bytes((json.dumps(prov, indent=1, sort_keys=True) + "\n").encode())
        files["provenance"] = {"path": str(ppath), "sha256": _sha(ppath.read_bytes())}
        manifest["figures"][fid] = files
    for tid, t in tables.items():
        rt = ResearchMetricTable(tid, t["title"], t["caption"], tuple(t["columns"]), tuple(tuple(r) for r in t["rows"]), tuple(t["sources"]), "C")
        files = {}
        for ext, data in (("csv", rt.csv_bytes()), ("json", rt.json_bytes()), ("md", rt.markdown_bytes())):
            path = out / "tables" / f"{tid}.{ext}"
            path.write_bytes(data)
            files[ext] = {"path": str(path), "sha256": _sha(data)}
        manifest["tables"][tid] = files
    (out / "export_manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    import argparse

    from fl10.bundle import build_bundle

    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="reports/fl10/runs/modeA")
    ap.add_argument("--eval", default="reports/fl10/eval/modeA")
    ap.add_argument("--out", default="reports/fl10/publication/modeA")
    a = ap.parse_args()
    m = export_all(build_bundle(Path(a.run), Path(a.eval)), Path(a.out))
    print(json.dumps({"figures": len(m["figures"]), "tables": len(m["tables"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
