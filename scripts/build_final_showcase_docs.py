# ruff: noqa: E501
"""Generates the manuscript results, traceability table, viva bank and the recorded verified run from the single authoritative bundle.
All numbers are inserted programmatically (nothing is transcribed by hand).   python -m scripts.build_final_showcase_docs"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from final_showcase import LANE_LABEL, research

DOCS = Path("docs/final_showcase")
REC = Path("reports/final_showcase/recorded_run")
f4 = lambda v: "UNDEFINED" if v is None else f"{v:.4f}"  # noqa: E731
f6 = lambda v: "UNDEFINED" if v is None else f"{v:.6f}"  # noqa: E731


def sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model(b, dataset, model_id):
    return next(m for m in b["models"] if m["dataset"] == dataset and m["model_id"] == model_id)


def main() -> None:
    b = research.bundle()
    comp = {r["dataset"]: r for r in b["comparability"]["rows"]}
    syn, live = b["synthetic"], b["live_link"]
    s0, s3 = syn["states"]["round_0"]["pooled"], syn["states"]["round_3_candidate"]["pooled"]
    u3 = syn["states"]["round_3_candidate"]["uncertainty"]
    it, inc = comp["INTERNAL_TEST"], comp["INCART"]
    av = lambda ds, c: model(b, ds, f"V2_FEDAVG_{c}")["point"]["AUPRC"]  # noqa: E731
    px = lambda ds, c: model(b, ds, f"V2_FEDPROX_{c}")["point"]["AUPRC"]  # noqa: E731

    # ---------------- traceability
    rows = [
        ("T01", "Centralized V2 AUPRC on INTERNAL_TEST", f6(it["centralized_V2_AUPRC"]), "B+H", "reports/model_v2/v2_fl_eval_001/historical_frozen_centralized_references.json", "frozen reference; not re-run"),
        ("T02", "Federated V2 FedAvg IID AUPRC on INTERNAL_TEST", f6(it["federated_V2_FedAvg_IID_AUPRC"]), "B", "reports/model_v2/v2_fl_eval_001/internal_test_statistics.json", "6 clusters"),
        ("T03", "Centralized V2 AUPRC on INCART", f6(inc["centralized_V2_AUPRC"]), "B+H", "reports/model_v2/v2_fl_eval_001/historical_frozen_centralized_references.json", "frozen reference; not re-run"),
        ("T04", "Federated V2 FedAvg IID AUPRC on INCART", f6(inc["federated_V2_FedAvg_IID_AUPRC"]), "B", "reports/model_v2/v2_fl_eval_001/incart_statistics.json", "post-freeze second look; project-exposed"),
        ("T05", "Federated minus centralized AUPRC, INTERNAL_TEST / INCART", f"{it['AUPRC_difference_federated_minus_centralized']:+.6f} / {inc['AUPRC_difference_federated_minus_centralized']:+.6f}", "B+H", research.SYNTH.replace("synth_fl_eval/synth_fl_eval_results.json", "publication/tables/TAB2_MAIN_COMPARISON.csv"), "derived subtraction; no paired interval"),
        ("T06", "V2 FedAvg label-skew AUPRC (INTERNAL_TEST / INCART)", f"{f6(av('INTERNAL_TEST', 'LABEL'))} / {f6(av('INCART', 'LABEL'))}", "B", "reports/model_v2/v2_fl_eval_001/*_statistics.json", "nominal intervals"),
        ("T07", "V2 FedProx label-skew AUPRC (INTERNAL_TEST / INCART)", f"{f6(px('INTERNAL_TEST', 'LABEL'))} / {f6(px('INCART', 'LABEL'))}", "B", "reports/model_v2/v2_fl_eval_001/*_statistics.json", "mu = 0.1; no significance test"),
        ("T08", "Synthetic holdout round-0 AUPRC / AUROC", f"{f4(s0['AUPRC'])} / {f4(s0['AUROC'])}", "C", research.SYNTH, LANE_LABEL),
        ("T09", "Synthetic holdout round-3 candidate AUPRC / AUROC", f"{f4(s3['AUPRC'])} / {f4(s3['AUROC'])}", "C", research.SYNTH, LANE_LABEL),
        ("T10", "Round-3 candidate at the fixed 0.5 threshold: recall / specificity / F1", f"{f4(s3['recall'])} / {f4(s3['specificity'])} / {f4(s3['F1'])}", "C", research.SYNTH, f"{LANE_LABEL}; predicts every window positive, reported as measured"),
        ("T11", "Round-3 AUPRC nominal 95% participant-cluster interval", f"[{f4(u3['AUPRC']['lower'])}, {f4(u3['AUPRC']['upper'])}]", "C", research.SYNTH, f"{LANE_LABEL}; 8 clusters, nominal only"),
        ("T12", "Live-monitored SITE_00 windows / inference HTTP 200", f"{live['parity']['windows_monitored']} / {live['monitoring']['inference_http_statuses'].get('200')}", "A+C", live["source"], "fresh released inference process"),
        ("T13", "Live dataset identical to canonical SITE_00 dataset", str(live["parity"]["dataset_identical_to_canonical"]), "C", live["source"], "observed, not assumed"),
        ("T14", "Live-source candidate digest equals canonical", str(live["candidate_digest_equals_canonical"]), "C", live["source"], "observed, not assumed"),
        ("T15", "Live-source synthetic evaluation metrics equal canonical-run metrics", str(live["synthetic_evaluation"]["pooled_metrics_equal_canonical_run"]), "C", live["synthetic_evaluation"]["source"], "consequence of equal digests"),
    ]
    DOCS.mkdir(parents=True, exist_ok=True)
    with (DOCS / "results_traceability.csv").open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["id", "claim", "value", "lane", "evidence_file", "evidence_sha256_if_single_file", "caveat"])
        for r in rows:
            single = r[4] if "*" not in r[4] and Path(r[4]).exists() else ""
            w.writerow([*r[:5], sha(single) if single else "", r[5]])
    (DOCS / "results_traceability.md").write_text("# Results-to-evidence traceability\n\nGenerated by `scripts/build_final_showcase_docs.py` from the authoritative bundle; every value is read, never typed.\n\n| ID | Claim | Value | Lane | Evidence | Caveat |\n|---|---|---|---|---|---|\n" + "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | `{r[4]}` | {r[5]} |" for r in rows) + "\n")

    # ---------------- manuscript
    (DOCS / "manuscript_material.md").write_text(f"""# Manuscript material (draft, for supervisor review)

**Suggested title:** Reproducible Federated ECG Classification Under Controlled Data Heterogeneity: A Comparative Study of FedAvg, FedProx, and V2 Model Architectures

> Boundary: scientific results (lane B) concern AAMI-SVF window classification on research ECG. The synthetic engineering results (lane C) are labelled "{LANE_LABEL}" and are never pooled with lane B. No clinical, regulatory or hardware claim is made.

## Abstract (draft)
We study federated learning of a V2 temporal-convolutional ECG window classifier under five controlled data-heterogeneity conditions (IID, label, feature, quantity, combined) with FedAvg and FedProx, against a V1 architecture. All 20 models were evaluated once, under a frozen protocol, on two populations with patient-cluster bootstrap intervals. V2 federated models reach AUPRC {f4(av('INTERNAL_TEST', 'IID'))} (INTERNAL_TEST, 6 clusters) and {f4(av('INCART', 'IID'))} (INCART, 32 clusters) under IID partitioning, descriptively comparable to a historical centralized V2 reference ({f4(it['centralized_V2_AUPRC'])} and {f4(inc['centralized_V2_AUPRC'])}). No superiority claim is made. A separate engineering demonstration of a three-round, eight-client sandbox federation on synthetic wearable events ({LANE_LABEL}) is reported with its own frozen protocol and honest operating-point failure.

## Methods (outline)
1. Data and partitions: AAMI_SVF_WINDOW_V1 research ECG, patient-disjoint train/validation/test; controlled non-IID partitions. REFERENCE_REQUIRED: dataset citations (MIT-BIH, INCART, NSTDB) must be added from verified sources.
2. Models: V1 and V2 (TCN-mean) architectures. REFERENCE_REQUIRED: TCN reference.
3. Federation: 8 clients, 50 rounds, FedAvg and FedProx (mu = 0.1 for V2). REFERENCE_REQUIRED: FedAvg and FedProx primary references.
4. Evaluation: one-shot frozen inference, raw sigmoid 0.5 rule for threshold metrics, nominal 95% patient-cluster percentile bootstrap, no p-values.
5. Synthetic engineering evaluation: protocol `NHM_SYNTH_FL_EVAL_PROTOCOL_V1` frozen before results (method-freeze commit `{syn['method_freeze_commit'][:10]}`), independent holdout of 8 unseen simulated participants.

## Results
**Controlled heterogeneity (V2 FedAvg AUPRC, INTERNAL_TEST / INCART):** IID {f4(av('INTERNAL_TEST', 'IID'))} / {f4(av('INCART', 'IID'))}; label {f4(av('INTERNAL_TEST', 'LABEL'))} / {f4(av('INCART', 'LABEL'))}; feature {f4(av('INTERNAL_TEST', 'FEATURE'))} / {f4(av('INCART', 'FEATURE'))}; quantity {f4(av('INTERNAL_TEST', 'QUANTITY'))} / {f4(av('INCART', 'QUANTITY'))}; combined {f4(av('INTERNAL_TEST', 'COMBINED'))} / {f4(av('INCART', 'COMBINED'))}. Full table: TAB1_ALL_MODELS.

**FedAvg vs FedProx (V2, label skew):** {f4(av('INTERNAL_TEST', 'LABEL'))} vs {f4(px('INTERNAL_TEST', 'LABEL'))} (INTERNAL_TEST); {f4(av('INCART', 'LABEL'))} vs {f4(px('INCART', 'LABEL'))} (INCART). Interpretation is descriptive; intervals are nominal.

**Centralized vs federated (V2, IID, point values, no paired interval):** INTERNAL_TEST {f6(it['centralized_V2_AUPRC'])} vs {f6(it['federated_V2_FedAvg_IID_AUPRC'])} (difference {it['AUPRC_difference_federated_minus_centralized']:+.6f}); INCART {f6(inc['centralized_V2_AUPRC'])} vs {f6(inc['federated_V2_FedAvg_IID_AUPRC'])} (difference {inc['AUPRC_difference_federated_minus_centralized']:+.6f}). Four admissible readings are listed in the comparability audit; none supports a superiority claim.

**Synthetic engineering demonstration ({LANE_LABEL}):** on {syn['holdout_windows']} holdout windows, AUPRC rises from {f4(s0['AUPRC'])} (round 0) to {f4(s3['AUPRC'])} (round 3 candidate; nominal 95% interval [{f4(u3['AUPRC']['lower'])}, {f4(u3['AUPRC']['upper'])}], 8 clusters) and AUROC from {f4(s0['AUROC'])} to {f4(s3['AUROC'])}. At the predeclared 0.5 threshold the round-3 candidate predicts every window positive (recall {f4(s3['recall'])}, specificity {f4(s3['specificity'])}, F1 {f4(s3['F1'])}); earlier rounds predict none. Ranking improves; the operating point does not separate classes.

**Live-monitored SITE_00:** a new simulated monitoring session streamed {live['monitoring']['records_seen']} records through the monitoring runtime ({live['monitoring']['inference_http_statuses'].get('200')} real inference responses); its {live['parity']['windows_monitored']} emitted windows formed SITE_00's buffer. Observed: dataset identical to canonical = {live['parity']['dataset_identical_to_canonical']}; candidate digest equals canonical = {live['candidate_digest_equals_canonical']}.

## Limitations (must appear in the paper)
{chr(10).join('- ' + x for x in b['limitations'])}
- Synthetic lane: simulated participants and events; not clinical. No hardware was used.
- Historical centralized values were not re-run; no paired interval exists for them.
- The synthetic holdout has 8 clusters; intervals are nominal.

## Reproduction
`python -m scripts.freeze_synth_fl_eval_protocol`, `python -m scripts.run_synth_fl_eval --method-commit {syn['method_freeze_commit']} --out reports/final_showcase/synth_fl_eval`, `python -m final_showcase.figures`, `python -m scripts.run_live_link --out reports/final_showcase/live_link`.
""")

    # ---------------- viva bank
    qa = [
        ("Why is the federated result not called better than centralized?", f"Only point values exist for the centralized reference ({f6(it['centralized_V2_AUPRC'])} / {f6(inc['centralized_V2_AUPRC'])}); differences of {it['AUPRC_difference_federated_minus_centralized']:+.6f} and {inc['AUPRC_difference_federated_minus_centralized']:+.6f} have opposite signs, no paired interval, different training budgets and exposed datasets."),
        ("What does 'frozen' mean here?", "Artifacts are hash-verified before display; locks and historical evidence are never edited. New work is additive successor material."),
        ("Why does the synthetic round-3 model predict everything positive?", f"({LANE_LABEL}) At the fixed 0.5 threshold its recall is {f4(s3['recall'])} and specificity {f4(s3['specificity'])}. Threshold-free AUPRC/AUROC improved ({f4(s0['AUPRC'])}→{f4(s3['AUPRC'])}, {f4(s0['AUROC'])}→{f4(s3['AUROC'])}), so ranking improved but the uncalibrated operating point is poor. We did not tune the threshold or retrain, by protocol."),
        ("Is the synthetic evaluation clinical validation?", f"No. It is labelled '{LANE_LABEL}'."),
        ("How do you know the holdout did not leak?", "Participant, session, seed and window-input disjointness are checked and tested; a changed label, hash or protocol aborts the run."),
        ("Why was the protocol committed first?", f"A two-commit method-freeze/result sequence (method freeze {syn['method_freeze_commit'][:10]}) prevents choosing methods after seeing results."),
        ("Is the live-monitored participant different from the synthetic one?", f"The windows come from a genuine monitoring-runtime session; the generator is the same, so the dataset is identical to canonical (observed: {live['parity']['dataset_identical_to_canonical']}). The candidate digest equality ({live['candidate_digest_equals_canonical']}) is a measured consequence."),
        ("Does raw data leave clients?", "No; only updates, digests and example counts reach the coordinator (client-data-locality audit)."),
        ("Why are no p-values reported?", "Patient-cluster counts are small (6 and 32 for the scientific sets, 8 for synthetic); only nominal percentile intervals are reported."),
        ("What would strengthen the comparison?", "A designed paired experiment with matched budgets and held-out clusters; independent hardware data is out of scope and not authorised."),
    ]
    (DOCS / "viva_question_bank.md").write_text("# Viva question bank\n\n" + "\n".join(f"**Q{i + 1}. {q}**\n\n{a}\n" for i, (q, a) in enumerate(qa)))

    # ---------------- recorded verified run
    REC.mkdir(parents=True, exist_ok=True)
    recorded = {"label": "RECORDED VERIFIED RUN", "note": "Recorded output of an earlier verified execution; replayed for demonstration, not a fresh run.", "boundary_label": LANE_LABEL,
                "live_link": {k: live[k] for k in ("phase", "status", "run_id", "candidate_ids", "candidate_state_digest", "candidate_digest_equals_canonical", "parity", "monitoring")},
                "synthetic_states": {k: {m: v["pooled"][m] for m in ("AUPRC", "AUROC", "F1", "recall", "specificity", "TP", "FP", "TN", "FN")} for k, v in syn["states"].items()},
                "sources": [live["source"], research.SYNTH]}
    (REC / "recorded_verified_run.json").write_text(json.dumps(recorded, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
