# NHM Research Prototype

NHM is a research-only physiological-pattern monitoring project. It is not a diagnostic device,
clinical decision-support system, treatment recommender, or clinically validated product.

The primary methodological authority is
`NHM_ML_Revised_Locked_Specification_v2.2.docx`. The current implementation phase is **T001**:
repository bootstrap, reproducibility, and source-authority lock. Real ML, dataset processing, and
device-semantic implementation have not started.

## Phase-01 environment

Python 3.11.x is required. Create the local environment and install the exact Phase-01 lock:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
```

The direct dependency declarations live in `pyproject.toml`; `requirements-dev.lock` is the single
exact resolved development snapshot used by CI and reproducible setup.

## Verification

```bash
make lint
make test
make smoke
make phase1
```

`make phase1` runs Ruff, all offline tests, the fixture-driven smoke execution, and evidence/hash
generation. Reports are written to `reports/t001/`. No MongoDB connection is made. Copy
`.env.example` only for future local integration and never commit real credentials.

