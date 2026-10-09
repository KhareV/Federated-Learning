# ruff: noqa: E501
"""Live-aware chart specifications for a 3- or 10-round run with PARTIAL evaluation.

Same spec schema as ``fl10.charts`` (so the same renderer and the same matplotlib exporter serve it) and the same figure ids/titles. Differences, all additive:
x axes cover every planned round; an unevaluated state is ``None`` (a gap) and is listed in the view's ``pending`` markers with its status; curve/confusion/histogram
views exist only for states that were genuinely scored; ``availability`` states whether the figure is AVAILABLE, PARTIAL or PENDING. Nothing is extrapolated.
A parity test builds this from the recorded FL10 Mode A run and requires the numeric payload to equal ``fl10.charts.build_specs``."""

from __future__ import annotations

from typing import Any

from fl10.inventory import FIGURES

THRESHOLD_METRICS = [("F1", "F1"), ("accuracy", "Accuracy"), ("balanced_accuracy", "Balanced accuracy"), ("recall", "Sensitivity (recall)"), ("specificity", "Specificity"), ("precision", "Precision (PPV)")]
LOW = "SIM_FL_"


def skey(r: int) -> str:
    return f"R{r:02d}"


def figure_title(fid: str, n: int) -> str:
    base = next(t for i, t, _ in FIGURES if i == fid)
    word = {3: "Three", 10: "Ten"}.get(n, str(n))
    cmp_a, cmp_b = comparison_pair(n)
    return (base.replace("Ten-round", f"{word}-round").replace("R0-R10", f"R0-R{n}")
            .replace("R10 minus R3", f"R{cmp_b} minus R{cmp_a}"))


def comparison_pair(n: int) -> tuple[int, int]:
    """Same-cohort paired comparison: R3 -> R10 for the extended run, initial R0 -> final R3 for the default run."""
    return (3, 10) if n == 10 else (0, n)


class Ctx:
    def __init__(self, b: dict[str, Any], selected: int | None = None) -> None:
        self.b, self.n = b, int(b["planned_rounds"])
        self.rounds = list(range(1, self.n + 1))
        self.xs = list(range(self.n + 1))
        self.states = [skey(r) for r in self.xs]
        ev = b["evaluation"]
        self.ev, self.evs = ev, ev["states"]
        self.status = ev.get("status", {})
        self.cmp_a, self.cmp_b = comparison_pair(self.n)
        self.selected = selected
        committed = {r["round"] for r in b["rounds"]}
        self.committed = sorted(committed)
        cr = b["client_rounds"]
        self.clients = sorted({r["client_id"] for r in cr} | {c["client_id"] for c in b.get("training_cohort", [])})
        self.cr = cr

    def has(self, s: str) -> bool:
        return s in self.evs

    def pooled(self, s: str) -> dict[str, Any] | None:
        return self.evs[s]["pooled"] if s in self.evs else None

    def metric(self, s: str, key: str) -> Any:
        p = self.pooled(s)
        return None if p is None else p.get(key)

    def metric_series(self, key: str) -> list[Any]:
        return [self.metric(s, key) for s in self.states]

    def pending_markers(self) -> list[dict[str, Any]]:
        return [{"x": i, "state": s, "status": self.status.get(s, "NOT_SUBMITTED")} for i, s in enumerate(self.states) if s not in self.evs]

    def by_cr(self, field: str) -> dict[str, dict[int, Any]]:
        out: dict[str, dict[int, Any]] = {c: {} for c in self.clients}
        for r in self.cr:
            out[r["client_id"]][r["round"]] = r[field]
        return out

    @property
    def prevalence(self) -> float | None:
        for s in self.states:
            p = self.pooled(s)
            if p is not None:
                return p["prevalence"]
        return None


def _line(name: str, xs: list[Any], ys: list[Any], *, dashed: bool = False, default: bool = True) -> dict[str, Any]:
    return {"name": name, "x": xs, "y": ys, "dashed": dashed, "default": default}


def _availability(spec: dict[str, Any], c: Ctx, *, needs: list[str] | None = None, note: str | None = None) -> None:
    needed = needs if needs is not None else c.states
    present = sum(1 for s in needed if s in c.evs)
    spec["availability"] = "AVAILABLE" if present == len(needed) and needed else ("PENDING" if present == 0 and needed else "PARTIAL")
    spec["availability_detail"] = note or (f"{present} of {len(needed)} required evaluated states available" if needed else "run data")


def build_specs(b: dict[str, Any], selected: int | None = None) -> dict[str, dict[str, Any]]:
    c = Ctx(b, selected)
    n, rounds, xs, clients = c.n, c.rounds, c.xs, c.clients
    prevalence = c.prevalence
    specs: dict[str, dict[str, Any]] = {}
    rr = b["rounds"]
    rr_by = {r["round"]: r for r in rr}
    windows = b["evaluation"]["windows"]

    def add(fid: str, caption: str, sources: list[str], views: list[dict[str, Any]], *, group: str | None = None, note: str | None = None, needs: list[str] | None = None, none_needed: bool = False,
            availability_note: str | None = None) -> None:
        specs[fid] = {"id": fid, "title": figure_title(fid, n), "caption": caption, "sources": sources, "views": views, "note": note, "group": group or next(g for i, _, g in FIGURES if i == fid), "synthetic_label": b["synthetic_label"]}
        if none_needed:
            specs[fid]["availability"] = "AVAILABLE" if (views and views[0].get("kind") == "diagram") or any(_has_data(v) for v in views) else "PENDING"
            specs[fid]["availability_detail"] = availability_note or "from committed rounds"
        else:
            _availability(specs[fid], c, needs=needs, note=availability_note)

    def lines_view(vid: str, label: str, x_label: str, y_label: str, series: list[dict[str, Any]], *, pending: bool = True) -> dict[str, Any]:
        view = {"id": vid, "label": label, "kind": "lines", "x_label": x_label, "y_label": y_label, "series": series}
        if pending:
            view["pending"] = c.pending_markers()
        return view

    # 01 architecture ---------------------------------------------------------------------------------------------------------------
    nodes = [{"id": cl, "label": f"{cl.replace(LOW, '')}: local data stays here", "kind": "client"} for cl in clients]
    add("FL10_FIG01", f"Eight logical clients (single machine) train locally for one epoch, submit updates, and the coordinator applies weighted FedAvg for {n} round{'s' if n != 1 else ''}; the highlighted round is the latest committed one.",
        ["run_report.json"], [{"id": "diagram", "label": "Architecture", "kind": "diagram", "nodes": nodes, "monitoring": "optional simulated ECG monitoring session -> SITE_00 buffer (Mode B)",
                               "stages": ["local optimizer (AdamW, 1 epoch)", "update submission (digest, example count)", "weighted FedAvg (Coordinator)", f"global model R00 -> R{n:02d}", "final engineering candidate (not promoted)"],
                               "current_round": max(c.committed) if c.committed else 0, "planned_rounds": n}], none_needed=True)
    # 02 global loss ----------------------------------------------------------------------------------------------------------------
    add("FL10_FIG02", "Example-weighted mean of the eight clients' actual local training losses per round (training data, not independent evaluation).", ["rounds.csv"],
        [lines_view("loss", "Weighted training loss", "Communication round", "Weighted mean local training loss (BCE, pos_weight applied)",
                    [_line("weighted mean training loss", rounds, [rr_by[r]["weighted_mean_training_loss"] if r in rr_by else None for r in rounds])], pending=False)], none_needed=True, availability_note=f"{len(rr)} of {n} rounds committed")
    # 03 per-client loss ------------------------------------------------------------------------------------------------------------
    loss = c.by_cr("mean_training_loss")
    add("FL10_FIG03", "Each client's actual mean local training loss per round (training data).", ["client_rounds.csv"],
        [lines_view("client_loss", "Per-client training loss", "Communication round", "Mean local training loss", [_line(cl.replace(LOW, ""), rounds, [loss[cl].get(r) for r in rounds]) for cl in clients], pending=False)],
        none_needed=True, availability_note=f"{len(rr)} of {n} rounds committed")
    # 04 AUPRC / AUROC --------------------------------------------------------------------------------------------------------------
    add("FL10_FIG04", f"AUPRC and AUROC of every EVALUATED global state on the SAME diagnostic holdout ({windows} windows, 16 participants); dashed line = AUPRC chance level (positive prevalence). {b['evaluation']['cohort_use']} No round was selected from these values.",
        ["evaluation_results.json"], [lines_view("rank", "AUPRC and AUROC", "Global state (round)", "Metric value",
                                                 [_line("AUPRC", xs, c.metric_series("AUPRC")), _line("AUROC", xs, c.metric_series("AUROC")), _line("AUPRC chance level (prevalence)", xs, [prevalence] * (n + 1) if prevalence is not None else [None] * (n + 1), dashed=True)])])
    # 05 threshold metrics ----------------------------------------------------------------------------------------------------------
    thr = [_line(label, xs, c.metric_series(key)) for key, label in THRESHOLD_METRICS]
    add("FL10_FIG05", "Threshold-dependent metrics at the predeclared fixed rule (raw sigmoid probability >= 0.5, no calibration). Gaps are UNDEFINED metrics (reason in the table) or states whose evaluation is still pending.", ["evaluation_results.json"],
        [lines_view("all", "All metrics", "Global state (round)", "Metric value at threshold 0.5", thr),
         *[lines_view(key, label, "Global state (round)", label, [_line(label, xs, c.metric_series(key))]) for key, label in THRESHOLD_METRICS]])
    # 06 BCE / Brier ----------------------------------------------------------------------------------------------------------------
    add("FL10_FIG06", "Unweighted binary cross-entropy (from logits) and Brier score (mean squared probability error) on the diagnostic holdout. Lower is better; both are independent of the 0.5 threshold.", ["evaluation_results.json"],
        [lines_view("both", "BCE and Brier", "Global state (round)", "Loss value (lower is better)", [_line("BCE (log loss)", xs, c.metric_series("BCE")), _line("Brier score", xs, c.metric_series("Brier"))])])
    # 07 ROC / 08 PR ----------------------------------------------------------------------------------------------------------------
    default_curves = {skey(0), skey(c.cmp_a), skey(c.cmp_b)} | ({skey(selected)} if selected is not None else set())
    evaluated = [s for s in c.states if s in c.evs and c.evs[s].get("curves")]
    add("FL10_FIG07", "Genuine ROC curves from the holdout predictions of each evaluated state; the selected round and the comparison endpoints are shown by default. AUROC in the legend.", ["holdout_predictions.csv"],
        [{"id": "roc", "label": "ROC", "kind": "curves", "x_label": "False-positive rate", "y_label": "True-positive rate (sensitivity)", "diagonal": True, "pending": c.pending_markers(), "series": [
            {"name": f"{s} (AUROC {c.evs[s]['pooled']['AUROC']:.4f})", "x": [p[0] for p in c.evs[s]["curves"]["roc"]], "y": [p[1] for p in c.evs[s]["curves"]["roc"]], "default": s in default_curves} for s in evaluated]}])
    add("FL10_FIG08", "Genuine precision-recall curves; legend shows average precision (non-interpolated), not a trapezoidal area. Dashed line = positive prevalence.", ["holdout_predictions.csv"],
        [{"id": "pr", "label": "Precision-recall", "kind": "curves", "x_label": "Recall", "y_label": "Precision", "hline": prevalence, "hline_label": "positive prevalence", "pending": c.pending_markers(), "series": [
            {"name": f"{s} (AP {c.evs[s]['pooled']['AUPRC']:.4f})", "x": [p[0] for p in c.evs[s]["curves"]["pr"]], "y": [p[1] for p in c.evs[s]["curves"]["pr"]], "default": s in default_curves} for s in evaluated]}])

    def cm(s: str) -> dict[str, Any]:
        p = c.evs[s]["pooled"]
        return {"label": s, "TP": p["TP"], "FP": p["FP"], "TN": p["TN"], "FN": p["FN"], "n": p["windows"], "positives": p["positives"], "negatives": p["negatives"]}

    pair_present = [skey(r) for r in (c.cmp_a, c.cmp_b) if skey(r) in c.evs]
    add("FL10_FIG09", "Confusion matrices at the fixed 0.5 rule on the diagnostic holdout (raw counts; row-normalised view available). Population size shown.", ["evaluation_results.json"],
        [*([{"id": "pair", "label": f"R{c.cmp_a:02d} versus R{c.cmp_b:02d}", "kind": "confusion", "matrices": [cm(s) for s in pair_present]}] if pair_present else []), *[{"id": s, "label": s, "kind": "confusion", "matrices": [cm(s)]} for s in c.states if s in c.evs]])

    def hist(s: str) -> dict[str, Any]:
        h = c.evs[s]["pooled"]["histogram"]
        return {"name": s, "edges": h["edges"], "positive": h["positive"], "negative": h["negative"]}

    bins = b["protocol"]["probability_histogram"]["bins"]
    add("FL10_FIG10", f"Predicted-probability distributions of actual positive and negative synthetic windows; {bins} equal-width bins on [0, 1] fixed in the protocol before any outcome existed. The dashed line is the 0.5 decision threshold.", ["holdout_predictions.csv"],
        [*([{"id": "pair", "label": f"R{c.cmp_a:02d} versus R{c.cmp_b:02d}", "kind": "hist", "threshold": 0.5, "panels": [hist(s) for s in pair_present]}] if pair_present else []), *[{"id": s, "label": s, "kind": "hist", "threshold": 0.5, "panels": [hist(s)]} for s in c.states if s in c.evs]])
    # 11 contribution matrix --------------------------------------------------------------------------------------------------------
    acc, status = c.by_cr("examples_processed"), c.by_cr("acceptance_status")
    add("FL10_FIG11", "Accepted-update matrix: cell value = examples contributed by the client's ACCEPTED update in that round (blank = no accepted update yet).", ["client_rounds.csv"],
        [{"id": "accepted", "label": "Accepted update (examples)", "kind": "heatmap", "rows": [cl.replace(LOW, "") for cl in clients], "cols": [f"R{r}" for r in rounds],
          "values": [[acc[cl].get(r) if status[cl].get(r) == "ACCEPTED" else None for r in rounds] for cl in clients], "value_label": "examples in accepted update"}], none_needed=True, availability_note=f"{len(rr)} of {n} rounds committed")

    # 12 training heatmap -----------------------------------------------------------------------------------------------------------
    def hm(field: str, label: str) -> dict[str, Any]:
        m = c.by_cr(field)
        return {"id": field, "label": label, "kind": "heatmap", "rows": [cl.replace(LOW, "") for cl in clients], "cols": [f"R{r}" for r in rounds], "values": [[m[cl].get(r) for r in rounds] for cl in clients], "value_label": label}

    add("FL10_FIG12", "Client x round training diagnostics from the actual run.", ["client_rounds.csv"], [hm("mean_training_loss", "Mean training loss"), hm("local_update_norm", "Local update L2 norm"), hm("examples_processed", "Examples processed"), hm("gradient_norm_mean", "Mean gradient L2 norm")],
        none_needed=True, availability_note=f"{len(rr)} of {n} rounds committed")
    # 13 weights --------------------------------------------------------------------------------------------------------------------
    w = c.by_cr("aggregation_weight")
    add("FL10_FIG13", "FedAvg aggregation weights = accepted example count / total accepted examples; each completed round sums to one.", ["client_rounds.csv", "rounds.csv"],
        [{"id": "weights", "label": "Aggregation weights", "kind": "stacked", "x_label": "Communication round", "y_label": "Normalised weight", "categories": [f"R{r}" for r in rounds],
          "series": [{"name": cl.replace(LOW, ""), "values": [w[cl].get(r) for r in rounds]} for cl in clients], "total_check": [sum(w[cl][r] for cl in clients) if all(r in w[cl] for cl in clients) else None for r in rounds]}], none_needed=True, availability_note=f"{len(rr)} of {n} rounds committed")
    # 14 dataset composition --------------------------------------------------------------------------------------------------------
    cohort = {x["client_id"]: x["counts"] for x in b["training_cohort"]}
    hold = b["evaluation"]["holdout_participants"]
    add("FL10_FIG14", "Training composition per client (TRAIN) and diagnostic-holdout composition per participant (EVALUATION). Training and holdout are separate populations that never overlap.", ["training_cohort.json", "holdout_manifest_v1.json"],
        [{"id": "training", "label": "Training: positives / negatives", "kind": "bars", "categories": [cl.replace(LOW, "") for cl in clients], "x_label": "Training client", "y_label": "Windows",
          "series": [{"name": "positive", "values": [cohort[cl]["synthetic_positive"] for cl in clients]}, {"name": "negative", "values": [cohort[cl]["synthetic_negative"] for cl in clients]}]},
         {"id": "holdout", "label": "Holdout: positives / negatives", "kind": "bars", "categories": [h["participant_id"] for h in hold], "x_label": "Diagnostic holdout participant", "y_label": "Windows",
          "series": [{"name": "positive", "values": [h["counts"]["synthetic_positive"] for h in hold]}, {"name": "negative", "values": [h["counts"]["synthetic_negative"] for h in hold]}]},
         {"id": "quality_train", "label": "Training quality: eligible vs excluded", "kind": "bars", "categories": [cl.replace(LOW, "") for cl in clients], "x_label": "Training client", "y_label": "Windows",
          "series": [{"name": "quality-eligible", "values": [cohort[cl]["trainable"] for cl in clients]}, {"name": "excluded (degraded)", "values": [cohort[cl]["DEGRADED"] for cl in clients]}, {"name": "excluded (unusable)", "values": [cohort[cl]["UNUSABLE"] for cl in clients]}]},
         {"id": "quality_holdout", "label": "Holdout quality: eligible vs excluded", "kind": "bars", "categories": [h["participant_id"] for h in hold], "x_label": "Diagnostic holdout participant", "y_label": "Windows",
          "series": [{"name": "quality-eligible", "values": [h["counts"]["trainable"] for h in hold]}, {"name": "excluded (degraded)", "values": [h["counts"]["DEGRADED"] for h in hold]}, {"name": "excluded (unusable)", "values": [h["counts"]["UNUSABLE"] for h in hold]}]}],
        none_needed=True, availability_note="source-backed cohort evidence")
    # 15 participant-level ----------------------------------------------------------------------------------------------------------
    pids = [h["participant_id"] for h in hold]
    wanted = [s for s in dict.fromkeys([skey(c.cmp_a), *( [skey(selected)] if selected is not None else []), skey(c.cmp_b)]) if s in c.evs]

    def pview(metric: str, label: str) -> dict[str, Any]:
        return {"id": metric, "label": label, "kind": "bars", "categories": pids, "x_label": "Diagnostic holdout participant", "y_label": label,
                "series": [{"name": s, "values": [c.evs[s]["participants"][p][metric] for p in pids]} for s in wanted]}

    add("FL10_FIG15", "Per diagnostic-holdout participant, for the comparison endpoints (and the selected round). Undefined values are shown as UNDEFINED, never averaged as zero.", ["participant_metrics.csv"],
        [pview("AUPRC", "AUPRC"), pview("AUROC", "AUROC"), pview("F1", "F1"), pview("recall", "Sensitivity (recall)"), pview("specificity", "Specificity")], needs=[skey(c.cmp_a), skey(c.cmp_b)])
    # 16 paired effects -------------------------------------------------------------------------------------------------------------
    paired = c.ev.get("paired")
    rows16 = ([{"label": m, "point": v["difference_point"], "lo": v["difference_interval"]["lower"], "hi": v["difference_interval"]["upper"], "valid": v["difference_interval"]["valid_replicates"], "invalid": v["invalid_replicates"]}
               for m, v in paired["metrics"].items()] if paired else [])
    add("FL10_FIG16", (f"Paired R{c.cmp_b:02d} minus R{c.cmp_a:02d} differences with nominal 95% paired participant-cluster percentile intervals ({paired['replicates']} replicates, {paired['clusters']} clusters). Zero line shown. Not a significance test."
                       if paired else f"Paired R{c.cmp_b:02d} minus R{c.cmp_a:02d} effects on the same holdout. PENDING: both states must be evaluated first."), ["evaluation_results.json"],
        [{"id": "paired", "label": "Paired differences", "kind": "intervals", "x_label": f"R{c.cmp_b:02d} - R{c.cmp_a:02d}", "rows": rows16}], needs=[skey(c.cmp_a), skey(c.cmp_b)],
        availability_note="paired comparison ready" if paired else "needs both comparison states evaluated")
    # 17 communication --------------------------------------------------------------------------------------------------------------
    dur = c.by_cr("client_duration_seconds")
    add("FL10_FIG17", "Measured logical update payload bytes (serialized size on the single-machine transport, not network traffic), measured client and round wall-clock durations, and cumulative accepted updates.", ["rounds.csv", "client_rounds.csv"],
        [lines_view("bytes", "Payload bytes by round", "Communication round", "Logical payload bytes", [_line("payload bytes (round)", rounds, [rr_by[r]["update_payload_bytes_total"] if r in rr_by else None for r in rounds]),
                                                                                                    _line("cumulative payload bytes", rounds, [rr_by[r]["cumulative_payload_bytes"] if r in rr_by else None for r in rounds])], pending=False),
         lines_view("client_time", "Client durations", "Communication round", "Seconds (wall clock)", [_line(cl.replace(LOW, ""), rounds, [dur[cl].get(r) for r in rounds]) for cl in clients], pending=False),
         lines_view("round_time", "Round durations", "Communication round", "Seconds (wall clock)", [_line("round duration", rounds, [rr_by[r]["round_duration_seconds"] if r in rr_by else None for r in rounds])], pending=False),
         lines_view("updates", "Cumulative accepted updates", "Communication round", "Accepted updates", [_line("cumulative accepted updates", rounds, [rr_by[r]["cumulative_accepted_updates"] if r in rr_by else None for r in rounds])], pending=False)],
        none_needed=True, availability_note=f"{len(rr)} of {n} rounds committed")
    # 18 lineage --------------------------------------------------------------------------------------------------------------------
    prog = b["state_progression"]
    lineage = ([{"state": "R00", "sha256": prog["0"]["sha256"], "previous": None, "accepted_updates": 0, "status": "FL_INIT_V2 (initial state)", "equals_frozen_reference": True}] if "0" in prog else [])
    for r in rr:
        parity = (r.get("parity") or {}).get("equals_frozen_reference")
        lineage.append({"state": f"R{r['round']:02d}", "sha256": r["global_state_sha256"], "previous": r["base_state_sha256"], "accepted_updates": r["accepted_updates"], "status": r["candidate_status"], "equals_frozen_reference": parity})
    add("FL10_FIG18", f"Linked lineage of the global states committed so far: each state's base is the previous committed state; R01-R03 are compared with the frozen canonical 3-round digests where a frozen reference exists; R{n:02d} is the single final engineering candidate (not promoted, not deployed).", ["run_report.json"],
        [{"id": "lineage", "label": "State lineage", "kind": "lineage", "states": lineage}], none_needed=True, availability_note=f"{len(lineage)} of {n + 1} states committed")

    # 19 per-batch ------------------------------------------------------------------------------------------------------------------
    def batch_view(field: str, label: str) -> dict[str, Any]:
        series = []
        for cl in clients:
            rows = sorted((x for x in b["batches"] if x["client_id"] == cl), key=lambda x: (x["round"], x["batch_index"]))
            series.append(_line(cl.replace(LOW, ""), [i + 1 for i in range(len(rows))], [x[field] for x in rows]))
        return {"id": field, "label": label, "kind": "lines", "x_label": "Optimizer step (cumulative per client)", "y_label": label, "series": series}

    add("FL10_FIG19", "Actual per-batch loss and gradient L2 norm captured by the read-only optimizer hooks (no inferred points).", ["batches.csv"], [batch_view("loss", "Batch loss"), batch_view("gradient_l2_norm", "Gradient L2 norm")],
        none_needed=True, availability_note="captured batches" if b["batches"] else "no batch captured yet")
    # 20 summary --------------------------------------------------------------------------------------------------------------------
    summary_states = [s for s in dict.fromkeys([skey(0), skey(c.cmp_a), *( [skey(selected)] if selected is not None else []), skey(c.cmp_b)]) if s in c.evs]
    groups = [("rates", "Ranking and fixed-threshold rates", "Rate (0-1)", [("AUPRC", "AUPRC"), ("AUROC", "AUROC"), ("F1", "F1"), ("balanced_accuracy", "Balanced acc."), ("recall", "Sensitivity"), ("specificity", "Specificity")]),
              ("loss", "Unweighted BCE", "Log loss", [("BCE", "BCE")]), ("counts", "Predicted class counts", "Windows", [("predicted_positives", "Predicted +"), ("predicted_negatives", "Predicted -")])]
    add("FL10_FIG20", "Integrated summary of the evaluated comparison states (initial, comparison endpoints, selected round) on the diagnostic holdout. Ranking and fixed-threshold metrics are shown together with the actual counts of predicted positives and negatives.", ["evaluation_results.json"],
        [{"id": gid, "label": label, "kind": "bars", "categories": [name for _, name in keys], "x_label": "Metric", "y_label": units, "series": [{"name": s, "values": [c.metric(s, key) for key, _ in keys]} for s in summary_states]} for gid, label, units, keys in groups],
        needs=[skey(0), skey(c.cmp_a), skey(c.cmp_b)])
    return specs


def _has_data(view: dict[str, Any]) -> bool:
    kind = view["kind"]
    if kind in ("lines", "curves"):
        return any(any(v is not None for v in (s.get("y") or [])) for s in view["series"])
    if kind == "bars":
        return any(s["values"] for s in view["series"])
    if kind == "stacked":
        return any(any(v is not None for v in s["values"]) for s in view["series"])
    if kind == "heatmap":
        return any(any(v is not None for v in row) for row in view["values"])
    if kind == "lineage":
        return bool(view["states"])
    return True
