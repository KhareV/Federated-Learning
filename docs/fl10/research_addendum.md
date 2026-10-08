# NHM-FL10-001 — synthetic engineering federation addendum

This is a separate, non-diagnostic engineering experiment. It does not alter the released centrally trained `MODEL_V2_FINAL`, `CAL_V2`, any AAMI-SVF scientific result, or the default three-round federation. Eight synthetic logical clients execute on one machine; they are not patients or hospitals. Mode B's SITE_00 is a **live-monitored simulated ECG**, not a person's physiology.

## Question and locked method

Does extending the existing FedAvg engineering cohort from three to ten communication rounds change optimization, ranking, and fixed-threshold classification on a fresh synthetic engineering-event cohort? The [pre-result protocol](../../configs/fl10/protocol_v1.json) and [16-participant holdout manifest](../../configs/fl10/holdout_manifest_v1.json) were committed at `f91a96a` before new prediction results. Two holdout participants represent each of the eight existing site conditions. The 16 participants are independent sampling clusters; their windows are correlated within participant. Training and holdout participants, sessions, seeds, and input-window hashes are disjoint under the recorded leakage audit. The target is `WEARABLE_SIM_EVENT_WINDOW_V1`, not AAMI-SVF arrhythmia classification.

The run uses the frozen V2-architecture initialization, existing one-epoch local AdamW settings and original weighted-FedAvg coordinator. R0 through R10 were evaluated on the *same* new holdout. R10 versus R3 was the predeclared endpoint comparison; no best round or threshold was selected using this holdout. The rule is raw `sigmoid(logit) >= 0.5`; `CAL_V2` is not applied. The nominal paired intervals use 2,000 participant-cluster draws with multiplicity and shared draws for both endpoints. They are not a clinical significance test or multiple-comparison-adjusted inference.

## Executed training

The canonical Mode A run completed 10 rounds with 8 accepted updates per round (80 total). It processed 723 unique eligible training windows repeatedly, yielding 7,230 example exposures, **not** 7,230 independent examples. R0–R3 state digests matched the frozen original reference. One separate R10 engineering candidate was created; it is neither promoted nor deployed. Mode B executed one simulated monitoring session for SITE_00, reused its verified eligible buffer across ten rounds, and used seven canonical synthetic peers. Its computed state digests matched Mode A for every round; equality was measured, not assumed. See [Mode A](../../reports/fl10/runs/modeA/run_report.json), [Mode B](../../reports/fl10/runs/modeB/run_report.json), and the Mode B `monitoring_link.json` in that directory.

The training path's *weighted mean local loss* decreased from 0.7145994498521955 at R1 to 0.15869885374164597 at R10. The aggregate update norm declined from 2.9368923867744177 to 1.07577347636594597, with some non-monotonicity. These are local optimization diagnostics, not generalization measures. The round ledger includes actual eight-client updates, example weights, hashes, batch loss, gradient norms where captured, logical payload bytes, and measured single-machine execution times. Each round also recorded deliberately injected malformed/stale/duplicate negative-control submissions; those rejected probes are **not** extra client contributions or evidence of a deployed hostile network.

## Fresh-holdout findings

The fresh holdout contains 1,446 eligible windows: 307 scheduled-event positives and 1,139 negatives. Full unrounded R0–R10 values, all applicable metrics, confusion counts, per-participant metrics, and undefined reasons are in [Table 01](../../reports/fl10/publication/modeA/tables/FL10_TAB01.csv) and the other linked [publication exports](../../reports/fl10/publication/modeA/export_manifest.json). A compact excerpt:

| State | AUPRC | AUROC | F1 | Sensitivity | Specificity | BCE | Brier | TP / FP / TN / FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| R0 | 0.628671 | 0.726971 | 0 | 0 | 1 | 0.650140 | 0.228541 | 0 / 0 / 1139 / 307 |
| R3 | 0.676186 | 0.802847 | 0.350257 | 1 | 0 | 0.724338 | 0.265607 | 307 / 1139 / 0 / 0 |
| R10 | 0.911570 | 0.966171 | 0.350257 | 1 | 0 | 3.499216 | 0.768504 | 307 / 1139 / 0 / 0 |

R10−R3 AUPRC = +0.23538432293741318 (nominal 95% interval +0.16365712017154027 to +0.31554781778530944); AUROC = +0.1633240198699928 (+0.11247388995290145 to +0.21153956618150827). Fixed-threshold F1, sensitivity, specificity, and confusion counts **did not improve**: both R3 and R10 predicted positive for every eligible window. BCE worsened by +2.7748780779939928 (+2.682355660924783 to +2.887171817680085), and Brier worsened by +0.502897011315907 (+0.49730083631540306 to +0.5090501439628473). All listed paired intervals used 2,000 valid draws and zero undefined draws. [Table 02](../../reports/fl10/publication/modeA/tables/FL10_TAB02.csv) contains every predeclared paired comparison.

The model increasingly ranked scheduled-event windows above negatives, but its raw probabilities moved toward positive-class saturation; threshold 0.5 no longer discriminated the classes. Ranking gains therefore do **not** establish a useful fixed-threshold classifier, good calibration, scientific AAMI-SVF efficacy, or a reason to deploy this engineering candidate. The R7–R10 AUPRC trajectory is not monotone (R7 0.915194, R8 0.893162, R9 0.878712, R10 0.911570), so a blanket diminishing-returns or monotonic-improvement claim would be false. The predeclared R10 endpoint remains the reported result.

## Interpretation and limitations

The 16-participant synthetic holdout is independent of this training cohort under the declared identity/hash tests, but it remains a small deterministic synthetic population. Nominal intervals quantify this sampling scheme only. Mode B is a simulated monitoring-link parity exercise; it does not convert this into patient-derived or personalized FL. Serialized payload bytes describe logical updates on one machine, not physical-network traffic. The prior eight-participant synthetic holdout was previously exposed and appears only in the historical continuity table; it was not used to choose the ten-round endpoint. No fresh clinical ECG inference, hardware validation, model promotion, or `CAL_V2` fitting occurred.

## Figures, tables, and reproduction

All 20 figures (SVG, 300-dpi PNG, CSV source data, JSON provenance) and 12 tables (CSV, JSON, Markdown) are inventoried with hashes in the [Mode A export manifest](../../reports/fl10/publication/modeA/export_manifest.json) and [Mode B export manifest](../../reports/fl10/publication/modeB/export_manifest.json). The app's `/app/observatory/fl10` route renders those measured chart specs and exposes every table. Figure 20 separates bounded rates, BCE, and predicted-window counts into different scales; mixing those on a single axis would hide the rates.

The recorded results are immutable evidence. To make a **new** local engineering run, use the documented CLI and a fresh explicit output directory, then evaluate with the already frozen protocol; do not overwrite the recorded paths. See [runbook](runbook.md) for the exact commands and checks. New results must remain separate from the frozen recorded run and cannot be described as a predeclared independent experiment merely because they reuse the already exposed holdout.

## Suggested manuscript paragraph

> In a predeclared synthetic engineering-event study with eight logical clients and a separate 16-participant holdout, extending weighted FedAvg from three to ten rounds increased average precision from 0.676 to 0.912 and AUROC from 0.803 to 0.966. However, at the fixed uncalibrated 0.5 threshold both R3 and R10 predicted every eligible holdout window positive, leaving F1 unchanged at 0.350 and specificity at zero. BCE and Brier score worsened substantially. These results show improved ranking but not usable fixed-threshold classification or clinical ECG efficacy. The ten-round checkpoint remains an undeployed engineering candidate.

External literature citations for a paper remain `REFERENCE_REQUIRED` until independently verified.

## Faculty demonstration, 3–5 minutes

1. Open `/app/observatory/fl10`; select **Recorded Verified Run — Mode A** and show the original three-round baseline panel and R0–R3 digest parity.
2. Show 80 accepted updates, 723 unique eligible windows, and 7,230 repeated exposures. Select SITE_00 and SITE_07; inspect their actual per-round weights and optimizer diagnostics.
3. Open Training and Optimizer & federation to show 10 measured loss points, batch traces, rejected negative-control probes, and the R0–R10 state lineage.
4. Open Classification and R3 vs R10. Show AUPRC/AUROC curves, the 0.5 threshold, confusion matrices, probability distributions, and the nominal participant-cluster intervals.
5. Explain the result honestly: ranking improves; all-positive threshold behavior remains; BCE/Brier deteriorate. Open Exports to demonstrate complete tables and source-data files. If a new run is impractical, the clearly labelled recorded run is the fallback, not a fake live animation.

## Viva prompts

- Why are 7,230 exposures not 7,230 independent observations? (The same 723 windows recur across ten rounds.)
- Why can AUROC/AUPRC rise while specificity stays zero? (Ranking and a fixed decision threshold answer different questions.)
- Why does falling local training loss not prove holdout calibration? (Optimization objective and generalization/probability quality differ.)
- Why is participant-cluster rather than window-level bootstrap used? (Windows within a participant are correlated.)
- Why was R10 reported despite R7's higher AUPRC? (R10 was the predeclared endpoint; selecting R7 post hoc would leak holdout outcomes into the decision.)
- Does Mode B train on a real patient's ECG? (No; it uses an authenticated, owner-bound **simulated** monitoring source.)
