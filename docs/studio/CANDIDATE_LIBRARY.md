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
| `cohort` | which synthetic cohort the run used (`ORIGINAL` or `REALISTIC`) |
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
