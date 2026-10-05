# NHM Research Prototype

NHM is a research-only physiological-pattern monitoring project. It is not a diagnostic device,
clinical decision-support system, treatment recommender, or clinically validated product.

The primary methodological authority is
`NHM_ML_Revised_Locked_Specification_v2.2.docx`. The current implementation phase is **T002**:
machine-checkable requirement, task, gate, freeze, experiment, and evidence traceability. Real ML,
dataset processing, and device-semantic implementation have not started.

Implementation sequencing is controlled by
`NHM_Solo_Implementation_Execution_Plan_v1.0.docx`. The master planner prompt is retained only as
historical planning input. All 36 task packets are source-bound in
`manifests/task_packets_v1.json` and checked by the semantic coverage audit.

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
