# Final verification, 2026-10-19: every flow, every combination, with independently verified values

Scope: real Chrome + Clerk + local Render replica + Atlas (isolated rehearsal database) driving the unchanged product. Hardware evidence level stays `VERIFIED_LOCAL_RENDER_REPLICA`: **no physical ESP32 was used** and the hardware sessions are emulated or generated, with assigned labels. Everything below is synthetic or emulated; nothing is a clinical or physical-device claim.

## What ran (verdict files under `reports/verification/browser/`)

| Gate | Covers | Result |
|---|---|---|
| `journey` | sketch-faithful emulator → local replica → Atlas rehearsal DB → `/monitoring` live → stop/record → `/history` → Observatory replay → V2 run | PASS, 25 checks |
| `demo_session` | generated showcase session in History, evidence, Observatory replay + trace, pretrained-V2 and tabular runs | PASS, 16 checks |
| `hardware_combos` | recorded hardware × {pretrained V2, untrained V2, stored candidate, tabular} × {original, realistic, recorded-noise}: 12 runs | PASS, 52 checks; 36 rounds verified independently |
| `fl_matrix` | 19 synthetic flows: 3 and 10 rounds, every cohort, untrained / pretrained / candidate starts (one an imported research checkpoint), monitored-site sources; each opened in the Observatory journal replay | PASS, 160 checks; 107 rounds verified independently, 50 aggregations re-derived bit-exact |
| `candidate_library`, `history_source`, `hardware_v2`, `realistic_cohort`, `recorded_noise_cohort`, `external_check`, `demo_path`, `ui_tour` | the remaining flows and pages (128 routes at four widths) | all PASS |

"Verified independently" means the verifier recomputes AUROC/AUPRC/F1/BCE from the stored per-window logits with its own implementation, recomputes the logits from the stored model state (maximum difference 0.0), checks every state digest chain, and for synthetic runs re-forms each aggregation by retraining the clients and comparing bit for bit.

## Verified results (AUROC / AUPRC, round 0 → last round, one training seed each)

Synthetic federation, evaluation on each cohort's own holdout:

| Run | Start | Cohort | AUROC | AUPRC |
|---|---|---|---|---|
| 3 rounds | pretrained V2 | original | 0.931 → 0.979 | 0.904 → 0.970 |
| 10 rounds | pretrained V2 | original | 0.931 → 0.999 | 0.904 → 0.996 |
| 3 rounds | pretrained V2 | realistic | 0.848 → 0.838 | 0.484 → 0.648 |
| 10 rounds | pretrained V2 | realistic | 0.848 → 0.915 | 0.484 → 0.828 |
| 3 rounds | pretrained V2 | recorded noise | 0.949 → 0.959 | 0.900 → 0.917 |
| 10 rounds | pretrained V2 | recorded noise | 0.949 → 0.957 | 0.900 → 0.901 |
| 10 rounds | untrained | original | 0.727 → 0.966 | 0.629 → 0.912 |
| 10 rounds | untrained | recorded noise | 0.610 → 0.911 | 0.316 → 0.763 |
| 3 rounds | untrained | realistic | 0.562 → 0.702 | 0.188 → 0.320 |
| 3 rounds | untrained | recorded noise | 0.610 → 0.868 | 0.316 → 0.659 |
| 3 rounds | research checkpoint R50 (real ECG) | original | 0.917 → 0.972 | 0.865 → 0.962 |
| 3 rounds | research checkpoint R38 (real ECG) | recorded noise | 0.971 → 0.952 | 0.899 → 0.905 |
| 3 rounds | candidate trained on original (10 r) | recorded noise | 0.955 → 0.971 | 0.879 → 0.922 |
| 3 rounds | candidate trained on recorded noise (10 r) | realistic | 0.812 → 0.729 | 0.372 → 0.493 |

Recorded hardware (one recorded client with assigned labels + seven synthetic peers, 3 rounds):

| Start | Cohort | AUROC | AUPRC |
|---|---|---|---|
| pretrained V2 | original | 0.931 → 0.981 | 0.904 → 0.972 |
| pretrained V2 | realistic | 0.848 → **0.697** | 0.484 → 0.531 |
| pretrained V2 | recorded noise | 0.949 → 0.958 | 0.900 → 0.915 |
| untrained V2 | original / realistic / recorded noise | 0.727 → 0.790 / 0.562 → 0.693 / 0.610 → 0.841 | 0.629 → 0.660 / 0.188 → 0.317 / 0.316 → 0.594 |
| stored candidate | original / realistic / recorded noise | 0.981 → 0.995 / 0.848 → **0.632** / 0.970 → 0.966 | 0.972 → 0.990 / 0.437 → 0.488 / 0.919 → 0.923 |
| tabular model | any | 0.490 (chance) on its own 94-window recorded holdout | 0.499 |

## Deductions (each limited to what one seed per cell can support)

1. **The measurement chain is sound.** Across 18 synthetic runs and 9 hardware runs every stored value reproduces from first principles, every aggregation re-derives bit for bit, and the page shows the stored value of every round. A live-monitored simulated site reproduces the canonical run exactly (same metrics to six decimals, for 3 rounds on all three cohorts).
2. **The tabular recorded-hardware model measures chance, as it should.** Its labels are random assignments, so AUROC 0.490 and AUPRC 0.499 on its holdout show the evaluation has no leakage that could turn noise into signal. It also shows that a high score on hardware runs describes the pipeline, never the device or a person.
3. **Cohort difficulty is not what its name suggests.** For the same pretrained V2 the invented-noise "realistic" cohort is hardest (AUROC 0.848, AUPRC 0.484); the recorded-noise cohort is nearly as easy as the original (0.949 / 0.900). That fits the earlier finding that the invented motion artifacts, not rhythm, drive most errors.
4. **Pretrained beats untrained at every round count, and the gap closes slowly.** At 3 rounds untrained reaches AUROC 0.70–0.87 against 0.84–0.98 pretrained; at 10 rounds the gap is 0.03–0.05 on the original and recorded-noise cohorts. Untrained runs on the realistic cohort learn ranking before they learn the 0.5 threshold (3 rounds: AUROC 0.70 but F1 0.017).
5. **Three rounds on the hardest cohort is not monotone.** Pretrained V2 on the realistic cohort for 3 rounds loses a little AUROC (0.848 → 0.838) while AUPRC rises; at 10 rounds both improve. A 3-round result on that cohort should not be read as "adaptation helps".
6. **A recorded client with assigned (random) labels can hurt, and only on the hard cohort.** On the original and recorded-noise cohorts a hardware run improves like a synthetic one (0.931 → 0.981 against 0.979; 0.949 → 0.958 against 0.959). On the realistic cohort the same run drops AUROC from 0.848 to 0.697 (and a candidate start from 0.848 to 0.632) while the synthetic 3-round run stays at 0.838. So label-noisy client data costs the most where the model is least certain.
7. **Candidates transfer only inside their family.** The candidate trained on the original cohort improves the recorded-noise cohort (0.955 → 0.971); the one trained on recorded noise is worse on the realistic cohort than the pretrained model it came from (0.812 start, 0.729 after 3 rounds), and one trained from scratch on the realistic cohort does not improve recorded noise (0.823 → 0.820). Adapting to one synthetic cohort is not a general improvement, which matches the PTB-XL finding that synthetic adaptation lowers real-ECG performance.
8. **Real-ECG federated checkpoints are as good as anything synthetic here.** The best-validation research checkpoint (R38, trained only on real MIT-BIH patients) scores 0.971 AUROC on the recorded-noise cohort before any synthetic training, above the pretrained V2's 0.949. Together with the PTB-XL check (R50 and R38 match the central V2 at 0.910 against 0.911 AUROC) this means the synthetic cohorts are not needed to get a good model, and synthetic scores should not be used to rank models.
9. **The upgrade shortlist agrees.** No stored candidate is shortlisted: the two research checkpoints match the released V2 on real ECG without beating it, and every synthetic-cohort or assigned-label candidate fails S4 (trained on real-ECG labels) whatever its synthetic score.

## Product defects found and fixed during the run

* `studio/bundle.py`: the pinned static data was published half-built, so two concurrent first requests could fail with `KeyError: 'historical'` (HTTP 500 on the run overview). Built once under a lock, "protocol" published last (`tests/test_studio_bundle_static_race.py`).
* `product/hardware_telemetry.py`: History could import a showcase collection while the app start was still inserting it, leaving a permanently truncated session. A collection is now imported only when complete (`tests/test_hardware_demo_session.py`).
* Gates wrote their test candidates into the real candidate library; every gate now uses a throwaway library, and the leftover test owner folder was removed.

## Limits

One training seed per cell, so differences of a few hundredths are within run-to-run variation (see `docs/realistic/REALISTIC_COHORT_V3.md`); all cohorts are synthetic; hardware sessions are emulated or generated with assigned labels; no physical device; the displayed live-card value in the hardware gate is a mid-run read and is not used here (the numbers above are the independently recomputed ones).
