# ruff: noqa: E501
"""Chart specifications (the ONLY place figure data is assembled). The same spec drives the matplotlib exports and the Svelte renderer, so a chart can never disagree with its table.
A value of None means UNDEFINED or NOT CAPTURED and is rendered as a gap with an explicit label, never as zero."""

from __future__ import annotations

from typing import Any

from fl10.inventory import FIGURES

RSTATES = [f"R{r:02d}" for r in range(11)]
THRESHOLD_METRICS = [("F1", "F1"), ("accuracy", "Accuracy"), ("balanced_accuracy", "Balanced accuracy"), ("recall", "Sensitivity (recall)"), ("specificity", "Specificity"), ("precision", "Precision (PPV)")]


def _pooled(b: dict[str, Any], s: str) -> dict[str, Any]:
    return b["evaluation"]["states"][s]["pooled"]


def _line(name: str, xs: list[Any], ys: list[Any], *, dashed: bool = False, default: bool = True, lo: list[Any] | None = None, hi: list[Any] | None = None) -> dict[str, Any]:
    return {"name": name, "x": xs, "y": ys, "dashed": dashed, "default": default, **({"lo": lo, "hi": hi} if lo is not None else {})}


def _clients(b: dict[str, Any]) -> list[str]:
    return sorted({r["client_id"] for r in b["client_rounds"]})


def _by_cr(b: dict[str, Any], field: str) -> dict[str, dict[int, Any]]:
    out: dict[str, dict[int, Any]] = {c: {} for c in _clients(b)}
    for r in b["client_rounds"]:
        out[r["client_id"]][r["round"]] = r[field]
    return out


def build_specs(b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rounds = list(range(1, 11))
    clients = _clients(b)
    prevalence = _pooled(b, "R00")["prevalence"]
    specs: dict[str, dict[str, Any]] = {}

    def add(fid: str, caption: str, sources: list[str], views: list[dict[str, Any]], group: str | None = None, note: str | None = None) -> None:
        title = next(t for i, t, _ in FIGURES if i == fid)
        specs[fid] = {"id": fid, "title": title, "caption": caption, "sources": sources, "views": views, "note": note, "group": group or next(g for i, _, g in FIGURES if i == fid)}

    # 01 architecture ----------------------------------------------------------------------------------------------------------------
    nodes = [{"id": c, "label": f"{c.replace('SIM_FL_', '')}: local data stays here", "kind": "client"} for c in clients]
    add("FL10_FIG01", "Eight logical clients (single machine) train locally for one epoch, submit updates, and the coordinator applies weighted FedAvg for ten rounds; SITE_00 may optionally be fed by one live-monitored simulated ECG session. This is an architecture illustration, not a claim of cross-institution federation.",
        ["run_report.json"], [{"id": "diagram", "label": "Architecture", "kind": "diagram", "nodes": nodes, "monitoring": "optional simulated ECG monitoring session -> SITE_00 buffer (Mode B)",
                               "stages": ["local optimizer (AdamW, 1 epoch)", "update submission (digest, example count)", "weighted FedAvg (Coordinator)", "global model R00 -> R10", "final engineering candidate (not promoted)"]}])
    # 02 global loss -----------------------------------------------------------------------------------------------------------------
    add("FL10_FIG02", "Example-weighted mean of the eight clients' actual local training losses per round (training data, not independent evaluation).", ["rounds.csv"],
        [{"id": "loss", "label": "Weighted training loss", "kind": "lines", "x_label": "Communication round", "y_label": "Weighted mean local training loss (BCE, pos_weight applied)", "series": [_line("weighted mean training loss", rounds, [r["weighted_mean_training_loss"] for r in b["rounds"]])]}])
    # 03 per-client loss -------------------------------------------------------------------------------------------------------------
    loss = _by_cr(b, "mean_training_loss")
    add("FL10_FIG03", "Each client's actual mean local training loss per round (training data).", ["client_rounds.csv"],
        [{"id": "client_loss", "label": "Per-client training loss", "kind": "lines", "x_label": "Communication round", "y_label": "Mean local training loss", "series": [_line(c.replace("SIM_FL_", ""), rounds, [loss[c].get(r) for r in rounds]) for c in clients]}])
    # 04 AUPRC / AUROC ---------------------------------------------------------------------------------------------------------------
    xs = list(range(11))
    add("FL10_FIG04", f"AUPRC and AUROC of every global state on the SAME fresh independent holdout ({b['evaluation']['windows']} windows, 16 participants); dashed line = AUPRC chance level (positive prevalence). No round was selected on this holdout.",
        ["evaluation_results.json"], [{"id": "rank", "label": "AUPRC and AUROC", "kind": "lines", "x_label": "Global state (round)", "y_label": "Metric value", "series": [
            _line("AUPRC", xs, [_pooled(b, s)["AUPRC"] for s in RSTATES]), _line("AUROC", xs, [_pooled(b, s)["AUROC"] for s in RSTATES]), _line("AUPRC chance level (prevalence)", xs, [prevalence] * 11, dashed=True)]}])
    # 05 threshold metrics -----------------------------------------------------------------------------------------------------------
    thr = [_line(label, xs, [_pooled(b, s)[key] for s in RSTATES]) for key, label in THRESHOLD_METRICS]
    add("FL10_FIG05", "Threshold-dependent metrics at the predeclared fixed rule (raw sigmoid probability >= 0.5, no calibration) on the independent holdout. Gaps are UNDEFINED metrics (e.g. precision when nothing is predicted positive).",
        ["evaluation_results.json"], [{"id": "all", "label": "All metrics", "kind": "lines", "x_label": "Global state (round)", "y_label": "Metric value at threshold 0.5", "series": thr},
                                      *[{"id": key, "label": label, "kind": "lines", "x_label": "Global state (round)", "y_label": label, "series": [_line(label, xs, [_pooled(b, s)[key] for s in RSTATES])]} for key, label in THRESHOLD_METRICS]])
    # 06 BCE / Brier -----------------------------------------------------------------------------------------------------------------
    add("FL10_FIG06", "Unweighted binary cross-entropy (from logits) and Brier score (mean squared probability error) on the independent holdout. Lower is better; both are probability-quality measures independent of the 0.5 threshold.",
        ["evaluation_results.json"], [{"id": "both", "label": "BCE and Brier", "kind": "lines", "x_label": "Global state (round)", "y_label": "Loss value (lower is better)", "series": [
            _line("BCE (log loss)", xs, [_pooled(b, s)["BCE"] for s in RSTATES]), _line("Brier score", xs, [_pooled(b, s)["Brier"] for s in RSTATES])]}])
    # 07 ROC / 08 PR -----------------------------------------------------------------------------------------------------------------
    states = b["evaluation"]["states"]
    default_curves = {"R00", "R03", "R10"}
    add("FL10_FIG07", "Genuine ROC curves from the independent-holdout predictions. R00, R03 and R10 are shown by default; every intermediate round can be toggled. AUROC in the legend.", ["holdout_predictions.csv"],
        [{"id": "roc", "label": "ROC", "kind": "curves", "x_label": "False-positive rate", "y_label": "True-positive rate (sensitivity)", "diagonal": True, "series": [
            {"name": f"{s} (AUROC {states[s]['pooled']['AUROC']:.4f})", "x": [p[0] for p in states[s]["curves"]["roc"]], "y": [p[1] for p in states[s]["curves"]["roc"]], "default": s in default_curves} for s in RSTATES]}])
    add("FL10_FIG08", "Genuine precision-recall curves; legend shows average precision (non-interpolated, sum of (R_n - R_{n-1}) P_n), not a trapezoidal area. Dashed line = positive prevalence.", ["holdout_predictions.csv"],
        [{"id": "pr", "label": "Precision-recall", "kind": "curves", "x_label": "Recall", "y_label": "Precision", "hline": prevalence, "hline_label": "positive prevalence", "series": [
            {"name": f"{s} (AP {states[s]['pooled']['AUPRC']:.4f})", "x": [p[0] for p in states[s]["curves"]["pr"]], "y": [p[1] for p in states[s]["curves"]["pr"]], "default": s in default_curves} for s in RSTATES]}])

    def cm(s: str) -> dict[str, Any]:
        p = _pooled(b, s)
        return {"label": s, "TP": p["TP"], "FP": p["FP"], "TN": p["TN"], "FN": p["FN"], "n": p["windows"], "positives": p["positives"], "negatives": p["negatives"]}

    add("FL10_FIG09", "Confusion matrices at the fixed 0.5 rule on the independent holdout (raw counts; row-normalised view available). Population size shown.", ["evaluation_results.json"],
        [{"id": "r3_r10", "label": "R03 versus R10", "kind": "confusion", "matrices": [cm("R03"), cm("R10")]}, *[{"id": s, "label": s, "kind": "confusion", "matrices": [cm(s)]} for s in RSTATES]])

    def hist(s: str) -> dict[str, Any]:
        h = _pooled(b, s)["histogram"]
        return {"name": s, "edges": h["edges"], "positive": h["positive"], "negative": h["negative"]}

    add("FL10_FIG10", f"Predicted-probability distributions of actual positive and negative synthetic windows; {b['protocol']['probability_histogram']['bins']} equal-width bins on [0, 1] fixed in the protocol before any outcome existed. Vertical line = fixed threshold 0.5.",
        ["holdout_predictions.csv"], [{"id": "r3_r10", "label": "R03 versus R10", "kind": "hist", "threshold": 0.5, "panels": [hist("R03"), hist("R10")]}, *[{"id": s, "label": s, "kind": "hist", "threshold": 0.5, "panels": [hist(s)]} for s in RSTATES]])
    # 11 contribution matrix ---------------------------------------------------------------------------------------------------------
    acc = _by_cr(b, "examples_processed")
    status = _by_cr(b, "acceptance_status")
    add("FL10_FIG11", "Accepted-update matrix: cell value = examples contributed by the client's ACCEPTED update in that round (null would mean no accepted update).", ["client_rounds.csv"],
        [{"id": "accepted", "label": "Accepted update (examples)", "kind": "heatmap", "rows": [c.replace("SIM_FL_", "") for c in clients], "cols": [f"R{r}" for r in rounds],
          "values": [[acc[c][r] if status[c][r] == "ACCEPTED" else None for r in rounds] for c in clients], "value_label": "examples in accepted update"}])
    # 12 training heatmap ------------------------------------------------------------------------------------------------------------
    def hm(field: str, label: str) -> dict[str, Any]:
        m = _by_cr(b, field)
        return {"id": field, "label": label, "kind": "heatmap", "rows": [c.replace("SIM_FL_", "") for c in clients], "cols": [f"R{r}" for r in rounds], "values": [[m[c].get(r) for r in rounds] for c in clients], "value_label": label}

    add("FL10_FIG12", "Client x round training diagnostics from the actual runs.", ["client_rounds.csv"], [hm("mean_training_loss", "Mean training loss"), hm("local_update_norm", "Local update L2 norm"), hm("examples_processed", "Examples processed"), hm("gradient_norm_mean", "Mean gradient L2 norm")])
    # 13 weights ---------------------------------------------------------------------------------------------------------------------
    w = _by_cr(b, "aggregation_weight")
    add("FL10_FIG13", "FedAvg aggregation weights = accepted example count / total accepted examples; each completed round sums to one.", ["client_rounds.csv", "rounds.csv"],
        [{"id": "weights", "label": "Aggregation weights", "kind": "stacked", "x_label": "Communication round", "y_label": "Normalised weight", "categories": [f"R{r}" for r in rounds],
          "series": [{"name": c.replace("SIM_FL_", ""), "values": [w[c][r] for r in rounds]} for c in clients], "total_check": [sum(w[c][r] for c in clients) for r in rounds]}])
    # 14 dataset composition ---------------------------------------------------------------------------------------------------------
    first = {r["client_id"]: r for r in b["client_rounds"] if r["round"] == 1}
    hold = b["evaluation"]["holdout_participants"]
    add("FL10_FIG14", "Training composition per client (TRAIN) and independent-holdout composition per participant (EVALUATION). Training and holdout are separate populations that never overlap.", ["client_rounds.csv", "holdout_manifest_v1.json"],
        [{"id": "training", "label": "Training: positives / negatives", "kind": "bars", "categories": [c.replace("SIM_FL_", "") for c in clients], "x_label": "Training client", "y_label": "Windows",
          "series": [{"name": "positive", "values": [first[c]["positive_labels"] for c in clients]}, {"name": "negative", "values": [first[c]["negative_labels"] for c in clients]}]},
         {"id": "holdout", "label": "Holdout: positives / negatives", "kind": "bars", "categories": [h["participant_id"] for h in hold], "x_label": "Independent holdout participant", "y_label": "Windows",
          "series": [{"name": "positive", "values": [h["counts"]["synthetic_positive"] for h in hold]}, {"name": "negative", "values": [h["counts"]["synthetic_negative"] for h in hold]}]},
         {"id": "quality_train", "label": "Training quality: eligible vs excluded", "kind": "bars", "categories": [c.replace("SIM_FL_", "") for c in clients], "x_label": "Training client", "y_label": "Windows",
          "series": [{"name": "quality-eligible", "values": [first[c]["quality_eligible_windows"] for c in clients]}, {"name": "excluded (degraded)", "values": [first[c]["excluded_degraded"] for c in clients]},
                     {"name": "excluded (unusable)", "values": [first[c]["excluded_unusable"] for c in clients]}]},
         {"id": "quality_holdout", "label": "Holdout quality: eligible vs excluded", "kind": "bars", "categories": [h["participant_id"] for h in hold], "x_label": "Independent holdout participant", "y_label": "Windows",
          "series": [{"name": "quality-eligible", "values": [h["counts"]["trainable"] for h in hold]}, {"name": "excluded (degraded)", "values": [h["counts"]["DEGRADED"] for h in hold]},
                     {"name": "excluded (unusable)", "values": [h["counts"]["UNUSABLE"] for h in hold]}]}])
    # 15 participant-level -----------------------------------------------------------------------------------------------------------
    pids = [h["participant_id"] for h in hold]

    def pview(metric: str, label: str) -> dict[str, Any]:
        return {"id": metric, "label": label, "kind": "bars", "categories": pids, "x_label": "Independent holdout participant", "y_label": label,
                "series": [{"name": s, "values": [states[s]["participants"][p][metric] for p in pids]} for s in ("R03", "R10")]}

    add("FL10_FIG15", "R03 versus R10 per independent holdout participant. Undefined values are shown as UNDEFINED, never averaged as zero.", ["participant_metrics.csv"],
        [pview("AUPRC", "AUPRC"), pview("AUROC", "AUROC"), pview("F1", "F1"), pview("recall", "Sensitivity (recall)"), pview("specificity", "Specificity")])
    # 16 paired effects --------------------------------------------------------------------------------------------------------------
    pm = b["evaluation"]["paired"]["metrics"]
    add("FL10_FIG16", f"Paired R10 minus R03 differences with nominal 95% paired participant-cluster percentile intervals ({b['evaluation']['paired']['replicates']} replicates, 16 clusters). Zero line shown. Not a significance test; no multiplicity adjustment.",
        ["evaluation_results.json"], [{"id": "paired", "label": "Paired differences", "kind": "intervals", "x_label": "R10 - R03", "rows": [{"label": m, "point": v["difference_point"], "lo": v["difference_interval"]["lower"], "hi": v["difference_interval"]["upper"],
                                                                                                                                     "valid": v["difference_interval"]["valid_replicates"], "invalid": v["invalid_replicates"]} for m, v in pm.items()]}])
    # 17 communication ---------------------------------------------------------------------------------------------------------------
    dur = _by_cr(b, "client_duration_seconds")
    rr = b["rounds"]
    add("FL10_FIG17", "Measured logical update payload bytes (serialized size on the single-machine transport, not network traffic), measured client and round wall-clock durations, and cumulative accepted updates.", ["rounds.csv", "client_rounds.csv"],
        [{"id": "bytes", "label": "Payload bytes by round", "kind": "lines", "x_label": "Communication round", "y_label": "Logical payload bytes", "series": [_line("payload bytes (round)", rounds, [r["update_payload_bytes_total"] for r in rr]), _line("cumulative payload bytes", rounds, [r["cumulative_payload_bytes"] for r in rr])]},
         {"id": "client_time", "label": "Client durations", "kind": "lines", "x_label": "Communication round", "y_label": "Seconds (wall clock)", "series": [_line(c.replace("SIM_FL_", ""), rounds, [dur[c].get(r) for r in rounds]) for c in clients]},
         {"id": "round_time", "label": "Round durations", "kind": "lines", "x_label": "Communication round", "y_label": "Seconds (wall clock)", "series": [_line("round duration", rounds, [r["round_duration_seconds"] for r in rr])]},
         {"id": "updates", "label": "Cumulative accepted updates", "kind": "lines", "x_label": "Communication round", "y_label": "Accepted updates", "series": [_line("cumulative accepted updates", rounds, [r["cumulative_accepted_updates"] for r in rr])]}])
    # 18 lineage ---------------------------------------------------------------------------------------------------------------------
    prog = b["state_progression"]
    lineage = [{"state": "R00", "sha256": prog["0"]["sha256"], "previous": None, "accepted_updates": 0, "status": "FL_INIT_V2 (initial state)", "equals_frozen_reference": True}]
    for r in rr:
        rid = r["round"]
        parity = (r.get("parity") or {}).get("equals_frozen_reference")
        lineage.append({"state": f"R{rid:02d}", "sha256": r["global_state_sha256"], "previous": r["base_state_sha256"], "accepted_updates": r["accepted_updates"], "status": r["candidate_status"], "equals_frozen_reference": parity})
    add("FL10_FIG18", "Linked lineage of the eleven global states: each state's base is the previous committed state; R01-R03 are compared with the frozen canonical 3-round digests; R10 is the single final engineering candidate (not promoted).", ["run_report.json"],
        [{"id": "lineage", "label": "State lineage", "kind": "lineage", "states": lineage}])
    # 19 per-batch -------------------------------------------------------------------------------------------------------------------
    def batch_view(field: str, label: str) -> dict[str, Any]:
        series = []
        for c in clients:
            rows = sorted((x for x in b["batches"] if x["client_id"] == c), key=lambda x: (x["round"], x["batch_index"]))
            series.append(_line(c.replace("SIM_FL_", ""), [i + 1 for i in range(len(rows))], [x[field] for x in rows]))
        return {"id": field, "label": label, "kind": "lines", "x_label": "Optimizer step (cumulative per client; 2 steps per round)", "y_label": label, "series": series}

    add("FL10_FIG19", "Actual per-batch loss and gradient L2 norm captured by the read-only optimizer hooks (no inferred points).", ["batches.csv"], [batch_view("loss", "Batch loss"), batch_view("gradient_l2_norm", "Gradient L2 norm")])
    # 20 summary ---------------------------------------------------------------------------------------------------------------------
    metric_groups = [
        ("rates", "Ranking and fixed-threshold rates", "Rate (0-1)",
         [("AUPRC", "AUPRC"), ("AUROC", "AUROC"), ("F1", "F1"),
          ("balanced_accuracy", "Balanced acc."), ("recall", "Sensitivity"),
          ("specificity", "Specificity")]),
        ("loss", "Unweighted BCE", "Log loss", [("BCE", "BCE")]),
        ("counts", "Predicted class counts", "Windows",
         [("predicted_positives", "Predicted +"),
          ("predicted_negatives", "Predicted -")]),
    ]
    add("FL10_FIG20", "Integrated summary of R00, R03 and R10 on the independent holdout. Ranking metrics and fixed-threshold metrics are shown together with the actual counts of predicted positives and negatives.", ["evaluation_results.json"],
        [{"id": group_id, "label": label, "kind": "bars",
          "categories": [name for _, name in keys], "x_label": "Metric", "y_label": units,
          "series": [{"name": state, "values": [_pooled(b, state)[key] for key, _ in keys]}
                     for state in ("R00", "R03", "R10")]}
         for group_id, label, units, keys in metric_groups])
    for spec in specs.values():
        spec["synthetic_label"] = b["synthetic_label"]
    return specs
