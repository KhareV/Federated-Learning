# Studio candidate library

Status: available. It stores the final engineering candidate of completed runs and lets any of them be the starting model (R0) of a later run.

## Why
A completed extended-engine run ends in one final engineering candidate. It used to exist only inside its run directory, which belongs to the per-launch temporary workspace (`nhm-faculty-demo-*`), so it disappeared with the next restart and could not be reused. The Models page showed "No engineering candidates yet" because it reads the product registry, which only the frozen 3-round product runs write to.

## What is stored
One directory per owner and candidate under a **stable, git-ignored** location (default `data/studio_candidates`, override with `NHM_CANDIDATE_LIBRARY_DIR`; the product launcher sets it, so the library survives restarts):

    <root>/<owner tag>/<candidate id>/candidate.json   identity, cohort, source, settings, base model, evaluation snapshot, digest
    <root>/<owner tag>/<candidate id>/state.bin        the serialized final global state

`candidate.json` is written last, so an interrupted write is never listed. Registration is idempotent; the same id with a different state is refused.

| Field | Meaning |
|---|---|
| `cohort` | which synthetic cohort the run used (`ORIGINAL`, `REALISTIC` or `REALISTIC_NSTDB`; `REAL_ECG` for imported research checkpoints) |
| `source_kind` | `SYNTHETIC_COHORT`, `LIVE_MONITORED_SITE`, or `RECORDED_HARDWARE` (pretrained-V2 family) |
| `base_model` | what the run started from (pretrained V2, untrained, or another candidate: lineage) |
| `metrics` | exploratory scores of the final round on its evaluation cohort (not a selection criterion) |
| `promoted`, `deployed`, `registered_in_product_registry`, `used_for_monitoring` | always `false` |

Which runs register: every completed run of the extended synthetic engine (either source mode) and every completed pretrained-V2 recorded-hardware run, automatically, once its evaluations have settled. The frozen 3-round product runs keep using the product registry, unchanged. A library failure never affects the run.

## Using a candidate
Pick **Stored engineering candidate** as the starting model in the Federation Studio starter (synthetic cohort, live-monitored simulated site, or recorded hardware with the pretrained-V2 family), then choose the candidate.

* The state is checked against its recorded digest and against the exact FL model layout before any training; any difference fails the run closed.
* R0 of the new run is that state, unchanged; the Generalisation lane still compares every round with the frozen V2 baseline.
* 3 rounds are allowed from a candidate (like the pretrained start).
* A candidate trained on one cohort may start a run on the other. The starter says so, and the run records both cohorts.
* A candidate belongs to the account that ran it; another account sees nothing and cannot start from it.
* A recorded-hardware candidate contains your recording's influence (its client trained on your windows); it stays private to your account.

## API
* `GET /product/v1/studio/candidates`, `GET /product/v1/studio/candidates/{id}` (owner-scoped)
* `POST /product/v1/studio/runs` with `initialisation: "CANDIDATE"` and `candidate_id`
* `POST /product/v1/studio/hardware-demo/runs` with `initialisation: "CANDIDATE"` and `candidate_id`
* capabilities: `candidate_library` (`count`, `rounds`: 3 and 10) and a `CANDIDATE` entry in the hardware starting models; `ten_round.rounds_by_initialisation` is unchanged

## Limits
* Candidates are engineering artefacts: not promoted, not deployed, never used for monitoring, no scientific or clinical claim. Their scores say little about each other when they come from different cohorts.
* The runs themselves (journals, figures, evidence) still live in the per-launch workspace; only the candidate state is durable. A candidate's `source_run_id` therefore identifies a run whose page may no longer exist after a restart.
* The tabular recorded-hardware family (fresh / warm start) has its own warm start from an earlier hardware run and is not part of this library.

## Imported research checkpoints (real MIT-BIH patients, no synthetic cohort)
The 50-round federated V2 checkpoints of experiment V2-FL-001 (round 50, and round 38, the best-validation checkpoint that the frozen FL evaluation family scored) can be added with `python -m scripts.register_research_candidates --owner <clerk user id>`. They are listed with source kind `RESEARCH_FEDERATED_CHECKPOINT` and cohort `REAL_ECG`: they were federated from a random start on eight simulated whole-patient sites of REAL MIT-BIH training patients, so no synthetic cohort stands behind them. The two values only ever occur together (the library refuses a mismatch). Their library scores are measured on the real MIT-BIH VALIDATION windows, which V2-FL-001 used to pick its best round (round 38 is optimistic there); they sit in their own score group and are never compared with synthetic-cohort scores. Like every candidate they are not promoted, not deployed and never used for monitoring, and they may start a later run on either synthetic cohort (the run records both).


## Segregation by training cohort, and every start x cohort combination
* The Models page and every candidate dropdown (synthetic and recorded-hardware starters) list candidates **by the cohort they were trained on**, in a fixed order: original, realistic (invented noise), realistic (recorded noise), then imported real-ECG research checkpoints. Newest first within a group. Each card still names the cohort it was *scored* on; scores on different evaluation cohorts are not comparable.
* Any starting model works with any synthetic cohort: pretrained V2, the untrained V2 network (`FL_INIT_V2`), or a stored candidate, for synthetic, live-monitored, History-session and recorded-hardware runs, at 3 or 10 rounds. The only run that stays on its own frozen engine is the 3-round untrained run on the canonical original cohort (the frozen product contract). The small tabular hardware model (`HARDWARE_DEMO_MODEL_V1`) has no synthetic peers, so a selected cohort is not used by it; the starter says so and still starts.
* An untrained V2 recorded-hardware run (`initialisation: "FL_INIT_V2"` on `POST /product/v1/studio/hardware-demo/runs`) starts from the seeded `FL_INIT_V2` state, the same untrained model a synthetic 10-round run starts from. It is the V2-architecture family: one recorded client plus seven synthetic peers, scored on its cohort's holdout. Its lineage reads `FL_INIT_V2 (initial state)`, never "pretrained checkpoint".

## Upgrade shortlist (`UPGRADE_SHORTLIST_POLICY_V1`)
`GET /product/v1/studio/candidates-upgrade-shortlist` and the **Upgrade shortlist** panel on the Models page rank the owner's stored candidates by an explicit evidence checklist (`studio/upgrade_shortlist.py`). It is read-only: **a shortlist is not an upgrade**, nothing is promoted, registered or deployed, and the released monitoring model stays `MODEL_V2_FINAL` + `CAL_V2`.

| Criterion | Meaning |
|---|---|
| S1 | scored on real, unseen ECG (a row in the PTB-XL external check) |
| S2 | not distinguishably worse than the released V2 on real ECG |
| S3 | better than the released V2 on real ECG (lower AUROC bound above the released point) |
| S4 | trained on real-ECG labels (synthetic-cohort adaptation lowered real-ECG performance) |
| S5 | F1 at the fixed 0.5 threshold of at least 0.5 on its evaluation cohort |
| S6 | calibration evidence exists (none does for any candidate) |
| S7 | a human release decision exists (NHM has no deployment path) |

A second, **engineering reuse** track asks a different question: is this candidate a better starting point for further sandbox work than the released model, on the cohort it was scored on? It needs no real-ECG evidence.

| Criterion | Meaning |
|---|---|
| E1 | AUROC and AUPRC on its evaluation cohort both at least 0.02 above the released V2 scored on that same cohort |
| E2 | F1 at the fixed 0.5 threshold of at least 0.5 |
| E3 | the cohort has a released-model reference |

The reference is the released V2's independently recomputed round-0 metrics from `reports/verification/browser/fl_matrix/fl_round_verification.json` (original 0.931 / 0.904, realistic 0.848 / 0.484, recorded noise 0.949 / 0.900 AUROC / AUPRC). Every engineering entry lists its risks: R1 synthetic-only evidence (synthetic adaptation lowered real-ECG performance), R2 assigned labels (recorded hardware), R3 scored on the cohort family it was adapted to.

Tiers, best first: `SHORTLISTED_FOR_REVIEW` (real-ECG evidence and no failing S criterion: a possible future custom model, still needs a human decision), `SHORTLISTED_FOR_SANDBOX_REUSE` (passes E1-E3: a better sandbox starting point on its own synthetic cohort, **never a case for deployment**), `COMPARABLE_NOT_BETTER` (matches the released model on real ECG without beating it), `NOT_SHORTLISTED`. S6 and S7 stay open for every candidate. With today's evidence no candidate reaches the review tier: the two federated research checkpoints match the central V2 on PTB-XL (AUROC 0.910 against 0.911) without beating it, and every synthetic-cohort or assigned-label candidate fails S4. Candidates that clearly beat the released model on their own synthetic cohort (for example a 10-round candidate with AUROC 0.999 on the original cohort) are shortlisted for sandbox reuse.
