# NHM Research Prototype

NHM is a research-only physiological-pattern monitoring project. It is not a diagnostic device,
clinical decision-support system, treatment recommender, or clinically validated product.

## Current state (2026-10)

NHM is a research prototype with three parts that are deliberately kept separate and labelled as such everywhere:

1. **Frozen scientific core.** A pretrained ECG window classifier (`MODEL_V2_FINAL`, AAMI-SVF target, MIT-BIH patient-disjoint split, INCART external second look), its calibration, and the federated-learning
   research lineage (IID, label-skew, FedProx, a narrow SecAgg+ shadow check). Every result is hash-bound to a committed report; see `docs/final_showcase/results_traceability.md`. These are the only
   results with real, expert-annotated ECG behind them.
2. **Research monitoring product.** A FastAPI backend (inference on 8001, product API on 8002), a SvelteKit frontend (4173) with Clerk test authentication, a simulated wearable monitor, persisted History,
   and a read-only Observatory over the evidence. Launch with `python -m scripts.run_nhm` (see "Default research runtime" below).
3. **Federation Studio (engineering demonstration).** Real local training and aggregation on one machine: 3- or 10-round FedAvg/FedProx runs, a round-1 SecAgg+ shadow verification, per-round evaluation by a
   read-only observer on a separate cohort, event journals with replay, figures/tables/exports, and a durable library of engineering candidates that can start later runs.
   Cohorts are synthetic: the **original** frozen cohort (default), the **realistic** cohort (variable rhythm, premature ectopic beats, invented motion artifacts, annotation-noisy labels; `docs/realistic/REALISTIC_COHORT_V2.md`) or the **realistic cohort with recorded noise** (the same rhythm and labels over recorded MIT-BIH Noise Stress Test noise at NSTDB's SNR levels; `docs/realistic/REALISTIC_COHORT_V3.md`).
   A recorded-hardware pipeline demonstration (MongoDB ESP32 telemetry resampled for V2) uses one recorded client plus seven synthetic peers.
   Any starting model works with any cohort (pretrained V2, the untrained V2 network, or a stored candidate; synthetic, monitored-site, History-session or recorded-hardware runs), candidates are listed by the cohort they were trained on, and a read-only **upgrade shortlist** on the Models page says which candidates could be put forward for review as a future custom model and what evidence is still missing (`docs/studio/CANDIDATE_LIBRARY.md`; nothing is promoted or deployed, and today none is shortlisted).

**Evidence beyond the frozen core.** `docs/ptbxl/PTBXL_EXTERNAL_CHECK_V1_RESULTS.md` (shown in the Observatory under "External check on real PTB-XL ECG") scores the frozen models on real PTB-XL ECG that no model was trained, selected or evaluated on (a record-level extension outside the locked scope): the pretrained V2 transfers (AUROC 0.91), V2 clearly beats V1, and adapting a model to a synthetic cohort lowers its performance on that real ECG. `python -m scripts.verify_fl_rounds` independently re-derives every round of every Studio federated run (state chain, predictions, every metric, paired intervals, and a bit-exact re-derivation of each aggregation); `python -m scripts.verify_hardware_connected_browser --fl-matrix` drives every cohort, round count and candidate start through the real UI and runs that verification on the result.

**What is not established.** No clinical validity, no diagnosis, no physical-device verification (the ESP32 path is verified only against an emulator and a local replica), no deployed service. Hardware and synthetic
labels are assigned or generator-defined, never expert ground truth; federated candidates are engineering artefacts, never deployed or used for monitoring. A pretrained-V2 hardware run trains on every complete
window and reports separately how many are graded VALID and how many lower-quality windows were accepted for experimental training.

**Where to look.** `docs/capstone/` (product protocol and runbooks), `docs/realistic/`, `docs/studio/CANDIDATE_LIBRARY.md`, `docs/hardware/` (hardware evidence and boundaries), `docs/unified_live_fl/` (evaluation policy),
`artifacts/` (the successor-lock chain that freezes accepted work). The sections below (Phase-01 environment, Verification) describe the original reproducible setup. `docs/SOURCE_AUTHORITY.md` keeps its historical
task-sequencing marker; it does not describe the current state of the project.

Local runtime state: by default each launch uses a fresh temporary workspace; `python -m scripts.run_nhm --durable` keeps one across restarts. Engineering candidates are kept in `data/studio_candidates` (git-ignored) and always survive restarts. Before a demonstration run `python -m scripts.demo_preflight` and see `docs/demo/DEMO_OPERATIONS.md` (durable state, separating generated demo data from real telemetry, fallbacks).

The primary methodological authority is `NHM_ML_Revised_Locked_Specification_v2.2.docx`; implementation sequencing was controlled by `NHM_Solo_Implementation_Execution_Plan_v1.0.docx` (36 source-bound task packets in
`manifests/task_packets_v1.json`). The master planner prompt is retained only as historical planning input.

## Phase-01 environment

Python 3.11.x is required. Create the local environment and install the exact Phase-01 lock:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
```

The direct dependency declarations live in `pyproject.toml`. `requirements-dev.lock` is the exact
project dependency resolution generated from an actual CPython 3.11 environment and is used by CI
and reproducible setup. It pins package versions across supported Python 3.11 environments; pip
still selects the appropriate platform distribution artifact.

`reports/t001/dependencies.txt` has a different role: it is generated from every installed
distribution in the machine that ran the gate. It is host-specific execution evidence and is not a
portable project lock. These artifacts must not be relabeled or substituted for one another.

## Verification

```bash
make lint
make test
make smoke
make phase1
make coverage
make phase2
```

`make phase1` runs Ruff, all offline tests, the fixture-driven smoke execution, and evidence/hash
generation. Reports are written to `reports/t001/`. No MongoDB connection is made. Copy
`.env.example` only for future local integration and never commit real credentials.

T001 closure additionally records a concrete GitHub Actions run and can be regenerated with:

```bash
PYTHONPATH=src .venv/bin/python scripts/generate_t001_closure.py --run-id RUN_ID
```

Future commits require an intentionally configured Git author identity. Configure it explicitly
with `git config user.name` and `git config user.email`; do not rewrite published history merely to
replace an identity that Git inferred previously.

`make coverage` deterministically rebuilds and audits the T002 registries. `make phase2` runs the
full lint/test suite, the T001 offline regression smoke, the coverage audit, and T002 evidence
generation. It does not download datasets or connect to MongoDB.

## Default research runtime (SOFTWARE_SYSTEM_V2)

The normal research-software API is the V2 stack: MODEL_V2_FINAL -> GATEWAY_ARTIFACT_V2 -> CAL_V2
(MIT-BIH source-domain calibration) -> ALERT_POLICY_V1_MODEL_V2_BINDING over the unchanged
API_SCHEMA_V1 (`POST /v1/infer-window`; no public model selector). It is a non-diagnostic research
prototype, not a clinical, medical-device or physical-wearable system. MODEL_V2_FINAL is a centrally
trained checkpoint; the project additionally contains a federated-learning research lineage for the
MODEL_V2 architecture that is not deployed.

```bash
make run-default                                  # == python -m scripts.run_nhm_default
cd frontend && npm ci && npm run build            # the normal build requests MODEL_V2_FINAL
```

Explicit operator-only rollback to the preserved V1 stack (MODEL_V1 / GATEWAY_ARTIFACT_V1 / CAL_V1 /
ALERT_POLICY_V1; the legacy `uvicorn api.app:app` entry is the same V1 stack):

```bash
make run-rollback-v1                              # == python -m scripts.run_nhm_default --profile rollback-v1
VITE_NHM_REQUEST_MODEL_ID=MODEL_V1 npm run build  # matching frontend build for the rollback profile
```

The profile is a launch decision, never a request parameter, and V1/V2 components are never mixed.
The historical scientific disposition `MODEL_V2_NOT_PROMOTED_RELEASE_CI` is unchanged: the default
change is a prospective research-software governance decision (`SYSTEM_V2_RELEASE_POLICY_V1`).
