# ruff: noqa: E501
"""The twelve predeclared tables, assembled from the single bundle. Machine-readable outputs keep full precision; None = UNDEFINED / NOT CAPTURED."""

from __future__ import annotations

from typing import Any

from fl10.inventory import METRIC_DEFINITIONS, TABLES

RSTATES = [f"R{r:02d}" for r in range(11)]
GLOBAL_COLS = ["AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "negative_predictive_value", "false_positive_rate", "false_negative_rate", "false_discovery_rate", "false_omission_rate", "MCC",
               "TP", "FP", "TN", "FN", "total_predictions", "predicted_positives", "predicted_negatives", "windows", "positives", "negatives", "prevalence", "BCE", "Brier", "mean_predicted_probability", "mean_score_positive_class",
               "mean_score_negative_class", "score_min", "score_max"]
PART_COLS = ["windows", "positives", "negatives", "AUPRC", "AUROC", "F1", "precision", "recall", "specificity", "balanced_accuracy", "accuracy", "TP", "FP", "TN", "FN", "BCE", "Brier"]


def _undef(m: dict[str, Any]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in m["undefined"].items())


def build_tables(b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ev = b["evaluation"]
    states = ev["states"]
    out: dict[str, dict[str, Any]] = {}

    def add(tid: str, columns: list[str], rows: list[list[Any]], caption: str, sources: list[str]) -> None:
        title = next(t for i, t in TABLES if i == tid)
        out[tid] = {"id": tid, "title": title, "columns": columns, "rows": rows, "caption": caption, "sources": sources, "synthetic_label": b["synthetic_label"]}

    q = ["0.05", "0.25", "0.5", "0.75", "0.95"]
    add("FL10_TAB01", ["state", *GLOBAL_COLS, *[f"score_q{x}" for x in q], "participant_macro_F1", "participants_defined", "participants_undefined", "undefined_reasons"],
        [[s, *[states[s]["pooled"][c] for c in GLOBAL_COLS], *[states[s]["pooled"]["score_quantiles"][x] for x in q], states[s]["participant_macro_F1"], states[s]["participants_defined"], states[s]["participants_undefined"], _undef(states[s]["pooled"])] for s in RSTATES],
        f"{b['synthetic_label']}. Independent 16-participant holdout; fixed threshold 0.5; blank = UNDEFINED (reason column).", ["evaluation_results.json"])
    pm = ev["paired"]["metrics"]
    add("FL10_TAB02", ["metric", "R03_point", "R03_lower", "R03_upper", "R10_point", "R10_lower", "R10_upper", "difference_R10_minus_R03", "difference_lower", "difference_upper", "valid_replicates", "invalid_replicates", "replicates", "seed", "clusters", "interpretation_limit"],
        [[m, v["A_point"], v["A_interval"]["lower"], v["A_interval"]["upper"], v["B_point"], v["B_interval"]["lower"], v["B_interval"]["upper"], v["difference_point"], v["difference_interval"]["lower"], v["difference_interval"]["upper"],
          v["difference_interval"]["valid_replicates"], v["invalid_replicates"], ev["paired"]["replicates"], ev["paired"]["seed"], ev["paired"]["clusters"], "nominal paired participant-cluster interval; 16 clusters; no multiplicity adjustment; not a significance claim"] for m, v in pm.items()],
        "Paired R10 - R03 on the same fresh holdout.", ["evaluation_results.json"])
    cr = b["client_rounds"]
    add("FL10_TAB03", list(cr[0]), [[r[c] for c in cr[0]] for r in cr], "Every client x round (80 rows) from the actual runs.", ["client_rounds.csv"])
    bt = b["batches"]
    add("FL10_TAB04", list(bt[0]), [[r[c] for c in bt[0]] for r in bt], "Every captured optimizer batch (read-only hooks).", ["batches.csv"])
    rows5 = []
    for s in RSTATES:
        for pid, m in states[s]["participants"].items():
            rows5.append([s, pid, *[m[c] for c in PART_COLS], _undef(m)])
    add("FL10_TAB05", ["state", "participant_id", *PART_COLS, "undefined_reasons"], rows5, "16 holdout participants x 11 states.", ["participant_metrics.csv"])
    sep = ev["separation"]
    rows6 = [[h["holdout_id"], h["participant_id"], h["site_condition"], h["replicate"], h["session_id"], h["seed"], h["counts"]["windows_emitted"], h["counts"]["trainable"], h["counts"]["DEGRADED"] + h["counts"]["UNUSABLE"],
              h["counts"]["synthetic_positive"], h["counts"]["synthetic_negative"], h["dataset_sha256"], "SEPARATE: " + ", ".join(f"{k}=0" for k in sep)] for h in ev["holdout_participants"]]
    add("FL10_TAB06", ["holdout_id", "participant_id", "site_condition", "replicate", "session_id", "seed", "windows_emitted", "eligible_windows", "excluded_windows", "positives", "negatives", "dataset_sha256", "separation_status"], rows6,
        "Composition and leakage audit; overlap counts against each excluded population: " + "; ".join(f"{k}: {v}" for k, v in sep.items()), ["holdout_manifest_v1.json", "evaluation_results.json"])
    add("FL10_TAB07", ["round", "expected_clients", "received_updates", "accepted_updates", "rejected_updates", "rejection_codes", "total_accepted_example_weight", "weighted_mean_training_loss", "aggregated_update_norm", "update_payload_bytes_total",
                       "round_duration_seconds", "cumulative_accepted_updates", "cumulative_example_exposures", "cumulative_payload_bytes", "base_state_sha256", "global_state_sha256", "aggregation_state", "candidate_status"],
        [[r["round"], r["expected_clients"], r["received_updates"], r["accepted_updates"], r["rejected_updates"], ";".join(x["code"] for x in r["rejections"]), r["total_accepted_example_weight"], r["weighted_mean_training_loss"], r["aggregated_update_norm"],
          r["update_payload_bytes_total"], r["round_duration_seconds"], r["cumulative_accepted_updates"], r["cumulative_example_exposures"], r["cumulative_payload_bytes"], r["base_state_sha256"], r["global_state_sha256"], r["aggregation_state"], r["candidate_status"]] for r in b["rounds"]],
        "Round-level federation evidence; rejected rows are injected adversarial submissions refused by the unchanged coordinator.", ["rounds.csv"])
    prog = b["state_progression"]
    parity = {r["round"]: (r.get("parity") or {}) for r in b["rounds"]}
    rows8 = [["R00", prog["0"]["sha256"], None, "FL_INIT_V2", True, "initial state", prog["0"]["finite"]]]
    for r in b["rounds"]:
        rows8.append([f"R{r['round']:02d}", r["global_state_sha256"], r["base_state_sha256"], f"states/R{r['round']:02d}.bin", parity[r["round"]].get("equals_frozen_reference"), r["candidate_status"], r["state_info"]["finite"]])
    add("FL10_TAB08", ["state", "sha256", "previous_state_sha256", "source_artifact", "equals_frozen_3_round_reference", "status", "finite"], rows8, "Lineage R00-R10 (null = no frozen reference exists for that round).", ["run_report.json"])
    add("FL10_TAB09", ["metric", "definition", "undefined_when", "implementation"], [[k, v[0], v[1], "final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable)"] for k, v in METRIC_DEFINITIONS.items()],
        "Metric equations and undefined-value policy (fixed in the protocol).", ["protocol_v1.json"])
    add("FL10_TAB10", ["evidence_lane", "data", "label_semantics", "use", "must_not_be_compared_with"],
        [["C: synthetic engineering FL (this experiment)", "simulated wearable windows, 8 training clients, 16 holdout participants", "WEARABLE_SIM_EVENT_WINDOW_V1 synthetic engineering events", "optimization/communication-round behaviour of a sandbox candidate", "AAMI-SVF scientific metrics, clinical performance"],
         ["B: scientific federated learning (frozen)", "real research ECG partitions", "AAMI_SVF_WINDOW_V1", "controlled heterogeneity, FedAvg vs FedProx", "synthetic engineering metrics"],
         ["H: historical centralized references (frozen)", "centralized V1/V2 models evaluated earlier", "AAMI_SVF_WINDOW_V1", "descriptive reference only (no paired interval)", "federated results as superiority claims"],
         ["A: released monitoring model", "MODEL_V2_FINAL + CAL_V2 (unchanged)", "AAMI_SVF_WINDOW_V1", "live monitoring", "the FL10 candidate (not promoted, not deployed)"]],
        "Evidence-boundary matrix.", ["protocol_v1.json"])
    hs = b["historical_exposed"]["states"]
    add("FL10_TAB11", ["state", "AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "BCE", "TP", "FP", "TN", "FN", "windows", "label"],
        [[k.replace("round_", "R0").replace("_candidate", ""), *[v[c] for c in ("AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "BCE", "TP", "FP", "TN", "FN", "windows")], b["historical_exposed"]["label"]] for k, v in hs.items()],
        b["historical_exposed"]["caveat"], [b["historical_exposed"]["source"]])
    checks = [
        ("Exactly ten committed rounds", b["run"]["rounds_committed"] == 10), ("80 accepted updates", b["run"]["accepted_updates_total"] == 80), ("eight accepted updates in every round", all(r["accepted_updates"] == 8 for r in b["rounds"])),
        ("R1-R3 equal frozen canonical digests", all(v is True for v in b["run"]["prefix_equals_frozen_reference"].values())), ("eleven states evaluated", sorted(states) == RSTATES),
        ("same holdout for R03 and R10", states["R03"]["pooled"]["windows"] == states["R10"]["pooled"]["windows"]), ("zero overlap with every excluded population", all(v["participant_overlap"] == v["session_overlap"] == v["window_input_overlap"] == 0 for v in sep.values())),
        ("confusion matrices reconcile", all(s["pooled"]["TP"] + s["pooled"]["FN"] == s["pooled"]["positives"] and s["pooled"]["TN"] + s["pooled"]["FP"] == s["pooled"]["negatives"] for s in states.values())),
        ("no round selected on the holdout", ev["round_selection"].startswith("NONE")), ("fixed threshold 0.5, no calibration", ev["threshold"] == 0.5 and ev["calibration"] == "NONE"),
        ("paired bootstrap valid replicates reported", all("valid_replicates" in v["difference_interval"] for v in pm.values())), ("per-batch diagnostics captured", len(b["batches"]) > 0),
        ("timing captured", all(r["round_duration_seconds"] is not None for r in b["rounds"])), ("candidate not promoted or deployed", not b["run"]["candidate"]["promoted"] and not b["run"]["candidate"]["deployed"])]
    add("FL10_TAB12", ["check", "status", "evidence"], [[c, "PASS" if ok else "FAIL", "computed from this run's bundle"] for c, ok in checks],
        "Bundle-level acceptance checks (export hashes and regression gates are verified separately in the lock verifier).", ["run_report.json", "evaluation_results.json"])
    return out
