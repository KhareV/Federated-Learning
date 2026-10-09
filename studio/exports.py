# ruff: noqa: E501
"""Run-specific publication exports (SVG, 300-dpi PNG, CSV, JSON provenance for every figure; CSV/JSON/Markdown for every table) generated from THIS run's verified
bundle. Reuses the FL10 matplotlib drawing code and table writer; a recorded FL10 figure is never exported under a live run id."""

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
from fl10 import figures as fl10_figures
from studio.specs import build_specs
from studio.tables import build_tables

EXPORT_VIEWS = {"FL10_FIG05": ["all"], "FL10_FIG09": ["pair"], "FL10_FIG10": ["pair"]}
SCHEMA = "STUDIO_EXPORT_MANIFEST_V1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def render(spec: dict[str, Any], b: dict[str, Any]) -> plt.Figure:
    panels = _panels(spec)
    if not panels:
        panels = [({"id": "pending", "label": "pending", "kind": "lines", "x_label": "", "y_label": "", "series": []}, None)]
    cols = min(3, len(panels)) if len(panels) > 1 else 1
    rows = int(np.ceil(len(panels) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(5.2 * cols, 3.6 * rows + 0.5), squeeze=False)
    for ax in axes.ravel()[len(panels):]:
        ax.axis("off")
    for ax, (view, sub) in zip(axes.ravel(), panels, strict=False):
        fl10_figures._draw(ax, view, sub)
    fig.suptitle(f"{spec['id']} - {spec['title']}", fontsize=9)
    fig.text(0.01, 0.003, f"{b['synthetic_label']} | run {b['run_id']} ({b['run_length']} rounds, {b['engine']}) | {b['source_label']} | {fl10_figures.UNDEFINED_NOTE}", fontsize=5.5, color="#7a3fa0", ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    return fig


def export_run(b: dict[str, Any], out: Path, *, eval_dir: Path | None = None, run_dir: Path | None = None) -> dict[str, Any]:
    specs, tables = build_specs(b), build_tables(b)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)
    source_hashes: dict[str, str] = {}
    data: dict[str, Any] = {}
    if run_dir is not None:
        for name in ("run_report.json", "client_rounds.csv", "batches.csv", "rounds.csv", "updates.csv"):
            if (run_dir / name).exists():
                source_hashes[name] = _sha((run_dir / name).read_bytes())
    if eval_dir is not None and eval_dir.is_dir():
        for path in sorted(eval_dir.glob("R*/*")) + [eval_dir / "paired.json"]:
            if path.is_file():
                source_hashes[str(path.relative_to(eval_dir))] = _sha(path.read_bytes())
    manifest: dict[str, Any] = {"schema_version": SCHEMA, "run_id": b["run_id"], "run_length": b["run_length"], "engine": b["engine"], "mode": b["mode"], "source_label": b["source_label"], "bundle_schema": b["schema_version"],
                                "protocol_sha256": b["protocol"]["sha256"], "evaluation_protocol_id": b["protocol"]["evaluation_protocol_id"], "cohort_use": b["evaluation"]["cohort_use"], "revision": b.get("revision"),
                                "source_hashes": source_hashes, "figures": {}, "tables": {}, "data": {}}
    for fid, spec in specs.items():
        fig = render(spec, b)
        files: dict[str, Any] = {}
        for ext, kw in (("svg", {}), ("png", {"dpi": 300})):
            path = out / "figures" / f"{fid}.{ext}"
            fig.savefig(path, bbox_inches="tight", metadata={"Date": None, "Creator": "nhm-studio"} if ext == "svg" else {"Software": ""}, **kw)
            files[ext] = {"path": str(path.relative_to(out)), "sha256": _sha(path.read_bytes())}
        plt.close(fig)
        rows = fl10_figures.flatten(spec)
        cols = list(dict.fromkeys(k for r in rows for k in r))
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        cpath = out / "figures" / f"{fid}.csv"
        cpath.write_bytes(buf.getvalue().encode())
        files["csv"] = {"path": str(cpath.relative_to(out)), "sha256": _sha(cpath.read_bytes()), "rows": len(rows)}
        prov = {"figure_id": fid, "title": spec["title"], "caption": spec["caption"], "synthetic_label": b["synthetic_label"], "sources": spec["sources"], "source_hashes": source_hashes, "run_id": b["run_id"], "run_length": b["run_length"],
                "engine": b["engine"], "source_label": b["source_label"], "availability": spec.get("availability"), "availability_detail": spec.get("availability_detail"), "threshold": "raw sigmoid >= 0.5 where applicable",
                "views": [v["id"] for v in spec["views"]], "exported_views": EXPORT_VIEWS.get(fid, "all"), "spec_sha256": _sha(json.dumps(spec, sort_keys=True, default=str).encode()),
                "evaluation_cohort": b["evaluation"]["cohort_use"] if spec["group"] == "evaluation" else None, "training_vs_evaluation": "evaluation" if spec["group"] == "evaluation" else "training/federation"}
        ppath = out / "figures" / f"{fid}.provenance.json"
        ppath.write_bytes((json.dumps(prov, indent=1, sort_keys=True) + "\n").encode())
        files["provenance"] = {"path": str(ppath.relative_to(out)), "sha256": _sha(ppath.read_bytes())}
        manifest["figures"][fid] = files
    for tid, t in tables.items():
        rt = ResearchMetricTable(tid, t["title"], t["caption"], tuple(t["columns"]), tuple(tuple(r) for r in t["rows"]), tuple(t["sources"]), "C")
        files = {}
        for ext, blob in (("csv", rt.csv_bytes()), ("json", rt.json_bytes()), ("md", rt.markdown_bytes())):
            path = out / "tables" / f"{tid}.{ext}"
            path.write_bytes(blob)
            files[ext] = {"path": str(path.relative_to(out)), "sha256": _sha(blob)}
        manifest["tables"][tid] = files
    if eval_dir is not None and eval_dir.is_dir():     # machine-readable full-precision evaluation evidence of THIS run
        records = [json.loads(p.read_text()) for p in sorted(eval_dir.glob("R*/record.json"))]
        blob = (json.dumps({"run_id": b["run_id"], "cohort_use": b["evaluation"]["cohort_use"], "records": records}, indent=1, sort_keys=True) + "\n").encode()
        (out / "data" / "evaluation_records.json").write_bytes(blob)
        data["evaluation_records"] = {"json": {"path": "data/evaluation_records.json", "sha256": _sha(blob)}}
        for path in sorted(eval_dir.glob("R*/predictions.csv")):
            target = out / "data" / f"predictions_{path.parent.name}.csv"
            target.write_bytes(path.read_bytes())
            data[f"predictions_{path.parent.name}"] = {"csv": {"path": f"data/{target.name}", "sha256": _sha(target.read_bytes())}}
    if run_dir is not None and (run_dir / "run_report.json").exists():
        target = out / "data" / "run_report.json"
        target.write_bytes((run_dir / "run_report.json").read_bytes())
        data["run_report"] = {"json": {"path": "data/run_report.json", "sha256": _sha(target.read_bytes())}}
    manifest["data"] = data
    (out / "export_manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest
