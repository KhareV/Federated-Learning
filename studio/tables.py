# ruff: noqa: E501
"""The twelve predeclared tables for a 3- or 10-round run with partial evaluation (same ids, columns and semantics as ``fl10.tables``).
Rows exist only for genuinely evaluated states / committed rounds; None = UNDEFINED or NOT CAPTURED, never zero. Machine-readable values keep full precision."""

from __future__ import annotations

from typing import Any

from fl10.inventory import METRIC_DEFINITIONS, TABLES
from fl10.tables import GLOBAL_COLS, PART_COLS
from studio.constants import COHORT_USE_LABEL
from studio.specs import comparison_pair, skey

Q = ["0.05", "0.25", "0.5", "0.75", "0.95"]


def _undef(m: dict[str, Any]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in m["undefined"].items())


def table_title(tid: str, n: int) -> str:
    base = next(t for i, t in TABLES if i == tid)
    a, b = comparison_pair(n)
    return base.replace("independent evaluation", "diagnostic evaluation").replace("R0-R10", f"R0-R{n}").replace("R3 versus R10", f"R{a} versus R{b}").replace("11 states", f"{n + 1} states")


def build_tables(b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    n = int(b["planned_rounds"])
    a, e = comparison_pair(n)
    ev = b["evaluation"]
    states = ev["states"]
    evaluated = [skey(r) for r in range(n + 1) if skey(r) in states]
    out: dict[str, dict[str, Any]] = {}

    def add(tid: str, columns: list[str], rows: list[list[Any]], caption: str, sources: list[str], *, empty_note: str | None = None) -> None:
        out[tid] = {"id": tid, "title": table_title(tid, n), "columns": columns, "rows": rows, "caption": caption + (f" {empty_note}" if empty_note and not rows else ""), "sources": sources,
                    "synthetic_label": b["synthetic_label"], "availability": "AVAILABLE" if rows else "PENDING"}

    label = f"{b['synthetic_label']}. {COHORT_USE_LABEL}."
    add("FL10_TAB01", ["state", *GLOBAL_COLS, *[f"score_q{x}" for x in Q], "participant_macro_F1", "participants_defined", "participants_undefined", "undefined_reasons"],
        [[s, *[states[s]["pooled"][c] for c in GLOBAL_COLS], *[states[s]["pooled"]["score_quantiles"][x] for x in Q], states[s]["participant_macro_F1"], states[s]["participants_defined"], states[s]["participants_undefined"], _undef(states[s]["pooled"])] for s in evaluated],
        f"{label} 16-participant holdout; fixed threshold 0.5; blank = UNDEFINED (reason column). Only genuinely evaluated states have rows.", ["evaluation_results.json"], empty_note="No state has been evaluated yet.")
    pm = (ev.get("paired") or {}).get("metrics")
    rows2 = ([[m, v["A_point"], v["A_interval"]["lower"], v["A_interval"]["upper"], v["B_point"], v["B_interval"]["lower"], v["B_interval"]["upper"], v["difference_point"], v["difference_interval"]["lower"], v["difference_interval"]["upper"],
               v["difference_interval"]["valid_replicates"], v["invalid_replicates"], ev["paired"]["replicates"], ev["paired"]["seed"], ev["paired"]["clusters"], f"nominal paired participant-cluster interval; {ev['paired']['clusters']} clusters; no multiplicity adjustment; not a significance claim"] for m, v in pm.items()] if pm else [])
    add("FL10_TAB02", ["metric", f"R{a:02d}_point", f"R{a:02d}_lower", f"R{a:02d}_upper", f"R{e:02d}_point", f"R{e:02d}_lower", f"R{e:02d}_upper", f"difference_R{e:02d}_minus_R{a:02d}", "difference_lower", "difference_upper", "valid_replicates", "invalid_replicates", "replicates", "seed", "clusters", "interpretation_limit"],
        rows2, f"Paired R{e:02d} - R{a:02d} on the same holdout (only when both states are evaluated).", ["evaluation_results.json"], empty_note="PENDING: both comparison states must be evaluated.")
    cr = b["client_rounds"]
    cols3 = list(cr[0]) if cr else ["run_id", "round", "client_id"]
    add("FL10_TAB03", cols3, [[r[c] for c in cols3] for r in cr], f"Every client x committed round ({len(cr)} rows) from the actual run.", ["client_rounds.csv"], empty_note="No round has been committed yet.")
    bt = b["batches"]
    cols4 = list(bt[0]) if bt else ["run_id", "round", "client_id", "batch_index", "batch_size", "loss", "gradient_l2_norm"]
    add("FL10_TAB04", cols4, [[r[c] for c in cols4] for r in bt], "Every captured optimizer batch (read-only hooks).", ["batches.csv"], empty_note="No batch captured yet.")
    rows5 = [[s, pid, *[m[c] for c in PART_COLS], _undef(m)] for s in evaluated for pid, m in states[s]["participants"].items()]
    add("FL10_TAB05", ["state", "participant_id", *PART_COLS, "undefined_reasons"], rows5, f"16 holdout participants x {len(evaluated)} evaluated states.", ["participant_metrics.csv"], empty_note="No state has been evaluated yet.")
    sep = ev["separation"]
    rows6 = [[h["holdout_id"], h["participant_id"], h["site_condition"], h["replicate"], h["session_id"], h["seed"], h["counts"]["windows_emitted"], h["counts"]["trainable"], h["counts"]["DEGRADED"] + h["counts"]["UNUSABLE"], h["counts"]["synthetic_positive"],
              h["counts"]["synthetic_negative"], h["dataset_sha256"], "SEPARATE: " + ", ".join(f"{k}=0" for k in sep)] for h in ev["holdout_participants"]]
    add("FL10_TAB06", ["holdout_id", "participant_id", "site_condition", "replicate", "session_id", "seed", "windows_emitted", "eligible_windows", "excluded_windows", "positives", "negatives", "dataset_sha256", "separation_status"], rows6,
        "Composition and leakage audit; overlap counts against each excluded population: " + "; ".join(f"{k}: {v}" for k, v in sep.items()), ["holdout_manifest_v1.json", "evaluation_results.json"])
    rr = b["rounds"]
    add("FL10_TAB07", ["round", "expected_clients", "received_updates", "accepted_updates", "rejected_updates", "rejection_codes", "total_accepted_example_weight", "weighted_mean_training_loss", "aggregated_update_norm", "update_payload_bytes_total",
                       "round_duration_seconds", "cumulative_accepted_updates", "cumulative_example_exposures", "cumulative_payload_bytes", "base_state_sha256", "global_state_sha256", "aggregation_state", "candidate_status"],
        [[r["round"], r["expected_clients"], r["received_updates"], r["accepted_updates"], r["rejected_updates"], ";".join(x["code"] for x in r["rejections"]), r["total_accepted_example_weight"], r["weighted_mean_training_loss"], r["aggregated_update_norm"], r["update_payload_bytes_total"],
          r["round_duration_seconds"], r["cumulative_accepted_updates"], r["cumulative_example_exposures"], r["cumulative_payload_bytes"], r["base_state_sha256"], r["global_state_sha256"], r["aggregation_state"], r["candidate_status"]] for r in rr],
        "Round-level federation evidence from coordinator acceptance and aggregation (rejection rows, where present, are adversarial controls refused by the unchanged coordinator).", ["rounds.csv"], empty_note="No round has been committed yet.")
    prog = b["state_progression"]
    parity = {r["round"]: (r.get("parity") or {}) for r in rr}
    base_id = (b["run"].get("initialisation") or {}).get("model_id", "FL_INIT_V2")
    rows8 = ([["R00", prog["0"]["sha256"], None, base_id if base_id != "FL_INIT_V2" else "FL_INIT_V2", None if base_id != "FL_INIT_V2" else True, "initial state" if base_id == "FL_INIT_V2" else "initial state (pretrained checkpoint)",
               prog["0"]["finite"]]] if "0" in prog else [])
    rows8 += [[f"R{r['round']:02d}", r["global_state_sha256"], r["base_state_sha256"], r.get("state_artifact") or f"states/R{r['round']:02d}.bin", parity[r["round"]].get("equals_frozen_reference"), r["candidate_status"], r["state_info"]["finite"]] for r in rr]
    add("FL10_TAB08", ["state", "sha256", "previous_state_sha256", "source_artifact", "equals_frozen_3_round_reference", "status", "finite"], rows8, "State lineage (null = no frozen reference exists for that round).", ["run_report.json"], empty_note="R00 not yet verified.")
    add("FL10_TAB09", ["metric", "definition", "undefined_when", "implementation"], [[k, v[0], v[1], "final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable)"] for k, v in METRIC_DEFINITIONS.items()],
        "Metric equations and undefined-value policy (fixed in the protocol).", ["protocol_v1.json"])
    add("FL10_TAB10", ["evidence_lane", "data", "label_semantics", "use", "must_not_be_compared_with"],
        [["C: synthetic engineering FL (this run)", "simulated wearable windows, 8 training clients, 16 diagnostic-holdout participants", "WEARABLE_SIM_EVENT_WINDOW_V1 synthetic engineering events", "optimization/communication-round behaviour on synthetic data", "real-ECG AAMI-SVF results or clinical performance"],
         ["B: scientific federated learning (frozen)", "real research ECG partitions", "AAMI_SVF_WINDOW_V1", "controlled heterogeneity, FedAvg vs FedProx", "synthetic engineering metrics"],
         ["H: historical centralized references (frozen)", "centralized V1/V2 models evaluated earlier", "AAMI_SVF_WINDOW_V1", "descriptive reference only (no paired interval)", "federated results as superiority claims"],
         ["A: released monitoring model", "MODEL_V2_FINAL + CAL_V2 (unchanged)", "AAMI_SVF_WINDOW_V1", "live monitoring", "the federated sandbox candidate (not promoted, not deployed)"]], "Evidence-boundary matrix.", ["protocol_v1.json"])
    hs = b["historical_exposed"]["states"]
    add("FL10_TAB11", ["state", "AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "BCE", "TP", "FP", "TN", "FN", "windows", "label"],
        [[k.replace("round_", "R0").replace("_candidate", ""), *[v[c] for c in ("AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "BCE", "TP", "FP", "TN", "FN", "windows")], b["historical_exposed"]["label"]] for k, v in hs.items()],
        b["historical_exposed"]["caveat"], [b["historical_exposed"]["source"]])
    prefix = b["run"].get("prefix_equals_frozen_reference") or {}
    pretrained = (b["run"].get("initialisation") or {}).get("model_id", "FL_INIT_V2") != "FL_INIT_V2"
    done = b["run"].get("status") == "COMPLETED"
    pass_rows = [
        (f"{n} committed rounds" if done else f"{len(rr)} of {n} rounds committed so far", len(rr) == n if done else None),
        (f"{8 * n} accepted updates" if done else f"{sum(r['accepted_updates'] for r in rr)} accepted updates so far", (b["run"].get("accepted_updates_total") == 8 * n) if done else None),
        ("eight accepted updates in every committed round", all(r["accepted_updates"] == 8 for r in rr) if rr else None),
        ("committed R1-R3 equal frozen canonical digests (FedAvg, where a reference exists)", "NA" if pretrained else (all(v is True for v in prefix.values()) if prefix else None)),
        ("every evaluated state belongs to this run (digest equals committed digest)", all(ev["state_digests"][s] == (prog[str(int(s[1:]))]["sha256"]) for s in evaluated if s in ev["state_digests"])),
        ("same diagnostic holdout for every evaluated state", len({states[s]["pooled"]["windows"] for s in evaluated}) <= 1),
        ("zero overlap with every excluded population", all(v["participant_overlap"] == v["session_overlap"] == v["window_input_overlap"] == 0 for v in sep.values())),
        ("confusion matrices reconcile", all(states[s]["pooled"]["TP"] + states[s]["pooled"]["FN"] == states[s]["pooled"]["positives"] and states[s]["pooled"]["TN"] + states[s]["pooled"]["FP"] == states[s]["pooled"]["negatives"] for s in evaluated)),
        ("no round selected on the holdout", ev["round_selection"].startswith("NONE")), ("fixed threshold 0.5, no calibration", ev["threshold"] == 0.5 and ev["calibration"] == "NONE"),
        ("candidate not promoted or deployed", (not b["run"]["candidate"]["promoted"] and not b["run"]["candidate"]["deployed"]) if b["run"].get("candidate") else None)]
    add("FL10_TAB12", ["check", "status", "evidence"], [[chk, "NOT APPLICABLE" if ok == "NA" else "PENDING" if ok is None else ("PASS" if ok else "FAIL"), "pretrained start: no frozen FL_INIT_V2 reference exists for this run" if ok == "NA" else "computed from this run's bundle"] for chk, ok in pass_rows],
        "Bundle-level acceptance checks (PENDING until the run reaches the state the check needs).", ["run_report.json", "evaluation_results.json"])
    return out
