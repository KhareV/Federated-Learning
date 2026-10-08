# NHM-FL10-001 — verification handoff

Status: local FL10 evidence and UI gates PASS; see `local_test_report.json` and `artifacts/fl10/NHM_FL10_001.lock.json` for the bound gate result. No push was performed.

The method was frozen in commit `f91a96a` before any new holdout predictions. Canonical Mode A and live-monitored simulated SITE_00 Mode B each completed ten genuine weighted-FedAvg rounds, eight accepted updates per round, and 80 accepted updates total. The same 723 eligible synthetic training windows were processed once per round (7,230 repeated exposures, not independent examples). Mode A R0–R3 digests match the historical three-round run; Mode B digests match Mode A by computation. The R10 candidate digest is `5ae2c3a44eb5ac1ce70108fb06e23fa695359dbb42349af6dde0b0b29723355f`. It is neither calibrated, promoted, nor deployed.

The independent holdout has 16 synthetic participants and 1,446 eligible windows (307 engineering-event positives, 1,139 negatives). It is disjoint from training by participant, session, seed and model-input window hash. Every R0–R10 state was scored on this same holdout at a predeclared raw-sigmoid threshold of 0.5, without CAL_V2. R10 versus R3 was predeclared; R7's higher AUPRC was not used to select a candidate. Mode A and Mode B evaluation results agree.

| State | AUPRC | AUROC | F1 | Sensitivity | Specificity | BCE | Brier | TP | FP | TN | FN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| R0 | 0.628671 | 0.726971 | 0 | 0 | 1 | 0.650140 | 0.228541 | 0 | 0 | 1139 | 307 |
| R3 | 0.676186 | 0.802847 | 0.350257 | 1 | 0 | 0.724338 | 0.265607 | 307 | 1139 | 0 | 0 |
| R10 | 0.911570 | 0.966171 | 0.350257 | 1 | 0 | 3.499216 | 0.768504 | 307 | 1139 | 0 | 0 |

R10−R3 paired nominal 95% participant-cluster intervals (2,000 valid draws): AUPRC +0.235384 [0.163657, 0.315548]; AUROC +0.163324 [0.112474, 0.211540]; F1 0 [0, 0]; BCE +2.774878 [2.682356, 2.887172]; Brier +0.502897 [0.497301, 0.509050]. Ranking improved, but both endpoints label every holdout window positive at 0.5, and probability quality worsened. This is a negative fixed-threshold/calibration result, not clinical efficacy.

Complete unrounded values and undefined-statistic reasons are in [Table 01](publication/modeA/tables/FL10_TAB01.csv). [Tables 02–12](publication/modeA/export_manifest.json) cover paired differences, all 80 client-round diagnostics, captured batches, all 16 participant results, composition/leakage, aggregation, lineage, metric definitions, claim boundaries, the previous exposed holdout, and acceptance. [Figures 01–20](publication/modeA/export_manifest.json) each have SVG, 300-dpi PNG, source CSV, and provenance JSON. Mode B has a separate equivalent export package. The application route `/app/observatory/fl10` exposes the figures, tables, selectors, recorded evidence, and owner-scoped opt-in execution.

Verification boundaries: the frontend browser smoke is an isolated DemoAuth preview, not a connected Clerk two-user E2E. Owner separation was tested at the API using two distinct test identities; no real hospital network or physical ECG patient is involved. The final UI claims only synthetic engineering-event evaluation, not AAMI-SVF efficacy. The original released model, calibration, scientific artifacts, default three-round route, and predecessor locks remain byte-identical. An interrupted new FL10 run fails closed rather than fabricating completion; resume is not implemented.

Verification: 30 FL10 Python tests passed, 41 predecessor/successor regression and tamper tests passed, 259 frontend tests passed (3 skipped), svelte-check reported zero errors and 123 warnings, production build passed, and the real-browser DEMO smoke passed at 1440/1024/768/390 px with no overflow or console errors. Reduced-motion and focus checks passed. The protected baseline audit found 92 of 92 recorded files unchanged. Connected Clerk two-user E2E was not performed; this is an explicit remaining validation boundary rather than an implied PASS.
